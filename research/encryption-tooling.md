# Encryption tooling for role-keyed oracle surfaces

Resolves issue #9. Surveys tooling for the pack format's reserved encryption
field: role-keyed encryption of the scoring surface (verifier) and admission
surface (reference solution, sabotage variant), where the same file must be
decryptable by a scorer key and an author key. Scope matches VISION.md
"Oracle secrecy": encryption here is process hygiene (a filesystem-wandering
agent finds ciphertext), not a competitive trust boundary.

## Criteria

1. Single-binary availability on macOS and Linux
2. Multi-recipient support: one ciphertext, scorer key plus author key
3. Scriptability from bash and Python
4. Key generation and storage ergonomics for a solo operator
5. Prior art in CTF or hidden-test-set tooling

## Candidates

### age (filippo.io/age)

- File encryption tool, format spec, and Go library. Static prebuilt
  binaries for macOS and Linux, plus Homebrew, apt, dnf, pacman, and
  `go install`. Source: https://github.com/FiloSottile/age
- Multi-recipient is native: repeat `-r` per recipient, or `-R` with a
  recipients file (one public key per line). The format wraps the file key
  once per recipient, so any listed identity decrypts independently.
- Keygen is one command with no ceremony: `age-keygen -o key.txt` prints
  the public key and writes the identity file. Keys are short strings
  (`age1...` public, `AGE-SECRET-KEY-...` private), storable as plain
  files or environment variables. No keyring, no trust model, no agent.
- Scriptable by design: `-e`/`-d`, stdin/stdout, `-i` identity files,
  exit codes. SSH keys also work as recipients/identities, which lets an
  operator reuse existing `~/.ssh` keys.
- Post-quantum hybrid keys exist behind `age-keygen -pq` for operators who
  want them; not needed for this threat model.

### rage (str4d/rage)

- Independent Rust implementation of the same age format, fully
  interoperable with the Go tool. Prebuilt binaries for macOS and Linux,
  `brew install rage`, `cargo install rage`, and distro packages.
  Source: https://github.com/str4d/rage
