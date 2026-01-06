#!/usr/bin/env python3
"""
Apple I Emulator
A Python implementation of the Apple I computer (1976).

This emulator faithfully recreates the original Apple I experience:
- MOS 6502 CPU running at ~1 MHz
- 4KB-8KB RAM
- Woz Monitor ROM
- Optional Integer BASIC
- Terminal display (40 columns)
- Keyboard input

Ported from jscrane/Apple1 (https://github.com/jscrane/Apple1)

Usage:
    python apple1.py [options]

Options:
    --basic     Load Integer BASIC
    --ram SIZE  RAM size in KB (4, 8, 32, or 48)
    --load FILE Load a binary file at specified address
    --addr ADDR Address to load file (hex, default: 0x0300)
    --run ADDR  Start execution at address (hex)
    --debug     Enable debug output
"""

import sys
import time
import argparse
from typing import Optional

from cpu6502 import CPU6502
from memory import Memory, RAM, ROM
from pia import Apple1PIA
from display import TerminalDisplay, ScreenBuffer
from keyboard import BufferedKeyboard, TerminalKeyboard
from roms import WOZ_MONITOR, APPLE1_BASIC, get_woz_monitor, get_basic


class Apple1:
    """
    Apple I Computer Emulator

    The Apple I was Steve Wozniak's first computer, introduced in 1976.
    It featured a MOS 6502 CPU, 4KB of RAM (expandable to 8KB), and
    the famous "Woz Monitor" ROM for basic system control.
    """

    # Clock speed in Hz (approximate - original was 1.023 MHz)
    CLOCK_SPEED = 1_000_000

    # Cycles per instruction (approximate average)
    CYCLES_PER_INSTRUCTION = 4

    def __init__(
        self,
        ram_size: int = 8 * 1024,
        load_basic: bool = False,
        debug: bool = False
    ):
        """
        Initialize the Apple I emulator.

        Args:
            ram_size: Amount of RAM in bytes (default 8KB)
            load_basic: Load Integer BASIC ROM
            debug: Enable debug output
        """
        self.debug = debug
        self.running = False
        self._cycles_per_frame = self.CLOCK_SPEED // 60  # Target 60 FPS

        # Initialize memory
        self.memory = Memory()

        # Add RAM (at $0000)
        self.ram = RAM(ram_size, base=0x0000)
        self.memory.add_device(self.ram)

        # Initialize PIA for keyboard/display I/O
        self.pia = Apple1PIA(base=0xD010)
        self.memory.add_device(self.pia)

        # Load Woz Monitor ROM ($FF00-$FFFF)
        monitor_data, monitor_base = get_woz_monitor()
        self.monitor_rom = ROM(monitor_data, base=monitor_base)
        self.memory.add_device(self.monitor_rom)

        # Optionally load BASIC ROM ($E000-$EFFF)
        if load_basic:
            basic_data, basic_base = get_basic()
            self.basic_rom = ROM(basic_data, base=basic_base)
            self.memory.add_device(self.basic_rom)

        # Initialize display
        self.display = TerminalDisplay()
        self.pia.set_display_callback(self._display_char)

        # Initialize keyboard
        self.keyboard = BufferedKeyboard()

        # Initialize CPU
        self.cpu = CPU6502(self.memory)

        if self.debug:
            print(f"Apple I initialized with {ram_size // 1024}KB RAM")
            if load_basic:
                print("Integer BASIC loaded at $E000")
            print("Woz Monitor loaded at $FF00")

    def _display_char(self, char: int):
        """Handle display output from PIA."""
        self.display.write(char)

    def reset(self):
        """Reset the Apple I to initial state."""
        self.cpu.reset()
        self.pia.reset()
        self.display.reset()
        self.keyboard.reset()
        if self.debug:
            print(f"Reset: PC=${self.cpu.PC:04X}")

    def load_program(self, data: bytes, address: int = 0x0300):
        """
        Load a program into memory.

        Args:
            data: Binary data to load
            address: Starting address
        """
        for i, byte in enumerate(data):
            self.memory.write(address + i, byte)
        if self.debug:
            print(f"Loaded {len(data)} bytes at ${address:04X}")

    def load_file(self, filename: str, address: int = 0x0300):
        """
        Load a binary file into memory.

        Args:
            filename: Path to binary file
            address: Starting address
        """
        with open(filename, 'rb') as f:
            data = f.read()
        self.load_program(data, address)

    def set_pc(self, address: int):
        """Set the program counter to a specific address."""
        self.cpu.PC = address & 0xFFFF
        if self.debug:
            print(f"PC set to ${self.cpu.PC:04X}")

    def type_string(self, s: str):
        """
        Type a string into the Apple I keyboard.

        Args:
            s: String to type (will be converted to uppercase)
        """
        self.keyboard.queue_string(s)

    def step(self) -> int:
        """
        Execute a single CPU instruction.

        Returns:
            Number of cycles used
        """
        # Process any keyboard input
        if self.keyboard.has_key() and not self.pia._key_ready:
            key = self.keyboard.get_key()
            if key is not None:
                self.pia.key_press(key)

        # Execute one instruction
        cycles = self.cpu.step()

        return cycles

    def run(self, cycles: int = 0):
        """
        Run the emulator for a specified number of cycles.

        Args:
            cycles: Number of cycles to run (0 = run forever)
        """
        self.running = True
        total_cycles = 0

        try:
            while self.running:
                total_cycles += self.step()

                if cycles > 0 and total_cycles >= cycles:
                    break

                # Throttle to approximate real speed
                if total_cycles >= self._cycles_per_frame:
                    total_cycles = 0
                    time.sleep(1 / 60)  # ~60 FPS

        except KeyboardInterrupt:
            self.running = False
            print("\nEmulator stopped")

    def run_until_halt(self, max_cycles: int = 1_000_000) -> int:
        """
        Run until the CPU halts or max cycles reached.

        Returns:
            Number of cycles executed
        """
        cycles = 0
        while not self.cpu.halted and cycles < max_cycles:
            cycles += self.step()
        return cycles

    def interactive(self):
        """
        Run the emulator in interactive mode with keyboard input.
        Works on both Windows and Unix/Linux/macOS.
        """
        import platform

        if platform.system() == 'Windows':
            self._interactive_windows()
        else:
            self._interactive_unix()

    def _interactive_windows(self):
        """Interactive mode for Windows using msvcrt."""
        import msvcrt

        self.running = True
        cycles = 0
        last_key_time = 0
        key_delay = 0.05  # 50ms debounce delay between key presses

        print("\nApple I Emulator - Press Ctrl+C to exit\n")
        print("=" * 40)

        try:
            while self.running:
                current_time = time.time()

                # Check for keyboard input (non-blocking on Windows)
                if msvcrt.kbhit():
                    char = msvcrt.getch()
                    # Handle special keys
                    if char == b'\x03':  # Ctrl+C
                        break

                    # Only accept key if enough time has passed (debounce)
                    # and PIA is ready
                    if (current_time - last_key_time >= key_delay and
                            not self.pia._key_ready):
                        if char == b'\r':  # Enter -> CR
                            self.pia.key_press(0x0D)
                        elif char == b'\x08':  # Backspace
                            self.pia.key_press(0x08)
                        elif len(char) == 1:
                            self.pia.key_press(char[0])
                        last_key_time = current_time

                # Process PIA keyboard buffer
                self.pia.poll_keyboard()

                # Execute CPU
                cycles += self.step()

                # Throttle
                if cycles >= self._cycles_per_frame:
                    cycles = 0
                    time.sleep(1 / 1000)  # Small delay

        except KeyboardInterrupt:
            pass
        finally:
            print("\n\nEmulator stopped")

    def _interactive_unix(self):
        """Interactive mode for Unix/Linux/macOS using termios."""
        import select
        import tty
        import termios

        # Set up terminal for raw input
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setcbreak(fd)
            self.running = True
            cycles = 0
            last_key_time = 0
            key_delay = 0.05  # 50ms debounce delay

            print("\nApple I Emulator - Press Ctrl+C to exit\n")
            print("=" * 40)

            while self.running:
                current_time = time.time()

                # Check for keyboard input
                if select.select([sys.stdin], [], [], 0)[0]:
                    char = sys.stdin.read(1)
                    if char:
                        # Handle special keys
                        if ord(char) == 3:  # Ctrl+C
                            break
                        # Only accept key if enough time has passed and PIA is ready
                        if (current_time - last_key_time >= key_delay and
                                not self.pia._key_ready):
                            self.pia.key_press(ord(char))
                            last_key_time = current_time

                # Process PIA keyboard buffer
                self.pia.poll_keyboard()

                # Execute CPU
                cycles += self.step()

                # Throttle
                if cycles >= self._cycles_per_frame:
                    cycles = 0
                    time.sleep(1 / 1000)  # Small delay

        except KeyboardInterrupt:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            print("\n\nEmulator stopped")

    def run_simple(self, input_string: str = "", max_cycles: int = 100_000) -> str:
        """
        Run the emulator with buffered input and capture output.

        Useful for testing and non-interactive use.

        Args:
            input_string: Input to type
            max_cycles: Maximum cycles to run

        Returns:
            Display output as string
        """
        # Use screen buffer for output capture
        buffer = ScreenBuffer()
        old_display = self.display
        self.display = buffer
        self.pia.set_display_callback(lambda c: buffer.write(c))

        # Queue input
        if input_string:
            self.keyboard.queue_string(input_string)

        # Run emulation
        cycles = 0
        while cycles < max_cycles:
            # Process keyboard
            if self.keyboard.has_key() and not self.pia._key_ready:
                key = self.keyboard.get_key()
                if key is not None:
                    self.pia.key_press(key)

            cycles += self.step()

            # Stop if no more input and waiting for key
            if not self.keyboard.has_key() and not self.pia._key_ready:
                # Give some extra cycles for output
                for _ in range(1000):
                    self.step()
                break

        # Restore display
        self.display = old_display
        self.pia.set_display_callback(self._display_char)

        return buffer.get_output_log()

    def debug_state(self) -> str:
        """Get the current CPU state for debugging."""
        return self.cpu.status_string()

    def dump_memory(self, start: int, length: int) -> str:
        """Dump a region of memory as hex."""
        return self.memory.hex_dump(start, length)


