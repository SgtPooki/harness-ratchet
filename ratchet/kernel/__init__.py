"""The verification kernel: pure mechanics, callable as a library.

Purity rule (issue #2, point 2): no imports from ratchet.runner or
ratchet.miner, no shelling to a harness, no bank-path assumptions; every
path is injected by the caller. Enforced by scripts/lint_kernel_imports.py
in CI.
"""

from ratchet.kernel.digests import (
    canonical_json,
    finding_digest,
    pack_digest,
    split_digest,
)
from ratchet.kernel.era import EraError, check_era, load_registry
from ratchet.kernel.gate import GATE_VERSION, GateDataError, decide, write_manifest
from ratchet.kernel.oracle import GRANDFATHERED_SABOTAGE, AdmissionResult, admit_task
from ratchet.kernel.pack import load_pack, materialize_bootstrap, validate_pack

__all__ = [
    "AdmissionResult",
    "EraError",
    "GATE_VERSION",
    "GRANDFATHERED_SABOTAGE",
    "GateDataError",
    "admit_task",
    "canonical_json",
    "check_era",
    "decide",
    "finding_digest",
    "load_pack",
    "load_registry",
    "materialize_bootstrap",
    "pack_digest",
    "split_digest",
    "validate_pack",
    "write_manifest",
]
