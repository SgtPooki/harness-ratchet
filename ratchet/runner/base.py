"""The runner interface (issue #2, point 2).

A runner drives one harness: run_rollout(task, cfg) -> TelemetryRow.
Telemetry extraction is runner-side; verdicts (the composite-pass rule,
the gate) stay kernel-side. This boundary is internal, not a
multi-harness adapter layer: the omp reference adapter stays the only
runner until a second harness is actually in use (VISION: The artifacts).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class RolloutSpec:
    """Everything one rollout needs, injected by the caller."""
    task_dir: Path            # task directory inside a pack
    task_id: str
    rollout: int              # 1-based index
    label: str                # run label; results append to run_root/results.jsonl
    run_root: Path            # runs/<label>
    model: str
    timeout_s: int
    standing_overlays: list[Path] = field(default_factory=list)
    extra_config: Path | None = None   # candidate overlay (the mutation artifact)
    extra_sys: str | None = None       # trust-header-wrapped append-system-prompt text


@dataclass
class TelemetryRow:
    """One results.jsonl row; field names and types match the bash-era schema."""
    ts: int
    task: str
    rollout: int
    model: str
    label: str
    passed: bool
    agent_rc: int
    duration_s: int
    tokens_in: int
    tokens_out: int
    verify_tail: str

    def to_json(self) -> dict:
        d = {
            "ts": self.ts, "task": self.task, "rollout": self.rollout,
            "model": self.model, "label": self.label, "pass": self.passed,
            "agent_rc": self.agent_rc, "duration_s": self.duration_s,
            "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
            "verify_tail": self.verify_tail,
        }
        return d


class Runner(Protocol):
    def run_rollout(self, spec: RolloutSpec) -> TelemetryRow: ...
