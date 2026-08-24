Bug report from production: "When our service generates two reports in the same
process, the SECOND report contains rows from the FIRST report, and its totals
are wrong. Generating each report in a fresh process works fine."

Reproduce with `python3 repro.py`, then find and fix the defect(s). The fix must
be in the library code (`reportlib/`), not in `repro.py`. Public function names
and signatures must not change.
