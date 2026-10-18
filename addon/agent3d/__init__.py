"""Blender extension: one entry point for everything.
- Install & connect: package contents -> workspace folder, MCP connector registered with Claude Desktop (Blender's bundled Python).
- Live mode: the open Blender shows the model the agent is building, step by step.
Panel: 3D View > sidebar (N) > tab named after the product. License: GPL-3.0-or-later.
"""
import importlib
import os
import sys
import tomllib

import bpy

from . import connect, live

DIR = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(DIR, "payload")   # present in the extension built by tools/release.py; absent = developer mode (repo)
WHEELS = os.path.join(DIR, "wheels")
REPO = os.path.dirname(os.path.dirname(DIR))


def identity():
    for root in (PAYLOAD, REPO):
        p = os.path.join(root, "identity.toml")
        if os.path.isfile(p):
            with open(p, "rb") as f:
                return tomllib.load(f)
    return dict(name="Agen3D", slug="agent3d", version="?")


def pref():
    return bpy.context.preferences.addons[__package__].preferences


def workspace_folder():
    if not os.path.isdir(PAYLOAD):
        return REPO  # developer mode: the repo is the workspace
    return bpy.path.abspath(pref().workspace_folder) or connect.default_workspace_folder(identity()["name"])


def telemetry():
    """Telemetry module from the workspace (same agent code the connector uses); None if not installed yet."""
    src = os.path.join(workspace_folder(), "src")
    if not os.path.isdir(os.path.join(src, "agent3d")):
        return None
    if src not in sys.path:
        sys.path.insert(0, src)
    return importlib.import_module("agent3d.telemetry")


def installed():
    return os.path.isfile(os.path.join(workspace_folder(), "mcp_connector.py"))


class Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    workspace_folder: bpy.props.StringProperty(name="Workspace folder", subtype="DIR_PATH", default="",
                                           description="Projects, renders and reference files. Empty = Documents/<name>")
    auto_live: bpy.props.BoolProperty(name="Start live preview when Blender opens", default=True)

    def draw(self, context):
        self.layout.prop(self, "workspace_folder")
        self.layout.prop(self, "auto_live")
        self.layout.label(text=f"Active workspace: {workspace_folder()}")


class AGENT3D_OT_install(bpy.types.Operator):
    """Copy the package to the workspace and register the connector with Claude Desktop"""
    bl_idname = "agent3d.install"
    bl_label = "Install & connect to Claude"
    config: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})  # tests: substitute config path

    def execute(self, context):
        ident_info, work = identity(), workspace_folder()
        if os.path.isdir(PAYLOAD):
            r = connect.install(PAYLOAD, work, WHEELS)
            self.report({"INFO"}, f"Installed to {work} ({r['wheel']} Python packages, {r['new_project']} new project files)")
        entry = connect.mcp_entry(work, bpy.app.binary_path)
        candidate = [self.config] if self.config else connect.claude_config_path()
        # Windows: write to %APPDATA%\Claude AND the Microsoft Store location if present (first Windows test 2026-10-17:
        # only the Store location was written because %APPDATA%\Claude did not exist yet, and Claude didn't load the server)
        exists = candidate if not self.config else candidate[:1]
        try:
            for c in exists:
                connect.write_config(c, ident_info["slug"], entry)
        except ValueError as e:  # corrupt Claude config: don't overwrite it
            self.report({"ERROR"}, f"claude_desktop_config.json is not valid JSON, left unchanged: {e}")
            return {"CANCELLED"}
        context.window_manager.clipboard = connect.claude_code_command(ident_info["slug"], entry)
        self.report({"INFO"}, f"Connected ({', '.join(exists)}). Quit Claude Desktop completely and reopen it. "
                              "The Claude Code command was copied to the clipboard.")
        live.start(os.path.join(work, "output", "live"))
        return {"FINISHED"}


class AGENT3D_OT_live(bpy.types.Operator):
    bl_idname = "agent3d.live"
    bl_label = "Live preview"
    enable: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        if self.enable:
            live.start(os.path.join(workspace_folder(), "output", "live"))
        else:
            live.stop()
        return {"FINISHED"}


class AGENT3D_OT_verdict(bpy.types.Operator):
    """Rate the last result (+1/-1). Sent as a number so the agent learns what people like"""
    bl_idname = "agent3d.verdict"
    bl_label = "Rate"
    value: bpy.props.IntProperty(default=1)

    def execute(self, context):
        t = telemetry()
        if t:
            t.record_verdict(1 if self.value > 0 else -1)
        self.report({"INFO"}, "Thanks, recorded" if t and t.active() else "Telemetry is off: rating not sent")
        return {"FINISHED"}


class AGENT3D_OT_telemetry(bpy.types.Operator):
    """Turn anonymous usage stats on or off (numbers only: no files, text or paths)"""
    bl_idname = "agent3d.telemetry"
    bl_label = "Telemetry"
    enable: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        t = telemetry()
        if t:
            t.configure(self.enable)
        return {"FINISHED"}


class AGENT3D_OT_open(bpy.types.Operator):
    bl_idname = "agent3d.buka_folder"
    bl_label = "Open workspace folder"

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=workspace_folder())
        return {"FINISHED"}


class AGENT3D_PT_panel(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Agen3D"
    bl_label = "Agent"

    def draw(self, context):
        ident_info, col = identity(), self.layout.column()
        col.label(text=f"{ident_info['name']} {ident_info['version']}")
        if installed():
            col.label(text="Connected to Claude", icon="CHECKMARK")
        col.operator("agent3d.install", text="Install & connect to Claude" if not installed() else "Reconnect / update")
        col.separator()
        col.label(text=live.status(), icon="HIDE_OFF" if live._state["active"] else "HIDE_ON")
        col.operator("agent3d.live", text="Stop live preview" if live._state["active"] else "Start live preview").enable = \
            not live._state["active"]
        d = live.read_manifest(live._state["folder"]) if live._state["folder"] else None
        if d and d.get("done"):
            r = col.row(align=True)
            r.operator("agent3d.verdict", text="Good", icon="SOLO_ON").value = 1
            r.operator("agent3d.verdict", text="Not good", icon="SOLO_OFF").value = -1
        col.operator("agent3d.buka_folder", icon="FILE_FOLDER")
        t = telemetry() if installed() else None
        if t:
            col.separator()
            enable = t.active()
            col.label(text="Anonymous usage stats: on" if enable else "Anonymous usage stats: off",
                      icon="CHECKBOX_HLT" if enable else "CHECKBOX_DEHLT")
            col.operator("agent3d.telemetry", text="Turn off" if enable else "Turn on").enable = not enable


CLASS = (Preferences, AGENT3D_OT_install, AGENT3D_OT_live, AGENT3D_OT_verdict, AGENT3D_OT_telemetry, AGENT3D_OT_open,
         AGENT3D_PT_panel)


def _auto():
    try:
        if pref().auto_live and installed():
            live.start(os.path.join(workspace_folder(), "output", "live"), new_only=True)
    except (KeyError, AttributeError):
        pass
    return None


def register():
    AGENT3D_PT_panel.bl_category = identity()["name"]  # sidebar tab = product name (read from identity.toml)
    for k in CLASS:
        bpy.utils.register_class(k)
    bpy.app.timers.register(_auto, first_interval=1.0)


def unregister():
    live.stop()
    for k in reversed(CLASS):
        bpy.utils.unregister_class(k)