def main():
    """Main entry point for the Apple I emulator."""
    parser = argparse.ArgumentParser(
        description='Apple I Emulator - A Python implementation of the 1976 Apple I computer'
    )
    parser.add_argument(
        '--basic', action='store_true',
        help='Load Integer BASIC ROM'
    )
    parser.add_argument(
        '--ram', type=int, default=8, choices=[4, 8, 32, 48],
        help='RAM size in KB (default: 8)'
    )
    parser.add_argument(
        '--load', type=str, metavar='FILE',
        help='Load a binary file into memory'
    )
    parser.add_argument(
        '--addr', type=str, default='0x0300',
        help='Address to load file (hex, default: 0x0300)'
    )
    parser.add_argument(
        '--run', type=str, metavar='ADDR',
        help='Start execution at address (hex)'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable debug output'
    )
    parser.add_argument(
        '--test', action='store_true',
        help='Run in test mode (non-interactive)'
    )

    args = parser.parse_args()

    # Create emulator
    apple1 = Apple1(
        ram_size=args.ram * 1024,
        load_basic=args.basic,
        debug=args.debug
    )

    # Reset to initialize
    apple1.reset()

    # Load program if specified
    if args.load:
        addr = int(args.addr, 16)
        apple1.load_file(args.load, addr)

    # Set PC if specified
    if args.run:
        addr = int(args.run, 16)
        apple1.set_pc(addr)

    # Run emulator
    if args.test:
        # Test mode - run briefly and exit
        print("Running in test mode...")
        output = apple1.run_simple("", 10000)
        print(f"Output: {repr(output)}")
    else:
        # Interactive mode
        try:
            apple1.interactive()
        except Exception as e:
            print(f"Error: {e}")
            if args.debug:
                import traceback
                traceback.print_exc()


if __name__ == '__main__':
    main()
