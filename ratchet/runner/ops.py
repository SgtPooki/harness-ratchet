"""The three omp surface operations (finding format v1, issue #5, point 2).

Exactly one op per finding; op semantics are idempotent and atomic with
trap-restore (any failure = full restore):

- config-overlay / apply-overlay: the overlay file ships verbatim and is
  applied as a standalone --config flag, never an edit to personal config.
- model-param / set: keyed merge into models.yml through the selector
  {omp_model_alias, yaml_id}; fails closed when the selector matches zero
  or multiple entries. The payload applies as declared (adaptive
  semantics were rejected); the prior value and a vacuous flag are
  recorded for the replication manifest.
- rules / append: a marker-delimited block (hr-mutation:<digest12>
  fences); re-apply replaces the block, restore removes it.

The trust-header --append-system-prompt channel is NOT an op: findings on
it are registry-inadmissible until a format version bump (#5 amendment);
the loop may still probe it (see probe).

Every op backs up the exact prior bytes at apply time and restore() puts
them back byte-for-byte; use the `applied` context manager for the
trap-restore guarantee.
"""

import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class OpError(Exception):
    """An op failed closed (bad selector, missing file); nothing was left applied."""


@dataclass
class ApplyRecord:
    surface: str            # config-overlay | model-param | rules
    vacuous: bool           # the op changed nothing (prior state already matched)
    prior_value: str | None = None   # model-param: the value the payload replaced


class ConfigOverlayOp:
    """Ships an overlay file applied via --config: no harness file is edited."""

    surface = "config-overlay"

    def __init__(self, overlay: Path):
        self.overlay = Path(overlay)

    def apply(self, standing_overlays: list[Path] = ()) -> ApplyRecord:
        if not self.overlay.is_file():
            raise OpError(f"overlay not found: {self.overlay}")
        mine = self.overlay.read_bytes()
        vacuous = any(Path(p).is_file() and Path(p).read_bytes() == mine
                      for p in standing_overlays)
        return ApplyRecord(surface=self.surface, vacuous=vacuous)

    def restore(self) -> None:
        pass


class ModelParamOp:
    """Keyed merge of one scalar param into one models.yml model entry.

    Line-oriented surgery so every unrelated byte (comments included) is
    preserved: the selector must match exactly one `- id: <yaml_id>` entry
    under the provider named by omp_model_alias's prefix, and the key must
    appear exactly once inside that entry, or the op fails closed.
    """

    surface = "model-param"

    def __init__(self, models_yml: Path, omp_model_alias: str, yaml_id: str,
                 key: str, value):
        self.models_yml = Path(models_yml)
        self.provider = omp_model_alias.split("/", 1)[0]
        self.alias = omp_model_alias
        self.yaml_id = yaml_id
        self.key = key
        self.value = value
        self._backup: bytes | None = None

    def _locate(self, lines: list[str]) -> tuple[int, int, int]:
        """Return (entry_start, entry_end, key_line) or fail closed."""
        provider = None
        entries = []
        provider_re = re.compile(r"^  (\S+?):\s*(#.*)?$")
        id_re = re.compile(rf"^(\s*)-\s+id:\s*{re.escape(self.yaml_id)}\s*(#.*)?$")
        for i, line in enumerate(lines):
            m = provider_re.match(line)
            if m:
                provider = m.group(1)
            m = id_re.match(line)
            if m and provider == self.provider:
                entries.append((i, len(m.group(1))))
        if len(entries) != 1:
            raise OpError(
                f"selector {{{self.alias}, {self.yaml_id}}} matches "
                f"{len(entries)} entries in {self.models_yml}; need exactly 1")
        start, indent = entries[0]
        end = len(lines)
        for j in range(start + 1, len(lines)):
            stripped = lines[j].strip()
            if not stripped:
                continue
            line_indent = len(lines[j]) - len(lines[j].lstrip())
            if line_indent <= indent:
                end = j
                break
        key_re = re.compile(rf"^(\s+){re.escape(self.key)}:\s*(\S.*?)\s*$")
        keys = [(j, key_re.match(lines[j])) for j in range(start + 1, end)
                if key_re.match(lines[j])]
        if len(keys) != 1:
            raise OpError(
                f"key {self.key!r} appears {len(keys)} times in entry "
                f"{self.yaml_id!r} of {self.models_yml}; need exactly 1")
        return start, end, keys[0][0]

    def apply(self) -> ApplyRecord:
        if not self.models_yml.is_file():
            raise OpError(f"models.yml not found: {self.models_yml}")
        original = self.models_yml.read_bytes()
        try:
            text = original.decode("utf-8")
            lines = text.splitlines(keepends=True)
            _, _, key_line = self._locate(lines)
            indent = lines[key_line][:len(lines[key_line]) - len(lines[key_line].lstrip())]
            prior = lines[key_line].strip().split(":", 1)[1].strip()
            newline = "\n" if lines[key_line].endswith("\n") else ""
            lines[key_line] = f"{indent}{self.key}: {self.value}{newline}"
            self._backup = original
            self.models_yml.write_bytes("".join(lines).encode("utf-8"))
            return ApplyRecord(surface=self.surface,
                               vacuous=prior == str(self.value), prior_value=prior)
        except OpError:
            raise
        except Exception as e:
            self.restore()
            raise OpError(f"model-param apply failed, restored: {e}") from e

    def restore(self) -> None:
        if self._backup is not None:
            self.models_yml.write_bytes(self._backup)
            self._backup = None


class RulesAppendOp:
    """Appends a marker-fenced block to RULES.md; re-apply replaces it."""

    surface = "rules"

    def __init__(self, rules_path: Path, text: str, digest12: str):
        if not re.fullmatch(r"[0-9a-f]{12}", digest12):
            raise OpError(f"digest12 must be 12 hex chars, got {digest12!r}")
        self.rules_path = Path(rules_path)
        self.text = text.rstrip("\n")
        self.digest12 = digest12
        self._backup: bytes | None = None

    @property
    def _start(self) -> str:
        return f"<!-- hr-mutation:{self.digest12} start -->"

    @property
    def _end(self) -> str:
        return f"<!-- hr-mutation:{self.digest12} end -->"

    def _block(self) -> str:
        return f"{self._start}\n{self.text}\n{self._end}\n"

    def _strip_block(self, text: str) -> str:
        pattern = re.compile(
            rf"\n?{re.escape(self._start)}\n.*?\n{re.escape(self._end)}\n",
            re.DOTALL)
        return pattern.sub("\n", text)

    def apply(self) -> ApplyRecord:
        if not self.rules_path.is_file():
            raise OpError(f"rules file not found: {self.rules_path}")
        original = self.rules_path.read_bytes()
        try:
            text = original.decode("utf-8")
            vacuous = self._block() in text
            if not vacuous:
                text = self._strip_block(text)  # re-apply replaces the block
                if not text.endswith("\n"):
                    text += "\n"
                text += "\n" + self._block()
                self._backup = original
                self.rules_path.write_bytes(text.encode("utf-8"))
            return ApplyRecord(surface=self.surface, vacuous=vacuous)
        except OpError:
            raise
        except Exception as e:
            self.restore()
            raise OpError(f"rules apply failed, restored: {e}") from e

    def restore(self) -> None:
        if self._backup is not None:
            self.rules_path.write_bytes(self._backup)
            self._backup = None


@contextmanager
def applied(op, **apply_kwargs):
    """Trap-restore: apply the op, always restore on the way out."""
    record = op.apply(**apply_kwargs)
    try:
        yield record
    finally:
        op.restore()
