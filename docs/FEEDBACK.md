# Feedback and usage stats

## Automatic usage stats (on by default)

After each job the agent sends anonymous numbers: version, OS, Blender version, command name, duration, check
results (check ID, pass/fail, numeric value), the error type if it crashed, and the Good / Not good rating from the
panel. A random install ID (not linked to you) is used to spot a single install flooding the data.

Never sent: file or project names, paths, prompts, images, meshes, free text. The server does not store IP addresses.
Events are filtered against a whitelist on your machine and again on the server.

Turn it off with **Turn off** in the panel, by setting `AGENT3D_TELEMETRY=0`, or by creating an empty file
`output/telemetry/MATI` in your workspace. Jobs never wait more than about 3 seconds on the stats server; if it is
unreachable, events are queued (max 500) and retried later.

## What happens with the data

Once a day the stats are analysed. Only signals coming from at least three different installs count, and installs
that look like spam are dropped. One problem is picked, reproduced, fixed, and released only if the full test suite
passes and a fixed benchmark shows nothing got slower or worse. Thresholds are never loosened to make a check pass.

## Written feedback

Open an issue with the feedback template. If you like, attach an anonymised export:

```
feedback record --kind defect --module builder --project <name> --text "what went wrong"
feedback export --approve 1        (writes submission.json, stripped of paths, emails, usernames, client files, tokens)
```

Without `--approve 1` only a preview is written.
