"""
Memory System for Apple I Emulator
Provides RAM, ROM, and memory-mapped I/O support.

Ported from jscrane/r65emu (https://github.com/jscrane/r65emu)
"""

from typing import Callable, Optional, List
from abc import ABC, abstractmethod


class MemoryDevice(ABC):
    """
    Abstract base class for memory-mapped devices.
    """

    def __init__(self, size: int, base: int = 0, readonly: bool = False):
        self.size = size
        self.base = base
        self.readonly = readonly

    @abstractmethod
    def read(self, address: int) -> int:
        """Read a byte from the device."""
        pass

    @abstractmethod
    def write(self, address: int, value: int):
        """Write a byte to the device."""
        pass

    def contains(self, address: int) -> bool:
        """Check if this device handles the given address."""
        return self.base <= address < self.base + self.size


class RAM(MemoryDevice):
    """
    Random Access Memory device.
    """

    def __init__(self, size: int, base: int = 0):
        super().__init__(size, base, readonly=False)
        self._data = bytearray(size)

    def read(self, address: int) -> int:
        offset = address - self.base
        if 0 <= offset < self.size:
            return self._data[offset]
        return 0

    def write(self, address: int, value: int):
        offset = address - self.base
        if 0 <= offset < self.size:
            self._data[offset] = value & 0xFF

    def clear(self):
        """Clear all RAM to zeros."""
        self._data = bytearray(self.size)

    def load(self, data: bytes, offset: int = 0):
        """Load data into RAM at the given offset."""
        for i, byte in enumerate(data):
            if offset + i < self.size:
                self._data[offset + i] = byte


class ROM(MemoryDevice):
    """
    Read-Only Memory device.
    """

    def __init__(self, data: bytes, base: int = 0):
        super().__init__(len(data), base, readonly=True)
        self._data = bytes(data)

    def read(self, address: int) -> int:
        offset = address - self.base
        if 0 <= offset < self.size:
            return self._data[offset]
        return 0

    def write(self, address: int, value: int):
        # ROM is read-only, ignore writes
        pass

    @classmethod
    def from_file(cls, filename: str, base: int = 0) -> 'ROM':
        """Load ROM from a binary file."""
        with open(filename, 'rb') as f:
            data = f.read()
        return cls(data, base)

    @classmethod
    def from_hex(cls, hex_data: List[int], base: int = 0) -> 'ROM':
        """Create ROM from a list of byte values."""
        return cls(bytes(hex_data), base)


class Memory:
    """
    Memory manager that handles address decoding and device mapping.

    Supports multiple memory-mapped devices with priority-based addressing.
    """

    def __init__(self, size: int = 0x10000):
        self.size = size
        self._devices: List[MemoryDevice] = []
        self._read_handlers: dict = {}
        self._write_handlers: dict = {}

    def add_device(self, device: MemoryDevice):
        """Add a memory-mapped device."""
        self._devices.append(device)
        # Sort by base address (descending) for priority
        self._devices.sort(key=lambda d: d.base, reverse=True)

    def remove_device(self, device: MemoryDevice):
        """Remove a memory-mapped device."""
        if device in self._devices:
            self._devices.remove(device)

    def register_read_handler(self, address: int, handler: Callable[[], int]):
        """Register a custom read handler for a specific address."""
        self._read_handlers[address] = handler

    def register_write_handler(self, address: int, handler: Callable[[int], None]):
        """Register a custom write handler for a specific address."""
        self._write_handlers[address] = handler

    def read(self, address: int) -> int:
        """Read a byte from memory."""
        address = address & 0xFFFF

        # Check for custom handler
        if address in self._read_handlers:
            return self._read_handlers[address]()

        # Find device that contains this address
        for device in self._devices:
            if device.contains(address):
                return device.read(address)

        # No device found, return 0xFF (open bus)
        return 0xFF

    def write(self, address: int, value: int):
        """Write a byte to memory."""
        address = address & 0xFFFF
        value = value & 0xFF

        # Check for custom handler
        if address in self._write_handlers:
            self._write_handlers[address](value)
            return

        # Find device that contains this address
        for device in self._devices:
            if device.contains(address):
                device.write(address, value)
                return

    def read_word(self, address: int) -> int:
        """Read a 16-bit word (little-endian)."""
        lo = self.read(address)
        hi = self.read((address + 1) & 0xFFFF)
        return (hi << 8) | lo

    def write_word(self, address: int, value: int):
        """Write a 16-bit word (little-endian)."""
        self.write(address, value & 0xFF)
        self.write((address + 1) & 0xFFFF, (value >> 8) & 0xFF)

    def load(self, data: bytes, address: int):
        """Load data into memory at the specified address."""
        for i, byte in enumerate(data):
            self.write(address + i, byte)

    def dump(self, start: int, length: int) -> bytes:
        """Dump a region of memory."""
        return bytes(self.read(start + i) for i in range(length))

    def hex_dump(self, start: int, length: int, bytes_per_line: int = 16) -> str:
        """Generate a hex dump of memory."""
        lines = []
        for offset in range(0, length, bytes_per_line):
            addr = start + offset
            hex_bytes = ' '.join(
                f'{self.read(addr + i):02X}'
                for i in range(min(bytes_per_line, length - offset))
            )
            ascii_chars = ''.join(
                chr(b) if 0x20 <= b < 0x7F else '.'
                for b in (self.read(addr + i) for i in range(min(bytes_per_line, length - offset)))
            )
            lines.append(f'{addr:04X}: {hex_bytes:<{bytes_per_line * 3}} {ascii_chars}')
        return '\n'.join(lines)
