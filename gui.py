import time

import dolphin_memory_engine
from imgui_bundle import hello_imgui, imgui

from addresses import ADDRESSES, MemoryAddress

POLL_INTERVAL = 0.25     # seconds


# ── Per-widget state ──────────────────────────────────────────────────────────

class WidgetState:
    def __init__(self, min_val: int, max_val: int):
        self.min_val   = min_val
        self.max_val   = max_val
        self.slider    = min_val
        self.entry_buf = str(min_val)
        self.freeze    = False
        self.display   = "—"


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


# One WidgetState per address, keyed by the MemoryAddress object
states: dict[MemoryAddress, WidgetState] = {
    addr: WidgetState(addr.min_val, addr.max_val) for addr in ADDRESSES
}

status_text = "Status: —"
hook_error  = ""
last_poll   = 0.0


# ── Poll (runs every frame, throttled by POLL_INTERVAL) ──────────────────────

def _poll():
    global status_text, last_poll

    now = time.monotonic()
    if now - last_poll < POLL_INTERVAL:
        return
    last_poll = now

    status_text = f"Status: {dolphin_memory_engine.get_status()}"

    if not dolphin_memory_engine.is_hooked():
        for state in states.values():
            state.display = "—"
        return

    for addr, state in states.items():
        try:
            v = addr.read()
            digits = addr.hex_digits
            hex_part = f"  (0x{v:0{digits}X})" if digits is not None else ""
            state.display = f"{v}{hex_part}"
            if state.freeze:
                addr.write(_clamp(state.slider, addr.min_val, addr.max_val))
            else:
                state.slider = _clamp(v, addr.min_val, addr.max_val)
        except RuntimeError:
            state.display = "read error"


# ── Per-address widget ────────────────────────────────────────────────────────

def _draw_memory_widget(addr: MemoryAddress, state: WidgetState):
    imgui.push_id(addr.name)

    flags = imgui.TreeNodeFlags_.default_open
    if imgui.collapsing_header(f"{addr.name}   [{hex(addr.addr)}]", flags):

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
                addr.write(new_val)

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
                    addr.write(v)
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
        for state in states.values():
            state.display = "—"

    imgui.same_line()
    imgui.text(status_text)

    if hook_error:
        imgui.text_colored(imgui.ImVec4(1.0, 0.3, 0.3, 1.0), f"Hook error: {hook_error}")

    imgui.spacing()

    # ── Memory widgets ──
    for addr in ADDRESSES:
        _draw_memory_widget(addr, states[addr])


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    runner_params = hello_imgui.RunnerParams()
    runner_params.app_window_params.window_title = "Dolphin Memory Tool"
    runner_params.app_window_params.window_geometry.size = (560, 380)
    runner_params.callbacks.show_gui = _gui
    hello_imgui.run(runner_params)
