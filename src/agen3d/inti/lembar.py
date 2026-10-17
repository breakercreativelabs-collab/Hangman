"""Contact sheet (numpy + bpy.data.images, tanpa PIL agar jalan identik di laptop dan cloud).
Setiap sel diberi label teks dan bilah status QC (hijau = lulus, merah = gagal). Format dari ekstensi path:
.jpg (kualitas 85, untuk repo: kecil) atau .png."""
import numpy as np

from .io import baca_png, simpan_gambar, ubah_ukuran

# Font bitmap 5x7: karakter + 7 baris (tiap baris 5 bit, basis 32)
_FONT = ("AEHHVHHH BUHHUHHU CEHGGGHE DUHHHHHU EVGGUGGV FVGGUGGG GEHGNHHF HHHHVHHH IE44444E J72222IC KHIKOKIH "
         "LGGGGGGV MHRLLHHH NHHPLJHH OEHHHHHE PUHHUGGG QEHHHLID RUHHUKIH SFGGE11U TV444444 UHHHHHHE VHHHHHA4 "
         "WHHHLLLA XHHA4AHH YHHHA444 ZV1248GV 0EHJLPHE 14C4444E 2EH1248V 3V2421HE 426AIV22 5VGU11HE 668GUHHE "
         "7V124888 8EHHEHHE 9EHHF12C :0CC0CC0 .00000CC -000V000 %OP248J3 #AAVAVAA /01248G0 =00V0V00 _000000V")
GLIF = {g[0]: np.array([[(int(c, 32) >> (4 - b)) & 1 for b in range(5)] for c in g[1:]], bool) for g in _FONT.split()}
HIJAU, MERAH, LATAR, TEKS = (0.20, 0.70, 0.30), (0.85, 0.15, 0.15), (0.10, 0.10, 0.10), (0.92, 0.92, 0.92)


def tulis(kanvas, teks, x, y_atas, skala=2, warna=TEKS):
    """Tulis teks (huruf besar) di kanvas (baris 0 = atas)."""
    for i, ch in enumerate(teks.upper()):
        g = GLIF.get(ch)
        if g is None:
            continue
        blok = np.kron(g, np.ones((skala, skala), bool))
        x0 = x + i * 6 * skala
        sub = kanvas[y_atas:y_atas + blok.shape[0], x0:x0 + blok.shape[1]]
        sub[blok[:sub.shape[0], :sub.shape[1]]] = warna


def bungkus(teks, n):
    """Pecah teks per kata menjadi baris <= n karakter."""
    baris = [""]
    for kata in teks.split():
        if baris[-1] and len(baris[-1]) + 1 + len(kata) > n:
            baris.append("")
        baris[-1] = (baris[-1] + " " + kata).strip()
    return baris


def buat(baris, path, judul, tinggi_sel=300, celah=12):
    """baris: list of (judul_baris, [ (path_png, label, lulus) ... ]). Menulis contact sheet, kembalikan (path, (W, H))."""
    kepala, tinggi_label = 40, 40
    sel = [[(np.flipud(baca_png(p)), lab, ok) for p, lab, ok in isi] for _, isi in baris]
    sel = [[(ubah_ukuran(im, tinggi_sel), lab, ok) for im, lab, ok in b] for b in sel]
    lebar_baris = [sum(im.shape[1] + celah for im, _, _ in b) + celah for b in sel]
    W = max(lebar_baris + [len(judul) * 18 + 2 * celah])
    tinggi_b = tinggi_sel + tinggi_label + 22 + celah
    H = kepala + len(sel) * tinggi_b + celah
    kan = np.empty((H, W, 3), "f")
    kan[:] = LATAR
    tulis(kan, judul, celah, 10, 3)
    for r, ((jb, _), b) in enumerate(zip(baris, sel)):
        y = kepala + r * tinggi_b
        tulis(kan, jb, celah, y, 2, (0.7, 0.7, 0.7))
        x = celah
        for im, lab, ok in b:
            yy = y + 20
            kan[yy:yy + tinggi_sel, x:x + im.shape[1]] = im
            kan[yy + tinggi_sel:yy + tinggi_sel + 5, x:x + im.shape[1]] = HIJAU if ok else MERAH
            for j, teks in enumerate(bungkus(lab, max(1, im.shape[1] // 12))[:2]):  # skala 2 = 12 px/karakter
                tulis(kan, teks, x, yy + tinggi_sel + 9 + j * 16, 2)
            x += im.shape[1] + celah
    path = simpan_gambar(path, np.flipud(kan), "contact_sheet")
    return path, (W, H)
