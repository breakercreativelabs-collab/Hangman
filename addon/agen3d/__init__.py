"""Ekstensi Blender: satu berkas untuk semuanya.
- Pasang & hubungkan: isi paket -> folder kerja, konektor MCP didaftarkan ke Claude Desktop (Python bawaan Blender).
- Mode tonton: Blender yang terbuka menampilkan model yang sedang dibangun agen, langkah demi langkah.
Panel: 3D View > sidebar (N) > tab bernama produk. Lisensi: GPL-3.0-or-later.
"""
import importlib
import os
import sys
import tomllib

import bpy

from . import koneksi, tonton

DIR = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.path.join(DIR, "payload")   # ada di ekstensi hasil alat/rilis.py; tidak ada = mode pengembang (repo)
WHEELS = os.path.join(DIR, "wheels")
REPO = os.path.dirname(os.path.dirname(DIR))


def identitas():
    for akar in (PAYLOAD, REPO):
        p = os.path.join(akar, "identitas.toml")
        if os.path.isfile(p):
            with open(p, "rb") as f:
                return tomllib.load(f)
    return dict(nama="Agen3D", slug="agen3d", versi="?")


def pref():
    return bpy.context.preferences.addons[__package__].preferences


def folder_kerja():
    if not os.path.isdir(PAYLOAD):
        return REPO  # mode pengembang: repo = folder kerja
    return bpy.path.abspath(pref().folder_kerja) or koneksi.folder_kerja_bawaan(identitas()["nama"])


def telemetri():
    """Modul telemetri dari folder kerja (kode agen yang sama dengan konektor); None bila belum terpasang."""
    src = os.path.join(folder_kerja(), "src")
    if not os.path.isdir(os.path.join(src, "agen3d")):
        return None
    if src not in sys.path:
        sys.path.insert(0, src)
    return importlib.import_module("agen3d.telemetri")


def terpasang():
    return os.path.isfile(os.path.join(folder_kerja(), "konektor_mcp.py"))


class Preferensi(bpy.types.AddonPreferences):
    bl_idname = __package__
    folder_kerja: bpy.props.StringProperty(name="Workspace folder", subtype="DIR_PATH", default="",
                                           description="Projects, renders and reference files. Empty = Documents/<name>")
    tonton_otomatis: bpy.props.BoolProperty(name="Start live preview when Blender opens", default=True)

    def draw(self, context):
        self.layout.prop(self, "folder_kerja")
        self.layout.prop(self, "tonton_otomatis")
        self.layout.label(text=f"Active workspace: {folder_kerja()}")


class AGEN3D_OT_pasang(bpy.types.Operator):
    """Copy the package to the workspace and register the connector with Claude Desktop"""
    bl_idname = "agen3d.pasang"
    bl_label = "Install & connect to Claude"
    config: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})  # uji: path config pengganti

    def execute(self, context):
        idn, kerja = identitas(), folder_kerja()
        if os.path.isdir(PAYLOAD):
            r = koneksi.pasang(PAYLOAD, kerja, WHEELS)
            self.report({"INFO"}, f"Installed to {kerja} ({r['wheel']} Python packages, {r['proyek_baru']} new project files)")
        entri = koneksi.entri_mcp(kerja, bpy.app.binary_path)
        calon = [self.config] if self.config else koneksi.jalur_config_claude()
        ada = [c for c in calon if os.path.isdir(os.path.dirname(c))] or calon[:1]
        try:
            for c in ada:
                koneksi.tulis_config(c, idn["slug"], entri)
        except ValueError as e:  # config Claude rusak: jangan ditimpa
            self.report({"ERROR"}, f"claude_desktop_config.json is not valid JSON, left unchanged: {e}")
            return {"CANCELLED"}
        context.window_manager.clipboard = koneksi.perintah_claude_code(idn["slug"], entri)
        self.report({"INFO"}, f"Connected ({', '.join(ada)}). Quit Claude Desktop completely and reopen it. "
                              "The Claude Code command was copied to the clipboard.")
        tonton.mulai(os.path.join(kerja, "artefak", "tonton"))
        return {"FINISHED"}


