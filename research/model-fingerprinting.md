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

vLLM does understand HF revisions: `--revision` (renamed `--weights-revision`,
[vllm PR #5453](https://github.com/vllm-project/vllm/pull/5453)) plus separate
`--code-revision` and `--tokenizer-revision` accept a branch, tag, or commit
id. vLLM loads weights from an HF repo id (resolved through the standard HF
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
is the sha256 of that GGUF. So for ollama-managed models the exact-weights
hash can be read straight out of the local manifest, and it agrees by
construction with "sha256 of the GGUF file": the same weights fingerprint
whether the user runs the file through llama.cpp directly or through ollama.
The model tag (`llama3.2:1b`) is mutable and, like vLLM's served name, only a
label.

### Existing conventions for model identity hashing

The closest thing to a standard is the OpenSSF Model Signing spec (OMS) and
sigstore's model-transparency project
([OMS spec](https://github.com/ossf/model-signing-spec),
[sigstore/model-transparency](https://github.com/sigstore/model-transparency),
[sigstore blog](https://blog.sigstore.dev/model-transparency-v1.0/)). OMS
signs a detached manifest listing every file in the model directory by sha256,
so weights, config, and tokenizer verify as a unit. That validates the shape
of the recommendation below: model identity is a digest over a canonical
per-file hash manifest, not a single-file hash and not a name. OMS adds
signatures and transparency logs on top; we only need the manifest digest, and
adopting the same per-file sha256 basis keeps a future bridge to OMS open.

Other conventions map onto the same split between exact identity and naming:
HF model card revisions pin metadata to commits (attribution, not content
identity, since the Hub could serve a repo differently than what was cached);
ollama digests are exact content identity; GGUF naming conventions
(basename-size-quant) are family naming.

## Recommendation

A fingerprint is two components, computed independently.

### Component 1: exact-weights digest

`weights: sha256:<hex>` where the hex is the sha256 of a canonical manifest
text:

1. Collect the behavior-determining files of the model directory: weight files
   (`*.safetensors`, `*.gguf`, `*.bin`, `*.pt`), weight indexes
   (`*.safetensors.index.json`), `config.json`, `generation_config.json`, and
   tokenizer files (`tokenizer.json`, `tokenizer_config.json`,
   `tokenizer.model`, `vocab.*`, `merges.txt`, `special_tokens_map.json`).
   Exclude documentation and images.
2. For each file obtain its sha256.
3. Canonical manifest: one line per file, `sha256:<hex>  <relative-path>`,
   sorted bytewise by path, newline separated. The digest of that text is the
   fingerprint.

For a single-file GGUF the manifest has one line, so the definition still
applies uniformly, but implementations may report the bare file sha256
alongside it since that is what ollama digests and community checksum lists
use.

Cheap computation, in order of preference:

- HF cache: read blob symlink targets for sha256 of every LFS file and the
  snapshot directory name for the commit; hash only the small non-LFS files.
  Effectively free.
- ollama: read the local manifest's layer digests. Free.
- Anything else (local directory, modified or merged weights, no-symlink
  cache): stream-hash the files once and cache the result keyed by absolute
  path, size, and mtime. Tens of seconds for tens of gigabytes, paid once per
  model, which is negligible next to a benchmark run.

### Component 2: family bucket

`family: <string>`, a normalized lowercase `basename-sizelabel` tag, for
example `qwen3-27b` or `llama3.2-1b`. It answers "what does the dashboard
group by" and deliberately ignores quantization, fine-tunes, and merges of the
same base at the same size.

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
  weights: sha256:9f2a...          # canonical manifest digest, exact identity
  family: qwen3-27b                # dashboard grouping bucket
  provenance:                      # optional, attribution only
    source: hf                     # hf | ollama | local
    repo: org/model-name           # when source is hf or ollama
    revision: 607a30d783df...      # full commit hash (hf) or manifest digest (ollama)
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

### What not to do

- Do not use vLLM served names, ollama tags, or HF branch names as any part of
  identity. All three are mutable labels.
- Do not trust GGUF `general.uuid` or `general.name` for exact identity; they
  are assigned metadata, absent or copy-pasted in practice.
- Do not hash tensor contents individually (parsing safetensors or GGUF
  internals) for v1. File-level sha256 is what every surveyed ecosystem
  already exposes or expects (LFS OIDs, ollama digests, OMS manifests), and
  it makes independently computed fingerprints agree with published hashes.
  Tensor-level hashing that survives resharding could be a later extension,
  flagged by a fingerprint algorithm version field.

## Sources

- https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache
- https://huggingface.co/docs/huggingface_hub/package_reference/file_download
- https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
- https://docs.vllm.ai/en/stable/cli/serve/
- https://github.com/vllm-project/vllm/pull/5453
- https://registry.ollama.ai/v2/library/llama3.2/manifests/1b
- https://github.com/ossf/model-signing-spec
- https://github.com/sigstore/model-transparency
- https://blog.sigstore.dev/model-transparency-v1.0/
