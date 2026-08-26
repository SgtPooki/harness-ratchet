"""harness-ratchet: mechanical harness improvement around a frozen local model.

Package layout (runner-rewrite resolution, issue #2):
  ratchet.kernel  — the verification kernel: pure mechanics (gate, oracle
                    admission, era registry, pack I/O, digests, schemas).
                    Never imports ratchet.runner or ratchet.miner; all paths
                    are injected by callers.
  ratchet.runner  — harness invocation (omp reference adapter; build step 2).
  ratchet.miner   — the excision task producer (build step 6).
  ratchet.cli     — the `ratchet` console command, eight verbs.
"""

__version__ = "0.1.0"
