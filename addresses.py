import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any

import dolphin_memory_engine


class AddrType(Enum):
    BYTE      = "byte"       # 1 byte,  unsigned int  (0–255)
    WORD_BE   = "word_be"    # 2 bytes, big-endian unsigned int
    DWORD_BE  = "dword_be"   # 4 bytes, big-endian unsigned int
    FLOAT_BE  = "float_be"   # 4 bytes, big-endian IEEE 754 float
    DOUBLE_BE = "double_be"  # 8 bytes, big-endian IEEE 754 double
    STRING    = "string"     # UTF-8 string (null-terminated, or fixed length via 'length')
    AOB       = "aob"        # raw byte sequence (requires 'length')
    STRUCT    = "struct"     # raw bytes – composite type (requires 'length')
    ARRAY     = "array"      # homogeneous list (requires 'length' + 'element_type')


# ── Fixed byte sizes for numeric/fixed-width types ───────────────────────────

_FIXED_SIZE: dict[AddrType, int] = {
    AddrType.BYTE:      1,
    AddrType.WORD_BE:   2,
    AddrType.DWORD_BE:  4,
    AddrType.FLOAT_BE:  4,
    AddrType.DOUBLE_BE: 8,
}

# struct format character for each fixed-width type (used by ARRAY)
_STRUCT_FMT: dict[AddrType, str] = {
    AddrType.BYTE:      "B",
    AddrType.WORD_BE:   "H",
    AddrType.DWORD_BE:  "I",
    AddrType.FLOAT_BE:  "f",
    AddrType.DOUBLE_BE: "d",
}


@dataclass(frozen=True)
class MemoryAddress:
    name:         str
    addr:         int
    type:         AddrType
    min_val:      int | float | None = None  # numeric types: slider/entry lower bound
    max_val:      int | float | None = None  # numeric types: slider/entry upper bound
    length:       int | None = None          # STRING: max bytes; AOB/STRUCT: byte count; ARRAY: element count
    element_type: AddrType | None = None     # ARRAY: type of each element (must be fixed-width)
    category:     str = ""                   # display category for GUI filtering
    inc_buttons:  bool = False               # show – / + step buttons next to the entry

    # ── Read ──────────────────────────────────────────────────────────────────

    def read(self) -> Any:
        t = self.type
        if t == AddrType.BYTE:
            return dolphin_memory_engine.read_byte(self.addr)
        if t == AddrType.WORD_BE:
            return struct.unpack(">H", dolphin_memory_engine.read_bytes(self.addr, 2))[0]
        if t == AddrType.DWORD_BE:
            return struct.unpack(">I", dolphin_memory_engine.read_bytes(self.addr, 4))[0]
        if t == AddrType.FLOAT_BE:
            return struct.unpack(">f", dolphin_memory_engine.read_bytes(self.addr, 4))[0]
        if t == AddrType.DOUBLE_BE:
            return struct.unpack(">d", dolphin_memory_engine.read_bytes(self.addr, 8))[0]
        if t == AddrType.STRING:
            n = self.length or 64
            raw = dolphin_memory_engine.read_bytes(self.addr, n)
            null = raw.find(b"\x00")
            chunk = raw[:null] if null != -1 else raw
            return chunk.decode("utf-8", errors="replace")
        if t in (AddrType.AOB, AddrType.STRUCT):
            if self.length is None:
                raise ValueError(f"{self.name}: 'length' is required for {t.value}")
            return dolphin_memory_engine.read_bytes(self.addr, self.length)
        if t == AddrType.ARRAY:
            if self.length is None or self.element_type is None:
                raise ValueError(f"{self.name}: 'length' and 'element_type' are required for ARRAY")
            elem_size = _FIXED_SIZE.get(self.element_type)
            if elem_size is None:
                raise ValueError(f"ARRAY element_type must be a fixed-width type, got {self.element_type}")
            raw = dolphin_memory_engine.read_bytes(self.addr, self.length * elem_size)
            fmt = _STRUCT_FMT[self.element_type]
            return list(struct.unpack_from(f">{self.length}{fmt}", raw))
        raise NotImplementedError(t)

    # ── Write ─────────────────────────────────────────────────────────────────

    def write(self, value: Any):
        t = self.type
        if t == AddrType.BYTE:
            dolphin_memory_engine.write_byte(self.addr, int(value))
        elif t == AddrType.WORD_BE:
            dolphin_memory_engine.write_bytes(self.addr, struct.pack(">H", int(value)))
        elif t == AddrType.DWORD_BE:
            dolphin_memory_engine.write_bytes(self.addr, struct.pack(">I", int(value)))
        elif t == AddrType.FLOAT_BE:
            dolphin_memory_engine.write_bytes(self.addr, struct.pack(">f", float(value)))
        elif t == AddrType.DOUBLE_BE:
            dolphin_memory_engine.write_bytes(self.addr, struct.pack(">d", float(value)))
        elif t == AddrType.STRING:
            encoded = str(value).encode("utf-8")
            if self.length:
                encoded = encoded[: self.length].ljust(self.length, b"\x00")
            else:
                encoded += b"\x00"
            dolphin_memory_engine.write_bytes(self.addr, encoded)
        elif t in (AddrType.AOB, AddrType.STRUCT):
            dolphin_memory_engine.write_bytes(self.addr, bytes(value))
        elif t == AddrType.ARRAY:
            if self.length is None or self.element_type is None:
                raise ValueError(f"{self.name}: 'length' and 'element_type' are required for ARRAY")
            fmt = _STRUCT_FMT[self.element_type]
            dolphin_memory_engine.write_bytes(
                self.addr, struct.pack(f">{self.length}{fmt}", *value)
            )
        else:
            raise NotImplementedError(t)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def hex_digits(self) -> int | None:
        """Hex digits needed to display a value of this type, or None for variable-width types."""
        size = _FIXED_SIZE.get(self.type)
        return size * 2 if size is not None else None


