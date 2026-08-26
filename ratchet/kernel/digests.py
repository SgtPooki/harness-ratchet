"""Content digests hr-pd-1 (pack), hr-sd-1 (split), hr-fd-1 (finding).

Locked by issues #3 (pack format) and #5 (finding format, amended
self-reference rule). The rules, verbatim from the resolutions:

hr-pd-1: manifest lines "sha256:<hex>  <relative-path>" sorted by path with
trailing newline; digest = sha256 of the manifest text. Files only; raw
bytes hashed (ciphertext bytes for encrypted surfaces); no line-ending
normalization; symlinks forbidden; forward-slash separators; UTF-8 NFC
paths; case or path collisions rejected; junk excluded by explicit
denylist. pack.json is excluded from the digest input and carries the
digest.

hr-sd-1: canonical JSON of split_version plus sorted role arrays (sorted
keys, UTF-8, trailing newline), sha256.

hr-fd-1: inherits hr-pd-1 canonicalization, but the metadata file
(finding.json, or replication.json for replications) is INCLUDED in the
digest input as canonical JSON with only its own "digest" field set to
null (amendment on #5: excluding it left claim metadata mutable).

Canonical JSON here and everywhere a resolution says "same rules as
hr-sd-1": json.dumps with sorted keys, compact separators, ensure_ascii
off (UTF-8), plus one trailing newline. The digest golden-vector tests
freeze this serialization permanently.
"""

import hashlib
import json
import unicodedata
from pathlib import Path

DENYLIST_NAMES = frozenset({".DS_Store", "Thumbs.db"})
DENYLIST_DIRS = frozenset({"__pycache__", ".git"})
DENYLIST_SUFFIXES = frozenset({".pyc", ".pyo"})


class DigestError(ValueError):
    """A directory violates the digest rules (symlink, collision, bad path)."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")) + "\n"


def _walk_files(root: Path):
    """Yield (relative-posix-path, absolute-path) for digestable files."""
    root = root.resolve()
    stack = [root]
    while stack:
        d = stack.pop()
        for entry in d.iterdir():
            rel = entry.relative_to(root).as_posix()
            if entry.is_symlink():
                raise DigestError(f"symlink forbidden in v1: {rel}")
            if entry.is_dir():
                if entry.name in DENYLIST_DIRS:
                    continue
                stack.append(entry)
            else:
                if entry.name in DENYLIST_NAMES or entry.suffix in DENYLIST_SUFFIXES:
                    continue
                yield rel, entry


def _manifest_text(root: Path, exclude: frozenset[str],
                   replace: dict[str, bytes]) -> str:
    entries: dict[str, str] = {}
    seen_fold: dict[str, str] = {}
    for rel, abspath in _walk_files(root):
        rel = unicodedata.normalize("NFC", rel)
        if rel in exclude:
            continue
        fold = rel.casefold()
        if rel in entries or fold in seen_fold:
            other = seen_fold.get(fold, rel)
            raise DigestError(f"path collision: {rel!r} vs {other!r}")
        seen_fold[fold] = rel
        data = replace[rel] if rel in replace else abspath.read_bytes()
        entries[rel] = sha256_hex(data)
    for rel, data in replace.items():
        if rel not in entries:
            entries[rel] = sha256_hex(data)
    lines = [f"sha256:{entries[rel]}  {rel}" for rel in sorted(entries)]
    return "\n".join(lines) + "\n"


def pack_digest(root: Path) -> str:
    """hr-pd-1 digest of a pack directory (pack.json excluded)."""
    return sha256_hex(
        _manifest_text(Path(root), frozenset({"pack.json"}), {}).encode("utf-8")
    )


def split_digest(split_version: int, held_in: list[str], held_out: list[str],
                 sentinel: list[str]) -> str:
    """hr-sd-1 digest of a split assignment."""
    doc = {
        "split_version": split_version,
        "held_in": sorted(held_in),
        "held_out": sorted(held_out),
        "sentinel": sorted(sentinel),
    }
    return sha256_hex(canonical_json(doc).encode("utf-8"))


def finding_digest(root: Path, meta_name: str = "finding.json") -> str:
    """hr-fd-1 digest of a finding (or replication) directory.

    The metadata file is included as canonical JSON with its "digest" field
    set to null; every other file follows hr-pd-1 rules.
    """
    root = Path(root)
    meta_path = root / meta_name
    if not meta_path.is_file():
        raise DigestError(f"{meta_name} missing from {root}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["digest"] = None
    replaced = canonical_json(meta).encode("utf-8")
    return sha256_hex(
        _manifest_text(root, frozenset(), {meta_name: replaced}).encode("utf-8")
    )
