# Security boundaries

Agent Audio is a local stdio MCP server. Run it with your own user account and
only grant it output directories you intend it to write to. It is not a sandbox
for untrusted clients or other programs running under the same account.

## Installer behavior

- Existing Skills are reused only when their files match. Conflicting Skills,
  linked destinations and mismatched MCP registrations are preserved and reported.
  Link checks cover the direct configuration directory/file and the Skill's
  client container, skills directory and tree. Ancestors above those boundaries
  (for example an OS-managed home alias) are allowed; this is not a filesystem
  sandbox. Each independent client outcome is reported, including partial failure.
- Codex and Claude native registration commands run with temporary, empty
  configuration directories. Only the generated Agent Audio entry is merged into
  the real config. Codex's unrelated bytes/comments are retained; JSON clients
  retain unrelated values. The installer does not run MCP list or connect to
  existing servers.
- Each config edit has a unique backup, a cooperating-writer lock and an atomic
  replacement. A concurrently changed file is refused before replacement. An
  unrelated external editor does not share this lock; avoid editing the same file
  during installation. Backup files may contain credentials: keep them private.
- Custom AGENT_AUDIO_HOME is persisted in new MCP registrations. Set this variable
  to a new directory to isolate a conflicting runtime; the installer never removes
  a conflicting checkout or recreates an existing virtual environment.
- Existing legacy registrations without Python's `-I` flag are reported as
  conflicts. Review and remove just that old Agent Audio entry before re-registering.

## Runtime and models

The official Stable Audio runtime is pinned to a tested Git commit. Before
installation or inference, its origin, HEAD and tracked files are checked.
An arbitrary folder with a README is never considered an executable runtime.
This is a provenance check, not protection against a malicious local account
that can rewrite Git metadata, dependencies or the server itself.

The opt-in CUDA/ROCm environments are separate from CPU/MLX. GPU model files
use a separate immutable Medium revision and are compared with resolved cache
content without independently pinned checksum references. GPU inference loads
the local checkpoint and bundled encoder with offline mode; it does not invoke
upstream's unpinned model resolver. Backend selection is saved only after the
GPU kernel probe and file readiness checks pass. This is not a generation test.

Model downloads use an immutable Hugging Face revision in Agent Audio's private
cache. TFLite files additionally have pinned SHA-256 checksums. MLX downloads are
revision-pinned and installed files are checked against the resolved cache
content, but do not have independently pinned SHA-256 reference values. The
[user-reported macOS generation test](docs/macos-mlx-validation.md) does not
provide that independent checksum verification. Licenses and gated-model
access remain user responsibilities; no acceptance is automated.
When cache hardlinking fails, models are copied to a private staging file on the
destination volume, verified and published without replacement. Interrupted
copies do not occupy the final model path. The destination filesystem must
support hardlinks; otherwise publication fails safely. An abrupt process kill
may leave a staging file, but a retry does not treat it as an installed model.

All backends use dedicated Python virtual environments and isolated Python
launches. Inherited Python import paths and common virtual-environment selectors
are removed. Generation is offline and never silently downloads new model
revisions. Explicit HF credentials and network proxy settings remain available
to the installation process; no tokens are copied from other model caches.

The upstream Python dependency requirements remain version ranges, so full
runtime dependency reproducibility is not yet guaranteed. The MCP application
itself is locked by uv.lock. Updating either runtime or model pins requires a
fresh installation and generation test; do not bypass conflicts by resetting an
existing user directory.

## Generation

Prompts are passed as arguments to a Python executable, never through a shell.
stdin is disconnected and diagnostic output goes to a private local log file
to protect the MCP JSON-RPC channel and avoid broken host stderr pipes. Logs
are deleted after successful runs; a failed inference retains its log under
`AGENT_AUDIO_HOME/logs` (or `~/.agent-audio/logs`) and reports its path. These
logs may contain prompts, so review them before sharing. Inference is serialized
to protect native caches/memory, with a 540-second process-tree timeout (Codex's
new entry gets 600 seconds).
Unix inference uses a dedicated process group and terminates remaining group
members when the parent completes, fails, times out or is cancelled. Windows
uses a Job Object. These mechanisms do not contain processes that deliberately
escape their group/job; the upstream runtime is trusted code.
Long CPU generations can hit that limit; they fail rather than returning a stale
file. An interrupted application can leave a lock file; check that its recorded
PID has exited before manually removing that lock.

Status checks do not perform inference, rehash model weights or import native
runtime dependencies. File readiness and upstream checkout provenance are
reported separately from those unperformed checks. Nonempty negative prompts
are rejected rather than silently ignored under the current guidance policy.

Outputs must be WAV files. Each run stages and validates a complete WAV before
publishing it with a same-volume hardlink. The destination must not exist, and
the filesystem must support hardlinks. Default names are unique. Neither an
existing file nor a symlink is overwritten; failed renders are cleaned up.

## Reporting

Use the repository's GitHub private vulnerability reporting channel if enabled.
Do not include tokens, personal configuration files or model weights in public
issues. CI checks Python code, model-free tests on Windows/macOS/Linux, the
application dependency lock, and CodeQL. These checks do not establish that
third-party model weights or all native libraries are free of vulnerabilities.
