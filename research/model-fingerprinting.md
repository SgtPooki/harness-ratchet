# Model fingerprinting for local weights

Research for issue #10. Question: how do local inference stacks identify exact
model weights, and what fingerprint definition should the claim schema use?

The claim schema (VISION.md, "The artifacts") pins a "model fingerprint (a hash
identifying the exact weights, and the family bucket the dashboard groups by)".
This document surveys how identity works in the stacks we care about (Hugging
Face Hub and transformers, vLLM, llama.cpp/GGUF, ollama), then recommends a
concrete two-component fingerprint a CLI can compute or look up cheaply.

## Survey

### Hugging Face Hub: revisions, LFS OIDs, cache layout

The Hub versions model repos with git plus git-LFS. A *revision* is a branch
name, tag, or commit hash; only the commit hash immutably identifies a state of
the repo. Weight files are stored in LFS, and an LFS pointer file records the
object id (OID), which is the sha256 of the file's content. The Hub exposes
this as the file's ETag: "an object's ETag is its git-sha1 if stored in git, or
its sha256 if stored in git-lfs"
([huggingface_hub file download reference](https://huggingface.co/docs/huggingface_hub/package_reference/file_download)).

The local cache makes both facts available offline for free
([manage-cache guide](https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache)):

- `snapshots/<commit-hash>/` names each cached revision by its full commit
  hash; `refs/main` maps the branch to that hash.
- `blobs/` stores each downloaded file under its hash as the filename: sha256
  for LFS files (all weight shards), git-sha1 for small non-LFS files
  (config.json, tokenizer files). Snapshot entries are symlinks into `blobs/`.
- `trees/<commit>.json` caches the full file listing with path, size, and hash
  per file.
- `hf cache verify` already re-checks cached files against Hub checksums,
  confirming these hashes are treated as the integrity ground truth.

So for any model that came through the HF cache, a CLI can read the exact
per-file sha256 of every weight shard and the source commit hash without
hashing a single byte: resolve the snapshot directory, follow each symlink,
and take the blob filename. Caveats: small non-LFS files carry git-sha1 blob
names, so their sha256 must be computed (they are kilobytes, so this is
negligible), and the Windows no-symlink cache mode copies files into
`snapshots/` directly, losing the hash-named blobs, in which case files must
be hashed.

The safetensors format itself carries no content hash: the header is a JSON
table of tensor names, dtypes, shapes, and offsets. Identity for safetensors
files is external (the LFS OID or a computed sha256 of the file).

### GGUF (llama.cpp): rich metadata, no weight hash

GGUF embeds identity-adjacent metadata in the file
([GGUF spec](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md)):
`general.name`, `general.architecture`, `general.basename`,
`general.size_label`, `general.file_type` (the quantization type, e.g.
MOSTLY_Q4_K_M), `general.quantization_version`, `general.source.url` and
`general.source.repo_url`, `general.base_model.{id}.*` lineage fields, and an
optional `general.uuid`.

Two conclusions. First, GGUF has no cryptographic hash of the tensor data;
`general.uuid` is optional and assigned, not content-derived, so none of these
fields can serve as the exact-weights component. The sha256 of the GGUF file
itself is the only reliable exact identity, and since quantization is baked
into the file, every quant variant of the same base model is a different file
with a different hash, which is the behavior we want. Second, the metadata is
exactly what the family bucket needs: basename plus size label plus
architecture is a machine-readable family, and file_type names the quant.

### vLLM: served name is a label, not an identity

vLLM's `--served-model-name` sets the string returned by `/v1/models` and used
in responses and metrics; it is an arbitrary operator-chosen alias, defaulting
to the `--model` argument
([vllm serve CLI reference](https://docs.vllm.ai/en/stable/cli/serve/)).
Multiple aliases can point at the same weights, and the same alias can point
at different weights across restarts. The served name therefore must never be
the fingerprint; it belongs in the runtime envelope as a label at most.

vLLM does understand HF revisions: current stable vLLM documents `--revision`
plus separate `--code-revision` and `--tokenizer-revision`, each accepting a
branch, tag, or commit id
([vllm serve CLI reference](https://docs.vllm.ai/en/stable/cli/serve/)). A
proposal to rename `--revision` to `--weights-revision`
([vllm PR #5453](https://github.com/vllm-project/vllm/pull/5453)) was closed
without merging, so `--revision` remains the flag. Two cautions. First, these
flags accept mutable refs, so only a full commit hash pins anything. Second,
even a pinned commit did not fully pin behavior before vLLM v0.22.0: advisory
[GHSA-3ww4-5jv9-j5gm](https://github.com/vllm-project/vllm/security/advisories/GHSA-3ww4-5jv9-j5gm)
(CVE-2026-47155) documents that revision pinning was not applied to all
artifact load paths (dynamic code, GGUF files, processors, sibling subfolder
weights could resolve from an unpinned revision), fixed in v0.22.0. Revision
flags therefore must not be treated as fully identifying loaded behavior
across vLLM versions, which is one more reason the fingerprint below is
computed from bytes on disk rather than from engine configuration.

vLLM loads weights from an HF repo id (resolved through the standard HF
cache) or a local directory. Identity of what vLLM is actually serving is
therefore the identity of that directory's files, which reduces to the HF
cache case or the local-directory case below.

### ollama: content-addressed already

ollama stores models as OCI-style manifests: a JSON manifest lists layers
(weights blob, template, params, system prompt), each identified by a sha256
digest, and blobs on disk are stored under their digest
([ollama registry manifest example](https://registry.ollama.ai/v2/library/llama3.2/manifests/1b),
[storage writeup](https://medium.com/@enisbaskapan/how-ollama-stores-models-11fc47f48955)).
The weights layer (media type `...image.model`) is a GGUF file, and its digest
is the sha256 of that GGUF. So for ollama-managed models the per-file sha256
can be read straight out of the local manifest, and it is the same value one
gets by hashing the GGUF file directly with llama.cpp in mind. Note that this
is a bare file hash, not the manifest-level fingerprint defined below; the
recommendation keeps both, with explicit rules so the derived fingerprint is
identical regardless of which stack served the file. The model tag
(`llama3.2:1b`) is mutable and, like vLLM's served name, only a label.

### Prior art: localmaxxing

[localmaxxing](https://www.localmaxxing.com/en) is the closest live system to
the registry dashboard: a public leaderboard of local inference results with
community submissions via a web form or the `lmx` CLI. Its identity scheme is
worth examining precisely because it is name-based end to end.

A leaderboard row is keyed by self-reported strings: a Hugging Face repo id,
a quantization label, the engine and its version, and the hardware. The
[models listing](https://www.localmaxxing.com/en/models) shows quantization
variants as separate entries (a base repo and its GPTQ-Int4 repackage are
distinct rows) with no cryptographic identity, revision display, or verified
badge anywhere. Grouping is by identical strings; rankings take the median
per group, require at least three runs, and exclude runs whose parameter
counts or quantization labels cannot be parsed
([get started](https://www.localmaxxing.com/en/get-started),
[leaderboard](https://www.localmaxxing.com/en/leaderboard)).

The `lmx` CLI's benchmark run payload confirms the trust boundary. It carries
an `hfId` (a repo id string, resolved from the engine's served-model alias by
a name search, with the resolution explicitly marked `status: alias`), a
`modelRevision` that in practice holds the mutable ref `main` rather than a
commit hash, a parsed `quantization` string whose resolution records its
source as the CLI itself, and engine name and version. Measurement provenance
is handled carefully (separate fields record where timing, TTFT, and token
counts came from), but nothing binds any of it to weight bytes: no file hash,
no commit pin, no manifest.

Three lessons for hr-mf-1:

- Validation of the premise. The closest live leaderboard demonstrates the
  default outcome when identity is not designed: rows keyed by self-reported
  names, a revision field that pins nothing, and no way to tell whether two
  submissions ran the same bytes. This is exactly the gap the exact-weights
  digest closes, and it confirms that served-name resolution (which lmx also
  does) is a labeling convenience, not identity.
- Quantization labels need a normalized vocabulary. localmaxxing must
  exclude runs with unparseable quantization labels to keep groups coherent,
  and the same model can surface twice when the quant lives in the repo name
  (GGUF-style) versus a metadata field (safetensors-style). hr-mf-1 avoids
  the identity half of this by content-addressing, but `provenance.quant`
  should still be drawn from a normalized enum so human-facing grouping does
  not fragment the way string-keyed rows do.
- Family grouping will be demanded by users. localmaxxing's per-repo rows
  fragment results across repackagings of the same base model, which is the
  reader problem the family bucket exists to solve; keeping family separate
  from exact identity, rather than choosing one as localmaxxing implicitly
  does, remains the right split.

### Existing conventions for model identity hashing

The closest thing to a standard is the OpenSSF Model Signing spec (OMS) and
sigstore's model-transparency project
([OMS spec](https://github.com/ossf/model-signing-spec),
[sigstore/model-transparency](https://github.com/sigstore/model-transparency),
[sigstore blog](https://blog.sigstore.dev/model-transparency-v1.0/)). OMS
signs a detached manifest listing every file in the model directory by sha256,
so weights, config, and tokenizer verify as a unit. That validates the shape
of the recommendation below: model identity is a digest over a canonical
per-file hash manifest, not a single-file hash and not a name. The alignment
is at the per-file sha256 basis only: our manifest text, file selection, and
digest construction differ from an OMS bundle, so our fingerprint will not
numerically equal any OMS hash. A future bridge to OMS is possible but needs
an explicit conversion step (recompute the OMS manifest from the same files),
not a hash comparison.

Other conventions map onto the same split between exact identity and naming:
HF model card revisions pin metadata to commits (attribution, not content
identity, since the Hub could serve a repo differently than what was cached);
ollama digests are exact content identity; GGUF naming conventions
(basename-size-quant) are family naming.

## Recommendation

A fingerprint is two components, computed independently.

### Component 1: exact-weights digest

`weights: sha256:<hex>` where the hex is the sha256 of a canonical manifest
text, computed under a versioned algorithm id (`hr-mf-1` for the definition
below). The algorithm id is recorded in the schema so a later revision of the
file-selection or canonicalization rules never silently collides with v1
digests.

1. Collect the behavior-determining files of the model directory: weight files
   (`*.safetensors`, `*.gguf`, `*.bin`, `*.pt`), weight indexes
   (`*.safetensors.index.json`), `config.json`, `generation_config.json`,
   tokenizer files (`tokenizer.json`, `tokenizer_config.json`,
   `tokenizer.model`, `vocab.*`, `merges.txt`, `special_tokens_map.json`),
   and chat template or processor configs when present
   (`chat_template.jinja`, `chat_template.json`, `preprocessor_config.json`,
   `processor_config.json`). Exclude documentation and images.
2. For each file obtain its sha256.
3. Canonical paths: relative to the model root, forward slashes, no leading
   `./`. A single-file model (one GGUF and nothing else) uses the fixed
   canonical path `model.gguf` regardless of the file's on-disk name, so that
   byte-identical GGUF files always yield the same digest whether they came
   from ollama's blob store, an HF download, or a renamed local copy.
4. Canonical manifest: one line per file, `sha256:<hex>  <canonical-path>`,
   sorted bytewise by path, newline separated, trailing newline. The sha256
   of that text is the fingerprint.

For a single-file GGUF the manifest has one line and the fingerprint is a
deterministic function of the bare file sha256. Implementations should report
the bare file hash alongside it (`provenance.file_sha256`), since that is the
value ollama digests and community checksum lists publish; the manifest digest
is the identity, the bare hash is the cross-check.

Scope for v1: standard full-weight model layouts only. Repos that ship custom
model code (`trust_remote_code`, `modeling_*.py` and friends) execute code
outside this file set, so v1 does not claim to capture their behavior in the
fingerprint; the code revision belongs in the runtime envelope, and the
GHSA-3ww4-5jv9-j5gm advisory above shows why conflating the two is dangerous.
Runtime-applied LoRA or other adapters are likewise runtime envelope entries
(base fingerprint plus declared adapters), while an adapter merged into the
weights is simply a new set of weight files and fingerprints normally.

Cheap computation, in order of preference:

- HF cache: read blob symlink targets for sha256 of every LFS file and the
  snapshot directory name for the commit; hash only the small non-LFS files.
  Effectively free. Two fallbacks are required before trusting this path:
  the `trees/<commit>.json` listing exists only when a sufficiently recent
  `snapshot_download()` populated it, and per-file `hf_hub_download()` calls
  can leave a snapshot with missing shards. The CLI must therefore verify the
  snapshot is complete against the commit's file listing (local tree cache or
  one Hub call) before emitting a manifest digest, and fall back to direct
  hashing (or refuse with a clear error when offline) if completeness cannot
  be established. A digest over a partial file set is worse than no digest.
- ollama: read the local manifest's layer digests. Free.
- Anything else (local directory, modified or merged weights, no-symlink
  cache): stream-hash the files once and persist the result in a local cache
  keyed by content evidence, not timestamps: absolute path, file size, and a
  partial hash (for example sha256 of the first and last mebibyte). mtime is
  not part of the key; it is trivially preserved by copy tools and editable,
  so it can validate a stale entry. Cost honesty: tens of gigabytes hash in
  tens of seconds on NVMe, but frontier-scale checkpoints run to hundreds of
  gigabytes and take minutes even on fast storage, so implementations should
  stream with a progress indicator and never discard the persisted cache
  between runs. Still a one-time cost per model, negligible next to a
  benchmark run.

### Component 2: family bucket

`family: <string>`, a normalized lowercase `basename-sizelabel[-tune]` tag,
for example `qwen3-27b-instruct`, `qwen3-27b` (the base model), or
`llama3.2-1b-instruct`. It answers "what does the dashboard group by" and
deliberately ignores quantization and repackaging, but it does encode
instruction-tune status: a base model and its instruct tune behave differently
enough on agentic tasks that grouping them would mislead readers. Third-party
fine-tunes and merges derived from a family keep that family string but are
distinguishable in the schema: `provenance` identifies the actual weights, and
`family_source` records whether the family was inferred from metadata or
declared by the operator. Readers should treat the family as "derived from
this base lineage at this size and tune level", never as "equivalent to the
base publisher's model".

Derivation, best source first:

- GGUF: `general.basename` + `general.size_label` (fall back to
  `general.name` and `general.architecture`).
- HF: the repo's `config.json` (`model_type`, layer and hidden dimensions to
  sanity-check the size label) plus the repo name; `base_model` metadata in
  the model card when present.
- Locally merged or heavily modified weights: the tooling proposes a family
  from config metadata and the operator confirms or overrides it. The family
  is a declared grouping key, not a verified fact, and the schema should mark
  operator-overridden families as such.

### Provenance block (attribution, not identity)

Alongside the two identity components, record where the weights came from when
known:

```yaml
model_fingerprint:
  algorithm: hr-mf-1               # fingerprint algorithm version
  weights: sha256:9f2a...          # canonical manifest digest, exact identity
  family: qwen3-27b-instruct       # dashboard grouping bucket
  family_source: inferred          # inferred | operator
  provenance:                      # optional, attribution only
    source: hf                     # hf | ollama | local
    repo: org/model-name           # when source is hf or ollama
    revision: 607a30d783df...      # full commit hash (hf) or manifest digest (ollama)
    file_sha256: sha256:1c4e...    # bare file hash, single-file models only
    quant: q4-k-m                  # baked-in quant scheme, or none
```

The HF commit hash is provenance, not identity: it lets a replicator fetch
the same weights, but the manifest digest is what proves they got them. Two
different repos publishing byte-identical weights produce the same `weights`
digest, which is correct.

### Interaction with the runtime envelope

The claim schema's runtime envelope already carries a quantization field.
Split the concern: quantization baked into the files (GPTQ, AWQ, GGUF quants)
changes the weight bytes and is therefore already captured by the `weights`
digest, with `provenance.quant` naming the scheme for humans. The runtime
envelope's quantization field covers only load-time transforms the engine
applies to unmodified files (for example on-the-fly fp8 or int8 loading),
which change behavior without changing the fingerprint.

### Locally modified or merged weights

- Always fingerprintable: the manifest digest is computed from bytes on disk
  and needs no registry. This is the whole point of a content hash.
- `provenance.source: local`, no repo or revision. Claims against such weights
  are inherently not registry re-runnable (VISION.md "Trust model": re-runs
  require obtainable weights) and can only accrue local-transfer credibility,
  so the schema should let the registry derive "weights obtainable" directly
  from provenance.
- Family stays operator-confirmed as above. A merge of two families is a new
  family string chosen by the operator.

### API-only and otherwise unhashable weights

Some claims will target models whose bytes the operator cannot read: hosted
API endpoints, or engines that hide the weights behind an opaque store. The
policy is explicit rather than best-effort: the fingerprint's `weights` field
is recorded as `unavailable` (no digest is fabricated from names or API
metadata), the family and provenance are still recorded as declared labels,
and the claim is restricted to the local-transfer credibility lane. Without an
exact-weights digest there is nothing for an exact replication to match and
nothing for a registry re-run to load, so such claims are ineligible for both
of those lanes (VISION.md "Trust model") and the registry can derive that
ineligibility mechanically from the fingerprint alone.

### What not to do

- Do not use vLLM served names, ollama tags, or HF branch names as any part of
  identity. All three are mutable labels.
- Do not trust GGUF `general.uuid` or `general.name` for exact identity; they
  are assigned metadata, absent or copy-pasted in practice.
- Do not hash tensor contents individually (parsing safetensors or GGUF
  internals) for v1. File-level sha256 is what every surveyed ecosystem
  already exposes or expects (LFS OIDs, ollama digests, OMS manifests), and
  it lets the per-file hashes in our manifest be cross-checked against
  published values even though the manifest digest itself is ours alone.
  Tensor-level hashing that survives resharding could be a later extension,
  flagged by a fingerprint algorithm version field.

## Sources

- https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache
- https://huggingface.co/docs/huggingface_hub/package_reference/file_download
- https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
- https://docs.vllm.ai/en/stable/cli/serve/
- https://github.com/vllm-project/vllm/pull/5453
- https://github.com/vllm-project/vllm/security/advisories/GHSA-3ww4-5jv9-j5gm
- https://registry.ollama.ai/v2/library/llama3.2/manifests/1b
- https://github.com/ossf/model-signing-spec
- https://github.com/sigstore/model-transparency
- https://www.localmaxxing.com/en/models
- https://blog.sigstore.dev/model-transparency-v1.0/
