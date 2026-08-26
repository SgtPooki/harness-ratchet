# Recency table: public floor tasks

Compiled at first public mint (2026-08-26), per the runner-rewrite resolution
on #2 point 8 and the criteria locked in #8 point 3.

Subject model: Qwen3.8-27B (served as vllm/homelab-default). The model
publishes NO knowledge cutoff (the model card omits it; the open question on
its discussion board is unanswered), so the locked fallback applies: release
date, 2026-08-14. Every date below is the target function's last material
change per single git log -L lookup, recorded as a conservative proxy, never
a contamination proof. Training data likely ends months before release, which
only strengthens the proxy.

| task | source repo | license | function | last change | commit | basis |
|---|---|---|---|---|---|---|
| 18-py-positional-column | tobymao/sqlglot | MIT (root, spot-checked; no conflicting notice in file) | _qualify_positional_column | 2026-08-19 | f62c344 | function-level git log -L |
| 19-py-qualify-columns-core | tobymao/sqlglot | MIT (same spot-check) | _qualify_columns | 2026-08-21 | b79cbf8 | function-level git log -L |
| 20-py-xml-elements | stanfordnlp/dspy | MIT (root, spot-checked; no conflicting notice in file) | _elements_to_value | 2026-08-21 | 33aaa19 | function-level git log -L |
| 21-py-columns-to-dots | tobymao/sqlglot | MIT (same spot-check) | _convert_columns_to_dots | 2026-08-16 | b4c9ad5 | function-level git log -L |

Rejected attempts, logged in the operator mint log per #8 point 4:
validate_qualify_columns (sqlglot, excision-error: its comparisons are
identity checks the auto-mutant cannot flip) and CV12 _eval_gen (sqlfluff,
baseline-failure at preflight: the rule-case runner loads fixtures through a
cwd-relative glob and integration marks that the hermetic verify pattern does
not satisfy).

Floor tasks are regression rails, not headroom: they are presumed passable by
subject-class models, and a vintage is an era marker, not an eternal
benchmark (VISION: task sourcing and contamination).
