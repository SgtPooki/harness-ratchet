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


# The v1 runner is serial (#12 decision 6): one rollout in flight. Recorded
# in baseline records, sweep_cost, and manifests; comparisons refuse
# mismatched values before the gate ever runs.
CONCURRENCY = 1


def sweep_cost(rows: list[TelemetryRow], *, elapsed_wall_s: int,
               rollouts_planned: int, aborted: bool,
               task_order: list[str]) -> dict:
    """The #12 decision 7 record: what one sweep actually cost.

    elapsed_wall_s and the summed rollout durations are recorded
    separately so serial and future parallel runs stay priceable and
    comparable.
    """
    return {
        "elapsed_wall_s": elapsed_wall_s,
        "sum_rollout_duration_s": sum(r.duration_s for r in rows),
        "tokens_in": sum(r.tokens_in for r in rows),
        "tokens_out": sum(r.tokens_out for r in rows),
        "rollouts_run": len(rows),
        "rollouts_planned": rollouts_planned,
        "aborted": aborted,
        "task_order": task_order,
        "concurrency": CONCURRENCY,
    }
