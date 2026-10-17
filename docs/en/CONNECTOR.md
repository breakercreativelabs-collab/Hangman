# MCP connector

The connector lets Claude Desktop, Claude Code and other MCP clients drive Blender. You talk to Claude, Claude calls
the connector's tools, and the connector runs Blender in the background on your machine.

```
You -> Claude -> MCP connector (konektor_mcp.py) -> Blender, headless (blender_cli.py)
```

## Easiest setup

Install the Blender extension zip from the releases page, open the sidebar tab in the 3D viewport and click
**Install & connect to Claude**. It copies the package to your workspace folder, unpacks the bundled Python packages
and adds the connector to `claude_desktop_config.json` (other servers in that file are kept and a `.bak` backup is
written first; an invalid config file is left untouched). The connector runs on Blender's own Python.

The same click copies a `claude mcp add ...` command to your clipboard for Claude Code.

## Tools

| Tool | What it does |
|---|---|
| `<module>__<command>` | One tool per CLI command, generated from the command catalog. New commands show up after restarting Claude. |
| `jalankan_kode` | Runs free-form Blender Python for things no command covers yet. Asks for your permission on every call. The code is saved in the job folder. |
| `status_pekerjaan`, `batalkan_pekerjaan`, `daftar_pekerjaan` | Long renders run as background jobs; these check, cancel and list them. |
| `diagnosa` | Blender version, GPU, Python, disk space. |
| `lihat_gambar` | Shows a contact sheet or preview in the chat. |
| `panduan` | How the agent works and which commands exist. |

File paths are limited to `artefak/` (renders, binaries), `proyek/` (project data) and `klien/` (your reference
files) inside the workspace.

## Manual setup (developers)

```
python -m venv .venv
.venv/bin/python -m pip install "mcp>=2,<3"      (Windows: .venv\Scripts\python ...)
.venv/bin/python konektor_mcp.py --config
```

The last command prints the JSON block for Claude Desktop and the `claude mcp add` command for Claude Code.

## Troubleshooting

- Not listed in Claude: quit Claude Desktop completely (tray icon > Quit) and start it again.
- Check **Settings > Developer** in Claude Desktop: the server should be listed and running. If it failed, the log
  is at `%APPDATA%\Claude\logs\mcp-server-<name>.log` (Windows) or `~/Library/Logs/Claude/` (macOS).
- Microsoft Store builds of Claude read the config from
  `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\`. The installer writes there too if that folder exists.
