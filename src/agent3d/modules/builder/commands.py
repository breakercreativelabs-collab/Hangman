"""CLI commands of the builder module (cli contract: COMMANDS = {name: (function(argv) -> exit code, summary)})."""
import os

from ...core import io


def _build(argv):
    from . import builder
    o = io.options(argv, dict(design=io.project("chess_pawn", "design.toml"), out="", render="1", sample="32",
                                   mode="full", live=os.environ.get("AGENT3D_LIVE") or os.environ.get("AGENT3D_TONTON", "0")))  # Blender extension: 1
    name = os.path.basename(os.path.dirname(os.path.abspath(o["design"])))
    out = os.path.abspath(o["out"] or io.artifact("builder", name))
    live = {"0": "", "1": io.artifact("live", name)}.get(o["live"], o["live"])  # 1 = output/live/<project>
    return builder.assemble(os.path.abspath(o["design"]), out, o["render"] == "1", int(o["sample"]), o["mode"],
                         os.path.abspath(live) if live else "")


def _set(argv):
    from . import set as set_
    o = io.options(argv, dict(set=io.project("chess_set", "set.toml"), out="", render="1", sample="24"))
    out = os.path.abspath(o["out"] or io.artifact("builder", "chess_set"))
    return set_.arrange(os.path.abspath(o["set"]), out, o["render"] == "1", int(o["sample"]))


def _test_live(argv):
    from . import test_live
    o = io.options(argv, dict(out=io.artifact("test", "live")))
    return test_live.run(os.path.abspath(o["out"]))


COMMANDS = {
    "build": (_build, "shape design (TOML from a prompt) -> SDF -> mesh + KC QC + negative tests + contact sheet (--mode preview: fast)"),
    "test_live": (_test_live, "test live mode without a GUI: step recorder + add-on loader (KT-01..05 + negative tests)"),
    "set": (_set, "piece set (set.toml) on a board in the starting position: set QC KS-01..06 + negative tests + sheet_set (builds pieces when needed)"),
}
