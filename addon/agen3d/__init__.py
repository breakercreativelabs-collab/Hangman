"""Ekstensi Blender: satu berkas untuk semuanya.
- Pasang & hubungkan: isi paket -> folder kerja, konektor MCP didaftarkan ke Claude Desktop (Python bawaan Blender).
- Mode tonton: Blender yang terbuka menampilkan model yang sedang dibangun agen, langkah demi langkah.
Panel: 3D View > sidebar (N) > tab Agen3D. Lisensi: GPL-3.0-or-later.
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
    folder_kerja: bpy.props.StringProperty(name="Folder kerja", subtype="DIR_PATH", default="",
                                           description="Proyek, hasil render, dan referensi klien. Kosong = Documents/<nama>")
    tonton_otomatis: bpy.props.BoolProperty(name="Tonton otomatis saat Blender dibuka", default=True)

    def draw(self, context):
        self.layout.prop(self, "folder_kerja")
        self.layout.prop(self, "tonton_otomatis")
        self.layout.label(text=f"Folder kerja aktif: {folder_kerja()}")


class AGEN3D_OT_pasang(bpy.types.Operator):
    """Salin paket ke folder kerja dan daftarkan konektor ke Claude Desktop"""
    bl_idname = "agen3d.pasang"
    bl_label = "Pasang & hubungkan ke Claude"
    config: bpy.props.StringProperty(default="", options={"SKIP_SAVE"})  # uji: path config pengganti

    def execute(self, context):
        idn, kerja = identitas(), folder_kerja()
        if os.path.isdir(PAYLOAD):
            r = koneksi.pasang(PAYLOAD, kerja, WHEELS)
            self.report({"INFO"}, f"Terpasang di {kerja} ({r['wheel']} paket Python, {r['proyek_baru']} berkas proyek baru)")
        entri = koneksi.entri_mcp(kerja, bpy.app.binary_path)
        calon = [self.config] if self.config else koneksi.jalur_config_claude()
        ada = [c for c in calon if os.path.isdir(os.path.dirname(c))] or calon[:1]
        try:
            for c in ada:
                koneksi.tulis_config(c, idn["slug"], entri)
        except ValueError as e:  # config Claude rusak: jangan ditimpa
            self.report({"ERROR"}, f"claude_desktop_config.json tidak valid, tidak diubah: {e}")
            return {"CANCELLED"}
        context.window_manager.clipboard = koneksi.perintah_claude_code(idn["slug"], entri)
        self.report({"INFO"}, f"Terhubung ({', '.join(ada)}). Tutup penuh Claude Desktop lalu buka lagi. "
                              "Perintah Claude Code sudah disalin ke clipboard.")
        tonton.mulai(os.path.join(kerja, "artefak", "tonton"))
        return {"FINISHED"}


class AGEN3D_OT_tonton(bpy.types.Operator):
    bl_idname = "agen3d.tonton"
    bl_label = "Tonton"
    nyala: bpy.props.BoolProperty(default=True)

    def execute(self, context):
        if self.nyala:
            tonton.mulai(os.path.join(folder_kerja(), "artefak", "tonton"))
        else:
            tonton.henti()
        return {"FINISHED"}


class AGEN3D_OT_vonis(bpy.types.Operator):
    """Suka / tidak suka hasil terakhir: dikirim sebagai angka (+1/-1) agar agen belajar selera"""
    bl_idname = "agen3d.vonis"
    bl_label = "Vonis"
    nilai: bpy.props.IntProperty(default=1)

    def execute(self, context):
        t = telemetri()
        if t:
            t.catat_vonis(1 if self.nilai > 0 else -1)
        self.report({"INFO"}, "Terima kasih, tercatat" if t and t.aktif() else "Telemetri mati: vonis tidak dikirim")
        return {"FINISHED"}


class AGEN3D_OT_telemetri(bpy.types.Operator):
    """Nyalakan/matikan kiriman angka anonim (tanpa berkas, teks, atau path)"""
    bl_idname = "agen3d.telemetri"
    bl_label = "Telemetri"
    nyala: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        t = telemetri()
        if t:
            t.atur(self.nyala)
        return {"FINISHED"}


class AGEN3D_OT_buka(bpy.types.Operator):
    bl_idname = "agen3d.buka_folder"
    bl_label = "Buka folder kerja"

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=folder_kerja())
        return {"FINISHED"}


class AGEN3D_PT_panel(bpy.types.Panel):
    bl_space_type, bl_region_type, bl_category = "VIEW_3D", "UI", "Agen3D"
    bl_label = "Agen"

    def draw(self, context):
        idn, col = identitas(), self.layout.column()
        col.label(text=f"{idn['nama']} {idn['versi']}")
        if terpasang():
            col.label(text="Terhubung ke Claude", icon="CHECKMARK")
        col.operator("agen3d.pasang", text="Pasang & hubungkan ke Claude" if not terpasang() else "Hubungkan ulang / perbarui")
        col.separator()
        col.label(text=tonton.status(), icon="HIDE_OFF" if tonton._keadaan["aktif"] else "HIDE_ON")
        col.operator("agen3d.tonton", text="Henti tonton" if tonton._keadaan["aktif"] else "Mulai tonton").nyala = \
            not tonton._keadaan["aktif"]
        d = tonton.baca_manifest(tonton._keadaan["folder"]) if tonton._keadaan["folder"] else None
        if d and d.get("selesai"):
            r = col.row(align=True)
            r.operator("agen3d.vonis", text="Suka", icon="SOLO_ON").nilai = 1
            r.operator("agen3d.vonis", text="Kurang", icon="SOLO_OFF").nilai = -1
        col.operator("agen3d.buka_folder", icon="FILE_FOLDER")
        t = telemetri() if terpasang() else None
        if t:
            col.separator()
            nyala = t.aktif()
            col.label(text="Bantu agen belajar: kirim angka anonim" if nyala else "Telemetri mati",
                      icon="CHECKBOX_HLT" if nyala else "CHECKBOX_DEHLT")
            col.operator("agen3d.telemetri", text="Matikan" if nyala else "Nyalakan").nyala = not nyala


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
    for k in KELAS:
        bpy.utils.register_class(k)
    bpy.app.timers.register(_otomatis, first_interval=1.0)


def unregister():
    tonton.henti()
    for k in reversed(KELAS):
        bpy.utils.unregister_class(k)
