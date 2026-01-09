"""
PIA (Peripheral Interface Adapter) Emulation
Emulates the MC6820/MC6821 PIA chip used in the Apple I for keyboard and display I/O.

The Apple I uses two PIA ports:
- Port A ($D010-$D011): Keyboard input
- Port B ($D012-$D013): Display output

Ported from jscrane/r65emu (https://github.com/jscrane/r65emu)
"""

from typing import Callable, Optional
from memory import MemoryDevice


class PIA(MemoryDevice):
    """
    MC6820/MC6821 Peripheral Interface Adapter emulation.

    The PIA provides two 8-bit bidirectional I/O ports (A and B) with
    handshaking control lines.

    Memory map (relative to base address):
    $00 - Port A Data/Direction Register (depending on CRA bit 2)
    $01 - Control Register A
    $02 - Port B Data/Direction Register (depending on CRB bit 2)
    $03 - Control Register B
    """

    # Control register bits
    IRQ1 = 0x80  # Interrupt flag 1
    IRQ2 = 0x40  # Interrupt flag 2

    def __init__(self, base: int = 0xD010):
        super().__init__(4, base)  # 4 registers

        # Data Direction Registers (0 = input, 1 = output)
        self.DDRA = 0x00
        self.DDRB = 0x00

        # Control Registers
        self.CRA = 0x00
        self.CRB = 0x00

        # Port output buffers
        self.ORA = 0x00  # Output Register A
        self.ORB = 0x00  # Output Register B

        # Port input buffers
        self.IRA = 0x00  # Input Register A
        self.IRB = 0x00  # Input Register B

        # Control line states
        self.CA1 = False
        self.CA2 = False
        self.CB1 = False
        self.CB2 = False

        # Handlers for port operations
        self._read_port_a: Optional[Callable[[], int]] = None
        self._read_port_b: Optional[Callable[[], int]] = None
        self._write_port_a: Optional[Callable[[int], None]] = None
        self._write_port_b: Optional[Callable[[int], None]] = None
        self._irq_handler: Optional[Callable[[], None]] = None

    def reset(self):
        """Reset the PIA to initial state."""
        self.DDRA = 0x00
        self.DDRB = 0x00
        self.CRA = 0x00
        self.CRB = 0x00
        self.ORA = 0x00
        self.ORB = 0x00
        self.IRA = 0x00
        self.IRB = 0x00
        self.CA1 = False
        self.CA2 = False
        self.CB1 = False
        self.CB2 = False

    def set_read_port_a_handler(self, handler: Callable[[], int]):
        """Set handler for reading Port A input."""
        self._read_port_a = handler

    def set_read_port_b_handler(self, handler: Callable[[], int]):
        """Set handler for reading Port B input."""
        self._read_port_b = handler

    def set_write_port_a_handler(self, handler: Callable[[int], None]):
        """Set handler for writing to Port A."""
        self._write_port_a = handler

    def set_write_port_b_handler(self, handler: Callable[[int], None]):
        """Set handler for writing to Port B."""
        self._write_port_b = handler

    def set_irq_handler(self, handler: Callable[[], None]):
        """Set handler for IRQ signaling."""
        self._irq_handler = handler

    def read(self, address: int) -> int:
        """Read from PIA register."""
        reg = (address - self.base) & 0x03

        if reg == 0:  # Port A Data/DDR
            if self.CRA & 0x04:  # Data register selected
                return self._read_port_a_data()
            else:  # DDR selected
                return self.DDRA

        elif reg == 1:  # Control Register A
            return self.CRA

        elif reg == 2:  # Port B Data/DDR
            if self.CRB & 0x04:  # Data register selected
                return self._read_port_b_data()
            else:  # DDR selected
                return self.DDRB

        elif reg == 3:  # Control Register B
            return self.CRB

        return 0

    def write(self, address: int, value: int):
        """Write to PIA register."""
        value = value & 0xFF
        reg = (address - self.base) & 0x03

        if reg == 0:  # Port A Data/DDR
            if self.CRA & 0x04:  # Data register selected
                self._write_port_a_data(value)
            else:  # DDR selected
                self.DDRA = value

        elif reg == 1:  # Control Register A
            self.CRA = (self.CRA & 0xC0) | (value & 0x3F)

        elif reg == 2:  # Port B Data/DDR
            if self.CRB & 0x04:  # Data register selected
                self._write_port_b_data(value)
            else:  # DDR selected
                self.DDRB = value

        elif reg == 3:  # Control Register B
            self.CRB = (self.CRB & 0xC0) | (value & 0x3F)

    def _read_port_a_data(self) -> int:
        """Read from Port A data register."""
        # Clear interrupt flags on read
        self.CRA &= ~(self.IRQ1 | self.IRQ2)

        # Get external input if handler registered
        if self._read_port_a:
            self.IRA = self._read_port_a()

        # Output bits come from ORA, input bits come from IRA
        return (self.ORA & self.DDRA) | (self.IRA & ~self.DDRA)

    def _read_port_b_data(self) -> int:
        """Read from Port B data register."""
        # Clear interrupt flags on read
        self.CRB &= ~(self.IRQ1 | self.IRQ2)

        # Get external input if handler registered
        if self._read_port_b:
            self.IRB = self._read_port_b()

        # Output bits come from ORB, input bits come from IRB
        return (self.ORB & self.DDRB) | (self.IRB & ~self.DDRB)

    def _write_port_a_data(self, value: int):
        """Write to Port A data register."""
        self.ORA = value
        if self._write_port_a:
            # Only output bits set as output in DDR
            self._write_port_a(value & self.DDRA)

    def _write_port_b_data(self, value: int):
        """Write to Port B data register."""
        self.ORB = value
        if self._write_port_b:
            # Only output bits set as output in DDR
            self._write_port_b(value & self.DDRB)

    def set_port_a(self, value: int):
        """Set Port A input value (from external device)."""
        self.IRA = value & 0xFF

    def set_port_b(self, value: int):
        """Set Port B input value (from external device)."""
        self.IRB = value & 0xFF

    def write_ca1(self, state: bool):
        """Set CA1 control line state."""
        old_state = self.CA1
        self.CA1 = state

        # Check for transition
        ca1_edge = (self.CRA & 0x02) != 0  # 0=falling, 1=rising
        if ca1_edge:
            triggered = not old_state and state  # Rising edge
        else:
            triggered = old_state and not state  # Falling edge

        if triggered:
            self.CRA |= self.IRQ1
            if self.CRA & 0x01:  # IRQ enabled
                if self._irq_handler:
                    self._irq_handler()

    def write_ca2(self, state: bool):
        """Set CA2 control line state (when configured as input)."""
        if (self.CRA & 0x20) == 0:  # CA2 is input
            old_state = self.CA2
            self.CA2 = state

            ca2_edge = (self.CRA & 0x10) != 0
            if ca2_edge:
                triggered = not old_state and state
            else:
                triggered = old_state and not state

            if triggered:
                self.CRA |= self.IRQ2
                if self.CRA & 0x08:
                    if self._irq_handler:
                        self._irq_handler()

    def write_cb1(self, state: bool):
        """Set CB1 control line state."""
        old_state = self.CB1
        self.CB1 = state

        cb1_edge = (self.CRB & 0x02) != 0
        if cb1_edge:
            triggered = not old_state and state
        else:
            triggered = old_state and not state

        if triggered:
            self.CRB |= self.IRQ1
            if self.CRB & 0x01:
                if self._irq_handler:
                    self._irq_handler()

    def write_cb2(self, state: bool):
        """Set CB2 control line state (when configured as input)."""
        if (self.CRB & 0x20) == 0:
            old_state = self.CB2
            self.CB2 = state

            cb2_edge = (self.CRB & 0x10) != 0
            if cb2_edge:
                triggered = not old_state and state
            else:
                triggered = old_state and not state

            if triggered:
                self.CRB |= self.IRQ2
                if self.CRB & 0x08:
                    if self._irq_handler:
                        self._irq_handler()


