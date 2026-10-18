"""connector: MCP server that exposes agent3d to the Claude apps (Desktop / Code).

Runs on the SYSTEM Python (needs the `mcp` package, which Blender's Python lacks) and does NOT import bpy or modules/.
All Blender work goes through a new Blender process (single CLI `blender_cli.py`), just like the test runner:
  blender.py    find Blender + command catalog (`help --json`, one MCP tool per CLI command)
  job.py        background jobs: start, status, cancel, output summary (QC JSON, contact sheet)
  execution.py  runs INSIDE Blender: free-form Python code (tool `run_code`) + diagnose
  server.py     list of MCP tools + instructions for Claude
Launcher: `mcp_connector.py` at the repo root. The product name comes from identity.toml (not written here).
"""
