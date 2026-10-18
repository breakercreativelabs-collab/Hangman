"""CLI commands of the product_shot module (cli contract: COMMANDS = {name: (function(argv) -> exit code, summary)})."""


def _run(argv):
    from . import run
    return run.main(argv)


def _curriculum(argv):
    from . import curriculum
    return curriculum.main(argv)


def _test(argv):
    from . import test
    return test.main(argv)


COMMANDS = {
    "run": (_run, "test/client product -> variant renders + QC-01..12 + contact sheet (--product bottle,can)"),
    "curriculum": (_curriculum, "all test products x 3 presets x palette -> REPORT.md + report.json"),
    "test": (_test, "verb tests + negative QC tests (88 tests) -> test_verbs.json"),
}
