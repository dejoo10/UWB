#!/usr/bin/env python3
# uwb_viewer_side_labels_show_both.py
# - Always show BOTH anchors and their distances.
# - Bounds are based on anchors (not the tag), so both stay on-screen.
# - Labels adapt: draw to the right of the anchor unless that would clip, then draw to the left.
# - FIX: Draws anchor distance labels on separate lines below each anchor to prevent overlap.

import socket, json, threading, queue, tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

HOST, PORT = "0.0.0.0", 8080
UPDATE_MS = 60
SMOOTH = 0.35

DEFAULT_ANCHORS = {
    "0x0001": (0.0, 0.0),
    "0x0002": (3.0, 0.0),
    "0x0003": (0.0, 3.0),
}

q_links = queue.Queue()

# ---------- TCP server ----------
def server_thread():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(1)
    while True:
        conn, _ = srv.accept()
        buf = b""
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8", "ignore"))
                        if isinstance(obj, dict) and "links" in obj:
                            q_links.put(obj["links"])
                    except json.JSONDecodeError:
                        pass
        finally:
            conn.close()

# ---------- trilateration ----------
def trilat(points, ranges, x0=None, y0=None, iters=12):
    if len(points) == 0:
        return None
    if len(points) == 1:
        x, y = points[0]
        r = max(ranges[0], 0.0)
        return (x + r, y)
    if x0 is None or y0 is None:
        x0 = sum(p[0] for p in points) / len(points)
        y0 = sum(p[1] for p in points) / len(points)
    x, y = x0, y0
    for _ in range(iters):
        j11 = j12 = j21 = j22 = b1 = b2 = 0.0
        for (xi, yi), ri in zip(points, ranges):
            dx, dy = x - xi, y - yi
            d = (dx * dx + dy * dy) ** 0.5 + 1e-9
            r = d - ri
            gx, gy = dx / d, dy / d
            j11 += gx * gx; j12 += gx * gy
            j21 += gy * gx; j22 += gy * gy
            b1 += gx * r;   b2 += gy * r
        det = j11 * j22 - j12 * j21
        if abs(det) < 1e-9:
            break
        dx = -(j22 * b1 - j12 * b2) / det
        dy = -(-j21 * b1 + j11 * b2) / det
        x += dx; y += dy
        if dx * dx + dy * dy < 1e-6:
            break
    return (x, y)

