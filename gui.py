import time

import dolphin_memory_engine
from imgui_bundle import hello_imgui, imgui

from addresses import ADDRESSES, DEBUG_ITEMS, FieldDef, InventoryItem, ITEM_NAMES, ITEMS, MemoryAddress

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

# Pre-built MemoryAddress objects for each inventory item field
_item_addrs: dict[InventoryItem, dict[str, MemoryAddress]] = {
    item: {f.name: item.field_addr(f) for f in item.fields}
    for item in [*ITEMS, *DEBUG_ITEMS]
}

# Widget states and display strings for inventory item fields
# keyed by (item, field_name)
item_states:   dict[tuple, WidgetState] = {}
item_displays: dict[tuple, str] = {}
for _item in [*ITEMS, *DEBUG_ITEMS]:
    for _f in _item.fields:
        _key = (_item, _f.name)
        item_displays[_key] = "\u2014"
        if not _f.read_only and _f.min_val is not None and _f.max_val is not None:
            item_states[_key] = WidgetState(_f.min_val, _f.max_val)

# Tracks the current Item ID byte for each inventory slot (updated each poll)
slot_item_ids: dict[InventoryItem, int] = {item: 0 for item in ITEMS}

status_text = "Status: —"
hook_error  = ""
last_poll   = 0.0
search_buf  = ""


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
            state.display = "\u2014"
        for key in item_displays:
            item_displays[key] = "\u2014"
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

    for item in [*ITEMS, *DEBUG_ITEMS]:
        for f in item.fields:
            ma  = _item_addrs[item][f.name]
            key = (item, f.name)
            try:
                v      = ma.read()
                digits = ma.hex_digits
                hex_part = f"  (0x{v:0{digits}X})" if digits is not None else ""
                item_displays[key] = f"{v}{hex_part}"
                if item in slot_item_ids and f.name == "Item ID":
                    slot_item_ids[item] = v
                if key in item_states:
                    state = item_states[key]
                    if state.freeze:
                        ma.write(_clamp(state.slider, f.min_val, f.max_val))
                    else:
                        state.slider = _clamp(v, f.min_val, f.max_val)
            except RuntimeError:
                item_displays[key] = "read error"


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

        if addr.inc_buttons:
            imgui.same_line()
            dec = imgui.button(" - ") or imgui.is_key_pressed(imgui.Key.page_down)
            if dec:
                v = _clamp(state.slider - 1, state.min_val, state.max_val)
                state.slider    = v
                state.entry_buf = str(v)
                if dolphin_memory_engine.is_hooked():
                    addr.write(v)
            imgui.same_line()
            inc = imgui.button(" + ") or imgui.is_key_pressed(imgui.Key.page_up)
            if inc:
                v = _clamp(state.slider + 1, state.min_val, state.max_val)
                state.slider    = v
                state.entry_buf = str(v)
                if dolphin_memory_engine.is_hooked():
                    addr.write(v)

        imgui.spacing()

    imgui.pop_id()


# ── Inventory item widget ────────────────────────────────────────────────────

def _draw_inventory_item(item: InventoryItem):
    imgui.push_id(item.name)

    item_id   = slot_item_ids.get(item, 0)
    item_name = ITEM_NAMES.get(item_id, f"Unknown ({item_id:#04x})")
    label     = f"{item_name}   [{hex(item.base_addr)}]"

    if imgui.tree_node_ex("hdr", imgui.TreeNodeFlags_.collapsing_header, label):
        for f in item.fields:
            key     = (item, f.name)
            display = item_displays.get(key, "\u2014")
            imgui.push_id(f.name)

            if key not in item_states:
                # Read-only field – just show current value
                imgui.text(f"{f.name}:  {display}")
            else:
                state = item_states[key]

                imgui.text(f"{f.name}:  {display}")
                imgui.same_line(spacing=20)
                _, state.freeze = imgui.checkbox("Freeze", state.freeze)

                imgui.set_next_item_width(-1)
                changed, new_val = imgui.slider_int(
                    "##slider", state.slider, f.min_val, f.max_val
                )
                if changed:
                    state.slider    = new_val
                    state.entry_buf = str(new_val)
                    if dolphin_memory_engine.is_hooked():
                        _item_addrs[item][f.name].write(new_val)

                imgui.text(f"Set exact ({f.min_val}\u2013{f.max_val}):")
                imgui.same_line()
                imgui.set_next_item_width(90)
                changed, state.entry_buf = imgui.input_text("##entry", state.entry_buf)
                imgui.same_line()
                if imgui.button("Apply"):
                    try:
                        v = _clamp(int(state.entry_buf), f.min_val, f.max_val)
                        state.slider    = v
                        state.entry_buf = str(v)
                        if dolphin_memory_engine.is_hooked():
                            _item_addrs[item][f.name].write(v)
                    except ValueError:
                        pass

                if f.inc_buttons:
                    imgui.same_line()
                    if imgui.button(" - "):
                        v = _clamp(state.slider - 1, f.min_val, f.max_val)
                        state.slider    = v
                        state.entry_buf = str(v)
                        if dolphin_memory_engine.is_hooked():
                            _item_addrs[item][f.name].write(v)
                    imgui.same_line()
                    if imgui.button(" + "):
                        v = _clamp(state.slider + 1, f.min_val, f.max_val)
                        state.slider    = v
                        state.entry_buf = str(v)
                        if dolphin_memory_engine.is_hooked():
                            _item_addrs[item][f.name].write(v)

            imgui.spacing()
            imgui.pop_id()

        imgui.spacing()

    imgui.pop_id()


# ── Main GUI callback (called every frame by hello_imgui) ─────────────────────

def _gui():
    global hook_error, search_buf
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

    # ── Search bar ──
    imgui.set_next_item_width(-1)
    _, search_buf = imgui.input_text_with_hint("##search", "Search addresses...", search_buf)

    imgui.spacing()

    # ── Category tabs + memory widgets ──
    query = search_buf.lower().strip()
    categories = ["All"] + sorted(
        {addr.category for addr in ADDRESSES if addr.category}
        | {item.category for item in [*ITEMS, *DEBUG_ITEMS] if item.category}
    )

    if imgui.begin_tab_bar("##categories"):
        for cat in categories:
            if imgui.begin_tab_item(cat)[0]:
                visible_addrs = [
                    addr for addr in ADDRESSES
                    if (cat == "All" or addr.category == cat)
                    and (not query or query in addr.name.lower())
                ]
                visible_items = [
                    item for item in [*ITEMS, *DEBUG_ITEMS]
                    if (cat == "All" or item.category == cat)
                    and (not query or query in item.name.lower()
                         or query in ITEM_NAMES.get(slot_item_ids.get(item, 0), "").lower())
                    and (
                        item.category != "Inventory"
                        or not dolphin_memory_engine.is_hooked()
                        or (slot_item_ids.get(item, 0) != 0 and slot_item_ids.get(item, 0) in ITEM_NAMES)
                    )
                ]
                if not visible_addrs and not visible_items:
                    imgui.text_disabled("No matches.")
                else:
                    for addr in visible_addrs:
                        _draw_memory_widget(addr, states[addr])
                    for item in visible_items:
                        _draw_inventory_item(item)
                imgui.end_tab_item()
        imgui.end_tab_bar()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    runner_params = hello_imgui.RunnerParams()
    runner_params.app_window_params.window_title = "Dolphin Memory Tool"
    runner_params.app_window_params.window_geometry.size = (560, 380)
    runner_params.callbacks.show_gui = _gui
    hello_imgui.run(runner_params)
