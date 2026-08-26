"""Digest golden vectors and canonicalization rules (hr-pd-1, hr-sd-1, hr-fd-1).

The hex literals were computed once at port time and freeze the algorithms:
a change to any digest is a format break, never a refactor.
"""

import json
import os

import pytest

from ratchet.kernel.digests import (
    DigestError,
    canonical_json,
    finding_digest,
    pack_digest,
    split_digest,
)

PD_GOLDEN = "6c9813f1305b933b7dcf3c1bc5823ba8bca2418b850ee2d21b47dffbcd7b6732"
SD_GOLDEN = "2354cf198756fdbc59626b1448985fbb04acc0fcabe5f4730b1f4b12fa5ff339"
FD_GOLDEN = "049ab39211dbf95d6942ae26a9e25d5ef85579b2bf9330250186f83694591ba4"


def mini_pack(root):
    (root / "01-alpha" / "workspace").mkdir(parents=True)
    (root / "01-alpha" / "prompt.md").write_text("Fix the widget.\n")
    (root / "01-alpha" / "workspace" / "widget.py").write_text("def widget():\n    pass\n")
    (root / "02-beta").mkdir()
    (root / "02-beta" / "prompt.md").write_bytes(
        "Café semantics.\r\nno normalization\n".encode())
    (root / "pack.json").write_text('{"excluded": "from digest"}')
    return root


def test_pack_digest_golden(tmp_path):
    assert pack_digest(mini_pack(tmp_path)) == PD_GOLDEN


def test_pack_digest_ignores_junk_and_pack_json(tmp_path):
    mini_pack(tmp_path)
    (tmp_path / ".DS_Store").write_bytes(b"junk")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_bytes(b"junk")
    (tmp_path / "01-alpha" / "stale.pyc").write_bytes(b"junk")
    (tmp_path / "pack.json").write_text('{"different": "content"}')
    assert pack_digest(tmp_path) == PD_GOLDEN


def test_pack_digest_sees_content_and_renames(tmp_path):
    mini_pack(tmp_path)
    (tmp_path / "02-beta" / "prompt.md").write_bytes(
        "Café semantics.\nno normalization\n".encode())  # \r\n -> \n must matter
    assert pack_digest(tmp_path) != PD_GOLDEN

    mini_pack_renamed = mini_pack(tmp_path / "again")
    (mini_pack_renamed / "02-beta" / "prompt.md").rename(
        mini_pack_renamed / "02-beta" / "PROMPT2.md")
    assert pack_digest(mini_pack_renamed) != PD_GOLDEN


def test_pack_digest_rejects_symlink(tmp_path):
    mini_pack(tmp_path)
    os.symlink(tmp_path / "01-alpha" / "prompt.md", tmp_path / "link.md")
    with pytest.raises(DigestError, match="symlink"):
        pack_digest(tmp_path)


def test_pack_digest_rejects_case_collision(tmp_path):
    # macOS filesystems are case-insensitive, so simulate the collision the
    # way it reaches the digest on Linux: two names equal after casefold.
    mini_pack(tmp_path)
    (tmp_path / "02-beta" / "Prompt.md").write_text("x")
    try:
        both = {p.name for p in (tmp_path / "02-beta").iterdir()}
        if {"prompt.md", "Prompt.md"} <= both:
            with pytest.raises(DigestError, match="collision"):
                pack_digest(tmp_path)
        else:
            pytest.skip("case-insensitive filesystem cannot host the collision")
    finally:
        pass


def test_split_digest_golden_and_order_independence():
    assert split_digest(2, ["b-task", "a-task"], ["c-task"], ["d-task"]) == SD_GOLDEN
    assert split_digest(2, ["a-task", "b-task"], ["c-task"], ["d-task"]) == SD_GOLDEN
    assert split_digest(3, ["a-task", "b-task"], ["c-task"], ["d-task"]) != SD_GOLDEN


def mini_finding(root, digest_value="0" * 64, indent=2):
    root.mkdir(exist_ok=True)
    (root / "finding.json").write_text(json.dumps(
        {"digest": digest_value, "slug": "maxtok-48k", "kind": "improvement"},
        indent=indent))
    (root / "mutation").mkdir(exist_ok=True)
    (root / "mutation" / "overlay.yml").write_text("maxTokens: 49152\n")
    (root / "evidence").mkdir(exist_ok=True)
    (root / "evidence" / "manifest.json").write_text('{"decision": "PROMOTE"}\n')
    return root


def test_finding_digest_golden(tmp_path):
    assert finding_digest(mini_finding(tmp_path / "f")) == FD_GOLDEN


def test_finding_digest_self_reference(tmp_path):
    """The stored digest value and finding.json's on-disk formatting must not
    affect the digest (amended hr-fd-1 rule: canonical JSON with digest=null),
    but every other claim field must."""
    a = finding_digest(mini_finding(tmp_path / "a", digest_value=FD_GOLDEN, indent=None))
    assert a == FD_GOLDEN
    b = mini_finding(tmp_path / "b")
    meta = json.loads((b / "finding.json").read_text())
    meta["kind"] = "negative-result"
    (b / "finding.json").write_text(json.dumps(meta))
    assert finding_digest(b) != FD_GOLDEN


def test_finding_digest_covers_evidence(tmp_path):
    f = mini_finding(tmp_path / "f")
    (f / "evidence" / "manifest.json").write_text('{"decision": "REJECT"}\n')
    assert finding_digest(f) != FD_GOLDEN


def test_canonical_json():
    assert canonical_json({"b": 1, "a": ["x", "y"], "u": "café"}) == \
        '{"a":["x","y"],"b":1,"u":"café"}\n'