# ---------- GUI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UWB Viewer (both distances visible)")
        self.geometry("1020x620")

        # Data
        self.anchors = {aid: {"x": x, "y": y, "r": None} for aid, (x, y) in DEFAULT_ANCHORS.items()}
        self.tag = None
        self.tag_s = None

        # Layout
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=10); left.grid(row=0, column=0, sticky="ns")
        self.canvas = tk.Canvas(self, bg="#0f0f0f"); self.canvas.grid(row=0, column=1, sticky="nsew")

        # Sidebar: table
        ttk.Label(left, text="Anchors", font=("Segoe UI", 14, "bold")).grid(sticky="w", pady=(0,6))
        self.table = ttk.Treeview(left, columns=("aid","x","y","r"), show="headings", height=8)
        for col, w, a in (("aid",90,"w"), ("x",70,"e"), ("y",70,"e"), ("r",70,"e")):
            self.table.heading(col, text=col); self.table.column(col, width=w, anchor=a)
        self.table.grid(sticky="ew")
        self.table.bind("<<TreeviewSelect>>", self._on_select)

        # Sidebar: editor
        frm = ttk.Frame(left); frm.grid(sticky="w", pady=6)
        self.e_aid, self.e_x, self.e_y = tk.StringVar(), tk.DoubleVar(), tk.DoubleVar()
        ttk.Label(frm, text="AID").grid(row=0, column=0, sticky="e"); ttk.Entry(frm, textvariable=self.e_aid, width=12).grid(row=0, column=1, sticky="w")
        ttk.Label(frm, text="x").grid(row=1, column=0, sticky="e");   ttk.Entry(frm, textvariable=self.e_x, width=10).grid(row=1, column=1, sticky="w")
        ttk.Label(frm, text="y").grid(row=2, column=0, sticky="e");   ttk.Entry(frm, textvariable=self.e_y, width=10).grid(row=2, column=1, sticky="w")

        btns = ttk.Frame(left); btns.grid(sticky="w", pady=4)
        ttk.Button(btns, text="Add/Update", command=self.add_update).grid(row=0, column=0, padx=2)
        ttk.Button(btns, text="Delete",     command=self.delete_anchor).grid(row=0, column=1, padx=2)

        # Sidebar: distances list
        ttk.Label(left, text="Distances", font=("Segoe UI", 12, "bold")).grid(sticky="w", pady=(8,2))
        self.dist_list = tk.Listbox(left, height=6)
        self.dist_list.grid(sticky="ew")

        self.note = tk.StringVar(value="Waiting for data…")
        ttk.Label(left, textvariable=self.note, wraplength=260).grid(sticky="w", pady=8)

        self._refresh_table()
        self._refresh_dist_list()

        threading.Thread(target=server_thread, daemon=True).start()
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.after(UPDATE_MS, self.tick)

        # text font (used for width measurement to avoid clipping)
        self.label_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")

    # Sidebar helpers
    def _refresh_table(self):
        for i in self.table.get_children():
            self.table.delete(i)
        for aid in sorted(self.anchors.keys()):
            a = self.anchors[aid]
            r = f"{a['r']:.2f}" if isinstance(a["r"], (int, float)) else "—"
            self.table.insert("", "end", iid=aid, values=(aid, f"{a['x']:.2f}", f"{a['y']:.2f}", r))

    def _refresh_dist_list(self):
        self.dist_list.delete(0, tk.END)
        for aid in sorted(self.anchors.keys()):
            a = self.anchors[aid]
            rtxt = f"{aid}: {a['r']:.2f} m" if isinstance(a["r"], (int,float)) else f"{aid}: —"
            self.dist_list.insert(tk.END, rtxt)

    def _on_select(self, *_):
        sel = self.table.selection()
        if not sel: return
        aid = sel[0]; a = self.anchors[aid]
        self.e_aid.set(aid); self.e_x.set(a["x"]); self.e_y.set(a["y"])

    def add_update(self):
        aid = self.e_aid.get().strip()
        if not aid:
            return messagebox.showwarning("AID missing", "Enter AID like 0x0001.")
        try:
            x = float(self.e_x.get()); y = float(self.e_y.get())
        except Exception:
            return messagebox.showwarning("Invalid", "x and y must be numbers.")
        self.anchors[aid] = {"x": x, "y": y, "r": self.anchors.get(aid, {}).get("r")}
        self._refresh_table(); self.draw()

    def delete_anchor(self):
        aid = self.e_aid.get().strip()
        if aid in self.anchors:
            del self.anchors[aid]
            self._refresh_table(); self._refresh_dist_list(); self.draw()

    # Networking -> state
    def tick(self):
        changed = False
        while True:
            try:
                links = q_links.get_nowait()
            except queue.Empty:
                break
            changed = True
            for L in links:
                aid = L.get("aid"); r = L.get("range")
                if not isinstance(aid, str) or not isinstance(r, (int,float)): continue
                self.anchors.setdefault(aid, {"x":0.0,"y":0.0,"r":None})
                self.anchors[aid]["r"] = float(r)

        if changed:
            pts, rs = [], []
            for a in self.anchors.values():
                if isinstance(a["r"], (int,float)):
                    pts.append((a["x"], a["y"])); rs.append(a["r"])
            if len(pts) >= 2:
                x0,y0 = (self.tag if self.tag else (None,None))
                est = trilat(pts, rs, x0, y0)
                if est:
                    self.tag = est
                    if self.tag_s is None: self.tag_s = est
                    else:
                        ex,ey = self.tag_s
                        self.tag_s = (ex + SMOOTH*(est[0]-ex), ey + SMOOTH*(est[1]-ey))
                    self.note.set(f"Tag ≈ ({self.tag_s[0]:.2f}, {self.tag_s[1]:.2f}) m")
            self._refresh_table(); self._refresh_dist_list(); self.draw()

        self.after(UPDATE_MS, self.tick)

    # Drawing
    def draw(self):
        c = self.canvas; c.delete("all")

        # ---- Auto zoom: use ANCHORS ONLY so both are always in view ----
        xs, ys = [], []
        for a in self.anchors.values():
            xs.append(a["x"]); ys.append(a["y"])
        if xs:
            pad = 4.0   # a bit more margin so labels have room
            xmin, xmax = min(xs)-pad, max(xs)+pad
            ymin, ymax = min(ys)-pad, max(ys)+pad
        else:
            xmin, ymin, xmax, ymax = -2, -2, 5, 5

        W, H = c.winfo_width() or 800, c.winfo_height() or 600
        sx = W / max(xmax - xmin, 1e-6)
        sy = H / max(ymax - ymin, 1e-6)
        s = min(sx, sy)
        ox = (W - s*(xmax - xmin)) * 0.5 - s*xmin
        oy = (H - s*(ymax - ymin)) * 0.5 + s*ymax

        def to_xy(x, y): return (ox + s*x, oy - s*y)

        # Tag + crosshair (drawn first so labels appear above it)
        txc=tyc=None
        if self.tag_s:
            tx, ty = self.tag_s
            txc, tyc = to_xy(tx, ty)
            c.create_line(0, tyc, W, tyc, fill="#222")
            c.create_line(txc, 0, txc, H, fill="#222")
            c.create_oval(txc-10, tyc-10, txc+10, tyc+10, outline="#FFD34D", width=4)

        # ---- Anchors + distance labels ----
        label_line_height = 22  # or adjust for your font size

        for idx, aid in enumerate(sorted(self.anchors.keys())):
            a = self.anchors[aid]
            axc, ayc = to_xy(a["x"], a["y"])
            # anchor square
            c.create_rectangle(axc-7, ayc-7, axc+7, ayc+7, outline="#45E0FF", width=3)

            # optional line to tag (keep or remove)
            if txc is not None:
                c.create_line(axc, ayc, txc, tyc, fill="#5c5c5c")

            if not isinstance(a["r"], (int,float)):
                continue

            label = f"{aid}: {a['r']:.2f} m"

            # draw each label on a different line below the anchor
            y_offset = 20  # downward offset from anchor
            total_offset = y_offset + idx * label_line_height

            offset = 12
            text_w = self.label_font.measure(label)
            x_right = axc + offset + text_w

            # If it would clip off the right edge, draw to the LEFT instead
            if x_right > W - 6:
                c.create_text(axc - offset, ayc + total_offset, text=label,
                              fill="#FFFFFF", anchor="e", font=self.label_font)
            else:
                c.create_text(axc + offset, ayc + total_offset, text=label,
                              fill="#FFFFFF", anchor="w", font=self.label_font)

if __name__ == "__main__":
    App().mainloop()
