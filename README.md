# Apple I Emulator (Python)

A Python implementation of the Apple I computer emulator.
Inspired by [jscrane/Apple1](https://github.com/jscrane/Apple1).

## Overview

The Apple I was Steve Wozniak's first computer, introduced in 1976. This emulator faithfully recreates the original Apple I experience:

- **MOS 6502 CPU** - Full instruction set implementation
- **4KB-48KB RAM** - Configurable memory size
- **Woz Monitor ROM** - Original system monitor by Steve Wozniak
- **Integer BASIC** - Optional BASIC interpreter
- **Terminal Display** - 40-column text display via terminal OR Tkinter graphical composite display
- **Keyboard Input** - Full keyboard emulation

## Requirements

- Python 3.7+
- No external dependencies required (uses only standard library)

## Installation

```bash
git clone <repository-url>
cd Apple-II-PY
```

## Usage

### Basic Usage

```bash
# Run with default settings (8KB RAM, Woz Monitor)
python apple1.py

# Run with Integer BASIC
python apple1.py --basic

# Run with 32KB RAM
python apple1.py --ram 32
```

### Command Line Options

```
--basic       Load Integer BASIC ROM
--ram SIZE    RAM size in KB (4, 8, 32, or 48)
--load FILE   Load a binary file at specified address
--addr ADDR   Address to load file (hex, default: 0x0300)
--run ADDR    Start execution at address (hex)
--debug       Enable debug output
--test        Run in test mode (non-interactive)
--gui         Run with Tkinter graphical interface
```

### Graphical Interface

To launch the emulator using the authentic 2513 character ROM matrix rendered via Tkinter, start the application with the `--gui` flag:

```bash
python apple1.py --basic --gui
```

The graphical interface features a meticulously detailed hardware aesthetic:
- **CRT Phosphor Glow**: An adjustable rotary knob simulates the bloom and fade of an original CRT screen.
- **Hardware Power Toggle**: A mechanical elbow/rocker switch with a real-time reactive status LED.
- **Raster Scanlines**: Precision visual banding mimics the authentic 1976 CRT monitor interlacing.
- **Paste Code Interface**: A dedicated window allows seamlessly pasting long BASIC or assembly blocks from your host clipboard directly into the Apple I buffer.

### Using the Woz Monitor

After starting the emulator, you'll see the `\` prompt from the Woz Monitor. Common commands:

- **Examine memory**: `300` (displays contents of $0300)
- **Examine range**: `300.30F` (displays $0300-$030F)
- **Deposit byte**: `300: A9 42` (writes $A9 $42 at $0300)
- **Run program**: `300R` (runs from $0300)

### Example Session

```
\
300: A9 42 85 00 00     # Enter a small program
300R                     # Run it
```

### Using BASIC

Start with `--basic` flag, then type `E000R` to run BASIC:

```bash
python apple1.py --basic
```

```
\
E000R
>10 PRINT "HELLO WORLD"
>20 END
>RUN
HELLO WORLD
```

## Architecture

The emulator is structured into several modules:

```
apple1.py      - Main emulator and integration
gui.py         - Tkinter graphical composite display driver
cpu6502.py     - MOS 6502 CPU emulation
memory.py      - Memory management (RAM, ROM, devices)
pia.py         - MC6820 PIA (keyboard/display I/O)
display.py     - Terminal display emulation
keyboard.py    - Keyboard input handling
roms.py        - ROM images (Woz Monitor, BASIC)
charmap.rom    - Signetics 2513 character generator ROM
test_apple1.py - Test suite
```

### Memory Map

| Address Range | Description |
|--------------|-------------|
| $0000-$0FFF  | RAM (4KB standard) |
| $1000-$7FFF  | Extended RAM (optional) |
| $D010-$D013  | PIA (Keyboard/Display) |
| $E000-$EFFF  | BASIC ROM (optional) |
| $FF00-$FFFF  | Woz Monitor ROM |

### PIA Registers

| Address | Description |
|---------|-------------|
| $D010   | Keyboard data (bit 7 = key ready) |
| $D011   | Keyboard control register |
| $D012   | Display data output |
| $D013   | Display control register |

## API Usage

The emulator can be used programmatically:

```python
from apple1 import Apple1

# Create emulator
apple = Apple1(ram_size=8192, load_basic=True)
apple.reset()

# Load and run a program
program = bytes([0xA9, 0x42, 0x85, 0x00, 0x00])  # LDA #$42, STA $00, BRK
apple.load_program(program, 0x0300)
apple.set_pc(0x0300)

# Run for a number of cycles
apple.run(cycles=1000)

# Or step through instructions
for _ in range(10):
    apple.step()
    print(apple.debug_state())
```

## Testing

Run the test suite:

```bash
python -m pytest test_apple1.py -v
# or
python test_apple1.py
```

## Credits

- Based on Apple I emulator: [jscrane/Apple1](https://github.com/jscrane/Apple1)
- 6502 emulation library: [jscrane/r65emu](https://github.com/jscrane/r65emu)
- Woz Monitor and Apple I BASIC are original works by Steve Wozniak
- Vibe coded by Reinaldo Torres https://github.com/reyco2000 using Gemini 3 Pro High. April 2026.

## License

This project is released under the MIT License.

The original ROMs (Woz Monitor, Integer BASIC) are preserved for historical and educational purposes.

## References

- [Apple I Owner's Manual](http://www.applefritter.com/files/a1man.pdf)
- [6502 Instruction Set Reference](http://www.6502.org/tutorials/6502opcodes.html)
- [Apple I Replica Project](http://www.applefritter.com/replica)
- [Sample source code for APPLE I](https://apple1software.com/)