class AGEN3D_OT_tonton(bpy.types.Operator):
    bl_idname = "agen3d.tonton"
    bl_label = "Live preview"
    nyala: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        if self.nyala:
            tonton.mulai(os.path.join(folder_kerja(), "artefak", "tonton"))
        else:
            tonton.henti()
        return {"FINISHED"}


class AGEN3D_OT_vonis(bpy.types.Operator):
    """Rate the last result (+1/-1). Sent as a number so the agent learns what people like"""
    bl_idname = "agen3d.vonis"
    bl_label = "Rate"
    nilai: bpy.props.IntProperty(default=1)

    def execute(self, context):
        t = telemetri()
        if t:
            t.catat_vonis(1 if self.nilai > 0 else -1)
        self.report({"INFO"}, "Thanks, recorded" if t and t.aktif() else "Telemetry is off: rating not sent")
        return {"FINISHED"}


class AGEN3D_OT_telemetri(bpy.types.Operator):
    """Turn anonymous usage stats on or off (numbers only: no files, text or paths)"""
    bl_idname = "agen3d.telemetri"
    bl_label = "Telemetry"
    nyala: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        t = telemetri()
        if t:
            t.atur(self.nyala)
        return {"FINISHED"}


class AGEN3D_OT_buka(bpy.types.Operator):
    bl_idname = "agen3d.buka_folder"
    bl_label = "Open workspace folder"

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=folder_kerja())
        return {"FINISHED"}


class AGEN3D_PT_panel(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Agen3D"
    bl_label = "Agent"

    def draw(self, context):
        idn, col = identitas(), self.layout.column()
        col.label(text=f"{idn['nama']} {idn['versi']}")
        if terpasang():
            col.label(text="Connected to Claude", icon="CHECKMARK")
        col.operator("agen3d.pasang", text="Install & connect to Claude" if not terpasang() else "Reconnect / update")
        col.separator()
        col.label(text=tonton.status(), icon="HIDE_OFF" if tonton._keadaan["aktif"] else "HIDE_ON")
        col.operator("agen3d.tonton", text="Stop live preview" if tonton._keadaan["aktif"] else "Start live preview").nyala = \
            not tonton._keadaan["aktif"]
        d = tonton.baca_manifest(tonton._keadaan["folder"]) if tonton._keadaan["folder"] else None
        if d and d.get("selesai"):
            r = col.row(align=True)
            r.operator("agen3d.vonis", text="Good", icon="SOLO_ON").nilai = 1
            r.operator("agen3d.vonis", text="Not good", icon="SOLO_OFF").nilai = -1
        col.operator("agen3d.buka_folder", icon="FILE_FOLDER")
        t = telemetri() if terpasang() else None
        if t:
            col.separator()
            nyala = t.aktif()
            col.label(text="Anonymous usage stats: on" if nyala else "Anonymous usage stats: off",
                      icon="CHECKBOX_HLT" if nyala else "CHECKBOX_DEHLT")
            col.operator("agen3d.telemetri", text="Turn off" if nyala else "Turn on").nyala = not nyala


KELAS = (Preferensi, AGEN3D_OT_pasang, AGEN3D_OT_tonton, AGEN3D_OT_vonis, AGEN3D_OT_telemetri, AGEN3D_OT_buka,
         AGEN3D_PT_panel)


def _otomatis():
    try:
        if pref().tonton_otomatis and terpasang():
            tonton.mulai(os.path.join(folder_kerja(), "artefak", "tonton"), hanya_baru=True)
    except (KeyError, AttributeError):
        pass
    return None


def register():
    AGEN3D_PT_panel.bl_category = identitas()["nama"]  # tab sidebar = nama produk (dibaca dari identitas.toml)
    for k in KELAS:
        bpy.utils.register_class(k)
    bpy.app.timers.register(_otomatis, first_interval=1.0)


def unregister():
    tonton.henti()
    for k in reversed(KELAS):
        bpy.utils.unregister_class(k)
