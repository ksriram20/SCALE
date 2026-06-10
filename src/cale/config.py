"""Configuration and environment loading."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


def _find_root():
    """Locate the project root (where config/ and skills/ live).

    Robust across run styles: an installed `scale` console script lives in
    site-packages, so we can't rely on this file's location. Prefer an explicit
    SCALE_HOME, then the cwd if it looks like the project (the Docker WORKDIR and
    the repo root both do), and only fall back to the source-tree heuristic.
    """
    env_root = os.environ.get("SCALE_HOME")
    if env_root:
        return Path(env_root)
    cwd = Path.cwd()
    if (cwd / "config" / "config.yaml").exists() or (cwd / "skills").exists():
        return cwd
    return Path(__file__).resolve().parents[2]


ROOT = _find_root()


def load_config(path=None):
    path = Path(path) if path else ROOT / "config" / "config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def source_path():
    return ROOT / "config" / "source.yaml"


def load_source(path=None):
    path = Path(path) if path else source_path()
    with open(path) as f:
        return yaml.safe_load(f)


def load_all_sources():
    """Every book the engine knows: the legacy config/source.yaml plus any
    per-book profiles under config/sources/*.yaml (deduped by title)."""
    sources, seen = [], set()
    sp = source_path()
    if sp.exists():
        s = load_source(sp)
        sources.append(s)
        seen.add(s.get("title"))
    sdir = ROOT / "config" / "sources"
    if sdir.exists():
        for f in sorted(sdir.glob("*.yaml")):
            s = yaml.safe_load(f.read_text())
            if s.get("title") not in seen:
                sources.append(s)
                seen.add(s.get("title"))
    return sources


def profile_path():
    return ROOT / "config" / "profile.yaml"


def load_profile(path=None):
    path = Path(path) if path else profile_path()
    with open(path) as f:
        return yaml.safe_load(f)


def validate_profile(profile):
    """Return a list of problems with the profile (empty == valid)."""
    problems = []
    for key in ("name", "role", "domain"):
        if not profile.get(key):
            problems.append(f"missing required field: {key}")
    if not profile.get("country"):
        problems.append("no country/locale — applications may default to a Western context (run `scale context`)")
    if not (profile.get("challenges") or profile.get("goals")):
        problems.append("no goals or challenges — applications will be generic")
    return problems


def env(key, default=None):
    return os.environ.get(key, default)
