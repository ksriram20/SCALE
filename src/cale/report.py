"""Faithfulness report — surfaces the auditor's per-law verdict for an episode.

Without this, the audit passes (or silently regenerates) invisibly. The report
makes the quality gate inspectable: which laws passed clean, which needed a
regeneration, and exactly what the auditor flagged.
"""

import logging

from .config import ROOT

log = logging.getLogger("cale.report")


def render_report(episode_number, category, segments):
    total = len(segments)
    n_pass = 0
    lines = []
    for s in segments:
        c = s["concept"]
        a = s.get("audit") or {}
        cf = bool(a.get("concept_faithful"))
        ag = bool(a.get("application_grounded"))
        ok = cf and ag
        n_pass += ok
        lines.append(f"## {c.get('title', '')}  [{'PASS' if ok else 'FAIL'}]")
        lines.append(f"- concept_faithful:     {cf}")
        lines.append(f"- application_grounded: {ag}")
        lines.append(f"- regenerations:        {s.get('regens', 0)}")
        for issue in a.get("issues") or []:
            lines.append(f"- issue: {issue}")
        lines.append("")
    header = [
        f"# Faithfulness report — Episode {episode_number:02d}: {category}",
        "",
        f"**{n_pass}/{total} units passed clean.**",
        "",
    ]
    return "\n".join(header + lines), n_pass, total


def write_report(cfg, episode_number, category, segments):
    text, n_pass, total = render_report(episode_number, category, segments)
    report_dir = ROOT / cfg["output"].get("report_dir", "output/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"episode_{episode_number:02d}.md"
    path.write_text(text, encoding="utf-8")
    try:
        path.chmod(0o666)   # host-editable (container writes as root)
    except OSError:
        pass
    log.info("faithfulness: %d/%d units clean -> %s", n_pass, total, path)
    return path
