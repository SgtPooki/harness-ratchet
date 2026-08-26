"""Channel liveness probes (issue #2, point 4: first-class, because findings
require the evidence).

A channel must pass an observable-token test before any A/B that uses it
(CONTEXT.md): inject "include token X" through the channel with a neutral
prompt, and check the token appears in the model's output. The cycle-3
lesson: when a probe fails, differentiate WHERE it died before assigning
blame.

Channels v1: rules (RULES.md append, a registry-admissible surface) and
append-system-prompt (trust-header wrapped; loop-only, inadmissible for
findings until a format version bump — #5 amendment).
"""

import json
import secrets
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ratchet.runner.omp import OmpRunner, wrap_trusted
from ratchet.runner.ops import RulesAppendOp, applied

CHANNELS = ("rules", "append-system-prompt")
PROBE_PROMPT = "Reply with a one-sentence greeting."


@dataclass
class ProbeResult:
    channel: str
    method: str
    token: str
    observed: bool
    model: str
    date: str
    rc: int

    def to_json(self) -> dict:
        return self.__dict__.copy()


def _stream_mentions(stream_path: Path, token: str) -> bool:
    try:
        return token in stream_path.read_text(errors="replace")
    except OSError:
        return False


def probe_channel(runner: OmpRunner, channel: str, *, model: str,
                  timeout_s: int, out_dir: Path,
                  standing_overlays: list[Path] = ()) -> ProbeResult:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}; have {CHANNELS}")
    token = "HR-" + secrets.token_hex(4).upper()
    instruction = f"When you respond, include the exact token {token}."
    out_dir.mkdir(parents=True, exist_ok=True)
    date = time.strftime("%Y-%m-%d")
    stream = out_dir / f"{date}-{channel}.stream.jsonl"
    stderr = out_dir / f"{date}-{channel}.stderr.txt"

    args = [runner.omp_cmd, "-p", "--auto-approve", "--model", model,
            "--no-title", "--mode", "json"]
    for overlay in standing_overlays:
        args += ["--config", str(Path(overlay).resolve())]

    if channel == "append-system-prompt":
        args += ["--append-system-prompt", wrap_trusted(instruction)]
        args.append(PROBE_PROMPT)
        rc = _run(args, stream, stderr, timeout_s)
    else:
        op = RulesAppendOp(runner.rules_path, instruction,
                           digest12=secrets.token_hex(6))
        args.append(PROBE_PROMPT)
        with applied(op):
            rc = _run(args, stream, stderr, timeout_s)

    result = ProbeResult(channel=channel, method="observable-token",
                         token=token, observed=_stream_mentions(stream, token),
                         model=model, date=date, rc=rc)
    (out_dir / f"{date}-{channel}.json").write_text(
        json.dumps(result.to_json(), indent=1) + "\n")
    return result


def _run(args, stream: Path, stderr: Path, timeout_s: int) -> int:
    with open(stream, "wb") as out, open(stderr, "wb") as err:
        try:
            return subprocess.run(args, stdout=out, stderr=err,
                                  timeout=timeout_s).returncode
        except subprocess.TimeoutExpired:
            return 124
