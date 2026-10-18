"""MCP connector launcher (outside src/; SYSTEM Python/venv with the `mcp` package, not Blender's Python):

  .venv/Scripts/python mcp_connector.py             stdio MCP server (started by the Claude app, don't run it by hand)
  .venv/Scripts/python mcp_connector.py --config    print the Claude Desktop config + the `claude mcp add` command

Like blender_cli.py, this launcher adds src/ to sys.path (forbidden inside src/, structure test b).
Installation guide: docs/CONNECTOR.md.
"""
import json
import os
import sys

if sys.version_info < (3, 11):  # tomllib (identity.toml)
    sys.exit("the connector needs Python 3.11+")
ROOT = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")  # Windows: don't run programs from cwd
os.chdir(ROOT)  # cwd = repo (the client may start the server from another project folder)
sys.path.insert(0, os.path.join(ROOT, "src"))
if os.path.isdir(os.path.join(ROOT, "lib")):  # Python packages (mcp, ...) unpacked by the Blender extension: Blender's bundled Python is enough
    import site
    sys.path.insert(0, os.path.join(ROOT, "lib"))
    site.addsitedir(os.path.join(ROOT, "lib"))  # process .pth files (pywin32 on Windows loads its DLLs via .pth)
from agent3d import identity  # noqa: E402


def config():
    script = os.path.join(ROOT, "mcp_connector.py")
    desktop = {"mcpServers": {identity.slug(): {"command": sys.executable, "args": [script],
                                                 "env": {"PYTHONUTF8": "1"}}}}
    print("Claude Desktop (merge into claude_desktop_config.json, then quit Claude completely and reopen it):")
    print(json.dumps(desktop, indent=2))
    print("\nClaude Code (once, works for every folder):")
    print(f'claude mcp add --scope user {identity.slug()} -e PYTHONUTF8=1 -- "{sys.executable}" "{script}"')


if __name__ == "__main__":
    if "--config" in sys.argv:
        config()
    else:
        from agent3d.connector.server import main
        main()
