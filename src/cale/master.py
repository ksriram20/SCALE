"""Audio mastering — the 'deep, bassy, broadcast' sound + an optional music bed.

Depth comes from a slight pitch-down, a bass low-shelf boost, compression, and
loudness normalization. An optional ambient track is mixed *under* the narration,
side-chain ducked so it dips when the voice speaks. Needs ffmpeg (in the Kokoro
container and the SCALE image); on a bare host without it, mastering is skipped.
"""

import logging
import random
import shutil
import subprocess
from pathlib import Path

from .config import ROOT

log = logging.getLogger("cale.master")


def _probe_rate(path):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate", "-of", "csv=p=0", str(path)]
        )
        return int(out.decode().strip())
    except Exception:
        return None


def _music_track(cfg):
    """Pick an ambient bed from tts.music.dir (a named one if set, else random)."""
    mcfg = (cfg.get("tts") or {}).get("music") or {}
    if not mcfg.get("enabled"):
        return None
    mdir = ROOT / mcfg.get("dir", "assets/music")
    if not mdir.exists():
        return None
    tracks = sorted(p for p in mdir.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".flac", ".ogg"))
    if not tracks:
        return None
    want = mcfg.get("track")
    if want:
        for t in tracks:
            if want.lower() in t.name.lower():
                return t
    return random.choice(tracks)


def master_audio(in_path, out_path, cfg, meta=None):
    """Master `in_path` -> `out_path`: pitch/bass/compression, optional ducked
    music bed, and embedded `meta` tags. Returns the final path."""
    m = (cfg.get("tts") or {}).get("master") or {}
    if not m.get("enabled"):
        return Path(in_path)
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg not on PATH — skipping mastering (run via Docker for it)")
        return Path(in_path)

    in_path, out_path = Path(in_path), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pitch = 1.0 - float(m.get("pitch_down_pct", 7)) / 100.0
    bass_db = float(m.get("bass_gain_db", 6))
    sr = _probe_rate(in_path) or 24000
    new_sr = int(sr * pitch)
    atempo = round(1.0 / pitch, 4)

    voice = (
        f"asetrate={new_sr},aresample=48000,atempo={atempo},"
        f"bass=g={bass_db}:f=110:w=0.6,"
    )
    if m.get("compress", True):
        voice += "acompressor=threshold=-18dB:ratio=3:attack=20:release=250,"
    voice += "dynaudnorm=f=200"

    meta_args = []
    for key in ("title", "artist", "album", "date", "genre", "comment"):
        val = (meta or {}).get(key)
        if val:
            meta_args += ["-metadata", f"{key}={val}"]
    fmt_args = ["-b:a", "320k"] if out_path.suffix.lower() == ".mp3" else []

    track = _music_track(cfg)
    if track:
        mus = cfg["tts"]["music"]
        gain = float(mus.get("gain_db", -22))
        lp = mus.get("lowpass_hz", 0)
        soften = f"lowpass=f={int(lp)}," if lp else ""   # roll off highs -> soft pad
        music_chain = f"volume={gain}dB,{soften}aresample=48000"
        if mus.get("duck", True):
            # asplit the voice: one copy mixes, one keys the side-chain (can't reuse a label).
            fc = (f"[0:a]{voice},asplit=2[v1][v2];"
                  f"[1:a]{music_chain}[m];"
                  f"[m][v2]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];"
                  f"[v1][md]amix=inputs=2:duration=first:normalize=0[mix]")
        else:
            fc = (f"[0:a]{voice}[v];[1:a]{music_chain}[m];"
                  f"[v][m]amix=inputs=2:duration=first:normalize=0[mix]")
        args = (["ffmpeg", "-y", "-loglevel", "error", "-i", str(in_path),
                 "-stream_loop", "-1", "-i", str(track), "-filter_complex", fc, "-map", "[mix]"]
                + meta_args + fmt_args + [str(out_path)])
        log.info("master + music bed: %s (%sdB%s)", track.name, gain,
                 ", ducked" if mus.get("duck", True) else "")
    else:
        args = (["ffmpeg", "-y", "-loglevel", "error", "-i", str(in_path), "-af", voice]
                + meta_args + fmt_args + [str(out_path)])

    subprocess.run(args, check=True)
    log.info("mastered -> %s (pitch -%s%%, bass +%sdB)", out_path, m.get("pitch_down_pct", 7), bass_db)
    return out_path
