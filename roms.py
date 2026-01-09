"""
Apple I ROM Images

Contains the original Apple I ROMs:
- Woz Monitor ($FF00-$FFFF): The original system monitor by Steve Wozniak
- Apple I BASIC ($E000-$EFFF): Integer BASIC interpreter

These ROMs are in the public domain and are preserved for historical purposes.
"""

import os

# Woz Monitor ROM ($FF00-$FFFF)
# The original Apple I monitor program written by Steve Wozniak
# Provides memory examination, modification, and program execution
# Loaded from WOZMON.bin file

def _load_woz_monitor() -> bytes:
    """Load the Woz Monitor ROM from WOZMON.bin file."""
    rom_path = os.path.join(os.path.dirname(__file__), 'WOZMON.bin')
    with open(rom_path, 'rb') as f:
        data = f.read(256)  # Read only the first 256 bytes ($FF00-$FFFF)
    return data

WOZ_MONITOR = _load_woz_monitor()

# Apple I Integer BASIC ($E000-$EFFF)
# Original Integer BASIC for the Apple I
# Loaded from basic.rom file

def _load_basic() -> bytes:
    """Load the Apple I BASIC ROM from basic.rom file."""
    rom_path = os.path.join(os.path.dirname(__file__), 'basic.rom')
    with open(rom_path, 'rb') as f:
        data = f.read(0x1000)  # Read up to 4KB ($E000-$EFFF)
    # Pad to 4KB if needed
    if len(data) < 0x1000:
        data = data + bytes([0x00] * (0x1000 - len(data)))
    return data

APPLE1_BASIC = _load_basic()


def get_woz_monitor() -> tuple:
    """
    Get the Woz Monitor ROM data and base address.

    Returns:
        Tuple of (data, base_address)
    """
    return (WOZ_MONITOR, 0xFF00)


def get_basic() -> tuple:
    """
    Get the BASIC ROM data and base address.

    Returns:
        Tuple of (data, base_address)
    """
    return (APPLE1_BASIC, 0xE000)


# Memory map for Apple I:
# $0000-$0FFF: RAM (4KB on original, can be expanded)
# $D010-$D013: PIA (Keyboard and Display I/O)
# $E000-$EFFF: BASIC ROM (optional)
# $FF00-$FFFF: Woz Monitor ROM

APPLE1_MEMORY_MAP = {
    'ram_start': 0x0000,
    'ram_end': 0x0FFF,  # 4KB standard, can extend to 8KB ($1FFF)
    'pia_start': 0xD010,
    'pia_end': 0xD013,
    'basic_start': 0xE000,
    'basic_end': 0xEFFF,
    'monitor_start': 0xFF00,
    'monitor_end': 0xFFFF,
}
