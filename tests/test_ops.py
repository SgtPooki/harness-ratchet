"""Op apply/restore idempotence and trap-restore for the three omp surface
ops (issue #2 point 7, deferred from step 1 to the step that built the
runner)."""

import pytest

from ratchet.runner.ops import (
    ApplyRecord,
    ConfigOverlayOp,
    ModelParamOp,
    OpError,
    RulesAppendOp,
    applied,
)

MODELS_YML = """\
# operator comments must survive untouched
providers:
  vllm:
    baseUrl: https://example.invalid/v1
    models:
      - id: homelab-default
        name: Qwen (thinking)   # inline comment
        contextWindow: 122880
        maxTokens: 32768
      - id: other-model
        contextWindow: 4096
        maxTokens: 1024
  lmstudio:
    models:
      - id: homelab-default
        maxTokens: 2048
"""

DIGEST12 = "abcdef123456"


@pytest.fixture()
def models_yml(tmp_path):
    p = tmp_path / "models.yml"
    p.write_text(MODELS_YML)
    return p


@pytest.fixture()
def rules_md(tmp_path):
    p = tmp_path / "RULES.md"
    p.write_text("# Rules\n\n- be sensible\n")
    return p


# --- model-param / set ------------------------------------------------------

def op_maxtok(models_yml, value=49152, alias="vllm/homelab-default",
              yaml_id="homelab-default", key="maxTokens"):
    return ModelParamOp(models_yml, alias, yaml_id, key, value)


def test_model_param_apply_and_restore_byte_exact(models_yml):
    original = models_yml.read_bytes()
    op = op_maxtok(models_yml)
    rec = op.apply()
    assert rec == ApplyRecord(surface="model-param", vacuous=False, prior_value="32768")
    text = models_yml.read_text()
    assert "maxTokens: 49152" in text
    assert "# operator comments must survive untouched" in text
    assert "name: Qwen (thinking)   # inline comment" in text
    assert "maxTokens: 2048" in text          # other provider untouched
    assert "maxTokens: 1024" in text          # other entry untouched
    op.restore()
    assert models_yml.read_bytes() == original


def test_model_param_reapply_is_vacuous(models_yml):
    op_maxtok(models_yml).apply()
    rec = op_maxtok(models_yml).apply()
    assert rec.vacuous is True
    assert rec.prior_value == "49152"


def test_model_param_selector_fails_closed(models_yml):
    with pytest.raises(OpError, match="matches 0"):
        op_maxtok(models_yml, yaml_id="nope").apply()
    with pytest.raises(OpError, match="matches 0"):
        op_maxtok(models_yml, alias="missing-provider/homelab-default").apply()
    # duplicate id inside ONE provider: 2 matches, fail closed
    dup = models_yml.read_text().replace(
        "      - id: other-model",
        "      - id: homelab-default\n        maxTokens: 7\n      - id: other-model")
    models_yml.write_text(dup)
    with pytest.raises(OpError, match="matches 2"):
        op_maxtok(models_yml).apply()


def test_model_param_missing_key_fails_closed(models_yml):
    with pytest.raises(OpError, match="appears 0"):
        op_maxtok(models_yml, key="temperature").apply()
    assert models_yml.read_text() == MODELS_YML  # nothing left applied


def test_model_param_trap_restore(models_yml):
    original = models_yml.read_bytes()
    with pytest.raises(RuntimeError):
        with applied(op_maxtok(models_yml)) as rec:
            assert rec.prior_value == "32768"
            assert "49152" in models_yml.read_text()
            raise RuntimeError("rollout blew up")
    assert models_yml.read_bytes() == original


# --- rules / append ---------------------------------------------------------

def test_rules_append_restore_and_fences(rules_md):
    original = rules_md.read_bytes()
    op = RulesAppendOp(rules_md, "- prefer minimal diffs", DIGEST12)
    rec = op.apply()
    assert rec.vacuous is False
    text = rules_md.read_text()
    assert f"<!-- hr-mutation:{DIGEST12} start -->" in text
    assert "- prefer minimal diffs" in text
    assert f"<!-- hr-mutation:{DIGEST12} end -->" in text
    op.restore()
    assert rules_md.read_bytes() == original


def test_rules_reapply_replaces_block(rules_md):
    RulesAppendOp(rules_md, "- old text", DIGEST12).apply()
    RulesAppendOp(rules_md, "- new text", DIGEST12).apply()
    text = rules_md.read_text()
    assert "- old text" not in text
    assert "- new text" in text
    assert text.count(f"hr-mutation:{DIGEST12} start") == 1


def test_rules_identical_block_is_vacuous(rules_md):
    RulesAppendOp(rules_md, "- same", DIGEST12).apply()
    frozen = rules_md.read_bytes()
    rec = RulesAppendOp(rules_md, "- same", DIGEST12).apply()
    assert rec.vacuous is True
    assert rules_md.read_bytes() == frozen


def test_rules_trap_restore(rules_md):
    original = rules_md.read_bytes()
    with pytest.raises(RuntimeError):
        with applied(RulesAppendOp(rules_md, "- x", DIGEST12)):
            raise RuntimeError("boom")
    assert rules_md.read_bytes() == original


def test_rules_bad_digest_rejected(rules_md):
    with pytest.raises(OpError, match="12 hex"):
        RulesAppendOp(rules_md, "- x", "not-a-digest")


def test_rules_missing_file_fails_closed(tmp_path):
    with pytest.raises(OpError, match="not found"):
        RulesAppendOp(tmp_path / "RULES.md", "- x", DIGEST12).apply()


# --- config-overlay / apply-overlay -----------------------------------------

def test_config_overlay_vacuous_iff_already_standing(tmp_path):
    overlay = tmp_path / "mut.yml"
    overlay.write_text("maxTokens: 49152\n")
    standing = tmp_path / "standing.yml"
    standing.write_text("advisor:\n  enabled: false\n")
    assert ConfigOverlayOp(overlay).apply(standing_overlays=[standing]).vacuous is False
    dup = tmp_path / "dup.yml"
    dup.write_text(overlay.read_text())
    assert ConfigOverlayOp(overlay).apply(standing_overlays=[dup]).vacuous is True


def test_config_overlay_missing_fails_closed(tmp_path):
    with pytest.raises(OpError, match="not found"):
        ConfigOverlayOp(tmp_path / "nope.yml").apply()
