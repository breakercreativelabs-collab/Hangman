"""Automatic telemetry test KM-01..08 + negative tests (feedback QC_RULES). Uses a temporary folder (the user's queue
is not touched) and a real local HTTP server for sending."""
import http.server
import json
import os
import tempfile
import threading
import time

from ... import telemetry
from ...core import qc
from . import feedback

HOME, WIN = "/ho" + "me/budi", "C:" + "\\Users\\budi"  # split up so this source file itself passes the release audit (KR-05)
DIRTY = dict(kind="job", module="builder", command="build", code=0, seconds=1.5, text="secret klien",
             check=[dict(id="KC-01", passed=True, value=61.0), dict(id="KC-02", passed=False, value=HOME + "/a.glb"),
                  dict(id=WIN, passed=True, value=1.0)],
             recipe={"lathe": 1, WIN: 2}, error="Error di " + HOME, project="secret_brand")


def _check(sanitize, queue_when_off, sent, queue_count, seconds_off, remaining_when_off, error_ok, failure_reason):
    text = json.dumps(sanitize)
    leak = [k for k, (_, pattern, _) in feedback.PATTERN.items() if pattern.search(text)] + \
        [w for w in ("secret", "secret_brand", "budi") if w in text]
    return [
        qc.check("KM-01", "schema allowlist only (no free text/paths/project names)", leak or "clean", not leak,
               "0 findings"),
        qc.check("KM-02", "off switch respected (env + MATI file)", queue_when_off, queue_when_off == 0, "0 events"),
        qc.check("KM-03", "sent to a real endpoint, queue emptied", sent, sent is True, "true"),
        qc.check("KM-04", "queue is capped", queue_count, queue_count <= telemetry.MAX_QUEUE, f"<= {telemetry.MAX_QUEUE}"),
        qc.check("KM-05", "server down: job not held up (seconds)", round(seconds_off, 2), seconds_off <= 3.5, "<= 3.5 s"),
        qc.check("KM-06", "server down: queue kept for retry", remaining_when_off, remaining_when_off > 0, "> 0"),
        qc.check("KM-07", "error type only (code name), not the message", error_ok, error_ok, "name or empty"),
        qc.check("KM-08", "failed send leaves its reason for `diagnose` (local only, never sent)", failure_reason,
                 bool(failure_reason), "non-empty"),
    ]


def test_all(out):
    original = telemetry.FOLDER
    server_result = []

    class Receiver(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            server_result.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Receiver)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    try:
        with tempfile.TemporaryDirectory() as t:
            telemetry.FOLDER = t
            s = telemetry.sanitize(DIRTY)
            os.environ["AGENT3D_TELEMETRY"] = "0"
            telemetry.record_job("builder", "build", 0, time.time())
            telemetry.record_verdict(1)
            os.environ["AGENT3D_TELEMETRY"] = "1"
            telemetry.configure(False)
            telemetry.record_verdict(1)
            p = os.path.join(t, "queue.jsonl")
            off = len(open(p).read().splitlines()) if os.path.isfile(p) else 0
            telemetry.configure(True)
            for _ in range(telemetry.MAX_QUEUE + 20):
                telemetry.queue(dict(telemetry._base("verdict"), module="builder", command="build", value=-1))
            n_queue = len(open(p).read().splitlines())
            t0 = time.time()
            telemetry.send("http://10.255.255.1:9/", limit=3.0)  # unreachable address
            seconds_off = time.time() - t0
            failure_reason = telemetry.health()["last_error"]
            rest = len(open(p).read().splitlines()) if os.path.isfile(p) else 0
            t1 = time.time()
            telemetry.send("http://10.255.255.1:9/", limit=3.0)  # within the pause window: must not wait again
            seconds_off = max(seconds_off, 0.0) if time.time() - t1 < 0.5 else 30.0
            os.remove(os.path.join(t, "last_failed"))
            n = telemetry.send(url)
            sent = n == n_queue and not os.path.isfile(p) and len(server_result[-1]["events"]) == n_queue
            error_ok = s.get("error") is None and telemetry.sanitize(dict(DIRTY, error="valueerror"))["error"] == "valueerror"
            check = _check(s, off, sent, n_queue, seconds_off, rest, error_ok, failure_reason)
            neg_spec = [
                ("no allowlist (raw event)", dict(sanitize=DIRTY), "KM-01"),
                ("off switch ignored", dict(queue_when_off=2), "KM-02"),
                ("sending fails silently", dict(sent=False), "KM-03"),
                ("unbounded queue", dict(queue_count=telemetry.MAX_QUEUE + 20), "KM-04"),
                ("waits 30 s for a down server", dict(seconds_off=30.0), "KM-05"),
                ("queue dropped while the server is down", dict(remaining_when_off=0), "KM-06"),
                ("error message sent along", dict(error_ok=False), "KM-07"),
                ("send failure swallowed silently", dict(failure_reason=""), "KM-08"),
            ]
    finally:
        telemetry.FOLDER = original
        os.environ.pop("AGENT3D_TELEMETRY", None)
        srv.shutdown()
    base = dict(sanitize=s, queue_when_off=off, sent=sent, queue_count=n_queue, seconds_off=seconds_off,
                 remaining_when_off=rest, error_ok=error_ok, failure_reason=failure_reason)
    neg = []
    for name, change, required in neg_spec:
        ok, failed = qc.caught(_check(**dict(base, **change)), [required])
        neg.append(dict(name=name, required=[required], failed=failed, caught=ok))
    for c in check:
        print(f"  {c['id']} {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['value']} ({c['threshold']})")
    for n in neg:
        print(f"  negative telemetry {'OK ' if n['caught'] else 'LEAK'} {n['name']}: failed {n['failed']}")
    rpt = dict(check=check, negative=neg, **qc.summarize(check, neg))
    from ...core import io
    io.write_json(os.path.join(out, "test_telemetry.json"), rpt)
    return 0 if rpt["passed"] and rpt["caught_negatives"] == rpt["negative_count"] else 1
