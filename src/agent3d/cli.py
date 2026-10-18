"""Single CLI entry point for all modules:

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- <module> <command> [--options value ...]
  blender -b --factory-startup -P blender_cli.py -- help        (list modules + commands)

Module contract: agent3d/modules/<module>/commands.py defines COMMANDS = {name: (function(argv) -> exit code, summary)}.
"""
import importlib
import sys

from . import identity
from .core import log

MODULE = ("product_shot", "reference_modeling", "tvc", "procedural", "builder", "feedback")


def module_command(name):
    return importlib.import_module(f"agent3d.modules.{name}.commands").COMMANDS


def help_text():
    print(f"{identity.title()}: {identity.description()}")
    print("Usage: blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- <module> <command> [--options value]")
    for m in MODULE:
        for p, (_, summarize) in module_command(m).items():
            print(f"  {m} {p:<16} {summarize}")


class _CaughtOptions(Exception):
    def __init__(self, defaults):
        super().__init__("options")
        self.defaults = defaults


def catalog():
    """[{module, command, summary, options}] without running the commands: `io.options` is intercepted, so each command
    function stops right where it reads its options. options = {name: default value} (None if the command does not use
    io.options). Used by the MCP connector to build one tool per command, complete with its parameters."""
    from .core import io
    original = io.options

    def intercept(argv, defaults):
        raise _CaughtOptions({k: str(v) for k, v in defaults.items()})

    result = []
    io.options = intercept
    try:
        for m in MODULE:
            for p, (function, summarize) in module_command(m).items():
                error = None
                try:
                    function([])
                    options, error = None, "command ran without reading options via io.options (breaks the contract)"
                except _CaughtOptions as e:
                    options = e.defaults
                except (Exception, SystemExit) as e:  # noqa: BLE001 - command failed before reading its options
                    options, error = None, f"{type(e).__name__}: {e}"[:300]
                result.append(dict(module=m, command=p, summary=summarize, options=options, error=error))
    finally:
        io.options = original
    return result


def main(argv=None):
    a = argv if argv is not None else (sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if a and a[0] in ("__run_code__", "__diagnose__"):  # MCP connector meta commands (not listed in help)
        from .connector import execution
        return int(getattr(execution, a[0].strip("_"))(a[1:]) or 0)
    if a[:2] in (["help", "--json"], ["help_text", "--json"]) and len(a) == 3:  # machine-readable catalog (MCP connector), written to a file
        import json
        with open(a[2], "w", encoding="utf-8", newline="\n") as f:
            json.dump(dict(title=identity.title(), description=identity.description(), command=catalog()), f,
                      ensure_ascii=False, indent=1)
        return 0
    if not a or a[0] in ("help", "help_text", "-h", "--help"):
        help_text()
        return 0
    if a[0] == "--version":
        print(identity.title())
        return 0
    if a[0] not in MODULE or len(a) < 2:
        print(f"unknown module or missing command: {a[:2]}; modules: {', '.join(MODULE)}")
        return 2
    entries = module_command(a[0])
    if a[1] not in entries:
        print(f"command '{a[1]}' does not exist in {a[0]}; available: {', '.join(entries)}")
        return 2
    log.banner(a[0], a[1])
    import time
    from . import telemetry
    t0 = time.time()
    try:
        code = int(entries[a[1]][0](a[2:]) or 0)
    except BaseException as e:  # the error is still raised; telemetry records only its TYPE (no message/path)
        telemetry.record_job(a[0], a[1], 1, t0, type(e).__name__.lower())
        raise
    telemetry.record_job(a[0], a[1], code, t0)
    return code
