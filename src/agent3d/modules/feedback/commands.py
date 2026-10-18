"""CLI commands of the feedback module (cli contract: COMMANDS = {name: (function(argv) -> exit code, summary)})."""
import os

from ...core import io, log, qc


def _record(argv):
    from . import feedback
    o = io.options(argv, dict(kind="defect", module="", project="", text="", report="", save=io.artifact("feedback")))
    e = feedback.record(os.path.abspath(o["save"]), o["kind"], o["module"], o["project"], o["text"],
                      os.path.abspath(o["report"]) if o["report"] else "")
    log.info(f"recorded LOCALLY ({e['kind']}, {e['module']}/{e['project']}); not sent anywhere. To send: feedback export --approve 1")
    return 0


def _export(argv):
    from . import feedback
    o = io.options(argv, dict(save=io.artifact("feedback"), approve="0", out=""))
    save = os.path.abspath(o["save"])
    b = feedback.submission(feedback.read_notes(save), o["approve"] == "1")
    check = feedback.audit(b)
    for c in check:
        print(f"  {c['id']} {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['value']} ({c['threshold']})")
    io.write_json(os.path.join(save, "preview_submission.json"), b)
    if not all(c["passed"] for c in check):
        log.info(f"submission NOT created (failed {[c['id'] for c in check if not c['passed']]}); preview: "
                 f"{os.path.join(save, 'preview_submission.json')}")
        return 0 if o["approve"] != "1" else 1
    out = os.path.abspath(o["out"] or os.path.join(save, "submission.json"))
    io.write_json(out, b)
    url = feedback.url_issue()
    log.info(f"submission {len(b['notes'])} notes -> {out}. Attach it to an Issue: {url or '(public repo not set in identity.toml)'}")
    return 0


def _test(argv):
    from . import feedback
    o = io.options(argv, dict(out=io.artifact("test", "feedback")))
    neg = feedback.submission_negative_tests()
    rpt = dict(negative=neg, **qc.summarize([], neg))
    io.write_json(os.path.join(os.path.abspath(o["out"]), "test_feedback.json"), rpt)
    return 0 if rpt["caught_negatives"] == rpt["negative_count"] else 1


def _test_telemetry(argv):
    from . import test_telemetry
    o = io.options(argv, dict(out=io.artifact("test", "telemetry")))
    return test_telemetry.test_all(os.path.abspath(o["out"]))


COMMANDS = {
    "record": (_record, "record a user defect/taste LOCALLY (text + QC numbers from --report), input that makes the agent smarter"),
    "export": (_export, "anonymous submission (paths/emails/references/tokens removed, audit KB-01..06) for a GitHub Issue; requires --approve 1"),
    "test_telemetry": (_test_telemetry, "test automatic telemetry KM-01..08 (allowlist, off switch, send, server down, failure reason) + negative tests"),
    "test": (_test, "negative tests of the feedback submission privacy audit (KB-01..06) + cleaning"),
}