# ── Inventory item struct support ─────────────────────────────────────────────

@dataclass(frozen=True)
class FieldDef:
    name:        str
    offset:      int
    type:        AddrType
    min_val:     int | float | None = None
    max_val:     int | float | None = None
    read_only:   bool = False
    inc_buttons: bool = False  # show – / + step buttons next to the entry


@dataclass(frozen=True)
class InventoryItem:
    name:      str
    base_addr: int
    category:  str = "Inventory"
    fields:    tuple[FieldDef, ...] = ()

    def field_addr(self, f: "FieldDef") -> MemoryAddress:
        """Return a MemoryAddress for an individual field of this item."""
        return MemoryAddress(
            name=f.name,
            addr=self.base_addr + f.offset,
            type=f.type,
            min_val=f.min_val,
            max_val=f.max_val,
        )


# ── Address table ─────────────────────────────────────────────────────────────

ADDRESSES: list[MemoryAddress] = [
    MemoryAddress("Slot 0 Item ID",      0x80A536EF, AddrType.BYTE, min_val=0, max_val=255, category="Inventory", inc_buttons=True),
    MemoryAddress("Leon HP",             0x80284780, AddrType.WORD_BE, min_val=0, max_val=2400,     category="Player"),
    MemoryAddress("Pesetas",             0x80284774, AddrType.DWORD_BE, min_val=0, max_val=99999999, category="Currency"),
]


# ── Inventory items ───────────────────────────────────────────────────────────

# Maps item ID byte value → human-readable name
ITEM_NAMES: dict[int, str] = {
    0x00: "Magnum Ammo",
    0x01: "Hand Grenade",
    0x02: "Incendiary Grenade",
    0x03: "Matilda",
    0x04: "Handgun Ammo",
    0x05: "First Aid Spray",
    0x06: "Green Herb",
    0x07: "Rifle Ammo",
    0x08: "Chicken Egg",
    0x09: "Brown Chicken Egg",
    0x0A: "Gold Chicken Egg",
    0x0E: "Flash Grenade",
    0x12: "Green Herb x2",
    0x13: "Green Herb x3",
    0x14: "Mixed Herbs (G+R)",
    0x15: "Mixed Herbs (G+R+Y)",
    0x16: "Mixed Herbs (G+Y)",
    0x17: "Rocket Launcher (Special)",
    0x18: "Shotgun Shells",
    0x19: "Red Herb",
    0x1A: "Handcannon Ammo",
    0x1B: "Wristwatch",
    0x1C: "Yellow Herb",
    0x1D: "Stone Tablet",
    0x1E: "Lion Ornament",
    0x1F: "Goat Ornament",
    0x20: "TMP Ammo",
    0x21: "Punisher",
    0x22: "Punisher w/ Silencer",
    0x23: "Handgun",
    0x24: "Handgun w/ Silencer",
    0x25: "Red9",
    0x26: "Red9 w/ Stock",
    0x27: "Blacktail",
    0x28: "Blacktail w/ Silencer",
    0x29: "Broken Butterfly",
    0x2A: "Killer7",
    0x2B: "Killer7 w/ Silencer",
    0x2C: "Shotgun",
    0x2D: "Striker",
    0x2E: "Rifle",
    0x2F: "Rifle (semi-auto)",
    0x30: "TMP",
    0x31: "TMP w/ Silencer",
    0x32: "TMP w/ Stock",
    0x33: "TMP w/ Silencer & Stock",
    0x34: "Chicago Typewriter",
    0x35: "Rocket Launcher",
    0x36: "Mine Thrower",
    0x37: "Handcannon",
    0x38: "Combat Knife",
    0x3E: "Custom TMP",
    0x3F: "Silencer (Handgun)",
    0x40: "Punisher",
    0x42: "Stock (Red9)",
    0x43: "Stock (TMP)",
    0x44: "Scope (Rifle)",
    0x45: "Scope (semi-auto Rifle)",
    0x46: "Mine-Darts",
    0x47: "Mine-Darts (Homing)",
    0x52: "Krauser's Bow",
    0x6D: "Infinite Launcher",
    0x94: "Riot Gun",
    0xA8: "Mixed Herbs (R+Y)",
    0xC5: "Infrared Scope",
}

_INV_BASE   = 0x80A536EF
_INV_STRIDE = 14          # struct size in bytes (confirmed from byte sequence)
_INV_SLOTS  = 256

_INV_FIELDS = (
    FieldDef("Item ID",  offset=0x00, type=AddrType.BYTE, min_val=0, max_val=255, inc_buttons=True),
    FieldDef("Quantity", offset=0x02, type=AddrType.BYTE, min_val=0, max_val=255),
    FieldDef("Ammo",     offset=0x08, type=AddrType.BYTE, min_val=0, max_val=255),
    FieldDef("Slot X",   offset=0x09, type=AddrType.BYTE, min_val=0, max_val=255),
    FieldDef("Slot Y",   offset=0x0A, type=AddrType.BYTE, min_val=0, max_val=255),
)

ITEMS: list[InventoryItem] = [
    InventoryItem(
        name=f"Slot {i}  [{_INV_BASE + i * _INV_STRIDE:#010x}]",
        base_addr=_INV_BASE + i * _INV_STRIDE,
        category="Inventory",
        fields=_INV_FIELDS,
    )
    for i in range(_INV_SLOTS)
]

DEBUG_ITEMS: list[InventoryItem] = []
