"""CLI commands of the tvc module (cli contract: COMMANDS = {name: (function(argv) -> exit code, summary)})."""


def _render(argv):
    from . import production
    return production.main(argv)


def _qc(argv):
    from . import report
    return report.main(argv)


COMMANDS = {
    "render": (_render, "build the TVC scene from tvc.toml, render frames + MP4 (--ratio 9x16|16x9 --quality test|final)"),
    "qc": (_qc, "QC TV-01..08 + 16 negative tests + test animatic + storyboard (--project am1)"),
}