class Apple1PIA:
    """
    Apple I specific PIA configuration.

    The Apple I uses the PIA as follows:
    - $D010: Keyboard data (bit 7 = strobe)
    - $D011: Keyboard control register
    - $D012: Display data (bit 7 = display ready)
    - $D013: Display control register

    When a key is pressed:
    - The ASCII code is placed in $D010 with bit 7 set
    - Reading $D010 clears bit 7

    When outputting a character:
    - Write ASCII to $D012
    - The display sets bit 7 of $D012 when ready for next char
    """

    def __init__(self, base: int = 0xD010):
        self.pia = PIA(base)

        # Keyboard state
        self._key_buffer = []
        self._key_ready = False
        self._last_key = 0

        # Display state
        self._display_ready = True
        self._display_callback: Optional[Callable[[int], None]] = None

        # Set up PIA handlers
        self.pia.set_read_port_a_handler(self._read_keyboard)
        self.pia.set_write_port_b_handler(self._write_display)
        self.pia.set_read_port_b_handler(self._read_display_status)

    @property
    def base(self) -> int:
        return self.pia.base

    @property
    def size(self) -> int:
        return self.pia.size

    def contains(self, address: int) -> bool:
        return self.pia.contains(address)

    def read(self, address: int) -> int:
        """Read from Apple I PIA."""
        reg = (address - self.pia.base) & 0x03

        if reg == 0:  # Keyboard data
            if self.pia.CRA & 0x04:  # Data register
                # Return key with strobe bit
                value = self._last_key
                if self._key_ready:
                    value |= 0x80
                    self._key_ready = False
                return value
            else:
                return self.pia.DDRA

        elif reg == 1:  # Keyboard control
            # Return CRA with bit 7 indicating key ready status
            # Bit 7 must be CLEAR when no key is ready, SET when key is ready
            value = self.pia.CRA & 0x7F  # Clear bit 7 first
            if self._key_ready:
                value |= 0x80  # Set bit 7 only if key ready
            return value

        elif reg == 2:  # Display data
            if self.pia.CRB & 0x04:
                # Return ORB with display ready flag in bit 7
                # Bit 7 CLEAR = ready, Bit 7 SET = busy
                # (Woz Monitor loops with BMI while bit 7 is set)
                value = self.pia.ORB & 0x7F
                if not self._display_ready:
                    value |= 0x80  # Set bit 7 when NOT ready (busy)
                return value
            else:
                return self.pia.DDRB

        elif reg == 3:  # Display control
            value = self.pia.CRB
            if self._display_ready:
                value |= 0x80  # Display ready flag
            return value

        return 0

    def write(self, address: int, value: int):
        """Write to Apple I PIA."""
        value = value & 0xFF
        reg = (address - self.pia.base) & 0x03

        if reg == 0:
            if self.pia.CRA & 0x04:
                self.pia.ORA = value
            else:
                self.pia.DDRA = value

        elif reg == 1:
            self.pia.CRA = (self.pia.CRA & 0xC0) | (value & 0x3F)

        elif reg == 2:
            if self.pia.CRB & 0x04:
                self.pia.ORB = value
                self._write_display(value & 0x7F)
            else:
                self.pia.DDRB = value

        elif reg == 3:
            self.pia.CRB = (self.pia.CRB & 0xC0) | (value & 0x3F)

    def _read_keyboard(self) -> int:
        """Read keyboard data."""
        if self._key_ready:
            return self._last_key | 0x80
        return self._last_key

    def _read_display_status(self) -> int:
        """Read display status."""
        if self._display_ready:
            return 0x00  # Ready (active low for some implementations)
        return 0x80

    def _write_display(self, value: int):
        """Write to display."""
        if self._display_callback:
            self._display_callback(value & 0x7F)
        self._display_ready = True

    def key_press(self, char: int):
        """
        Simulate a key press.

        Args:
            char: ASCII code of the key (0-127)
        """
        # Convert to uppercase (Apple I keyboard was uppercase only)
        if 0x61 <= char <= 0x7A:  # a-z
            char -= 0x20  # Convert to A-Z

        # Handle special keys
        if char == 0x0A:  # LF -> CR
            char = 0x0D

        self._last_key = char & 0x7F
        self._key_ready = True

        # Trigger CA1 interrupt
        self.pia.write_ca1(True)
        self.pia.write_ca1(False)

    def key_press_string(self, s: str):
        """Queue a string of key presses."""
        for char in s:
            self._key_buffer.append(ord(char))

    def poll_keyboard(self) -> bool:
        """Process any buffered keyboard input. Returns True if a key was processed."""
        if self._key_buffer and not self._key_ready:
            self.key_press(self._key_buffer.pop(0))
            return True
        return False

    def set_display_callback(self, callback: Callable[[int], None]):
        """Set callback for display output."""
        self._display_callback = callback

    def reset(self):
        """Reset the PIA."""
        self.pia.reset()
        self._key_buffer = []
        self._key_ready = False
        self._last_key = 0
        self._display_ready = True
