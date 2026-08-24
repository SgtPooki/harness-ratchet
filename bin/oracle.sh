#!/bin/bash
# Solvability gate: for every task, the UNMODIFIED workspace must FAIL its
# verifier, and workspace + reference solution must PASS it. A task that
# fails either direction must not be used for scoring.
set -u
cd "$(dirname "$0")/.."
fail=0

run_verify() { # $1=task dir  $2=workspace copy
  if [ -f "$1/verify/verify.py" ]; then
    python3 "$1/verify/verify.py" "$2" >/dev/null 2>&1
  elif [ -f "$1/verify/verify.mjs" ]; then
    node "$1/verify/verify.mjs" "$2" >/dev/null 2>&1
  else
    echo "  no verifier found in $1"; return 2
  fi
}

for task in tasks/*/; do
  name=$(basename "$task")
  tmp=$(mktemp -d)
  cp -R "$task/workspace/." "$tmp/"

  if run_verify "$task" "$tmp"; then
    echo "ORACLE FAIL [$name]: unmodified workspace already passes (task is vacuous)"
    fail=1
  fi

  cp -R "$task/solution/." "$tmp/"
  if run_verify "$task" "$tmp"; then
    echo "oracle ok   [$name]"
  else
    echo "ORACLE FAIL [$name]: reference solution does not pass verifier"
    fail=1
  fi
  rm -rf "$tmp"

  # Verifier-robustness check: a deliberately WRONG solution must FAIL.
  # Guards against tautological verifiers (checks one happy path, or passes
  # anything). Optional per-task sabotage/ dir; REQUIRED for generated tasks.
  if [ -d "$task/sabotage" ]; then
    tmp=$(mktemp -d)
    cp -R "$task/workspace/." "$tmp/"
    cp -R "$task/solution/." "$tmp/"
    cp -R "$task/sabotage/." "$tmp/"
    if run_verify "$task" "$tmp"; then
      echo "ORACLE FAIL [$name]: sabotaged solution PASSES verifier (verifier is too weak)"
      fail=1
    else
      echo "  sabotage ok [$name]"
    fi
    rm -rf "$tmp"
  fi
done

exit $fail
