"""Era registry: the pinned comparison baseline (label, split, gate, model,
standing-overlay hashes).

Port of the registry half of bin/gate.py (era registry v1.3). Every gate
invocation verifies the requested baseline against the registry instead of
operator memory; mismatches are data errors (exit 2), never verdicts —
the runner-rewrite resolution (#2 point 7) locks that exit code. (The
bash-era gate.py's sys.exit(str) de facto exited 1 on these paths, against
its own documented contract; the port implements the documented and locked
behavior.)

Kernel purity: all paths injected; the registry file location and the git
commit for set_at_commit are the caller's business.
"""

import hashlib
import json
from pathlib import Path

from ratchet.kernel.gate import GATE_VERSION


class EraError(Exception):
    """A registry check failed: a data error (exit 2), never a verdict."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_registry(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise EraError(f"gate: no {path} — record one with --set-active <label>")
    return json.loads(path.read_text())


def build_registry(*, label: str, results: dict[str, list[dict]], split: dict,
                   configs: list[str], config_root: Path, set_at_commit: str,
                   ts: int, concurrency: int = 1) -> dict:
    """Assemble a registry record for --set-active. Raises EraError on bad input."""
    models = sorted({r["model"] for rs in results.values() for r in rs})
    if len(models) != 1:
        raise EraError(f"gate: {label} mixes models {models}; a baseline must be single-model")
    cfg_hashes = {}
    for c in configs:
        p = Path(config_root) / c
        if not p.is_file():
            raise EraError(f"gate: config {c} not found")
        cfg_hashes[c] = sha256_file(p)
    return {
        "label": label, "split_version": split["split_version"],
        "gate_version": GATE_VERSION, "model": models[0],
        "config_sha256": cfg_hashes, "set_at_commit": set_at_commit,
        "ts": ts, "concurrency": concurrency,
    }


def check_era(registry: dict, *, baseline_label: str, split: dict,
              base: dict[str, list[dict]], cand: dict[str, list[dict]],
              config_root: Path, gate_version: int = GATE_VERSION) -> None:
    """Verify a gate invocation against the era registry.

    Raises EraError listing every mismatch; returns None when the eras line up.
    """
    errs = []
    if baseline_label != registry["label"]:
        errs.append(f"baseline {baseline_label!r} is not the active baseline "
                    f"{registry['label']!r} (re-point with --set-active if deliberate)")
    if registry["split_version"] != split["split_version"]:
        errs.append(f"era mismatch: registry split v{registry['split_version']} vs "
                    f"split.json v{split['split_version']} — record a new baseline first")
    if registry["gate_version"] != gate_version:
        errs.append(f"gate changed (registry v{registry['gate_version']} vs v{gate_version}) "
                    "— re-record the baseline under the current gate")
    for c, want in registry.get("config_sha256", {}).items():
        p = Path(config_root) / c
        have = sha256_file(p) if p.is_file() else "<missing>"
        if have != want:
            errs.append(f"config ancestry broken: {c} changed since the baseline "
                        "was recorded — the comparison is cross-era")
    models = sorted({r["model"] for rs in list(base.values()) + list(cand.values()) for r in rs})
    if models != [registry["model"]]:
        errs.append(f"model mismatch: registry {registry['model']!r} vs run rows {models}")
    if errs:
        raise EraError("gate: era-registry check failed:\n  - " + "\n  - ".join(errs))
