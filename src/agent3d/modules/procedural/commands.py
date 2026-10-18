"""CLI commands of the procedural module (cli contract: COMMANDS = {name: (function(argv) -> exit code, summary)})."""
import os

from ...core import io


def _tree(argv):
    from . import tree
    o = io.options(argv, dict(out=io.artifact("procedural"), render="1", sample="128"))
    tree.example_scene(os.path.abspath(o["out"]), o["render"] == "1", int(o["sample"]))
    return 0


def _match(argv):
    from . import match
    match.match(os.path.abspath(io.options(argv, dict(out=io.artifact("procedural", "matches")))["out"]))
    return 0


def _test(argv):
    from . import test
    return test.main(argv)


COMMANDS = {
    "tree": (_tree, "3 example trees (fixed preset + seed) -> render + .blend (--render 0 to skip rendering)"),
    "match": (_match, "mimic a reference tree silhouette (parameter optimization with IoU)"),
    "test": (_test, "QC-001/002/005/006 + baseline regression + QC-001 negative test"),
}
