# md8800_gui_v8.py
# MD8800 VFD GUI — v8

import time, datetime, random
import tkinter as tk
from tkinter import ttk, messagebox
import serial, serial.tools.list_ports

try:
    import psutil
    HAVE_PSUTIL = True
except Exception:
    HAVE_PSUTIL = False

BAUD = 9600
STOPBITS = serial.STOPBITS_TWO

def hexstr(bs: bytes) -> str:
    return " ".join(f"{b:02X}" for b in bs)

def parse_hex(s: str) -> bytes:
    s = s.strip().replace(",", " ").replace(";", " ")
    if not s: return b""
    return bytes(int(x, 16) for x in s.split())

class VFD:
    def __init__(self, log_cb):
        self.s = None
        self.log = log_cb

    def open(self, port: str):
        try:
            self.s = serial.Serial(
                port=port, baudrate=BAUD, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=STOPBITS,
                timeout=0.3, write_timeout=0.5
            )
            self.log(f"[connected] {port} @ {BAUD} 8N2")
        except Exception as e:
            self.log(f"[error] open: {e}")
            messagebox.showerror("Serial", str(e))

    def close(self):
        if self.s:
            try: self.s.close()
            except: pass
            self.s = None
            self.log("[disconnected]")

    def send(self, b: bytes, note=""):
        if not self.s or not self.s.is_open:
            self.log("[error] not connected"); return
        try:
            self.s.write(b)
            self.log(f"TX: {hexstr(b)}  {note}")
        except Exception as e:
            self.log(f"[error] write: {e}")

    def RESET(self): self.send(b"\x1F", "RESET")
    def ESC(self, code: int, *params: int, note=""):
        self.send(bytes([0x1B, code] + list(params)),
                  f"ESC {code:02X} {' '.join(f'{p:02X}' for p in params)} {note}")

    # ---- Core / Modes ----
    def mode_2line(self):   self.ESC(0x20, note="2-line")
    def mode_line1(self):   self.ESC(0x21, note="write line1")
    def mode_line2(self):   self.ESC(0x22, note="write line2")
    def soft_clear(self):   self.ESC(0x50, note="soft clear")
    def pos1(self):         self.ESC(0x51, note="pos1 / CR")
    def display_on(self):   self.ESC(0x52, note="display ON")
    def display_off(self):  self.ESC(0x53, note="display OFF")
    def demo_rain(self):    self.ESC(0x54, note="demo rain")
    def bars_vert(self):    self.ESC(0xF0, note="bars vertical")
    def bars_horiz(self):   self.ESC(0xF1, note="bars horizontal")
    def prod_version(self): self.ESC(0xF5, note="product/version")
    def set_brightness(self, level:int):
        lvl = max(0, min(5, int(level)))
        self.ESC(0x40, lvl, note=f"brightness {lvl}")

    def write_text(self, s: str):
        data = s.encode("ascii", "ignore")
        self.send(data, f'"{s}"')

    # ---- Clock ----
    def clock_24h(self):  self.ESC(0x01, note="24h clock")
    def clock_12h(self):  self.ESC(0x02, note="12h clock")
    def clock_stop(self): self.ESC(0x03, note="clock stop move")
    def clock_move(self): self.ESC(0x04, note="clock move")
    def clock_show(self): self.ESC(0x05, note="clock show")
    def clock_set(self, dt: datetime.datetime):
        m,h,d,mo,y = dt.minute, dt.hour, dt.day, dt.month, dt.year
        self.ESC(0x00, m, h, d, mo, (y>>8)&0xFF, y&0xFF,
                 note=f"clock set {h:02d}:{m:02d} {d:02d}.{mo:02d}.{y}")

    # ---- Icons (ESC 30 sub val) ----
    def icon_brightness(self, sub:int, level:int):
        lvl = max(0, min(6, int(level)))
        self.ESC(0x30, sub & 0xFF, lvl & 0xFF, note=f"icon {sub:02X} brightness {lvl}")
    def icon_bool(self, sub:int, on:bool):
        self.ESC(0x30, sub & 0xFF, 0x01 if on else 0x00,
                 note=f"icon {sub:02X} {'ON' if on else 'OFF'}")

    def set_record(self, on:bool):      self.icon_bool(0x08, on)
    # Email mapping: white 0x09, red 0x0A
    def set_email_white(self, on:bool): self.icon_bool(0x09, on)
    def set_email_red(self, on:bool):   self.icon_bool(0x0A, on)

    # Speaker / Muted
    def set_speaker_mode(self, mode:int):
        # 0 off, 1 muted (0x14), 2 speaker (0x13)
        self.icon_bool(0x13, mode == 2)
        self.icon_bool(0x14, mode == 1)

    # Volume bars 0..8 -> 0x0B..0x11 plus 0x12 red underbar
    def set_volume_level(self, level:int):
        lvl = max(0, min(8, int(level)))
        for sub in (0x0B,0x0C,0x0D,0x0E,0x0F,0x10,0x11,0x12):
            self.icon_bool(sub, False)
        bar_ids = (0x0B,0x0C,0x0D,0x0E,0x0F,0x10,0x11)
        for i in range(min(lvl, 7)):
            self.icon_bool(bar_ids[i], True)
        self.icon_bool(0x12, lvl == 8)

    # Red bars 0..3
    def set_wifi_level(self, level:int):
        lvl = max(0, min(3, int(level)))
        for sub in (0x15,0x16,0x17):
            self.icon_bool(sub, False)
        if lvl >= 1: self.icon_bool(0x15, True)
        if lvl >= 2: self.icon_bool(0x16, True)
        if lvl >= 3: self.icon_bool(0x17, True)

    # Boxes 0..4 -> 0x18..0x1C
    def set_box(self, which:int, on:bool):
        self.icon_bool(0x18 + which, on)

    # Mini-matrix (ESC 31 + 9 cols). Device wants RIGHT->LEFT columns.
    # Vertical: top row is bit0 on this unit.
    def mm_send_cols(self, cols9_left_to_right):
        cols = list(cols9_left_to_right)
        cols.reverse()
        self.send(bytes([0x1B,0x31] + [c & 0x7F for c in cols]), "mm frame")
    def mm_clear(self):
        self.send(b"\x1B\x31" + bytes([0]*9), "mm clear")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MD8800 VFD Control — v8")
        self.geometry("1040x820")

        self._make_scrollable()
        self._init_style()
        self.dark_mode = False

        self.vfd = VFD(self.log)

        # loops from v7
        self.loop_clock_text = False
        self.loop_clock_sync = False
        self.loop_vol_sweep  = False
        self.loop_wifi_scan  = False
        self.loop_icon_wave  = False
        self.loop_marquee    = False
        self.loop_cylon      = False
        self.loop_spin       = False
        self.loop_twinkle    = False
        self.loop_cpu_meter  = False
        self.loop_icon_carousel = False
        self.loop_icon_pulse    = False
        self.loop_email_blink   = False
        self.loop_record_blink  = False
        self.loop_text_bounce   = False
        self.loop_mini_rain     = False
        self.loop_mini_snake    = False
        self.loop_net_meter     = False
        self.loop_disk_meter    = False
        self.loop_mem_meter     = False

        # NEW loops (v8)
        self.loop_ball          = False
        self.loop_stickman      = False
        self.loop_gol           = False
        self.loop_clock_bars    = False
        self.loop_snake_game    = False

        # fps → ms (existing)
        self.ms_vol_sweep   = 120
        self.ms_wifi_scan   = 160
        self.ms_icon_wave   = 140
        self.ms_marquee     = 120
        self.ms_cylon       = 120
        self.ms_spin        = 120
        self.ms_twinkle     = 100
        self.ms_cpu_meter   = 250
        self.ms_icon_carousel = 160
        self.ms_icon_pulse    = 120
        self.ms_email_blink   = 300
        self.ms_record_blink  = 350
        self.ms_text_bounce   = 120
        self.ms_mini_rain     = 120
        self.ms_mini_snake    = 140
        self.ms_net_meter     = 400
        self.ms_disk_meter    = 300
        self.ms_mem_meter     = 500

        # NEW speeds (v8)
        self.ms_ball        = 100
        self.ms_stickman    = 120
        self.ms_gol         = 200
        self.ms_clock_bars  = 500
        self.ms_snake_game  = 140  # game tick

        # state for some modes
        self._bounce_dir = +1
        self._bounce_pos = 0
        self._snake_path = [(r,c) for r in range(7) for c in (range(9) if r%2==0 else reversed(range(9)))]
        self._snake_len  = 10
        self._snake_idx  = 0
        self._rain_drops = []
        self._rain_p = 0.35

        # v8 states
        self._ball_pos = [3,4]  # r,c
        self._ball_vel = [1,1]
        self._stick_col = -3
        self._stick_frames = self._build_stickman_frames()
        self._gol_grid = self._rand_grid()
        # Snake game state
        self._g_snake = [(3,2),(3,1),(3,0)]   # list of (r,c), head first
        self._g_dir = (0,1)                   # dr,dc
        self._g_pending = (0,1)
        self._g_food = self._rand_food(self._g_snake)
        self._g_score = 0
        self._g_paused = False

        # Global key binds for snake controls
        self.bind_all("<Left>",  lambda e:self._snake_key(-0, -1))
        self.bind_all("<Right>", lambda e:self._snake_key(0, 1))
        self.bind_all("<Up>",    lambda e:self._snake_key(-1, 0))
        self.bind_all("<Down>",  lambda e:self._snake_key(1, 0))

        # build UI
        self._build_header(self.body)
        self._build_conn(self.body)
        self._build_core(self.body)
        self._build_clock(self.body)
        self._build_brightness(self.body)
        self._build_icons(self.body)
        self._build_multimedia(self.body)
        self._build_macros(self.body)
        self._build_more_macros(self.body)
        self._build_meters(self.body)
        self._build_games(self.body)         # NEW: Snake + new MM modes
        self._build_custom(self.body)
        self._build_log(self.body)

    # ---------- Theme ----------
    def _init_style(self):
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.palette_light = {"bg":"#f4f4f4","fg":"#111","accent":"#2f6fed","entrybg":"#ffffff","textbg":"#ffffff","textfg":"#111"}
        self.palette_dark  = {"bg":"#1e1f22","fg":"#ddd","accent":"#4e8cff","entrybg":"#2a2b2f","textbg":"#1b1c1f","textfg":"#e6e6e6"}
        self._apply_palette(self.palette_light)

    def _apply_palette(self, pal):
        self.configure(bg=pal["bg"])
        self.style.configure("TFrame", background=pal["bg"])
        self.style.configure("TLabelframe", background=pal["bg"], foreground=pal["fg"])
        self.style.configure("TLabelframe.Label", background=pal["bg"], foreground=pal["fg"])
        self.style.configure("TLabel", background=pal["bg"], foreground=pal["fg"])
        self.style.configure("TButton", background=pal["bg"], foreground=pal["fg"])
        self.style.map("TButton", background=[("active", pal["accent"])], foreground=[("active", "#fff")])
        self.style.configure("TRadiobutton", background=pal["bg"], foreground=pal["fg"])
        self.style.configure("TCheckbutton", background=pal["bg"], foreground=pal["fg"])
        if hasattr(self, "logbox"):
            self.logbox.configure(bg=pal["textbg"], fg=pal["textfg"], insertbackground=pal["textfg"])
        if hasattr(self, "canvas"):
            self.canvas.configure(bg=pal["bg"])

    def _toggle_theme(self):
        self.dark_mode = not self.dark_mode
        pal = self.palette_dark if self.dark_mode else self.palette_light
        self._apply_palette(pal)

    # ---------- Scroll container ----------
    def _make_scrollable(self):
        container = ttk.Frame(self); container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(container, highlightthickness=0, bg="#f4f4f4")
        vscroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y"); self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        self.body_id = self.canvas.create_window((0,0), window=self.body, anchor="nw")
        def _on_body_config(_):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            self.canvas.itemconfig(self.body_id, width=self.canvas.winfo_width())
        self.body.bind("<Configure>", _on_body_config)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.body_id, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if event.num == 4:   self.canvas.yview_scroll(-2, "units")
        elif event.num == 5: self.canvas.yview_scroll( 2, "units")
        else:                self.canvas.yview_scroll(-1*(event.delta//120), "units")

    # ---------- Sections (same as v7 up to meters) ----------
    def _build_header(self, parent):
        f = ttk.Frame(parent); f.pack(fill="x", padx=8, pady=(8,0))
        ttk.Label(f, text="MD8800 VFD Control — v8").pack(side="left")
        ttk.Button(f, text="Dark / Light", command=self._toggle_theme).pack(side="right")

    def _build_conn(self, parent):
        f = ttk.LabelFrame(parent, text="Connection")
        f.pack(fill="x", padx=8, pady=6)
        ttk.Label(f, text="Port:").pack(side="left", padx=(8,4))
        self.cmb = ttk.Combobox(f, width=14, state="readonly")
        self._refresh_ports(); self.cmb.pack(side="left", padx=4)
        ttk.Button(f, text="Refresh", command=self._refresh_ports).pack(side="left", padx=4)
        ttk.Button(f, text="Connect", command=self._connect).pack(side="left", padx=4)
        ttk.Button(f, text="Disconnect", command=self._disconnect).pack(side="left", padx=4)
        ttk.Button(f, text="RESET (0x1F)", command=self.vfd.RESET).pack(side="left", padx=10)

    def _build_core(self, parent):
        f = ttk.LabelFrame(parent, text="Core / Modes")
        f.pack(fill="x", padx=8, pady=6)
        for text, fn in [
            ("2-line (ESC 20)", self.vfd.mode_2line),
            ("Write line1 (ESC 21)", self.vfd.mode_line1),
            ("Write line2 (ESC 22)", self.vfd.mode_line2),
            ("Soft Clear (ESC 50)", self.vfd.soft_clear),
            ("Pos1 / CR (ESC 51)", self.vfd.pos1),
            ("Display ON (ESC 52)", self.vfd.display_on),
            ("Display OFF (ESC 53)", self.vfd.display_off),
            ("Demo Rain (ESC 54)", self.vfd.demo_rain),
            ("Bars Vert (ESC F0)", self.vfd.bars_vert),
            ("Bars Horiz (ESC F1)", self.vfd.bars_horiz),
            ("Product/Version (ESC F5)", self.vfd.prod_version),
        ]:
            ttk.Button(f, text=text, command=fn).pack(side="left", padx=4, pady=4)

        e = ttk.LabelFrame(parent, text="Write Text")
        e.pack(fill="x", padx=8, pady=6)
        self.txt = tk.Entry(e, width=64); self.txt.pack(side="left", padx=6, pady=4)
        ttk.Button(e, text="Send", command=lambda:self.vfd.write_text(self.txt.get())).pack(side="left", padx=6)

    def _build_clock(self, parent):
        f = ttk.LabelFrame(parent, text="Clock")
        f.pack(fill="x", padx=8, pady=6)
        ttk.Button(f, text="24h (ESC 01)", command=self.vfd.clock_24h).pack(side="left", padx=4, pady=4)
        ttk.Button(f, text="12h (ESC 02)", command=self.vfd.clock_12h).pack(side="left", padx=4, pady=4)
        ttk.Button(f, text="Stop move (ESC 03)", command=self.vfd.clock_stop).pack(side="left", padx=4, pady=4)
        ttk.Button(f, text="Move (ESC 04)", command=self.vfd.clock_move).pack(side="left", padx=4, pady=4)
        ttk.Button(f, text="Show (ESC 05)", command=self.vfd.clock_show).pack(side="left", padx=4, pady=4)
        ttk.Button(f, text="Set from PC now", command=lambda:self.vfd.clock_set(datetime.datetime.now())
                  ).pack(side="left", padx=12)

        ft = ttk.LabelFrame(parent, text="PC clock as TEXT (updates every second)")
        ft.pack(fill="x", padx=8, pady=6)
        ttk.Label(ft, text="Line:").pack(side="left", padx=(8,4))
        self.clock_line = ttk.Combobox(ft, state="readonly", width=6, values=["0","1"]); self.clock_line.set("0")
        self.clock_line.pack(side="left", padx=4)
        ttk.Label(ft, text="Format:").pack(side="left", padx=(12,4))
        self.clock_fmt = tk.Entry(ft, width=26); self.clock_fmt.insert(0, "%H:%M:%S  %d.%m.%Y")
        self.clock_fmt.pack(side="left", padx=4)
        ttk.Button(ft, text="Start", command=self._clock_text_start).pack(side="left", padx=8)
        ttk.Button(ft, text="Stop",  command=self._clock_text_stop).pack(side="left", padx=4)

        fs = ttk.LabelFrame(parent, text="Sync device clock every minute")
        fs.pack(fill="x", padx=8, pady=6)
        ttk.Button(fs, text="Start sync", command=self._clock_sync_start).pack(side="left", padx=8)
        ttk.Button(fs, text="Stop sync",  command=self._clock_sync_stop).pack(side="left", padx=4)

    def _build_brightness(self, parent):
        f = ttk.LabelFrame(parent, text="Brightness")
        f.pack(fill="x", padx=8, pady=6)
        ttk.Label(f, text="Global (0..5)").pack(side="left", padx=(8,4))
        self.bright = tk.Scale(f, from_=0, to=5, orient="horizontal", length=220,
                               command=lambda v:self.vfd.set_brightness(int(float(v))))
        self.bright.set(3); self.bright.pack(side="left", padx=6)

    def _build_icons(self, parent):
        f = ttk.LabelFrame(parent, text="Icons & Indicators (ESC 30 xx yy)")
        f.pack(fill="x", padx=8, pady=6)
        top = ttk.Frame(f); top.pack(fill="x", pady=3)
        for name, sub in [("HDD",0x00),("1394",0x01),("CD",0x02),("USB",0x03),
                          ("Movie",0x04),("TV",0x05),("Music",0x06),("Photo",0x07)]:
            col = ttk.Frame(top); col.pack(side="left", padx=6)
            ttk.Label(col, text=name).pack()
            s = tk.Scale(col, from_=0, to=6, orient="vertical", length=120,
                         command=lambda v, sub=sub: self.vfd.icon_brightness(sub, int(float(v))))
            s.set(0); s.pack()

        mid = ttk.Frame(f); mid.pack(fill="x", pady=6)
        recf = ttk.LabelFrame(mid, text="Recording (0x08)")
        recf.pack(side="left", padx=6)
        self.var_rec = tk.BooleanVar()
        tk.Checkbutton(recf, text="On", variable=self.var_rec,
                       command=lambda:self.vfd.set_record(self.var_rec.get())).pack(padx=6, pady=4)

        em = ttk.LabelFrame(mid, text="Email (0x09 white, 0x0A red)")
        em.pack(side="left", padx=6)
        self.email_mode = tk.IntVar(value=0)
        ttk.Radiobutton(em, text="Off",   variable=self.email_mode, value=0,
                        command=lambda:(self.vfd.set_email_white(False),
                                        self.vfd.set_email_red(False))).pack(anchor="w")
        ttk.Radiobutton(em, text="White", variable=self.email_mode, value=1,
                        command=lambda:(self.vfd.set_email_white(True),
                                        self.vfd.set_email_red(False))).pack(anchor="w")
        ttk.Radiobutton(em, text="White+Red", variable=self.email_mode, value=2,
                        command=lambda:(self.vfd.set_email_white(True),
                                        self.vfd.set_email_red(True))).pack(anchor="w")

        sp = ttk.LabelFrame(mid, text="Speaker (0x13 speaker / 0x14 muted)")
        sp.pack(side="left", padx=6)
        self.sp_mode = tk.IntVar(value=0)
        for label, val in [("Off",0),("Muted",1),("Speaker",2)]:
            ttk.Radiobutton(sp, text=label, variable=self.sp_mode, value=val,
                            command=lambda:self.vfd.set_speaker_mode(self.sp_mode.get())).pack(anchor="w")

        vol = ttk.LabelFrame(mid, text="Volume 0..8 (bars 0x0B..0x11, red 0x12)")
        vol.pack(side="left", padx=6)
        self.vol_scale = tk.Scale(vol, from_=0, to=8, orient="horizontal", length=220,
                                  command=lambda v:self.vfd.set_volume_level(int(float(v))))
        self.vol_scale.set(0); self.vol_scale.pack(padx=6, pady=6)

        wf = ttk.LabelFrame(mid, text="Red bars 0..3 (0x15..0x17)")
        wf.pack(side="left", padx=6)
        self.wifi_scale = tk.Scale(wf, from_=0, to=3, orient="horizontal", length=160,
                                   command=lambda v:self.vfd.set_wifi_level(int(float(v))))
        self.wifi_scale.set(0); self.wifi_scale.pack(padx=6, pady=6)

        bx = ttk.LabelFrame(f, text="Bounding boxes (0x18..0x1C)")
        bx.pack(fill="x", padx=4, pady=6)
        self.box_vars = [tk.BooleanVar() for _ in range(5)]
        names = ["HDD..USB (0x18)", "Movie..Photo (0x19)", "Rec/MM (0x1A)", "Email (0x1B)", "Volume (0x1C)"]
        for i, nm in enumerate(names):
            tk.Checkbutton(bx, text=nm, variable=self.box_vars[i],
                           command=lambda i=i: self.vfd.set_box(i, self.box_vars[i].get())
                           ).pack(side="left", padx=6)

    def _build_multimedia(self, parent):
        f = ttk.LabelFrame(parent, text="Mini-matrix 9×7 (ESC 31 + 9 cols)")
        f.pack(fill="x", padx=8, pady=6)
        self.mm_cells = [[tk.IntVar(value=0) for _ in range(9)] for __ in range(7)]
        grid = ttk.Frame(f); grid.pack(side="left", padx=8, pady=4)
        for r in range(7):
            rowf = ttk.Frame(grid); rowf.pack()
            for c in range(9):
                tk.Checkbutton(rowf, width=2, variable=self.mm_cells[r][c]).pack(side="left")
        btns = ttk.Frame(f); btns.pack(side="left", padx=12)
        ttk.Button(btns, text="Send frame", command=self._send_mm_from_grid).pack(fill="x", pady=3)
        ttk.Button(btns, text="Clear", command=self.vfd.mm_clear).pack(fill="x", pady=3)
        self.mm_presets = {
            "Play ▶":  [0x00,0x00,0x08,0x1C,0x3E,0x7F,0x00,0x00,0x00],
            "Stop ■":  [0x00,0x3E,0x3E,0x3E,0x3E,0x3E,0x00,0x00,0x00],
            "Pause ⏸":[0x00,0x3E,0x3E,0x00,0x3E,0x3E,0x00,0x00,0x00],
            "FF »":    [0x00,0x08,0x1C,0x3E,0x08,0x1C,0x3E,0x00,0x00],
            "RW «":    [0x00,0x3E,0x1C,0x08,0x3E,0x1C,0x08,0x00,0x00],
            "Heart ♥": [0x00,0x0C,0x1E,0x3E,0x7C,0x3E,0x1E,0x0C,0x00],
            "Heart ⭘":[0x0C,0x12,0x21,0x41,0x02,0x41,0x21,0x12,0x0C],
        }
        self.mm_choice = ttk.Combobox(btns, state="readonly", width=14, values=list(self.mm_presets.keys()))
        self.mm_choice.set("Play ▶"); self.mm_choice.pack(fill="x", pady=3)
        ttk.Button(btns, text="Send preset",
                   command=lambda:self.vfd.mm_send_cols(self.mm_presets[self.mm_choice.get()])
                   ).pack(fill="x", pady=3)

    # (Existing macros/more macros/meters from v7) ----
    # To save space, these methods are identical to v7 (volume sweep, wifi, icon waves, marquee,
    # cylon, spin, twinkle, icon carousel/pulse, email blink, record blink, text bounce, rain,
    # snake path, plus psutil meters). They are included below unchanged.

    def _build_macros(self, parent):
        f = ttk.LabelFrame(parent, text="Macros / Fun modes (set FPS for each)")
        f.pack(fill="x", padx=8, pady=6)
        def fps_spin(parent, initial, cb):
            wrap = ttk.Frame(parent); wrap.pack(padx=6)
            ttk.Label(wrap, text="FPS:").pack(side="left")
            sp = tk.Spinbox(wrap, from_=1, to=60, width=4, command=lambda:cb(int(sp.get())))
            sp.delete(0, "end"); sp.insert(0, str(initial))
            sp.pack(side="left", padx=4)
            return sp
        vs = ttk.LabelFrame(f, text="Volume sweep"); vs.pack(side="left", padx=8, pady=4)
        ttk.Button(vs, text="Start", command=self._vol_sweep_start).pack(fill="x", pady=2)
        ttk.Button(vs, text="Stop",  command=self._vol_sweep_stop).pack(fill="x")
        fps_spin(vs, round(1000/self.ms_vol_sweep), self._set_vol_sweep_fps)

        ws = ttk.LabelFrame(f, text="Wi-Fi scan"); ws.pack(side="left", padx=8, pady=4)
        ttk.Button(ws, text="Start", command=self._wifi_scan_start).pack(fill="x", pady=2)
        ttk.Button(ws, text="Stop",  command=self._wifi_scan_stop).pack(fill="x")
        fps_spin(ws, round(1000/self.ms_wifi_scan), self._set_wifi_scan_fps)

        iw = ttk.LabelFrame(f, text="Icon brightness wave"); iw.pack(side="left", padx=8, pady=4)
        ttk.Button(iw, text="Start", command=self._icon_wave_start).pack(fill="x", pady=2)
        ttk.Button(iw, text="Stop",  command=self._icon_wave_stop).pack(fill="x")
        fps_spin(iw, round(1000/self.ms_icon_wave), self._set_icon_wave_fps)

        mq = ttk.LabelFrame(f, text="Marquee text"); mq.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(mq); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Line:").pack(side="left", padx=(6,4))
        self.marquee_line = ttk.Combobox(row, state="readonly", width=6, values=["0","1"]); self.marquee_line.set("0")
        self.marquee_line.pack(side="left")
        ttk.Label(row, text="Text:").pack(side="left", padx=(10,4))
        self.marquee_text = tk.Entry(row, width=40); self.marquee_text.insert(0, "Hello from MD8800   ")
        self.marquee_text.pack(side="left")
        btns = ttk.Frame(mq); btns.pack(fill="x")
        ttk.Button(btns, text="Start", command=self._marquee_start).pack(side="left", padx=6)
        ttk.Button(btns, text="Stop",  command=self._marquee_stop).pack(side="left")
        fps_spin(btns, round(1000/self.ms_marquee), self._set_marquee_fps)

        cy = ttk.LabelFrame(f, text="Cylon (volume ping-pong)"); cy.pack(side="left", padx=8, pady=6)
        ttk.Button(cy, text="Start", command=self._cylon_start).pack(fill="x", pady=2)
        ttk.Button(cy, text="Stop",  command=self._cylon_stop).pack(fill="x")
        fps_spin(cy, round(1000/self.ms_cylon), self._set_cylon_fps)

        mm = ttk.LabelFrame(f, text="Mini-matrix animations"); mm.pack(side="left", padx=8, pady=6)
        ttk.Button(mm, text="Spinner Start", command=self._spin_start).pack(fill="x", pady=2)
        ttk.Button(mm, text="Spinner Stop",  command=self._spin_stop).pack(fill="x")
        wrap = ttk.Frame(mm); wrap.pack()
        sp = tk.Spinbox(wrap, from_=1, to=60, width=4, command=lambda:self._set_spin_fps(int(sp.get())))
        tk.Label(wrap, text="FPS:").pack(side="left"); sp.delete(0,"end"); sp.insert(0, round(1000/self.ms_spin)); sp.pack(side="left", padx=4)
        ttk.Separator(mm, orient="horizontal").pack(fill="x", pady=4)
        ttk.Button(mm, text="Twinkle Start", command=self._twinkle_start).pack(fill="x", pady=2)
        ttk.Button(mm, text="Twinkle Stop",  command=self._twinkle_stop).pack(fill="x")
        wrap2 = ttk.Frame(mm); wrap2.pack()
        sp2 = tk.Spinbox(wrap2, from_=1, to=60, width=4, command=lambda:self._set_twinkle_fps(int(sp2.get())))
        tk.Label(wrap2, text="FPS:").pack(side="left"); sp2.delete(0,"end"); sp2.insert(0, round(1000/self.ms_twinkle)); sp2.pack(side="left", padx=4)

    def _build_more_macros(self, parent):
        f = ttk.LabelFrame(parent, text="More Macros / Fun modes")
        f.pack(fill="x", padx=8, pady=6)
        def fps_spin(parent, initial, cb):
            wrap = ttk.Frame(parent); wrap.pack(padx=6)
            ttk.Label(wrap, text="FPS:").pack(side="left")
            sp = tk.Spinbox(wrap, from_=1, to=60, width=4, command=lambda:cb(int(sp.get())))
            sp.delete(0, "end"); sp.insert(0, str(initial))
            sp.pack(side="left", padx=4)
            return sp

        ic = ttk.LabelFrame(f, text="Icon Carousel"); ic.pack(side="left", padx=8, pady=6)
        ttk.Button(ic, text="Start", command=self._icon_carousel_start).pack(fill="x", pady=2)
        ttk.Button(ic, text="Stop",  command=self._icon_carousel_stop).pack(fill="x")
        fps_spin(ic, round(1000/self.ms_icon_carousel), self._set_icon_carousel_fps)

        ip = ttk.LabelFrame(f, text="Icon Pulse (phased)"); ip.pack(side="left", padx=8, pady=6)
        ttk.Button(ip, text="Start", command=self._icon_pulse_start).pack(fill="x", pady=2)
        ttk.Button(ip, text="Stop",  command=self._icon_pulse_stop).pack(fill="x")
        fps_spin(ip, round(1000/self.ms_icon_pulse), self._set_icon_pulse_fps)

        eb = ttk.LabelFrame(f, text="Email Blink"); eb.pack(side="left", padx=8, pady=6)
        ttk.Button(eb, text="Start", command=self._email_blink_start).pack(fill="x", pady=2)
        ttk.Button(eb, text="Stop",  command=self._email_blink_stop).pack(fill="x")
        fps_spin(eb, round(1000/self.ms_email_blink), self._set_email_blink_fps)

        rb = ttk.LabelFrame(f, text="Record Blink"); rb.pack(side="left", padx=8, pady=6)
        ttk.Button(rb, text="Start", command=self._record_blink_start).pack(fill="x", pady=2)
        ttk.Button(rb, text="Stop",  command=self._record_blink_stop).pack(fill="x")
        fps_spin(rb, round(1000/self.ms_record_blink), self._set_record_blink_fps)

        tb = ttk.LabelFrame(f, text="Text Bounce"); tb.pack(fill="x", padx=8, pady=6)
        row = ttk.Frame(tb); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Line:").pack(side="left", padx=(6,4))
        self.bounce_line = ttk.Combobox(row, state="readonly", width=6, values=["0","1"]); self.bounce_line.set("1")
        self.bounce_line.pack(side="left")
        ttk.Label(row, text="Text:").pack(side="left", padx=(10,4))
        self.bounce_text = tk.Entry(row, width=40); self.bounce_text.insert(0, "Bouncing!")
        self.bounce_text.pack(side="left")
        btns = ttk.Frame(tb); btns.pack(fill="x")
        ttk.Button(btns, text="Start", command=self._text_bounce_start).pack(side="left", padx=6)
        ttk.Button(btns, text="Stop",  command=self._text_bounce_stop).pack(side="left")
        fps_spin(btns, round(1000/self.ms_text_bounce), self._set_text_bounce_fps)

        rn = ttk.LabelFrame(f, text="Mini-matrix Rain"); rn.pack(side="left", padx=8, pady=6)
        ttk.Button(rn, text="Start", command=self._rain_start).pack(fill="x", pady=2)
        ttk.Button(rn, text="Stop",  command=self._rain_stop).pack(fill="x")
        fps_spin(rn, round(1000/self.ms_mini_rain), self._set_mini_rain_fps)

        sn = ttk.LabelFrame(f, text="Mini-matrix Snake (path)"); sn.pack(side="left", padx=8, pady=6)
        ttk.Button(sn, text="Start", command=self._snake_start).pack(fill="x", pady=2)
        ttk.Button(sn, text="Stop",  command=self._snake_stop).pack(fill="x")
        fps_spin(sn, round(1000/self.ms_mini_snake), self._set_mini_snake_fps)

    def _build_meters(self, parent):
        f = ttk.LabelFrame(parent, text="System meters (psutil optional)")
        f.pack(fill="x", padx=8, pady=6)
        def fps_spin(parent, initial, cb):
            wrap = ttk.Frame(parent); wrap.pack(padx=6)
            ttk.Label(wrap, text="FPS:").pack(side="left")
            sp = tk.Spinbox(wrap, from_=1, to=60, width=4, command=lambda:cb(int(sp.get())))
            sp.delete(0, "end"); sp.insert(0, str(initial))
            sp.pack(side="left", padx=4)
            return sp

        nm = ttk.LabelFrame(f, text="Net meter → red bars (0..3)")
        nm.pack(side="left", padx=8, pady=6)
        if HAVE_PSUTIL:
            ttk.Button(nm, text="Start", command=self._net_meter_start).pack(fill="x", pady=2)
            ttk.Button(nm, text="Stop",  command=self._net_meter_stop).pack(fill="x")
            fps_spin(nm, round(1000/self.ms_net_meter), self._set_net_meter_fps)
        else:
            ttk.Label(nm, text="Install psutil: pip install psutil").pack(padx=6, pady=10)

        dm = ttk.LabelFrame(f, text="Disk meter → HDD brightness")
        dm.pack(side="left", padx=8, pady=6)
        if HAVE_PSUTIL:
            ttk.Button(dm, text="Start", command=self._disk_meter_start).pack(fill="x", pady=2)
            ttk.Button(dm, text="Stop",  command=self._disk_meter_stop).pack(fill="x")
            fps_spin(dm, round(1000/self.ms_disk_meter), self._set_disk_meter_fps)
        else:
            ttk.Label(dm, text="Install psutil").pack(padx=6, pady=10)

        mm = ttk.LabelFrame(f, text="RAM meter → USB brightness")
        mm.pack(side="left", padx=8, pady=6)
        if HAVE_PSUTIL:
            ttk.Button(mm, text="Start", command=self._mem_meter_start).pack(fill="x", pady=2)
            ttk.Button(mm, text="Stop",  command=self._mem_meter_stop).pack(fill="x")
            fps_spin(mm, round(1000/self.ms_mem_meter), self._set_mem_meter_fps)
        else:
            ttk.Label(mm, text="Install psutil").pack(padx=6, pady=10)

    # ---------- NEW: Games & extra mini-matrix modes ----------
    def _build_games(self, parent):
        f = ttk.LabelFrame(parent, text="Games & Extra Mini-matrix Modes")
        f.pack(fill="x", padx=8, pady=8)

        # Snake (playable)
        sg = ttk.LabelFrame(f, text="SNAKE (mini-matrix)")
        sg.pack(side="left", padx=8, pady=6)

        btnrow = ttk.Frame(sg); btnrow.pack(fill="x")
        ttk.Button(btnrow, text="Start", command=self._snake_game_start).pack(side="left", padx=4)
        ttk.Button(btnrow, text="Pause/Resume", command=self._snake_game_toggle_pause).pack(side="left", padx=4)
        ttk.Button(btnrow, text="Reset", command=self._snake_game_reset).pack(side="left", padx=4)

        # FPS spinner for snake
        row = ttk.Frame(sg); row.pack(pady=4)
        ttk.Label(row, text="FPS:").pack(side="left")
        self.snake_fps_spin = tk.Spinbox(row, from_=1, to=60, width=4, command=lambda:self._set_snake_game_fps(int(self.snake_fps_spin.get())))
        self.snake_fps_spin.delete(0,'end'); self.snake_fps_spin.insert(0, round(1000/self.ms_snake_game))
        self.snake_fps_spin.pack(side="left", padx=4)

        # On-screen D-pad
        pad = ttk.Frame(sg); pad.pack(pady=6)
        ttk.Button(pad, text="↑", width=4, command=lambda:self._snake_key(-1,0)).grid(row=0, column=1)
        ttk.Button(pad, text="←", width=4, command=lambda:self._snake_key(0,-1)).grid(row=1, column=0)
        ttk.Button(pad, text="↓", width=4, command=lambda:self._snake_key(1,0)).grid(row=1, column=1)
        ttk.Button(pad, text="→", width=4, command=lambda:self._snake_key(0,1)).grid(row=1, column=2)

        self.snake_score_lbl = ttk.Label(sg, text="Score: 0"); self.snake_score_lbl.pack(pady=(6,2))
        ttk.Label(sg, text="Controls: Arrow keys or D-pad").pack()

        # Extra mini-matrix quickies
        ex = ttk.LabelFrame(f, text="Extra MM Modes")
        ex.pack(side="left", padx=8, pady=6)
        # Bouncy ball
        bb = ttk.Frame(ex); bb.pack(fill="x", pady=2)
        ttk.Button(bb, text="Bouncy Ball Start", command=self._ball_start).pack(side="left")
        ttk.Button(bb, text="Stop", command=self._ball_stop).pack(side="left", padx=6)
        self._mk_fps_spin(ex, "Ball FPS:", self.ms_ball, self._set_ball_fps)

        # Stickman run
        st = ttk.Frame(ex); st.pack(fill="x", pady=2)
        ttk.Button(st, text="Stickman Run Start", command=self._stickman_start).pack(side="left")
        ttk.Button(st, text="Stop", command=self._stickman_stop).pack(side="left", padx=6)
        self._mk_fps_spin(ex, "Stickman FPS:", self.ms_stickman, self._set_stickman_fps)

        # Game of Life
        gl = ttk.Frame(ex); gl.pack(fill="x", pady=2)
        ttk.Button(gl, text="Game of Life Start", command=self._gol_start).pack(side="left")
        ttk.Button(gl, text="Stop", command=self._gol_stop).pack(side="left", padx=6)
        ttk.Button(gl, text="Randomize", command=lambda:self._gol_randomize()).pack(side="left", padx=6)
        self._mk_fps_spin(ex, "GoL FPS:", self.ms_gol, self._set_gol_fps)

        # Clock bars
        cb = ttk.Frame(ex); cb.pack(fill="x", pady=2)
        ttk.Button(cb, text="Clock Bars Start", command=self._clock_bars_start).pack(side="left")
        ttk.Button(cb, text="Stop", command=self._clock_bars_stop).pack(side="left", padx=6)
        self._mk_fps_spin(ex, "Clock Bars FPS:", self.ms_clock_bars, self._set_clock_bars_fps)

    def _mk_fps_spin(self, parent, label, ms_val, setter):
        wrap = ttk.Frame(parent); wrap.pack(pady=2)
        ttk.Label(wrap, text=label).pack(side="left")
        sp = tk.Spinbox(wrap, from_=1, to=60, width=4, command=lambda:setter(int(sp.get())))
        sp.delete(0,"end"); sp.insert(0, round(1000/ms_val)); sp.pack(side="left", padx=4)

    # ---------- Helpers ----------
    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.cmb["values"] = ports
        if ports: self.cmb.set(ports[0])

    def _connect(self):
        port = self.cmb.get().strip()
        if not port:
            messagebox.showwarning("Port", "Pick a COM port."); return
        self.vfd.open(port)
        self.vfd.RESET(); time.sleep(0.08)
        self.vfd.mode_2line()

    def _disconnect(self): self.vfd.close()

    def _send_esc_custom(self):
        try: code = int(self.e_code.get().strip(), 16)
        except:
            messagebox.showerror("ESC", "Bad ESC code hex"); return
        params = parse_hex(self.e_params.get())
        self.vfd.ESC(code, *list(params))

    def _send_raw(self):
        data = parse_hex(self.e_raw.get()); self.vfd.send(data, "RAW")

    def _send_mm_from_grid(self):
        cols = []
        for c in range(9):
            v = 0
            for r in range(7):
                if self.mm_cells[r][c].get():
                    v |= (1 << r)
            cols.append(v & 0x7F)
        self.vfd.mm_send_cols(cols)

    # ---------- FPS utils ----------
    def _fps_to_ms(self, fps): return max(10, int(1000 / max(1, min(60, fps))))
    # existing setters
    def _set_vol_sweep_fps(self, fps):   self.ms_vol_sweep   = self._fps_to_ms(fps)
    def _set_wifi_scan_fps(self, fps):   self.ms_wifi_scan   = self._fps_to_ms(fps)
    def _set_icon_wave_fps(self, fps):   self.ms_icon_wave   = self._fps_to_ms(fps)
    def _set_marquee_fps(self, fps):     self.ms_marquee     = self._fps_to_ms(fps)
    def _set_cylon_fps(self, fps):       self.ms_cylon       = self._fps_to_ms(fps)
    def _set_spin_fps(self, fps):        self.ms_spin        = self._fps_to_ms(fps)
    def _set_twinkle_fps(self, fps):     self.ms_twinkle     = self._fps_to_ms(fps)
    def _set_cpu_meter_fps(self, fps):   self.ms_cpu_meter   = self._fps_to_ms(fps)
    def _set_icon_carousel_fps(self, fps): self.ms_icon_carousel = self._fps_to_ms(fps)
    def _set_icon_pulse_fps(self, fps):    self.ms_icon_pulse    = self._fps_to_ms(fps)
    def _set_email_blink_fps(self, fps):   self.ms_email_blink   = self._fps_to_ms(fps)
    def _set_record_blink_fps(self, fps):  self.ms_record_blink  = self._fps_to_ms(fps)
    def _set_text_bounce_fps(self, fps):   self.ms_text_bounce   = self._fps_to_ms(fps)
    def _set_mini_rain_fps(self, fps):     self.ms_mini_rain     = self._fps_to_ms(fps)
    def _set_mini_snake_fps(self, fps):    self.ms_mini_snake    = self._fps_to_ms(fps)
    def _set_net_meter_fps(self, fps):     self.ms_net_meter     = self._fps_to_ms(fps)
    def _set_disk_meter_fps(self, fps):    self.ms_disk_meter    = self._fps_to_ms(fps)
    def _set_mem_meter_fps(self, fps):     self.ms_mem_meter     = self._fps_to_ms(fps)
    # new setters
    def _set_ball_fps(self, fps):          self.ms_ball          = self._fps_to_ms(fps)
    def _set_stickman_fps(self, fps):      self.ms_stickman      = self._fps_to_ms(fps)
    def _set_gol_fps(self, fps):           self.ms_gol           = self._fps_to_ms(fps)
    def _set_clock_bars_fps(self, fps):    self.ms_clock_bars    = self._fps_to_ms(fps)
    def _set_snake_game_fps(self, fps):    self.ms_snake_game    = self._fps_to_ms(fps)

    # ---------- Existing fun modes (same logic as v7) ----------
    # (Implementations identical to v7; omitted comments for brevity)
    def _clock_text_start(self):
        if self.loop_clock_text: return
        self.loop_clock_text = True; self._clock_text_tick()
    def _clock_text_stop(self): self.loop_clock_text = False
    def _clock_text_tick(self):
        if not self.loop_clock_text: return
        line = 0 if self.clock_line.get() == "0" else 1
        fmt = self.clock_fmt.get() or "%H:%M:%S"
        try: s = datetime.datetime.now().strftime(fmt)
        except: s = datetime.datetime.now().strftime("%H:%M:%S %d.%m.%Y")
        (self.vfd.mode_line1() if line==0 else self.vfd.mode_line2())
        self.vfd.pos1(); self.vfd.write_text(s[:16])
        self.after(1000, self._clock_text_tick)

    def _clock_sync_start(self):
        if self.loop_clock_sync: return
        self.loop_clock_sync = True; self._clock_sync_tick()
    def _clock_sync_stop(self): self.loop_clock_sync = False
    def _clock_sync_tick(self):
        if not self.loop_clock_sync: return
        self.vfd.clock_set(datetime.datetime.now())
        self.after(60_000, self._clock_sync_tick)

    def _vol_sweep_start(self):
        if self.loop_vol_sweep: return
        self.loop_vol_sweep = True; self._vol_sweep_tick(0, +1)
    def _vol_sweep_stop(self): self.loop_vol_sweep = False
    def _vol_sweep_tick(self, lvl, step):
        if not self.loop_vol_sweep: return
        self.vfd.set_volume_level(lvl)
        nxt = lvl + step
        if nxt > 8: nxt, step = 7, -1
        if nxt < 0: nxt, step = 1, +1
        self.after(self.ms_vol_sweep, lambda:self._vol_sweep_tick(nxt, step))

    def _wifi_scan_start(self):
        if self.loop_wifi_scan: return
        self.loop_wifi_scan = True; self._wifi_scan_tick(0)
    def _wifi_scan_stop(self):
        self.loop_wifi_scan = False; self.vfd.set_wifi_level(0)
    def _wifi_scan_tick(self, state):
        if not self.loop_wifi_scan: return
        seq = [0,1,2,3,2,1]
        self.vfd.set_wifi_level(seq[state % len(seq)])
        self.after(self.ms_wifi_scan, lambda:self._wifi_scan_tick(state+1))

    def _icon_wave_start(self):
        if self.loop_icon_wave: return
        self.loop_icon_wave = True; self._icon_wave_tick(0, +1)
    def _icon_wave_stop(self):
        self.loop_icon_wave = False
        for sub in range(0x00, 0x08): self.vfd.icon_brightness(sub, 0)
    def _icon_wave_tick(self, lvl, step):
        if not self.loop_icon_wave: return
        for sub in range(0x00, 0x08): self.vfd.icon_brightness(sub, lvl)
        nxt = lvl + step
        if nxt > 6: nxt, step = 5, -1
        if nxt < 0: nxt, step = 1, +1
        self.after(self.ms_icon_wave, lambda:self._icon_wave_tick(nxt, step))

    def _marquee_start(self):
        if self.loop_marquee: return
        self.loop_marquee = True; self._marquee_offset = 0; self._marquee_tick()
    def _marquee_stop(self): self.loop_marquee = False
    def _marquee_tick(self):
        if not self.loop_marquee: return
        line = 0 if self.marquee_line.get() == "0" else 1
        raw = self.marquee_text.get() or ""
        s = (" " * 16) + raw + (" " * 16)
        i = self._marquee_offset % (len(s)-15)
        chunk = s[i:i+16]
        (self.vfd.mode_line1() if line==0 else self.vfd.mode_line2())
        self.vfd.pos1(); self.vfd.write_text(chunk)
        self._marquee_offset += 1
        self.after(self.ms_marquee, self._marquee_tick)

    def _cylon_start(self):
        if self.loop_cylon: return
        self.loop_cylon = True; self._cylon_tick(0, +1)
    def _cylon_stop(self):
        self.loop_cylon = False; self.vfd.set_volume_level(0)
    def _cylon_tick(self, pos, step):
        if not self.loop_cylon: return
        level = min(7, max(0, pos+1))
        self.vfd.set_volume_level(level)
        nxt = pos + step
        if nxt > 6: nxt, step = 5, -1
        if nxt < 0: nxt, step = 1, +1
        self.after(self.ms_cylon, lambda:self._cylon_tick(nxt, step))

    def _spin_start(self):
        if self.loop_spin: return
        self.loop_spin = True; self._spin_state = 0
        self._spin_frames = [
            [0x00,0x08,0x08,0x08,0x7F,0x08,0x08,0x08,0x00],
            [0x00,0x00,0x00,0x7F,0x08,0x7F,0x00,0x00,0x00],
            [0x00,0x10,0x10,0x10,0x7F,0x10,0x10,0x10,0x00],
            [0x00,0x00,0x00,0x7F,0x08,0x7F,0x00,0x00,0x00],
        ]
        self._spin_tick()
    def _spin_stop(self):
        self.loop_spin = False; self.vfd.mm_clear()
    def _spin_tick(self):
        if not self.loop_spin: return
        frame = self._spin_frames[self._spin_state % len(self._spin_frames)]
        self.vfd.mm_send_cols(frame)
        self._spin_state += 1
        self.after(self.ms_spin, self._spin_tick)

    def _twinkle_start(self):
        if self.loop_twinkle: return
        self.loop_twinkle = True; self._twinkle_cols = [0]*9; self._twinkle_tick()
    def _twinkle_stop(self):
        self.loop_twinkle = False; self.vfd.mm_clear()
    def _twinkle_tick(self):
        if not self.loop_twinkle: return
        cols = self._twinkle_cols[:]
        for _ in range(3):
            c = random.randint(0,8); r = random.randint(0,6)
            cols[c] ^= (1 << r)
        self._twinkle_cols = [c & 0x7F for c in cols]
        self.vfd.mm_send_cols(self._twinkle_cols)
        self.after(self.ms_twinkle, self._twinkle_tick)

    def _icon_carousel_start(self):
        if self.loop_icon_carousel: return
        self.loop_icon_carousel = True; self._icon_carousel_idx = 0; self._icon_carousel_tick()
    def _icon_carousel_stop(self):
        self.loop_icon_carousel = False
        for sub in range(0x00, 0x08): self.vfd.icon_brightness(sub, 0)
    def _icon_carousel_tick(self):
        if not self.loop_icon_carousel: return
        i = self._icon_carousel_idx % 8
        for sub in range(0x00, 0x08): self.vfd.icon_brightness(sub, 0)
        self.vfd.icon_brightness(0x00 + i, 6)
        self._icon_carousel_idx += 1
        self.after(self.ms_icon_carousel, self._icon_carousel_tick)

    def _icon_pulse_start(self):
        if self.loop_icon_pulse: return
        self.loop_icon_pulse = True; self._icon_pulse_phase = 0; self._icon_pulse_tick()
    def _icon_pulse_stop(self):
        self.loop_icon_pulse = False
        for sub in range(0x00, 0x08): self.vfd.icon_brightness(sub, 0)
    def _icon_pulse_tick(self):
        if not self.loop_icon_pulse: return
        for i in range(8):
            p = (self._icon_pulse_phase + i*2) % 12
            lvl = p if p <= 6 else 12 - p
            self.vfd.icon_brightness(0x00 + i, lvl)
        self._icon_pulse_phase = (self._icon_pulse_phase + 1) % 12
        self.after(self.ms_icon_pulse, self._icon_pulse_tick)

    def _email_blink_start(self):
        if self.loop_email_blink: return
        self.loop_email_blink = True; self._email_state = 0; self._email_blink_tick()
    def _email_blink_stop(self):
        self.loop_email_blink = False
        self.vfd.set_email_white(False); self.vfd.set_email_red(False)
    def _email_blink_tick(self):
        if not self.loop_email_blink: return
        st = self._email_state % 4
        self.vfd.set_email_white(st in (1,3))
        self.vfd.set_email_red(st in (2,3))
        self._email_state += 1
        self.after(self.ms_email_blink, self._email_blink_tick)

    def _record_blink_start(self):
        if self.loop_record_blink: return
        self.loop_record_blink = True; self._rec_on = False; self._record_blink_tick()
    def _record_blink_stop(self):
        self.loop_record_blink = False; self.vfd.set_record(False)
    def _record_blink_tick(self):
        if not self.loop_record_blink: return
        self._rec_on = not self._rec_on
        self.vfd.set_record(self._rec_on)
        self.after(self.ms_record_blink, self._record_blink_tick)

    def _text_bounce_start(self):
        if self.loop_text_bounce: return
        self.loop_text_bounce = True
        self._bounce_dir = +1; self._bounce_pos = 0; self._text_bounce_tick()
    def _text_bounce_stop(self): self.loop_text_bounce = False
    def _text_bounce_tick(self):
        if not self.loop_text_bounce: return
        line = 0 if self.bounce_line.get() == "0" else 1
        raw  = (self.bounce_text.get() or " ").strip()
        s    = raw[:16]
        width= 16; n = max(0, width - len(s))
        chunk = (" " * self._bounce_pos) + s + (" " * (n - self._bounce_pos))
        (self.vfd.mode_line1() if line==0 else self.vfd.mode_line2())
        self.vfd.pos1(); self.vfd.write_text(chunk[:16])
        if n > 0:
            self._bounce_pos += self._bounce_dir
            if self._bounce_pos >= n: self._bounce_pos, self._bounce_dir = n, -1
            if self._bounce_pos <= 0: self._bounce_pos, self._bounce_dir = 0, +1
        self.after(self.ms_text_bounce, self._text_bounce_tick)

    def _rain_start(self):
        if self.loop_mini_rain: return
        self.loop_mini_rain = True; self._rain_drops = []; self._rain_tick()
    def _rain_stop(self):
        self.loop_mini_rain = False; self.vfd.mm_clear(); self._rain_drops = []
    def _rain_tick(self):
        if not self.loop_mini_rain: return
        if random.random() < self._rain_p:
            self._rain_drops.append((0, random.randint(0,8)))
        new = []
        for (r,c) in self._rain_drops:
            r2 = r + 1
            if r2 <= 6: new.append((r2,c))
        self._rain_drops = new
        cols = [0]*9
        for (r,c) in self._rain_drops:
            cols[c] |= (1 << r)
        self.vfd.mm_send_cols(cols)
        self.after(self.ms_mini_rain, self._rain_tick)

    def _snake_start(self):
        if self.loop_mini_snake: return
        self.loop_mini_snake = True; self._snake_idx = 0; self._snake_tick()
    def _snake_stop(self):
        self.loop_mini_snake = False; self.vfd.mm_clear()
    def _snake_tick(self):
        if not self.loop_mini_snake: return
        head_idx = self._snake_idx
        tail_idx = max(0, head_idx - self._snake_len)
        segment = []
        for k in range(tail_idx, head_idx+1):
            (r,c) = self._snake_path[k % len(self._snake_path)]
            segment.append((r,c))
        cols = [0]*9
        for (r,c) in segment:
            cols[c] |= (1 << r)
        self.vfd.mm_send_cols(cols)
        self._snake_idx += 1
        self.after(self.ms_mini_snake, self._snake_tick)

    # ---------- NEW v8 mini-matrix modes ----------
    # Bouncy ball
    def _ball_start(self):
        self._stop_all_mm()
        self.loop_ball = True; self._ball_tick()
    def _ball_stop(self):
        self.loop_ball = False; self.vfd.mm_clear()
    def _ball_tick(self):
        if not self.loop_ball: return
        r,c = self._ball_pos
        vr,vc = self._ball_vel
        r2, c2 = r+vr, c+vc
        if r2 < 0 or r2 > 6: vr = -vr; r2 = r+vr
        if c2 < 0 or c2 > 8: vc = -vc; c2 = c+vc
        self._ball_pos = [r2,c2]; self._ball_vel = [vr,vc]
        cols = [0]*9
        cols[c2] |= (1 << r2)
        self.vfd.mm_send_cols(cols)
        self.after(self.ms_ball, self._ball_tick)

    # Stickman run (scroll frames across)
    def _stickman_start(self):
        self._stop_all_mm()
        self.loop_stickman = True; self._stick_col = 9; self._stick_idx = 0; self._stickman_tick()
    def _stickman_stop(self):
        self.loop_stickman = False; self.vfd.mm_clear()
    def _stickman_tick(self):
        if not self.loop_stickman: return
        frame = self._stick_frames[self._stick_idx % len(self._stick_frames)]  # 9-wide frame
        # slide from right to left
        self._stick_col -= 1
        cols = [0]*9
        for i in range(9):
            src = i - (9 - self._stick_col)
            if 0 <= src < 9:
                cols[i] = frame[src]
        self.vfd.mm_send_cols(cols)
        if self._stick_col <= 0:
            self._stick_col = 9
            self._stick_idx += 1
        self.after(self.ms_stickman, self._stickman_tick)

    # Game of Life
    def _gol_start(self):
        self._stop_all_mm()
        self.loop_gol = True; self._gol_tick()
    def _gol_stop(self):
        self.loop_gol = False; self.vfd.mm_clear()
    def _gol_randomize(self):
        self._gol_grid = self._rand_grid()
    def _gol_tick(self):
        if not self.loop_gol: return
        cols = [0]*9
        for r in range(7):
            for c in range(9):
                if self._gol_grid[r][c]:
                    cols[c] |= (1 << r)
        self.vfd.mm_send_cols(cols)
        self._gol_grid = self._gol_step(self._gol_grid)
        self.after(self.ms_gol, self._gol_tick)

    # Clock bars (H/M/S bar heights across 3+3+3 columns)
    def _clock_bars_start(self):
        self._stop_all_mm()
        self.loop_clock_bars = True; self._clock_bars_tick()
    def _clock_bars_stop(self):
        self.loop_clock_bars = False; self.vfd.mm_clear()
    def _clock_bars_tick(self):
        if not self.loop_clock_bars: return
        now = datetime.datetime.now()
        H, M, S = now.hour, now.minute, now.second
        def bars(val, maxval):
            h = int(round((val/maxval)*7))
            col = 0
            for i in range(h):
                col |= (1 << i)
            return [col]*3
        cols = bars(H, 23) + bars(M, 59) + bars(S, 59)
        self.vfd.mm_send_cols(cols[:9])
        self.after(self.ms_clock_bars, self._clock_bars_tick)

    # ---------- Playable Snake Game ----------
    def _snake_game_start(self):
        self._stop_all_mm()
        self.loop_snake_game = True
        self._g_paused = False
        self._show_snake_score()
        self._snake_game_tick()

    def _snake_game_toggle_pause(self):
        if not self.loop_snake_game: return
        self._g_paused = not self._g_paused
        self._status_text("Paused" if self._g_paused else "Running")

    def _snake_game_reset(self):
        self._g_snake = [(3,2),(3,1),(3,0)]
        self._g_dir = (0,1); self._g_pending = (0,1)
        self._g_food = self._rand_food(self._g_snake)
        self._g_score = 0
        self._show_snake_score()
        self.vfd.mm_clear()

    def _set_snake_game_fps(self, fps):
        self.ms_snake_game = self._fps_to_ms(fps)

    def _snake_key(self, dr, dc):
        # ignore reverse direction
        pr, pc = self._g_dir
        if (dr,dc) == (-pr,-pc): return
        self._g_pending = (dr,dc)

    def _snake_game_tick(self):
        if not self.loop_snake_game: return
        if not self._g_paused:
            self._g_dir = self._g_pending
            head = self._g_snake[0]
            nr = head[0] + self._g_dir[0]
            nc = head[1] + self._g_dir[1]
            # wall collision -> game over
            if not (0 <= nr <= 6 and 0 <= nc <= 8) or (nr,nc) in self._g_snake:
                self._status_text("Game Over!")
                self.loop_snake_game = False
                return
            new_head = (nr,nc)
            self._g_snake = [new_head] + self._g_snake
            if new_head == self._g_food:
                self._g_score += 1
                self._g_food = self._rand_food(self._g_snake)
                self._show_snake_score()
            else:
                self._g_snake.pop()  # move

            cols = [0]*9
            # draw food
            cols[self._g_food[1]] |= (1 << self._g_food[0])
            # draw snake
            for (r,c) in self._g_snake:
                cols[c] |= (1 << r)
            self.vfd.mm_send_cols(cols)
        self.after(self.ms_snake_game, self._snake_game_tick)

    def _show_snake_score(self):
        self.snake_score_lbl.config(text=f"Score: {self._g_score}")
        self.vfd.mode_line1(); self.vfd.pos1(); self.vfd.write_text(f"SNAKE SCORE:{self._g_score:2d}"[:16])
        self.vfd.mode_line2(); self.vfd.pos1(); self.vfd.write_text("Arrows / D-pad   "[:16])

    def _status_text(self, s):
        self.vfd.mode_line2(); self.vfd.pos1(); self.vfd.write_text((s + " " * 16)[:16])

    # ---------- Utility (MM stop & helpers) ----------
    def _stop_all_mm(self):
        # stop all modes that write the mini-matrix
        self.loop_spin = self.loop_twinkle = False
        self.loop_mini_rain = self.loop_mini_snake = False
        self.loop_ball = self.loop_stickman = False
        self.loop_gol = self.loop_clock_bars = False
        self.loop_snake_game = False
        self.vfd.mm_clear()

    def _rand_grid(self):
        return [[1 if random.random() < 0.3 else 0 for _ in range(9)] for __ in range(7)]

    def _gol_step(self, g):
        out = [[0]*9 for _ in range(7)]
        for r in range(7):
            for c in range(9):
                n = 0
                for dr in (-1,0,1):
                    for dc in (-1,0,1):
                        if dr==0 and dc==0: continue
                        rr, cc = r+dr, c+dc
                        if 0 <= rr < 7 and 0 <= cc < 9 and g[rr][cc]: n += 1
                if g[r][c] and (n==2 or n==3): out[r][c]=1
                elif (not g[r][c]) and (n==3): out[r][c]=1
        return out

    def _rand_food(self, snake):
        free = [(r,c) for r in range(7) for c in range(9) if (r,c) not in snake]
        return random.choice(free) if free else (3,4)

    def _build_stickman_frames(self):
        # 4 frames; each 9 columns; bit0 = top row
        # Simple 3-wide stickman centered; rest columns zero.
        frames = []
        # helper to place a 3-col sprite at center (cols 3..5)
        def center3(cols3):
            cols = [0]*9
            cols[3:6] = cols3
            return cols
        # Frame A (standing)
        A = center3([
            0b0010000,  # head (row 3)
            0b0111000,  # torso block-ish
            0b0010000,
        ])
        # arms/legs sprinkled around via extra bits:
        A[2] |= 0b0001000  # left arm up
        A[6] |= 0b0100000  # right leg
        frames.append(A)

        # Frame B (left step)
        B = center3([
            0b0010000,
            0b0111000,
            0b0010000,
        ])
        B[2] |= 0b0011000  # arms
        B[5] |= 0b0100000  # leg
        frames.append(B)

        # Frame C (right step)
        C = center3([
            0b0010000,
            0b0111000,
            0b0010000,
        ])
        C[4] |= 0b0001000
        C[6] |= 0b0010000
        frames.append(C)

        # Frame D (both out)
        D = center3([
            0b0010000,
            0b0111000,
            0b0010000,
        ])
        D[2] |= 0b0100000
        D[4] |= 0b0001000
        frames.append(D)
        return frames

    # ---------- Custom & Log ----------
    def _build_custom(self, parent):
        f = ttk.LabelFrame(parent, text="Custom / RAW")
        f.pack(fill="x", padx=8, pady=6)
        ttk.Label(f, text="ESC code (hex):").pack(side="left", padx=(8,4))
        self.e_code = tk.Entry(f, width=6); self.e_code.insert(0, "52"); self.e_code.pack(side="left", padx=4)
        ttk.Label(f, text="params (hex):").pack(side="left", padx=(12,4))
        self.e_params = tk.Entry(f, width=40); self.e_params.insert(0,""); self.e_params.pack(side="left", padx=4)
        ttk.Button(f, text="Send ESC", command=self._send_esc_custom).pack(side="left", padx=6)
        ttk.Label(f, text=" | RAW hex:").pack(side="left", padx=(12,4))
        self.e_raw = tk.Entry(f, width=40); self.e_raw.insert(0, "1B 55"); self.e_raw.pack(side="left", padx=4)
        ttk.Button(f, text="Send RAW", command=self._send_raw).pack(side="left", padx=6)

    def _build_log(self, parent):
        f = ttk.LabelFrame(parent, text="Log")
        f.pack(fill="both", expand=True, padx=8, pady=8)
        self.logbox = tk.Text(f, height=16, wrap="none", bg="#ffffff", fg="#111111", insertbackground="#111111")
        self.logbox.pack(fill="both", expand=True, padx=6, pady=6)
        self.log("Ready.")

    def log(self, s: str):
        self.logbox.insert("end", s+"\n"); self.logbox.see("end")

    # ---------- System meters (psutil) ----------
    def _net_meter_start(self):
        if not HAVE_PSUTIL:
            messagebox.showwarning("psutil", "Install psutil: pip install psutil")
            return
        if self.loop_net_meter: return
        self.loop_net_meter = True
        io = psutil.net_io_counters()
        self._net_prev_bytes = io.bytes_recv + io.bytes_sent
        self._net_prev_t = time.time()
        self._net_meter_tick()

    def _net_meter_stop(self):
        self.loop_net_meter = False
        self.vfd.set_wifi_level(0)

    def _net_meter_tick(self):
        if not self.loop_net_meter: return
        io = psutil.net_io_counters()
        now = time.time()
        cur = io.bytes_recv + io.bytes_sent
        dt = max(1e-3, now - self._net_prev_t)
        bps = (cur - self._net_prev_bytes) * 8.0 / dt  # bits per second

        # map to 0..3 (conservative thresholds; tweak if you want)
        if bps < 64_000:       lvl = 0
        elif bps < 512_000:    lvl = 1
        elif bps < 5_000_000:  lvl = 2
        else:                  lvl = 3

        self.vfd.set_wifi_level(lvl)
        self._net_prev_bytes = cur
        self._net_prev_t = now
        self.after(self.ms_net_meter, self._net_meter_tick)

    def _disk_meter_start(self):
        if not HAVE_PSUTIL:
            messagebox.showwarning("psutil", "Install psutil: pip install psutil")
            return
        if self.loop_disk_meter: return
        self.loop_disk_meter = True
        dio = psutil.disk_io_counters()
        self._disk_prev = (dio.read_bytes + dio.write_bytes)
        self._disk_prev_t = time.time()
        self._disk_meter_tick()

    def _disk_meter_stop(self):
        self.loop_disk_meter = False
        # HDD icon brightness → 0
        self.vfd.icon_brightness(0x00, 0)

    def _disk_meter_tick(self):
        if not self.loop_disk_meter: return
        dio = psutil.disk_io_counters()
        now = time.time()
        cur = dio.read_bytes + dio.write_bytes
        dt = max(1e-3, now - self._disk_prev_t)
        Bps = (cur - self._disk_prev) / dt  # bytes/s

        # map activity to brightness 0..6
        if   Bps < 64_000:        lvl = 0
        elif Bps < 256_000:       lvl = 1
        elif Bps < 1_000_000:     lvl = 2
        elif Bps < 4_000_000:     lvl = 3
        elif Bps < 16_000_000:    lvl = 4
        elif Bps < 64_000_000:    lvl = 5
        else:                     lvl = 6

        self.vfd.icon_brightness(0x00, lvl)  # HDD brightness
        self._disk_prev = cur
        self._disk_prev_t = now
        self.after(self.ms_disk_meter, self._disk_meter_tick)

    def _mem_meter_start(self):
        if not HAVE_PSUTIL:
            messagebox.showwarning("psutil", "Install psutil: pip install psutil")
            return
        if self.loop_mem_meter: return
        self.loop_mem_meter = True
        self._mem_meter_tick()

    def _mem_meter_stop(self):
        self.loop_mem_meter = False
        # USB icon brightness → 0
        self.vfd.icon_brightness(0x03, 0)

    def _mem_meter_tick(self):
        if not self.loop_mem_meter: return
        vm = psutil.virtual_memory()
        # map 0..100% → 0..6
        lvl = max(0, min(6, int(round(vm.percent / 100.0 * 6))))
        self.vfd.icon_brightness(0x03, lvl)  # USB brightness used as "RAM" meter
        self.after(self.ms_mem_meter, self._mem_meter_tick)

if __name__ == "__main__":
    App().mainloop()
