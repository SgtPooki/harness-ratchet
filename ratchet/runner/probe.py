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
    # config-key probes only: how often the observable appeared with and
    # without the key set. Liveness is the DIFFERENCE, never the raw count.
    control_count: int | None = None
    probe_count: int | None = None
    key: str | None = None

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


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


def _overlay_for(key: str, value, path: Path) -> Path:
    """Write a minimal overlay setting one dotted config key."""
    node: dict = {}
    cur = node
    parts = key.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value
    def dump(d, indent=0):
        out = []
        for k, v in d.items():
            if isinstance(v, dict):
                out.append(f"{'  ' * indent}{k}:")
                out.append(dump(v, indent + 1))
            else:
                out.append(f"{'  ' * indent}{k}: {json.dumps(v)}")
        return "\n".join(out)
    path.write_text(dump(node) + "\n")
    return path


def probe_config_key(runner: OmpRunner, key: str, extreme_value, observable: str,
                     *, model: str, timeout_s: int, out_dir: Path,
                     standing_overlays: list[Path] = ()) -> ProbeResult:
    """Liveness for ONE config key, by behaviour rather than by acceptance.

    omp silently accepts a config overlay containing an unknown key, and
    silently accepts a wrong-typed value for a real one: a session runs clean
    either way and nothing warns. So a typo in a mutation overlay produces a
    null A/B result indistinguishable from a real null, and the gate would
    record a verdict on a mutation that never happened. Acceptance proves
    nothing; only a behaviour difference does.

    The method: run the same neutral prompt twice, once with the standing
    overlays alone and once with the key set to a deliberately extreme value,
    and count an observable marker in each stream. The key is LIVE only if the
    counts differ.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    date = time.strftime("%Y-%m-%d")
    slug = key.replace(".", "-")
    base_args = [runner.omp_cmd, "-p", "--auto-approve", "--model", model,
                 "--no-title", "--mode", "json"]
    for overlay in standing_overlays:
        base_args += ["--config", str(Path(overlay).resolve())]

    control_stream = out_dir / f"{date}-{slug}.control.stream.jsonl"
    rc_control = _run(base_args + [PROBE_PROMPT], control_stream,
                      out_dir / f"{date}-{slug}.control.stderr.txt", timeout_s)

    # The overlay filename is deliberately neutral. Named after the key, it
    # would contain the observable ("compact" inside "compaction"), and a
    # harness that echoes its own arguments into the stream would then be
    # counted as a behaviour change. The probe would report LIVE for a key
    # that does nothing, which is the exact failure it exists to catch.
    overlay_path = _overlay_for(key, extreme_value,
                                out_dir / f"{date}-probe-{secrets.token_hex(4)}.yml")
    probe_stream = out_dir / f"{date}-{slug}.probe.stream.jsonl"
    rc_probe = _run(base_args + ["--config", str(overlay_path), PROBE_PROMPT],
                    probe_stream, out_dir / f"{date}-{slug}.probe.stderr.txt",
                    timeout_s)

    def count(p: Path) -> int:
        needle, echo = observable.lower(), overlay_path.name.lower()
        try:
            return sum(1 for line in p.read_text(errors="replace").splitlines()
                       if needle in line.lower() and echo not in line.lower())
        except OSError:
            return 0

    control_count, probe_count = count(control_stream), count(probe_stream)
    result = ProbeResult(
        channel=f"config-key:{key}", method="extreme-value-observable",
        token=observable, observed=probe_count != control_count, model=model,
        date=date, rc=rc_probe or rc_control,
        control_count=control_count, probe_count=probe_count, key=key)
    (out_dir / f"{date}-{slug}.json").write_text(
        json.dumps(result.to_json(), indent=1) + "\n")
    return result
