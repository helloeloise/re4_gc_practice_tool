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


# ── Address table ─────────────────────────────────────────────────────────────

ADDRESSES: list[MemoryAddress] = [
    MemoryAddress("Striker Ammunition", 0x80A53B03, AddrType.BYTE,    min_val=0,  max_val=255),
    MemoryAddress("Leon HP",            0x80284780, AddrType.WORD_BE, min_val=0,  max_val=2400),
]
