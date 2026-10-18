"""Contact sheet (numpy + bpy.data.images, no PIL, so it runs identically on laptop and cloud).
Each cell gets a text label and a QC status bar (green = passed, red = failed). Format from the path extension:
.jpg (quality 85, small enough for the repo) or .png."""
import numpy as np

from .io import read_png, save_image, resize

# 5x7 bitmap font: character + 7 rows (each row 5 bits, base 32)
_FONT = ("AEHHVHHH BUHHUHHU CEHGGGHE DUHHHHHU EVGGUGGV FVGGUGGG GEHGNHHF HHHHVHHH IE44444E J72222IC KHIKOKIH "
         "LGGGGGGV MHRLLHHH NHHPLJHH OEHHHHHE PUHHUGGG QEHHHLID RUHHUKIH SFGGE11U TV444444 UHHHHHHE VHHHHHA4 "
         "WHHHLLLA XHHA4AHH YHHHA444 ZV1248GV 0EHJLPHE 14C4444E 2EH1248V 3V2421HE 426AIV22 5VGU11HE 668GUHHE "
         "7V124888 8EHHEHHE 9EHHF12C :0CC0CC0 .00000CC -000V000 %OP248J3 #AAVAVAA /01248G0 =00V0V00 _000000V")
GLYPH = {g[0]: np.array([[(int(c, 32) >> (4 - b)) & 1 for b in range(5)] for c in g[1:]], bool) for g in _FONT.split()}
GREEN, RED, BACKGROUND, TEXT = (0.20, 0.70, 0.30), (0.85, 0.15, 0.15), (0.10, 0.10, 0.10), (0.92, 0.92, 0.92)


def write(canvas, text, x, y_top, scale=2, color=TEXT):
    """Draw text (uppercase) on the canvas (row 0 = top)."""
    for i, ch in enumerate(text.upper()):
        g = GLYPH.get(ch)
        if g is None:
            continue
        block = np.kron(g, np.ones((scale, scale), bool))
        x0 = x + i * 6 * scale
        sub = canvas[y_top:y_top + block.shape[0], x0:x0 + block.shape[1]]
        sub[block[:sub.shape[0], :sub.shape[1]]] = color


def wrap(text, n):
    """Word-wrap text into rows of <= n characters."""
    row = [""]
    for word in text.split():
        if row[-1] and len(row[-1]) + 1 + len(word) > n:
            row.append("")
        row[-1] = (row[-1] + " " + word).strip()
    return row


def make(row, path, title, cell_height=300, gap=12):
    """row: list of (title_row, [ (path_png, label, passed) ... ]). Writes the contact sheet, returns (path, (W, H))."""
    head, label_height = 40, 40
    cell = [[(np.flipud(read_png(p)), lab, ok) for p, lab, ok in contents] for _, contents in row]
    cell = [[(resize(im, cell_height), lab, ok) for im, lab, ok in b] for b in cell]
    row_width = [sum(im.shape[1] + gap for im, _, _ in b) + gap for b in cell]
    W = max(row_width + [len(title) * 18 + 2 * gap])
    height_b = cell_height + label_height + 22 + gap
    H = head + len(cell) * height_b + gap
    canvas_arr = np.empty((H, W, 3), "f")
    canvas_arr[:] = BACKGROUND
    write(canvas_arr, title, gap, 10, 3)
    for r, ((jb, _), b) in enumerate(zip(row, cell)):
        y = head + r * height_b
        write(canvas_arr, jb, gap, y, 2, (0.7, 0.7, 0.7))
        x = gap
        for im, lab, ok in b:
            yy = y + 20
            canvas_arr[yy:yy + cell_height, x:x + im.shape[1]] = im
            canvas_arr[yy + cell_height:yy + cell_height + 5, x:x + im.shape[1]] = GREEN if ok else RED
            for j, text in enumerate(wrap(lab, max(1, im.shape[1] // 12))[:2]):  # scale 2 = 12 px/character
                write(canvas_arr, text, x, yy + cell_height + 9 + j * 16, 2)
            x += im.shape[1] + gap
    path = save_image(path, np.flipud(canvas_arr), "contact_sheet")
    return path, (W, H)
