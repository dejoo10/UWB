#!/usr/bin/env python3
# uwb_viewer_calib.py
# UWB viewer with per-anchor range calibration (bias), robust trilateration,
# and anchors locked (steady). Only the tag moves.

import socket, json, threading, queue, math, tkinter as tk
from tkinter import ttk, messagebox

HOST, PORT = "0.0.0.0", 8080

# ---- DEFINE YOUR FIXED ANCHORS HERE (meters) ----
# AIDs must match what the tag sends (e.g., "0x1781", "0x1782").
# Example: A1 at (0,0), A2 at (3,0)
DEFAULT_ANCHORS = {
    "0x1781": (0.0, 0.0),
    "0x1782": (3.0, 0.0),
}
# If False, we will NOT auto-add unknown anchors (keeps anchors steady).
ALLOW_AUTO_ADD = False

SMOOTH_ALPHA = 0.35
UPDATE_MS    = 50

# Robust trilateration knobs
EPS_DI       = 1e-6
LM_LAMBDA    = 1e-2
LM_DECAY     = 0.7
LM_GROW      = 2.0
MAX_STEP     = 1.2
HUBER_DELTA  = 0.25
MAX_ITERS    = 25

q_links = queue.Queue()

# ---------------- TCP server ----------------
def server_thread():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(1)
    print(f"Listening on {HOST}:{PORT}")
    while True:
        conn, addr = srv.accept()
        print("Client connected:", addr)
        buf = b""
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk: break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line: continue
                    try:
                        obj = json.loads(line.decode("utf-8", "ignore"))
                        if isinstance(obj, dict) and "links" in obj:
                            q_links.put(obj["links"])
                    except json.JSONDecodeError:
                        pass
        finally:
            conn.close()
            print("Client closed")

# --------------- math (trilateration) ---------------
def _huber_weight(r, d=HUBER_DELTA):
    ar = abs(r)
    return 1.0 if ar <= d else d/ar

def trilaterate(points, ranges, x0=None, y0=None,
                iters=MAX_ITERS, lam=LM_LAMBDA):
    """
    Robust trilateration using corrected ranges.
    - 2 anchors: exact circle intersection (two solutions); pick the one closest to (x0,y0).
                 If no real intersection, *preserve previous perpendicular offset* from baseline.
    - >=3 anchors: Levenberg–Marquardt + Huber weights, step clamp, adaptive damping.
    """
    n = len(points)
    if n == 0: return None
    if n == 1:
        x, y = points[0]; r = max(ranges[0], 0.0)
        return (x + r, y)

    # ---- exactly 2 anchors: allow either side of the baseline and keep offset when disjoint ----
    if n == 2:
        (x1, y1), (x2, y2) = points
        r1, r2 = float(ranges[0]), float(ranges[1])
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) + 1e-12
        ex, ey = dx / d, dy / d

        # along-baseline solution
        a = (r1*r1 - r2*r2 + d*d) / (2*d)
        px, py = x1 + a*ex, y1 + a*ey  # closest point on the baseline to the intersections

        # perpendicular unit normal (left-hand)
        nx, ny = -ey, ex

        # perpendicular height squared
        h2 = r1*r1 - a*a
        if h2 > 0:
            h = math.sqrt(h2)
            cand1 = (px + h*nx, py + h*ny)
            cand2 = (px - h*nx, py - h*ny)
            if (x0 is not None) and (y0 is not None):
                d1 = (cand1[0]-x0)**2 + (cand1[1]-y0)**2
                d2 = (cand2[0]-x0)**2 + (cand2[1]-y0)**2
                return cand1 if d1 <= d2 else cand2
            return cand1
        else:
            # Circles don't intersect; keep the previous signed perpendicular offset from the baseline point (px,py)
            if (x0 is not None) and (y0 is not None):
                prev_off = (x0 - px)*nx + (y0 - py)*ny
                # Optional cap to avoid absurd carry-over when geometry degenerates:
                # prev_off = max(min(prev_off, d), -d)
                return (px + prev_off*nx, py + prev_off*ny)
            # No previous estimate → fall back to baseline point
            return (px, py)

    # ---- 3+ anchors: LM + Huber ----
    if x0 is None or y0 is None:
        x0 = sum(p[0] for p in points)/n
        y0 = sum(p[1] for p in points)/n

    x, y = x0, y0
    last_cost = None
    lam_local = lam

    for _ in range(iters):
        j11=j12=j22=b1=b2=0.0
        valid=0
        for (xi, yi), ri in zip(points, ranges):
            dx, dy = x-xi, y-yi
            di = math.hypot(dx, dy)
            if di < EPS_DI:
                gx, gy = 1.0, 0.0
                di = EPS_DI
            else:
                gx, gy = dx/di, dy/di
            r = di - ri
            w = _huber_weight(r)
            j11 += w*gx*gx; j12 += w*gx*gy; j22 += w*gy*gy
            b1  += w*gx*r;  b2  += w*gy*r
            valid += 1
        if valid < 2: break

        j11d, j22d = j11+lam_local, j22+lam_local
        det = j11d*j22d - j12*j12
        if abs(det) < 1e-12:
            lam_local *= LM_GROW
            continue

        dx = - ( j22d*b1 - j12*b2)/det
        dy = - (-j12 *b1 + j11d*b2)/det

        step = math.hypot(dx, dy)
        if step > MAX_STEP:
            s = MAX_STEP/step; dx*=s; dy*=s

        xn, yn = x+dx, y+dy

        # Huber loss for accept/reject
        new_cost = 0.0
        for (xi, yi), ri in zip(points, ranges):
            rr = math.hypot(xn-xi, yn-yi) - ri
            a = abs(rr)
            new_cost += rr*rr if a <= HUBER_DELTA else HUBER_DELTA*HUBER_DELTA + 2*HUBER_DELTA*(a-HUBER_DELTA)

        if (last_cost is None) or (new_cost <= last_cost):
            x, y = xn, yn
            last_cost = new_cost
            lam_local = max(lam_local*LM_DECAY, 1e-6)
            if dx*dx + dy*dy < 1e-6: break
        else:
            lam_local = min(lam_local*LM_GROW, 1e6)

    return (x, y)

