# Rules & QC: MCP connector + single CLI

Skill memory for the connector layer. Every defect is recorded here (defect → fix → numeric check/test → status), then
implemented in code. Tests: the `structure` (f), `cli` (`tests/smoke.py`) and `connector` (`tests/connector.py`, a real
MCP client) suites in the single runner. Every rule has a negative test.

## Rules
| ID | Rule | Check (test) | Negative |
|---|---|---|---|
| K-01 | Server name = `identity.toml` slug (renaming the product = editing one file) | connector K-01 | structure (a) rejects the name in any other file |
| K-02 | Every `help` command = one MCP tool (automatic catalog) + a CLI smoke-test row; the catalog reads the options of every command | connector K-02 (number of CLI tools == catalog > 0; options readable) | cli: a command without a smoke test = fail; the catalog flags commands that don't use io.options |
| K-03 | Only `run_code` requires user permission (`anthropic/requiresUserInteraction`) | connector K-03 | other tools don't carry the marker (the check is not tautological) |
| K-04 | A free-form code error = failed job + traceback (no fake success); `sys.exit(0)` = success | connector K-04 | code `1/0` |
| K-05 | Paths only inside the `output/`, `projects/`, `references/` zones (realpath + normcase); drive-relative paths, `..`, secrets, code and `.git` are rejected with a readable message; `project` = an existing folder; other_options names are validated | connector K-05 (lowercase drive letter accepted) | `..`, `output/../../x`, `github-recovery-codes.txt`, `identity.toml`, temp outside the repo, `C:..`, `D:x`, `project=../am1`, key `x --evil` |
| K-06 | Tool calls never hang: wait ≤ `AGENT3D_WAIT_LIMIT` (default 50 s < Claude Desktop limit ~60 s), then return the job id | connector K-06 | ask for 600 s → returns ≤ limit + 5 s |
| K-07 | Jobs run under a two-stage wrapper (orphaned, broken away from the job object when allowed). Alive = the `hidup.lock` lock, not a PID. The status always ends honestly | connector K-07a (survives `taskkill /T` of its launcher) | K-07b: SDK client session closed → `disconnected` + reason, not "running" forever |
| K-08 | The stdio server never writes to stdout; cwd = repo; `NoDefaultCurrentDirectoryInExePath=1` | all connector tests (the protocol breaks if violated) | — |
| K-09 | A CLI command passes = exit code 0 **and** the promised files exist | cli | command without its promised files |
| K-10 | Responses are capped: HASIL ≤ 8000 characters (full value in result.json), log ≤ 20 lines × 300, text ≤ 60k, images ≤ 700 KB | connector K-10 | HASIL of 500k characters |
| K-12 | A job status is never a fake "disconnected": done.json is re-read after the lock is released; the start grace period also applies while the lock file exists but is not locked yet; the wrapper retries the lock for 2 s | extension KE-06 (the end-to-end test found it: pawn finished with code 0 but status "disconnected") | connector K-12 (deterministic race test: old code -> fake 'disconnected') |
| K-13 | The per-OS extension ships ALL dependencies using the target OS markers (pip evaluates markers against the OS it runs on); packages are loaded with `site.addsitedir` so .pth files run | release KR-08 + negative "without pywin32" | first Windows test: mcp needs pywin32 on Windows -> "Server disconnected" |
| K-11 | The connector (system Python) never imports bpy/mathutils/core/modules, except `execution.py` (runs inside Blender) | structure (f) | synthetic tree where `connector/server.py` imports bpy + core |

## Defect history
| ID | Defect | Fix | Check | Status |
|---|---|---|---|---|
| C-B1 | `reference_modeling build` crashed after saving (`v.data.vertices` on an object without a mesh) | print MESH objects only; code 0 when the .blend is written (`bd1b4c7`) | cli: build | ✅ 2026-10-15 |
| C-B2 | `tvc render --blend 1` failed: the render folder did not exist yet | `os.makedirs` before saving | cli: tvc render | ✅ 2026-10-15 |
| C-B3 | Extraction commands could not be tested without client photos | `reference_modeling test_photo` (synthetic photo, non-generative) | cli: extract_contour round trip ±3 mm | ✅ 2026-10-15 |
| C-K1 | Path rejected but the message was swallowed ("Error executing tool") | every error → `ToolError` | K-05 | ✅ |
| C-K2 | Cancelled job ended with status "unknown" | the wrapper is the only writer of done.json; cancel via the cancel_requested file | cancel test | ✅ |
| C-K3 | Helper names clashed across files (`_write`, `catalog`, `entries`, `key`) | unique names; `core.io.write_json` inside Blender | structure (c) | ✅ |
| C-K4 | The path fence was bypassed by values without a separator (`..`, `C:..`, `D:x`) and the zone was the whole repo (could overwrite secrets/code) | fence per option name + output/projects/client zones + realpath/normcase | K-05 | ✅ (adversarial review) |
| C-K5 | The claim "the job keeps running after the session closes" was untested and wrong for job-object clients | two-stage launch + an honest `disconnected` status; the claim in the docs was corrected | K-07a/b | ✅ (review) |
| C-K6 | Cancel/alive used raw PIDs (PID reuse → could kill another process; tasklist crashed on non-English Windows) | `hidup.lock` file lock | K-07, cancel test | ✅ (review) |
| C-K7 | The connector suite in the runner ignored the exit code and could read a stale connector.json | json deleted first + required item "exit code 0"; a crashing test still writes a FAIL item | runner | ✅ (review) |
| C-K8 | wait_seconds was unbounded; diagnose waited 90 s (cut off by Desktop, job id lost) | `WAIT_LIMIT` in one place; diagnose ≤ 40 s + id | K-06 | ✅ (review) |
| C-K9 | Server start waited for Blender (catalog) up to 120 s | cached catalog (key: Blender path + code mtime), cold start ≤ 25 s | start test | ✅ (review) |
| C-K10 | A job's output summary picked up other jobs' files (open time window, whole-repo scan) | window [start, done], scan the folders the job declares, skip other job folders, summary stored once | — | ✅ (review) |
| C-K11 | Unbounded responses (HASIL, log) exceeded the client's output limit | K-10 | K-10 | ✅ (review) |
| C-K12 | Cancelling a run_code call did not stop its code | CancelledError → cancel the job | — (needs a client that cancels; to be tested manually) | 🟡 |

## Known limits (not defects, recorded honestly)
- A client that puts the server in a KILL_ON_JOB_CLOSE job object without breakaway permission (Python SDK client; Claude
  Desktop unknown) kills the job when the session closes → status `disconnected`. Claude Code closes the server with
  `taskkill /T`: the job survives (K-07a).
- Concurrent jobs writing to the same output folder are not prevented (v0); Claude's instructions forbid re-running a
  command that is still running.
