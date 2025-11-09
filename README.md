MD8800 VFD Control (GUI)

A tiny Python/Tkinter app to drive the Medion MD8800 / M18ST05A front-panel VFD over a USB-serial adapter. It lets you write text to the two 16-char lines, set/sync the clock, toggle all icons/LEDs, animate the 9×7 mini-matrix, and run a bunch of fun modes (plus a playable Snake game). Built for Windows (COM ports), also works on Linux (/dev/ttyUSB*).

Features

Connect @ 9600 8N2 and send ESC/RAW quickly (built-in console).

Text control: line 0/1, soft clear, CR, marquee, bounce.

Clock: 12/24-hour, move/stop, show/hide, sync from PC.

Brightness & icons: HDD/1394/CD/USB/Movie/TV/Music/Photo levels; record; email (white/red); speaker/mute; volume bars; red bars; bounding boxes.

Mini-matrix (9×7): live editor, presets (play/pause/heart/etc), per-pixel send.

Fun modes/macros: spinner, twinkle, rain, cylon, icon wave/pulse, icon carousel, clock-bars, stickman run, bouncy ball, Game of Life — all with per-mode FPS.

System meters (optional): net→red bars, disk→HDD icon, RAM→USB icon (via psutil).

Playable Snake: arrow keys or on-screen D-pad; score on text lines; adjustable speed.

Dark/Light theme and scrollable UI.

Install
pip install pyserial psutil   # psutil optional (for meters)

Run
python md8800_gui.py


Pick your COM port, Connect, then use the buttons/sliders.

Snake: press Start, use arrow keys (or on-screen arrows), Pause/Reset as needed.

Notes

If a matrix mode is running, starting another will stop the previous one (prevents clashes).

“Custom / RAW” lets you send ESC <hex> or arbitrary hex bytes for quick testing.

Protocol References / Thanks

LCDproc MD8800.c driver (command set)

spacerace/m18st05 (early tooling)

yetanothercarbot/medion-vfd (examples & inspiration)

(No official affiliation with Medion. Use at your own risk.)
