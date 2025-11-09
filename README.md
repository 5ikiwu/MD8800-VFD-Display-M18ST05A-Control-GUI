# MD8800 VFD Control (GUI)

A Python/Tkinter app for the **Medion MD8800 / M18ST05A** front-panel VFD.
Control text lines, clock, icon LEDs, and the 9×7 mini-matrix — with built-in fun modes and a playable **Snake** game. Works on Windows (COM ports) and Linux (`/dev/ttyUSB*`) via USB-serial (CH340/CP2102/etc) at **9600 8N2**.

---

## ✨ Features

* **Text control:** write to line 0/1, soft-clear, CR, marquee, bounce.
* **Clock:** 12/24-hour, move/stop, show, **sync from PC**.
* **Brightness & icons:** HDD/1394/CD/USB/Movie/TV/Music/Photo levels; record; email (white/red); speaker/mute; volume bars; red bars; bounding boxes.
* **Mini-matrix (9×7):** live pixel editor, presets (play/pause/heart…), per-pixel send.
* **Fun modes/macros (per-mode FPS):** spinner, twinkle, rain, cylon, icon wave/pulse, icon carousel, clock-bars, stickman run, bouncy ball, Game of Life.
* **System meters (optional):** net → red bars, disk → HDD icon, RAM → USB icon (via `psutil`).
* **Playable Snake:** arrow keys or on-screen D-pad; score on text lines; adjustable speed.
* **Dark/Light theme** and **scrollable UI**.

---

## 📦 Install

```bash
# Python 3.9+ recommended
pip install pyserial psutil   # psutil optional (for system meters)
```

---

## ▶️ Run

```bash
python md8800_gui.py
```

1. Select your **COM** port → **Connect**.
2. Use the panels to send text, toggle icons, edit the mini-matrix, or start fun modes.

**Snake controls**

* Start/Pause/Reset buttons in the **Games** section
* **Arrow keys** or on-screen **D-pad**
* FPS spinner to change game speed

---

## 🔧 Notes

* Device serial: **9600 baud, 8N2** (no parity, two stop bits).
* Starting a mini-matrix mode automatically stops the previous one to avoid collisions.
* Use **Custom / RAW** to send `ESC <hex>` or arbitrary hex bytes for quick testing.

---

## 🙌 Credits / References

* LCDproc driver: `[MD8800.c](https://github.com/lcdproc/lcdproc/blob/master/server/drivers/MD8800.c)` (command set)
* `[spacerace/m18st05](https://github.com/spacerace/m18st05)` (early tooling)
* `[yetanothercarbot/medion-vfd](https://github.com/yetanothercarbot/medion-vfd)` (examples & inspiration)

> Not affiliated with Medion. Use at your own risk.
