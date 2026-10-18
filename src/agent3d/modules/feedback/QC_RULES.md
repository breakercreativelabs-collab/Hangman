# QC_RULES for the feedback module (user submissions)

Submissions = material that makes the agent smarter, from many users. Principle: **nothing is sent automatically**;
without `--approve 1` there is only a preview. A submission is cleaned (`cleanup`) and then audited; a failed audit =
no submission is created.

| ID | Check | Threshold | Why |
|---|---|---|---|
| KB-01 | No absolute paths (Windows `C:\...`, `/home`, `/Users`, ...) | 0 findings | paths contain user names & client job names |
| KB-02 | No email addresses | 0 | personal data |
| KB-03 | No `references/...` | 0 | client file names can leak a brand or a confidential project |
| KB-04 | No tokens/keys (`ghp_`, `sk-ant-`, `AKIA`, PEM keys, ...) | 0 | secrets |
| KB-05 | Explicit approval (`--approve 1`) | true | data leaves only with the user's permission |
| KB-06 | Submission size | <= 200 KB | the Issue stays readable; not a place for big files |

Cleaning also replaces the OS user name (USER/USERNAME) with `<user>`.
Negative tests (`feedback test`): 6 dirty submissions without cleaning MUST fail their own checks; a dirty submission
after cleaning MUST pass and the user name in paths must be gone.

Known gap (do not promise otherwise): free text may still contain a brand/client name typed by a person; the regexes
cannot recognize that. That is why the user must read the preview before sending (the Issue template reminds them).

## Automatic telemetry (user decision 2026-10-17: on by default without asking; announced + off switch)
`src/agent3d/telemetry.py` (client) + `services/telemetry/worker.js` (server, developer repo only). Tests: `feedback test_telemetry`
(KM) and `node services/telemetry/test.mjs` (KS-T).

| ID | Check | Threshold | Why |
|---|---|---|---|
| KM-01 | Events contain only the schema allowlist (check IDs, numbers, code names) | 0 free text/paths/project names | privacy without asking is only acceptable if the data really is anonymous |
| KM-02 | Off switch respected (env AGENT3D_TELEMETRY=0 or the old AGENT3D_TELEMETRI=0, `MATI` file, panel button) | 0 events | the user must be able to stop it with one click |
| KM-03 | Sent to a real endpoint, queue emptied | true | |
| KM-04 | Queue is capped | <= 500 | an offline user's disk does not fill up |
| KM-05 | A down server does not hold up the job | <= 3.5 s, then a 10 minute pause | telemetry must never slow down work |
| KM-06 | Server down: queue is kept | > 0 | |
| KM-07 | Errors carry only their type | code name | error messages can contain paths |
| KM-08 | A failed send keeps its reason locally (`last_failed`), shown by `diagnose` | non-empty | the 0.2.6 install on Windows never reached the server and the cause was invisible (2026-10-17) |
| KS-T01..06 | Server: accepts valid events; text/paths are not stored; no IP column; flood limit 2000/installation/day; summary only with a token; broken JSON handled safely | pass | poisoning & privacy on the server side |
Poisoning in analysis: installations with > 30% of events or >= 50 identical verdicts are excluded; a signal needs >= 3 installations.
