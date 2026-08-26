"""Harness invocation: the runner interface and the omp reference adapter.

The kernel never imports this package (CI-linted). The interface is an
internal boundary, not a multi-harness adapter layer: omp stays the only
runner until a second harness is actually in use (VISION: The artifacts).

Modules: base (RolloutSpec, TelemetryRow, Runner protocol), omp (the
reference adapter, ported from bin/run.sh), ops (the three surface
operations from the finding format), probe (channel liveness).
"""
