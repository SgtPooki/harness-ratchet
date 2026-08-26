"""Operator configuration: ratchet.toml at the bank root (issue #2, point 3).

Resolution order: an explicit --config path, then the RATCHET_CONFIG
environment variable, then a cwd-walk toward the filesystem root looking
for ratchet.toml. Absent everywhere: fail closed telling the operator to
run init. All relative paths in the file resolve relative to the toml
file's directory.

Minimal v1 schema, locked:
  [paths]             runs_dir (local, gitignored), era_dir
  [packs]             bootstrap, bank
  [runner]            harness, model, timeout_s, k
  [overlays.standing] paths = [...]
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_ENV = "RATCHET_CONFIG"
CONFIG_NAME = "ratchet.toml"


class ConfigError(Exception):
    """Missing or invalid operator config: a usage error (exit 2)."""


@dataclass
class RatchetConfig:
    path: Path            # the toml file itself
    runs_dir: Path
    era_dir: Path
    bootstrap_pack: Path
    bank_pack: Path
    harness: str
    model: str
    timeout_s: int
    k: int
    standing_overlays: list[Path] = field(default_factory=list)

    @property
    def root(self) -> Path:
        return self.path.parent

    @property
    def active_baseline(self) -> Path:
        return self.era_dir / "ACTIVE_BASELINE"

    @property
    def split_file(self) -> Path:
        return self.era_dir / "split.json"


def find_config(explicit: str | os.PathLike | None = None,
                cwd: Path | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise ConfigError(f"config not found: {p}")
        return p
    env = os.environ.get(CONFIG_ENV)
    if env:
        p = Path(env)
        if not p.is_file():
            raise ConfigError(f"{CONFIG_ENV} points at a missing file: {p}")
        return p
    d = (cwd or Path.cwd()).resolve()
    for candidate in [d, *d.parents]:
        p = candidate / CONFIG_NAME
        if p.is_file():
            return p
    raise ConfigError(
        f"no {CONFIG_NAME} found (looked from {d} upward; set {CONFIG_ENV} or "
        "pass --config) — run `ratchet init <bank-path>` to create a bank")


def load_config(explicit: str | os.PathLike | None = None,
                cwd: Path | None = None) -> RatchetConfig:
    path = find_config(explicit, cwd)
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e

    def section(name) -> dict:
        v = doc.get(name)
        if not isinstance(v, dict):
            raise ConfigError(f"{path}: missing [{name}] section")
        return v

    def want(sec: dict, sec_name: str, key: str, kind: type):
        if key not in sec:
            raise ConfigError(f"{path}: missing {sec_name}.{key}")
        v = sec[key]
        if not isinstance(v, kind) or isinstance(v, bool):
            raise ConfigError(f"{path}: {sec_name}.{key} must be {kind.__name__}")
        return v

    root = path.parent
    paths, packs, runner = section("paths"), section("packs"), section("runner")
    overlays = doc.get("overlays", {}).get("standing", {})
    overlay_paths = overlays.get("paths", [])
    if not isinstance(overlay_paths, list) or not all(isinstance(p, str) for p in overlay_paths):
        raise ConfigError(f"{path}: overlays.standing.paths must be a list of strings")

    cfg = RatchetConfig(
        path=path,
        runs_dir=root / want(paths, "paths", "runs_dir", str),
        era_dir=root / want(paths, "paths", "era_dir", str),
        bootstrap_pack=root / want(packs, "packs", "bootstrap", str),
        bank_pack=root / want(packs, "packs", "bank", str),
        harness=want(runner, "runner", "harness", str),
        model=want(runner, "runner", "model", str),
        timeout_s=want(runner, "runner", "timeout_s", int),
        k=want(runner, "runner", "k", int),
        standing_overlays=[root / p for p in overlay_paths],
    )
    missing = [str(p) for p in cfg.standing_overlays if not p.is_file()]
    if missing:
        raise ConfigError(f"{path}: standing overlays not found: {missing}")
    return cfg
