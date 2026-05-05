import struct
import time

import dolphin_memory_engine
from imgui_bundle import hello_imgui, imgui

AMMO_ADDR = 0x80A53B03   # 1 byte,  0–255
HP_ADDR   = 0x80284780   # 2 bytes, 0–2400

POLL_INTERVAL = 0.25     # seconds


# ── Memory helpers ────────────────────────────────────────────────────────────

def _read_word_be(addr: int) -> int:
    raw = dolphin_memory_engine.read_bytes(addr, 2)
    return struct.unpack(">H", raw)[0]


def _write_word_be(addr: int, value: int):
    dolphin_memory_engine.write_bytes(addr, struct.pack(">H", value))


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


# ── Per-widget state ──────────────────────────────────────────────────────────

class WidgetState:
    def __init__(self, min_val: int, max_val: int):
        self.min_val   = min_val
        self.max_val   = max_val
        self.slider    = min_val
        self.entry_buf = str(min_val)
        self.freeze    = False
        self.display   = "—"


ammo_state  = WidgetState(0, 255)
hp_state    = WidgetState(0, 2400)

status_text = "Status: —"
hook_error  = ""
last_poll   = 0.0


# ── Writers ───────────────────────────────────────────────────────────────────

def _write_ammo(v: int):
    try:
        dolphin_memory_engine.write_byte(AMMO_ADDR, v)
    except RuntimeError:
        pass


def _write_hp(v: int):
    try:
        _write_word_be(HP_ADDR, v)
    except RuntimeError:
        pass


# ── Poll (runs every frame, throttled by POLL_INTERVAL) ──────────────────────

def _poll():
    global status_text, last_poll

    now = time.monotonic()
    if now - last_poll < POLL_INTERVAL:
        return
    last_poll = now

    status_text = f"Status: {dolphin_memory_engine.get_status()}"

    if not dolphin_memory_engine.is_hooked():
        ammo_state.display = "—"
        hp_state.display   = "—"
        return

    # Ammo (1 byte)
    try:
        v = dolphin_memory_engine.read_byte(AMMO_ADDR)
        ammo_state.display = f"{v}  (0x{v:02X})"
        if ammo_state.freeze:
            _write_ammo(_clamp(ammo_state.slider, 0, 255))
        else:
            ammo_state.slider = _clamp(v, 0, 255)
    except RuntimeError:
        ammo_state.display = "read error"

    # HP (2 bytes big-endian)
    try:
        v = _read_word_be(HP_ADDR)
        hp_state.display = f"{v}  (0x{v:04X})"
        if hp_state.freeze:
            _write_hp(_clamp(hp_state.slider, 0, 2400))
        else:
            hp_state.slider = _clamp(v, 0, 2400)
    except RuntimeError:
        hp_state.display = "read error"


# ── Per-address widget ────────────────────────────────────────────────────────

def _draw_memory_widget(label: str, addr: int, state: WidgetState, write_fn):
    imgui.push_id(label)

    flags = imgui.TreeNodeFlags_.default_open
    if imgui.collapsing_header(f"{label}   [{hex(addr)}]", flags):

        # Current value + Freeze on the same line
        imgui.text(f"Current value:  {state.display}")
        imgui.same_line(spacing=20)
        changed, state.freeze = imgui.checkbox("Freeze", state.freeze)

        # Full-width slider
        imgui.set_next_item_width(-1)
        changed, new_val = imgui.slider_int(
            "##slider", state.slider, state.min_val, state.max_val
        )
        if changed:
            state.slider    = new_val
            state.entry_buf = str(new_val)
            if dolphin_memory_engine.is_hooked():
                write_fn(new_val)

        # Exact-value entry + Apply button
        imgui.text(f"Set exact ({state.min_val}–{state.max_val}):")
        imgui.same_line()
        imgui.set_next_item_width(90)
        changed, state.entry_buf = imgui.input_text("##entry", state.entry_buf)
        imgui.same_line()
        if imgui.button("Apply"):
            try:
                v = _clamp(int(state.entry_buf), state.min_val, state.max_val)
                state.slider    = v
                state.entry_buf = str(v)
                if dolphin_memory_engine.is_hooked():
                    write_fn(v)
            except ValueError:
                pass

        imgui.spacing()

    imgui.pop_id()


# ── Main GUI callback (called every frame by hello_imgui) ─────────────────────

def _gui():
    global hook_error
    _poll()

    # ── Connection ──
    imgui.separator_text("Connection")

    if imgui.button("Hook"):
        hook_error = ""
        try:
            dolphin_memory_engine.hook()
        except Exception as exc:
            hook_error = str(exc)

    imgui.same_line()

    if imgui.button("Unhook"):
        hook_error = ""
        try:
            dolphin_memory_engine.un_hook()
        except Exception:
            pass
        ammo_state.display = "—"
        hp_state.display   = "—"

    imgui.same_line()
    imgui.text(status_text)

    if hook_error:
        imgui.text_colored(imgui.ImVec4(1.0, 0.3, 0.3, 1.0), f"Hook error: {hook_error}")

    imgui.spacing()

    # ── Memory widgets ──
    _draw_memory_widget("Striker Ammunition", AMMO_ADDR, ammo_state, _write_ammo)
    _draw_memory_widget("Leon HP",            HP_ADDR,   hp_state,   _write_hp)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    runner_params = hello_imgui.RunnerParams()
    runner_params.app_window_params.window_title = "Dolphin Memory Tool"
    runner_params.app_window_params.window_geometry.size = (560, 380)
    runner_params.callbacks.show_gui = _gui
    hello_imgui.run(runner_params)
