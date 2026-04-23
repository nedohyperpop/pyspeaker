import ctypes
import sys
import time
import os
import random
import atexit
import signal
import threading
import subprocess
import msvcrt

WATCHDOG_FILE = "watchdog.stop"

# ---------------- WATCHDOG ----------------
if "--watchdog" in sys.argv:
    try:
        parent_pid = int(sys.argv[-1])
    except:
        sys.exit()

    dll_path = os.path.join(os.path.dirname(__file__), "inpoutx64.dll")

    try:
        p = ctypes.WinDLL(dll_path)
    except:
        sys.exit()

    while True:
        time.sleep(0.1)

        if os.path.exists(WATCHDOG_FILE):
            break

        handle = ctypes.windll.kernel32.OpenProcess(1, 0, parent_pid)

        if not handle:
            try:
                val = p.Inp32(0x61)
                p.Out32(0x61, val & ~3)
            except:
                pass
            break
        else:
            ctypes.windll.kernel32.CloseHandle(handle)

    sys.exit()

# ---------------- DLL ----------------
dll_path = os.path.join(os.path.dirname(__file__), "inpoutx64.dll")

if not os.path.exists(dll_path):
    print("ERROR: inpoutx64.dll not found")
    sys.exit()

try:
    p = ctypes.WinDLL(dll_path)
except Exception as e:
    print("DLL load error:", e)
    sys.exit()

# гасим зависший звук при старте
try:
    val = p.Inp32(0x61)
    p.Out32(0x61, val & ~3)
except:
    pass

# запуск watchdog
subprocess.Popen(
    [sys.executable, os.path.abspath(sys.argv[0]), "--watchdog", str(os.getpid())],
    creationflags=0x08000000  # без окна
)

# ---------------- STATE ----------------
running = True
loop = False
speed = 1.0
lock = threading.Lock()

# ---------------- NOTES ----------------
NOTES = {
    "C": 261, "C#": 277, "D": 293, "D#": 311,
    "E": 329, "F": 349, "F#": 369, "G": 392,
    "G#": 415, "A": 440, "A#": 466, "B": 493
}

def note_to_freq(note):
    try:
        if note[1] == "#":
            key = note[:2]
            octave = int(note[2:])
        else:
            key = note[0]
            octave = int(note[1:])
        base = NOTES.get(key)
        if base is None:
            return None
        return int(base * (2 ** (octave - 4)))
    except:
        return None

# ---------------- SAFE STOP ----------------
def stop_speaker():
    try:
        val = p.Inp32(0x61)
        p.Out32(0x61, val & ~3)
    except:
        pass

def safe_exit():
    global running
    with lock:
        running = False
    stop_speaker()

atexit.register(stop_speaker)

def handle_exit(sig, frame):
    safe_exit()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)
try:
    signal.signal(signal.SIGTERM, handle_exit)
except:
    pass

# ---------------- BEEP ----------------
def beep(freq, dur):
    global running

    stop_speaker()

    if freq <= 0:
        end = time.perf_counter() + dur
        while time.perf_counter() < end:
            if not running:
                return
            time.sleep(0.001)
        return

    try:
        div = int(1193182 / freq)
    except:
        return

    try:
        p.Out32(0x43, 0xB6)
        p.Out32(0x42, div & 0xFF)
        p.Out32(0x42, (div >> 8) & 0xFF)

        tmp = p.Inp32(0x61)
        p.Out32(0x61, tmp | 3)

        end = time.perf_counter() + dur
        while time.perf_counter() < end:
            if not running:
                stop_speaker()
                return
            time.sleep(0.001)

        stop_speaker()
    except:
        stop_speaker()

# ---------------- COMMAND EXEC ----------------
def run_sequence(seq):
    global speed, loop, running

    stop_speaker()

    while True:
        if not running:
            return

        for cell in seq:
            if not running:
                return

            if cell.startswith("speed="):
                try:
                    speed = float(cell.split("=", 1)[1])
                except:
                    print("Bad speed:", cell)
                continue

            if cell == "loop=on":
                loop = True
                continue
            if cell == "loop=off":
                loop = False
                continue

            repeat = 1
            if "x" in cell:
                try:
                    parts = cell.split("x", 1)
                    cell = parts[0]
                    repeat = int(parts[1])
                except:
                    print("Bad repeat:", cell)
                    continue

            if cell.startswith("rand-"):
                try:
                    dur = int(cell.split("-", 1)[1]) / 1000
                except:
                    print("Bad rand:", cell)
                    continue

                for _ in range(repeat):
                    if not running:
                        return
                    beep(random.randint(300, 1500), dur * speed)
                continue

            if "-" not in cell:
                print("Bad format:", cell)
                continue

            try:
                freq_part, dur_part = cell.split("-", 1)
                dur = int(dur_part) / 1000
            except:
                print("Error:", cell)
                continue

            if freq_part[0].isalpha():
                freq = note_to_freq(freq_part.upper())
                if freq is None:
                    print("Bad note:", freq_part)
                    continue
            else:
                try:
                    freq = int(freq_part)
                except:
                    print("Bad freq:", freq_part)
                    continue

            freq = max(0, min(freq, 20000))

            for _ in range(repeat):
                if not running:
                    return
                beep(freq, dur * speed)

        if not loop:
            break

# ---------------- INPUT THREAD ----------------
def input_thread():
    global running, loop

    buffer = ""

    while True:
        if not running:
            return

        if msvcrt.kbhit():
            ch = msvcrt.getwch()

            if ch == "\r":
                print()  # перенос строки
                cmd = buffer.strip()
                buffer = ""

                if cmd == "stop":
                    running = False
                    stop_speaker()
                    print("STOP")

                elif cmd == "exit":
                    safe_exit()
                    return

                elif cmd == "loop=on":
                    loop = True
                    print("loop ON")

                elif cmd == "loop=off":
                    loop = False
                    print("loop OFF")

                elif cmd == "kw":
                    open(WATCHDOG_FILE, "w").close()
                    print("watchdogs stopped")

            elif ch == "\b":
                if buffer:
                    buffer = buffer[:-1]
                    print("\b \b", end="", flush=True)
            else:
                buffer += ch
                print(ch, end="", flush=True)

        time.sleep(0.005)

# ---------------- HELP ----------------
def show_help(script):
    print(f"""
Usage:
  {script} <cells>

Format:
  440-100        freq-duration(ms)
  A4-100         note-duration
  0-200          pause
  100-100x3      repeat
  rand-200       random freq
  speed=0.5      speed multiplier
  loop=on        enable loop
  loop=off       disable loop

Commands (runtime):
  stop           stop current playback
  exit           exit program
  kw             (kill watchdog) stop all watchdog processes

Example:
  {script} loop=on A4-100 C5-100 E5-200 0-100
""")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    script = os.path.basename(sys.argv[0])
    args = sys.argv[1:]

    if len(args) == 0 or args[0] == "help":
        show_help(script)
        sys.exit()

    if args[0] == "stop":
        stop_speaker()
        sys.exit()

    threading.Thread(target=input_thread, daemon=True).start()

    try:
        run_sequence(args)
    finally:
        stop_speaker()