# ---------------- GUI ----------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UWB Viewer (Calibrated, Anchors Locked)")
        self.geometry("980x660")

        # Data model: x, y (meters), r (raw), bias (meters)
        self.anchors = {aid: {'x':x,'y':y,'r':None,'bias':0.0} for aid,(x,y) in DEFAULT_ANCHORS.items()}
        self.tag = None
        self.tag_smooth = None

        # Layout
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self, padding=10); left.grid(row=0, column=0, sticky="ns")
        self.canvas = tk.Canvas(self, bg="#111"); self.canvas.grid(row=0, column=1, sticky="nsew")

        ttk.Label(left, text="Anchors (locked positions)", font=("Segoe UI", 12, "bold")).grid(sticky="w")

        self.show_inactive = tk.BooleanVar(value=True)
        self.show_ranges   = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="Show anchors without range", variable=self.show_inactive,
                        command=self._refresh_all).grid(sticky="w")
        ttk.Checkbutton(left, text="Show range circles", variable=self.show_ranges,
                        command=self.draw).grid(sticky="w", pady=(0,6))

        self.table = ttk.Treeview(left, columns=("aid","x","y","r","bias"), show="headings", height=8)
        for col, w, a in (("aid",90,"w"), ("x",70,"e"), ("y",70,"e"), ("r",80,"e"), ("bias",70,"e")):
            self.table.heading(col, text=col); self.table.column(col, width=w, anchor=a)
        self.table.grid(sticky="ew")
        self.table.bind("<<TreeviewSelect>>", self._on_select)

        # Distances list (corrected)
        ttk.Label(left, text="Distances (corrected)", font=("Segoe UI", 11, "bold")).grid(sticky="w", pady=(10,0))
        self.dist = ttk.Treeview(left, columns=("aid","rcorr"), show="headings", height=5)
        self.dist.heading("aid", text="aid"); self.dist.column("aid", width=90, anchor="w")
        self.dist.heading("rcorr", text="r (m)"); self.dist.column("rcorr", width=80, anchor="e")
        self.dist.grid(sticky="ew", pady=(2,6))

        # Editor (positions are locked unless you manually change them here)
        f = ttk.Frame(left); f.grid(sticky="ew", pady=6)
        self.a_aid, self.a_x, self.a_y, self.a_bias = tk.StringVar(), tk.DoubleVar(), tk.DoubleVar(), tk.DoubleVar()
        for i,(lbl,var,w) in enumerate((("AID",self.a_aid,12),("x",self.a_x,10),("y",self.a_y,10),("bias",self.a_bias,10))):
            ttk.Label(f, text=lbl, width=7).grid(row=i, column=0, sticky="e")
            ttk.Entry(f, textvariable=var, width=w).grid(row=i, column=1, sticky="w")
        b = ttk.Frame(left); b.grid(sticky="ew", pady=4)
        ttk.Button(b, text="Add/Update", command=self.add_update).grid(row=0, column=0, padx=2)
        ttk.Button(b, text="Delete", command=self.delete_anchor).grid(row=0, column=1, padx=2)
        ttk.Button(b, text="Calibrate here", command=self.calibrate_here).grid(row=0, column=2, padx=8)

        self.status = tk.StringVar(value="Waiting for data…")
        ttk.Label(left, textvariable=self.status, wraplength=240).grid(sticky="w", pady=8)

        self._refresh_all()
        self.canvas.bind("<Configure>", lambda e: self.draw())
        threading.Thread(target=server_thread, daemon=True).start()
        self.after(UPDATE_MS, self.tick)

    # ----- helpers -----
    def _refresh_all(self):
        self._refresh_table()
        self._refresh_dist()
        self.draw()

    def _refresh_table(self):
        for i in self.table.get_children(): self.table.delete(i)
        def is_active(a): return isinstance(a['r'], (int,float))
        items = [(aid,a) for aid,a in self.anchors.items()
                 if self.show_inactive.get() or is_active(a)]
        for aid,a in sorted(items):
            rtxt = f"{a['r']:.2f}" if isinstance(a['r'], (int,float)) else ""
            self.table.insert("", "end", iid=aid,
                              values=(aid, f"{a['x']:.2f}", f"{a['y']:.2f}", rtxt, f"{a['bias']:.2f}"))

    def _refresh_dist(self):
        for i in self.dist.get_children(): self.dist.delete(i)
        for aid,a in sorted(self.anchors.items()):
            if isinstance(a['r'], (int,float)):
                rc = a['r'] + a['bias']
                if rc < 0: rc = 0.0
                self.dist.insert("", "end", values=(aid, f"{rc:.2f}"))

    def _on_select(self, *_):
        sel = self.table.selection()
        if not sel: return
        aid = sel[0]; a = self.anchors[aid]
        self.a_aid.set(aid); self.a_x.set(a['x']); self.a_y.set(a['y']); self.a_bias.set(a['bias'])

    # ----- actions -----
    def add_update(self):
        aid = self.a_aid.get().strip()
        if not aid:
            return messagebox.showwarning("AID missing", "Enter an AID like 0xA1B2.")
        try:
            x = float(self.a_x.get()); y = float(self.a_y.get()); b = float(self.a_bias.get())
        except Exception:
            return messagebox.showwarning("Invalid", "x, y, and bias must be numbers.")
        # Manual edits are allowed; this is the only way to change positions.
        if aid not in self.anchors:
            self.anchors[aid] = {'x':x,'y':y,'r':None,'bias':b}
        else:
            self.anchors[aid]['x']=x; self.anchors[aid]['y']=y; self.anchors[aid]['bias']=b
        self._refresh_all()

    def delete_anchor(self):
        aid = self.a_aid.get().strip()
        if aid in self.anchors:
            del self.anchors[aid]
            self._refresh_all()

    def calibrate_here(self):
        """Set bias so that each anchor's corrected range equals its geometric distance to the current tag."""
        if not self.tag:
            return messagebox.showinfo("No tag estimate", "Move the tag or wait until an estimate appears.")
        tx, ty = self.tag
        changed = False
        for a in self.anchors.values():
            if isinstance(a['r'], (int,float)):
                geom = math.hypot(tx - a['x'], ty - a['y'])        # true distance given current tag
                a['bias'] = geom - a['r']                           # bias to add to raw range
                changed = True
        if changed:
            self._refresh_all()

    # ----- data update -----
    def tick(self):
        updated = False
        while True:
            try: links = q_links.get_nowait()
            except queue.Empty: break
            updated = True
            for l in links:
                aid = l.get("aid"); r = l.get("range")
                if not isinstance(aid,str) or not isinstance(r,(int,float)): continue

                # ---- LOCK: do not auto-create or move anchors ----
                if aid not in self.anchors:
                    # Unknown AID; ignore to keep anchors steady.
                    # (You can add it manually from the left panel.)
                    continue

                # Only update the measured range; position remains fixed.
                self.anchors[aid]['r'] = float(r)

        if updated:
            pts, rs = [], []
            for a in self.anchors.values():
                if isinstance(a['r'], (int,float)):
                    rc = a['r'] + a['bias']
                    if rc < 0: rc = 0.0
                    pts.append((a['x'], a['y']))
                    rs.append(rc)

            if len(pts) >= 2:
                x0, y0 = (self.tag if self.tag else (None, None))
                est = trilaterate(pts, rs, x0, y0)
                if est:
                    self.tag = est
                    if self.tag_smooth is None:
                        self.tag_smooth = est
                    else:
                        ex,ey = self.tag_smooth
                        self.tag_smooth = (ex + SMOOTH_ALPHA*(est[0]-ex),
                                           ey + SMOOTH_ALPHA*(est[1]-ey))
                    self.status.set(f"Tag ≈ ({self.tag_smooth[0]:.2f}, {self.tag_smooth[1]:.2f}) m")

            self._refresh_all()

        self.after(UPDATE_MS, self.tick)

    # ----- drawing -----
    def draw(self):
        c = self.canvas; c.delete("all")

        xs=[a['x'] for a in self.anchors.values()]
        ys=[a['y'] for a in self.anchors.values()]
        if self.tag_smooth: xs.append(self.tag_smooth[0]); ys.append(self.tag_smooth[1])
        if xs:
            xmin, xmax = min(xs)-1, max(xs)+1
            ymin, ymax = min(ys)-1, max(ys)+1
        else:
            xmin,ymin,xmax,ymax = -1,-1,4,4

        W,H = c.winfo_width() or 800, c.winfo_height() or 600
        sx = W/max(xmax-xmin,1e-6); sy = H/max(ymax-ymin,1e-6)
        s = min(sx,sy)
        ox = (W - s*(xmax-xmin))*0.5 - s*xmin
        oy = (H - s*(ymax-ymin))*0.5 + s*ymax
        def to_xy(x,y): return (ox + s*x, oy - s*y)

        # grid
        step=1.0
        x = math.floor(xmin/step)*step
        while x <= xmax:
            x0,y0 = to_xy(x,ymin); x1,y1 = to_xy(x,ymax)
            c.create_line(x0,y0,x1,y1,fill="#1e1e1e"); x+=step
        y = math.floor(ymin/step)*step
        while y <= ymax:
            x0,y0 = to_xy(xmin,y); x1,y1 = to_xy(xmax,y)
            c.create_line(x0,y0,x1,y1,fill="#1e1e1e"); y+=step
        # axes
        x0,y0 = to_xy(0,ymin); x1,y1 = to_xy(0,ymax); c.create_line(x0,y0,x1,y1,fill="#2c2c2c",width=2)
        x0,y0 = to_xy(xmin,0); x1,y1 = to_xy(xmax,0); c.create_line(x0,y0,x1,y1,fill="#2c2c2c",width=2)

        # anchors with range circles (using corrected ranges)
        tcx=tcy=None
        if self.tag_smooth:
            tcx,tcy = to_xy(self.tag_smooth[0], self.tag_smooth[1])

        for aid,a in self.anchors.items():
            cx,cy = to_xy(a['x'],a['y'])
            r=6
            c.create_rectangle(cx-r,cy-r,cx+r,cy+r,outline="#00FFFF",width=2)

            ax_off, ay_off = 0, 0
            if tcx is not None and (abs(tcx - cx) < 30) and (abs(tcy - cy) < 30):
                ax_off, ay_off = -18, 18
            c.create_text(cx+10+ax_off, cy-10+ay_off, text=aid, fill="#9DF", anchor="w")
            c.create_text(cx+10+ax_off, cy+4+ay_off,
                          text=f"({a['x']:.2f},{a['y']:.2f}) m", fill="#9DF", anchor="w")

            if self.show_ranges.get() and isinstance(a.get('r'), (int,float)):
                rc = a['r'] + a['bias']
                if rc < 0: rc = 0.0
                rr = rc * s
                c.create_oval(cx-rr,cy-rr,cx+rr,cy+rr,outline="#303030")

        # tag + callouts (use corrected ranges for labels)
        if self.tag_smooth:
            tx,ty = self.tag_smooth
            tcx,tcy = to_xy(tx,ty)
            c.create_oval(tcx-7, tcy-7, tcx+7, tcy+7, outline="#FFCC00", width=3)
            c.create_text(tcx+16, tcy-22, text=f"TAG ({tx:.2f},{ty:.2f}) m",
                          fill="#FFC", anchor="w", font=("Segoe UI",10,"bold"))

            for i,(aid,a) in enumerate(sorted(self.anchors.items())):
                if not isinstance(a.get('r'), (int,float)): continue
                acx,acy = to_xy(a['x'],a['y'])
                c.create_line(acx,acy,tcx,tcy,fill="#666",dash=(4,3))
                # perpendicular distance labels
                mx,my = (acx+tcx)/2, (acy+tcy)/2
                vx,vy = tcx-acx, tcy-acy
                vlen = math.hypot(vx,vy) + 1e-9
                nx,ny = -vy/vlen, vx/vlen
                sign  = 1 if (i % 2 == 0) else -1
                offset = 14 + (i % 3) * 6
                lx,ly = mx + sign*offset*nx, my + sign*offset*ny
                rc = max(a['r'] + a['bias'], 0.0)
                c.create_text(lx, ly, text=f"{rc:.2f} m", fill="#EEE", font=("Segoe UI",9,"bold"))
                c.create_oval(lx-2, ly-2, lx+2, ly+2, outline="#EEE")

if __name__ == "__main__":
    App().mainloop()
