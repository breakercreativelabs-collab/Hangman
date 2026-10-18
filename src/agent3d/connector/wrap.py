"""Job wrapper (stdlib only, system Python `-I`), two stages so the job detaches from the MCP server's process tree:

  python -I wrap.py --detach <folder>   stage 1 (launcher): start stage 2 detached (new process group, no console,
                                          breakaway from the job object if allowed), record wrapper.json, then exit
                                          (the child is orphaned: the client's `taskkill /T` does not reach it)
  python -I wrap.py --run_job <folder>   stage 2 (wrapper): hold the hidup.lock lock, run argv.json, watch for the
                                          cancel_requested file, write done.json (atomically) at the end

Alive = hidup.lock is locked (not a PID: PIDs can be reused by other processes, review finding). Cancel = the
cancel_requested file; only the wrapper stops its own child and writes done.json (single writer).
Known limit: a client that puts the server in a KILL_ON_JOB_CLOSE job object without breakaway permission (e.g. the
Python SDK client) still kills the job when the session closes; the status is then recorded as `disconnected` (see job.status).
"""
import json
import os
import subprocess
import sys
import time

WINDOWS = sys.platform == "win32"


def lock_file(f):
    """Non-blocking exclusive lock on an open file; True on success."""
    try:
        if WINDOWS:
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def unlock_file(f):
    if WINDOWS:
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def still_alive(folder):
    """True = the wrapper holds the lock; False = it doesn't (dead/done); None = the lock file was never created."""
    p = os.path.join(folder, "hidup.lock")
    if not os.path.isfile(p):
        return None
    with open(p, "a+") as f:
        if lock_file(f):
            unlock_file(f)
            return False
        return True


def write_atomic(path, data):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def detach(folder):
    argv = [sys.executable, "-I", os.path.abspath(__file__), "--run_job", folder]
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
              cwd=folder)
    detach_job = True
    if WINDOWS:
        base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            p = subprocess.Popen(argv, creationflags=base | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
        except OSError:  # the client's job object does not allow breakaway
            p = subprocess.Popen(argv, creationflags=base, **kw)
            detach_job = False
    else:
        p = subprocess.Popen(argv, start_new_session=True, **kw)
    write_atomic(os.path.join(folder, "wrapper.json"), dict(pid=p.pid, detach_from_job_object=detach_job))
    return 0


def terminate(p):
    """Stop the wrapper's child (Blender) and its descendants, via its own handle (not a PID from a file)."""
    if WINDOWS:
        tk = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")
        subprocess.run([tk, "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill()


def run_job(folder):
    with open(os.path.join(folder, "argv.json"), encoding="utf-8") as f:
        req = json.load(f)
    code, was_cancelled = None, False
    with open(os.path.join(folder, "hidup.lock"), "a+") as kf:
        for _ in range(20):  # K-12: the status checker may hold the lock briefly; retry before giving up
            if lock_file(kf):
                break
            time.sleep(0.1)
        else:
            return 3  # this job is already held by another wrapper
        try:
            with open(os.path.join(folder, "log.txt"), "a", encoding="utf-8", errors="replace") as log:
                try:
                    p = subprocess.Popen(req["argv"], cwd=req["cwd"], stdout=log, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL)
                except OSError as e:
                    log.write(f"FAILED TO START: {e}\n")
                    code = 127
                else:
                    while p.poll() is None:
                        if not was_cancelled and os.path.exists(os.path.join(folder, "cancel_requested")):
                            was_cancelled = True
                            terminate(p)
                        time.sleep(0.5)
                    code = p.returncode
        finally:
            write_atomic(os.path.join(folder, "done.json"), dict(code=code, done=time.time(), cancelled=was_cancelled))
    return 0


if __name__ == "__main__":
    mode, folder = sys.argv[1], os.path.abspath(sys.argv[2])
    sys.exit(detach(folder) if mode == "--detach" else run_job(folder))