- Matters here mainly as ecosystem insurance: two maintained
  implementations of one open spec (https://age-encryption.org/v1), plus
  it is the engine behind the Python bindings below.

### OpenSSL hybrid (openssl cms / smime)

- `openssl cms -encrypt` does real hybrid multi-recipient encryption (one
  AES data key, wrapped per recipient), but recipients must be X.509
  certificates, not bare keys. Docs:
  https://docs.openssl.org/3.1/man1/openssl-cms/
- For a solo operator that means generating and tracking self-signed certs
  per role, choosing cipher and padding flags correctly by hand
  (`-aes-256-gcm`, `-keyopt rsa_padding_mode:oaep`), and living with
  OpenSSL version drift between macOS (LibreSSL by default) and Linux.
  Community recipes exist precisely because the incantations are easy to
  get wrong, e.g. https://gist.github.com/kennwhite/9918739
- Ubiquitous binary, but the worst ergonomics and the most footguns of the
  set. No advantage over age for this use.

### GPG

- Multi-recipient works (`gpg -r scorer -r author -e file`) and GPG is
  packaged everywhere, though not single-binary (gpg, gpg-agent, dirmngr,
  keyring directories). Docs: https://gnupg.org/documentation/
- The cost is the surrounding machinery: keyring state in `~/.gnupg`,
  trust model prompts, agent processes, and batch-mode flags
  (`--batch --yes --pinentry-mode loopback --trust-model always`) needed
  to make it behave in scripts. The age project exists largely as a
  reaction to this complexity.
- Justifiable if web-of-trust identity or smartcard signing were
  requirements. They are not: the pack format needs file confidentiality
  keyed by role, nothing more.

## Scriptability from Python

- age/rage: the pyrage package (https://github.com/woodruffw/pyrage,
  https://pypi.org/project/pyrage/) provides native Python bindings over
  rage via PyO3, with type stubs. In-process encrypt/decrypt with x25519
  or SSH identities, no subprocess needed. Subprocess to the `age` binary
  is equally trivial (`age -d -i key.txt -o out enc.age`) and keeps the
  kernel dependency-free.
- OpenSSL: subprocess only, with the flag-correctness burden above.
- GPG: subprocess plus python-gnupg wrappers, all of which manage keyring
  state; heavier than the problem requires.

## Prior art

- Hidden test sets: Jacovi et al., "Stop Uploading Test Data in Plain
  Text" (EMNLP 2023) recommends publishing benchmark test data encrypted
  with a key so crawlers cannot ingest it, exactly the contamination
  posture VISION.md takes for oracle surfaces.
  https://aclanthology.org/2023.emnlp-main.308/
- BIG-bench pairs a canary GUID with the option of encrypting test files:
  https://github.com/google/BIG-bench (canary and data-encryption guidance
  in the contribution docs). Canary strings are complementary to, not a
  substitute for, encryption.
- Secrets-in-git ecosystem: SOPS supports age natively as a key backend
  (https://github.com/getsops/sops#encrypting-using-age), and age is the
  common choice for committing encrypted files to public repos. No
  dominant CTF-specific convention surfaced; CTF platforms typically keep
  flags server-side rather than shipping encrypted oracles, so the
  closest prior art is the hidden-test-set literature above.

## Recommendation

Use age. It is the only candidate that hits all five criteria without
caveats: single static binary on both platforms, native multi-recipient
encryption with bare short keys, pipeline-friendly CLI, one-command
keygen with file-based key storage, and direct prior art in the
hidden-test-set literature (encrypt-what-you-publish). rage guarantees
the format outlives any one implementation, and pyrage gives an
in-process Python path if the kernel ever wants one. GPG and OpenSSL both
solve the problem but each drags in machinery (keyrings and trust
prompts; X.509 and cipher-flag correctness) that a solo operator would
maintain forever for zero added benefit at this trust boundary.

Concretely per pack: encrypt each protected surface to two recipients,
`age -r <scorer-pubkey> -r <author-pubkey> -o verifier.py.age verifier.py`.
The manifest's encryption field records the scheme (`age-v1`) and the
recipient role labels, never the keys. The operator keeps one identity
file per role (for example `~/.config/harness-ratchet/scorer.key`,
generated by `age-keygen`), and the scorer public key ships with the pack
tooling so authors can encrypt to it.

## Runner-integration sketch

Goal: the agent process never sees verifier plaintext; decryption happens
only after the agent process has exited.

1. Pack layout: `task/verifier.py.age` (and `reference/`, `sabotage/`
   equivalents) alongside the plaintext agent surface. The manifest marks
   each surface `plaintext` or `age-v1` with recipient roles.
2. Agent phase: the runner materializes only the agent surface into the
   agent workspace. Ciphertext files are not copied in; even if the agent
   escapes its workspace and reads the pack, it finds `.age` ciphertext.
3. Scoring phase, after the agent process exits and its workspace is
   snapshotted:
   - Create a private scratch dir outside the agent workspace:
     `mktemp -d` with mode 0700, on a path the agent sandbox never had
     mounted.
   - Decrypt: `age -d -i "$SCORER_KEY" -o "$scratch/verifier.py" \
     task/verifier.py.age`. Non-zero exit fails the run as a scoring
     error, distinct from a task failure.
   - Run the verifier from the scratch dir against the snapshotted
     workspace.
   - `rm -rf` the scratch dir in a finally block. Plaintext lifetime is
     the verifier invocation only.
4. Admission audit uses the author identity the same way to decrypt the
   reference and sabotage surfaces; the gate machinery is otherwise
   unchanged because decryption is a thin pre-step, not a format change.
5. Plaintext packs skip step 3's decrypt and read the verifier in place,
   so `plaintext` stays the zero-cost default the format already reserves.

Trust caveat, restated from VISION.md: anyone who holds the scorer key
can read the verifier. This design enforces process hygiene against the
agent, not secrecy against humans.
