"""
MOS 6502 CPU Emulator
A Python implementation of the 6502 processor used in the Apple I.

Ported from jscrane/r65emu (https://github.com/jscrane/r65emu)
"""

from typing import Callable, Optional


class CPU6502:
    """
    MOS Technology 6502 CPU emulator.

    Implements all official 6502 opcodes with proper timing and flag handling.
    """

    # Status flag bit positions
    FLAG_C = 0x01  # Carry
    FLAG_Z = 0x02  # Zero
    FLAG_I = 0x04  # Interrupt Disable
    FLAG_D = 0x08  # Decimal Mode
    FLAG_B = 0x10  # Break
    FLAG_U = 0x20  # Unused (always 1)
    FLAG_V = 0x40  # Overflow
    FLAG_N = 0x80  # Negative

    # Interrupt vectors
    NMI_VECTOR = 0xFFFA
    RESET_VECTOR = 0xFFFC
    IRQ_VECTOR = 0xFFFE

    def __init__(self, memory: 'Memory'):
        self.memory = memory

        # Registers
        self.A = 0x00      # Accumulator
        self.X = 0x00      # X index register
        self.Y = 0x00      # Y index register
        self.SP = 0xFD     # Stack pointer (starts at 0x01FD)
        self.PC = 0x0000   # Program counter

        # Status flags (stored individually for speed)
        self.C = False     # Carry
        self.Z = False     # Zero
        self.I = True      # Interrupt disable
        self.D = False     # Decimal mode
        self.B = False     # Break
        self.V = False     # Overflow
        self.N = False     # Negative

        # Internal state
        self._halted = False
        self._irq_pending = False
        self._nmi_pending = False
        self._cycles = 0

        # Build opcode table
        self._build_opcode_table()

    def reset(self):
        """Reset the CPU to initial state."""
        self.A = 0x00
        self.X = 0x00
        self.Y = 0x00
        self.SP = 0xFD
        self.I = True
        self.D = False
        self.B = False
        self._halted = False
        self._irq_pending = False
        self._nmi_pending = False

        # Read reset vector
        lo = self.memory.read(self.RESET_VECTOR)
        hi = self.memory.read(self.RESET_VECTOR + 1)
        self.PC = (hi << 8) | lo

    def _read_byte(self, addr: int) -> int:
        """Read a byte from memory."""
        return self.memory.read(addr & 0xFFFF)

    def _write_byte(self, addr: int, value: int):
        """Write a byte to memory."""
        self.memory.write(addr & 0xFFFF, value & 0xFF)

    def _read_word(self, addr: int) -> int:
        """Read a 16-bit word from memory (little-endian)."""
        lo = self._read_byte(addr)
        hi = self._read_byte((addr + 1) & 0xFFFF)
        return (hi << 8) | lo

    def _fetch_byte(self) -> int:
        """Fetch the next byte from PC and increment PC."""
        value = self._read_byte(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        return value

    def _fetch_word(self) -> int:
        """Fetch the next word from PC and increment PC by 2."""
        lo = self._fetch_byte()
        hi = self._fetch_byte()
        return (hi << 8) | lo

    # Stack operations
    def _push_byte(self, value: int):
        """Push a byte onto the stack."""
        self._write_byte(0x0100 + self.SP, value & 0xFF)
        self.SP = (self.SP - 1) & 0xFF

    def _pop_byte(self) -> int:
        """Pop a byte from the stack."""
        self.SP = (self.SP + 1) & 0xFF
        return self._read_byte(0x0100 + self.SP)

    def _push_word(self, value: int):
        """Push a word onto the stack (high byte first)."""
        self._push_byte((value >> 8) & 0xFF)
        self._push_byte(value & 0xFF)

    def _pop_word(self) -> int:
        """Pop a word from the stack."""
        lo = self._pop_byte()
        hi = self._pop_byte()
        return (hi << 8) | lo

    # Status register operations
    def get_status(self) -> int:
        """Get the status register as a byte."""
        status = self.FLAG_U  # Unused flag always set
        if self.C: status |= self.FLAG_C
        if self.Z: status |= self.FLAG_Z
        if self.I: status |= self.FLAG_I
        if self.D: status |= self.FLAG_D
        if self.B: status |= self.FLAG_B
        if self.V: status |= self.FLAG_V
        if self.N: status |= self.FLAG_N
        return status

    def set_status(self, value: int):
        """Set the status register from a byte."""
        self.C = bool(value & self.FLAG_C)
        self.Z = bool(value & self.FLAG_Z)
        self.I = bool(value & self.FLAG_I)
        self.D = bool(value & self.FLAG_D)
        self.B = bool(value & self.FLAG_B)
        self.V = bool(value & self.FLAG_V)
        self.N = bool(value & self.FLAG_N)

    def _set_nz(self, value: int):
        """Set N and Z flags based on value."""
        self.Z = (value & 0xFF) == 0
        self.N = bool(value & 0x80)

    # Addressing modes - return the address
    def _addr_imm(self) -> int:
        """Immediate: operand is at PC."""
        addr = self.PC
        self.PC = (self.PC + 1) & 0xFFFF
        return addr

    def _addr_zp(self) -> int:
        """Zero page: address is single byte."""
        return self._fetch_byte()

    def _addr_zpx(self) -> int:
        """Zero page,X: address + X (wraps in zero page)."""
        return (self._fetch_byte() + self.X) & 0xFF

    def _addr_zpy(self) -> int:
        """Zero page,Y: address + Y (wraps in zero page)."""
        return (self._fetch_byte() + self.Y) & 0xFF

    def _addr_abs(self) -> int:
        """Absolute: 16-bit address."""
        return self._fetch_word()

    def _addr_abx(self) -> int:
        """Absolute,X: 16-bit address + X."""
        base = self._fetch_word()
        return (base + self.X) & 0xFFFF

    def _addr_aby(self) -> int:
        """Absolute,Y: 16-bit address + Y."""
        base = self._fetch_word()
        return (base + self.Y) & 0xFFFF

    def _addr_ind(self) -> int:
        """Indirect: address at 16-bit address (JMP only, with page wrap bug)."""
        ptr = self._fetch_word()
        lo = self._read_byte(ptr)
        # 6502 bug: if ptr is at xxFF, high byte comes from xx00
        if (ptr & 0xFF) == 0xFF:
            hi = self._read_byte(ptr & 0xFF00)
        else:
            hi = self._read_byte(ptr + 1)
        return (hi << 8) | lo

    def _addr_izx(self) -> int:
        """Indexed indirect (X): address at (zp + X)."""
        zp = (self._fetch_byte() + self.X) & 0xFF
        lo = self._read_byte(zp)
        hi = self._read_byte((zp + 1) & 0xFF)
        return (hi << 8) | lo

    def _addr_izy(self) -> int:
        """Indirect indexed (Y): address at (zp) + Y."""
        zp = self._fetch_byte()
        lo = self._read_byte(zp)
        hi = self._read_byte((zp + 1) & 0xFF)
        base = (hi << 8) | lo
        return (base + self.Y) & 0xFFFF

    def _addr_rel(self) -> int:
        """Relative: signed offset from PC (for branches)."""
        offset = self._fetch_byte()
        if offset & 0x80:
            offset -= 256
        return (self.PC + offset) & 0xFFFF

    # ALU operations
    def _adc(self, value: int):
        """Add with carry."""
        if self.D:
            # BCD mode
            lo = (self.A & 0x0F) + (value & 0x0F) + (1 if self.C else 0)
            hi = (self.A >> 4) + (value >> 4)
            if lo > 9:
                lo -= 10
                hi += 1
            self.Z = ((self.A + value + (1 if self.C else 0)) & 0xFF) == 0
            self.N = bool(hi & 0x08)
            self.V = not (((self.A ^ value) & 0x80) != 0) and (((self.A ^ (hi << 4)) & 0x80) != 0)
            if hi > 9:
                hi -= 10
                self.C = True
            else:
                self.C = False
            self.A = ((hi << 4) | (lo & 0x0F)) & 0xFF
        else:
            # Binary mode
            result = self.A + value + (1 if self.C else 0)
            self.C = result > 0xFF
            self.V = bool(((self.A ^ result) & (value ^ result) & 0x80))
            self.A = result & 0xFF
            self._set_nz(self.A)

    def _sbc(self, value: int):
        """Subtract with carry (borrow)."""
        if self.D:
            # BCD mode
            lo = (self.A & 0x0F) - (value & 0x0F) - (0 if self.C else 1)
            hi = (self.A >> 4) - (value >> 4)
            if lo < 0:
                lo += 10
                hi -= 1
            if hi < 0:
                hi += 10
                self.C = False
            else:
                self.C = True
            result = self.A - value - (0 if self.C else 1)
            self.V = bool(((self.A ^ result) & ((255 - value) ^ result) & 0x80))
            self._set_nz(result & 0xFF)
            self.A = ((hi << 4) | (lo & 0x0F)) & 0xFF
        else:
            # Binary mode (use complement for subtraction)
            self._adc(value ^ 0xFF)

    def _cmp(self, reg: int, value: int):
        """Compare register with value."""
        result = reg - value
        self.C = reg >= value
        self._set_nz(result & 0xFF)

    def _and(self, value: int):
        """Logical AND."""
        self.A = self.A & value
        self._set_nz(self.A)

    def _ora(self, value: int):
        """Logical OR."""
        self.A = self.A | value
        self._set_nz(self.A)

    def _eor(self, value: int):
        """Logical XOR."""
        self.A = self.A ^ value
        self._set_nz(self.A)

    def _asl(self, value: int) -> int:
        """Arithmetic shift left."""
        self.C = bool(value & 0x80)
        result = (value << 1) & 0xFF
        self._set_nz(result)
        return result

    def _lsr(self, value: int) -> int:
        """Logical shift right."""
        self.C = bool(value & 0x01)
        result = value >> 1
        self._set_nz(result)
        return result

    def _rol(self, value: int) -> int:
        """Rotate left through carry."""
        old_c = 1 if self.C else 0
        self.C = bool(value & 0x80)
        result = ((value << 1) | old_c) & 0xFF
        self._set_nz(result)
        return result

    def _ror(self, value: int) -> int:
        """Rotate right through carry."""
        old_c = 0x80 if self.C else 0
        self.C = bool(value & 0x01)
        result = (value >> 1) | old_c
        self._set_nz(result)
        return result

    def _inc(self, value: int) -> int:
        """Increment."""
        result = (value + 1) & 0xFF
        self._set_nz(result)
        return result

    def _dec(self, value: int) -> int:
        """Decrement."""
        result = (value - 1) & 0xFF
        self._set_nz(result)
        return result

    def _bit(self, value: int):
        """Bit test."""
        self.N = bool(value & 0x80)
        self.V = bool(value & 0x40)
        self.Z = (self.A & value) == 0

    # Branch helper
    def _branch(self, condition: bool):
        """Execute a branch if condition is true."""
        addr = self._addr_rel()
        if condition:
            self.PC = addr

    # Interrupt handling
    def raise_irq(self):
        """Raise an IRQ interrupt."""
        self._irq_pending = True

    def raise_nmi(self):
        """Raise an NMI interrupt."""
        self._nmi_pending = True

    def _handle_irq(self):
        """Handle IRQ interrupt."""
        if not self.I:
            self._push_word(self.PC)
            self._push_byte(self.get_status() & ~self.FLAG_B)
            self.I = True
            lo = self._read_byte(self.IRQ_VECTOR)
            hi = self._read_byte(self.IRQ_VECTOR + 1)
            self.PC = (hi << 8) | lo
            self._irq_pending = False

    def _handle_nmi(self):
        """Handle NMI interrupt."""
        self._push_word(self.PC)
        self._push_byte(self.get_status() & ~self.FLAG_B)
        self.I = True
        lo = self._read_byte(self.NMI_VECTOR)
        hi = self._read_byte(self.NMI_VECTOR + 1)
        self.PC = (hi << 8) | lo
        self._nmi_pending = False

    def _brk(self):
        """Break interrupt."""
        self.PC = (self.PC + 1) & 0xFFFF
        self._push_word(self.PC)
        self._push_byte(self.get_status() | self.FLAG_B)
        self.I = True
        lo = self._read_byte(self.IRQ_VECTOR)
        hi = self._read_byte(self.IRQ_VECTOR + 1)
        self.PC = (hi << 8) | lo

    def step(self) -> int:
        """Execute a single instruction. Returns cycles used."""
        if self._halted:
            return 0

        # Check for interrupts
        if self._nmi_pending:
            self._handle_nmi()
        elif self._irq_pending and not self.I:
            self._handle_irq()

        # Fetch and decode opcode
        opcode = self._fetch_byte()

        # Execute instruction
        cycles = self._execute(opcode)
        self._cycles += cycles

        return cycles

    def run(self, num_instructions: int = 1):
        """Run the CPU for a number of instructions."""
        for _ in range(num_instructions):
            if self._halted:
                break
            self.step()

    @property
    def cycles(self) -> int:
        """Get the total cycle count."""
        return self._cycles

    @property
    def halted(self) -> bool:
        """Check if the CPU is halted."""
        return self._halted

    def status_string(self) -> str:
        """Get a human-readable status string."""
        flags = ""
        flags += "N" if self.N else "n"
        flags += "V" if self.V else "v"
        flags += "-"
        flags += "B" if self.B else "b"
        flags += "D" if self.D else "d"
        flags += "I" if self.I else "i"
        flags += "Z" if self.Z else "z"
        flags += "C" if self.C else "c"
        return f"PC:{self.PC:04X} A:{self.A:02X} X:{self.X:02X} Y:{self.Y:02X} SP:{self.SP:02X} [{flags}]"

    def _build_opcode_table(self):
        """Build the opcode execution table."""
        # This will be called to set up the opcode handlers
        pass

    def _execute(self, opcode: int) -> int:
        """Execute an opcode and return the cycle count."""
        # Opcode dispatch - organized by opcode value
        # Format: opcode -> (operation, cycles)

        if opcode == 0x00:  # BRK
            self._brk()
            return 7

        elif opcode == 0x01:  # ORA (zp,X)
            self._ora(self._read_byte(self._addr_izx()))
            return 6

        elif opcode == 0x05:  # ORA zp
            self._ora(self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0x06:  # ASL zp
            addr = self._addr_zp()
            self._write_byte(addr, self._asl(self._read_byte(addr)))
            return 5

        elif opcode == 0x08:  # PHP
            self._push_byte(self.get_status() | self.FLAG_B)
            return 3

        elif opcode == 0x09:  # ORA #
            self._ora(self._read_byte(self._addr_imm()))
            return 2

        elif opcode == 0x0A:  # ASL A
            self.A = self._asl(self.A)
            return 2

        elif opcode == 0x0D:  # ORA abs
            self._ora(self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0x0E:  # ASL abs
            addr = self._addr_abs()
            self._write_byte(addr, self._asl(self._read_byte(addr)))
            return 6

        elif opcode == 0x10:  # BPL
            self._branch(not self.N)
            return 2

        elif opcode == 0x11:  # ORA (zp),Y
            self._ora(self._read_byte(self._addr_izy()))
            return 5

        elif opcode == 0x15:  # ORA zp,X
            self._ora(self._read_byte(self._addr_zpx()))
            return 4

        elif opcode == 0x16:  # ASL zp,X
            addr = self._addr_zpx()
            self._write_byte(addr, self._asl(self._read_byte(addr)))
            return 6

        elif opcode == 0x18:  # CLC
            self.C = False
            return 2

        elif opcode == 0x19:  # ORA abs,Y
            self._ora(self._read_byte(self._addr_aby()))
            return 4

        elif opcode == 0x1D:  # ORA abs,X
            self._ora(self._read_byte(self._addr_abx()))
            return 4

        elif opcode == 0x1E:  # ASL abs,X
            addr = self._addr_abx()
            self._write_byte(addr, self._asl(self._read_byte(addr)))
            return 7

        elif opcode == 0x20:  # JSR abs
            addr = self._fetch_word()
            self._push_word((self.PC - 1) & 0xFFFF)
            self.PC = addr
            return 6

        elif opcode == 0x21:  # AND (zp,X)
            self._and(self._read_byte(self._addr_izx()))
            return 6

        elif opcode == 0x24:  # BIT zp
            self._bit(self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0x25:  # AND zp
            self._and(self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0x26:  # ROL zp
            addr = self._addr_zp()
            self._write_byte(addr, self._rol(self._read_byte(addr)))
            return 5

        elif opcode == 0x28:  # PLP
            self.set_status(self._pop_byte())
            return 4

        elif opcode == 0x29:  # AND #
            self._and(self._read_byte(self._addr_imm()))
            return 2

        elif opcode == 0x2A:  # ROL A
            self.A = self._rol(self.A)
            return 2

        elif opcode == 0x2C:  # BIT abs
            self._bit(self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0x2D:  # AND abs
            self._and(self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0x2E:  # ROL abs
            addr = self._addr_abs()
            self._write_byte(addr, self._rol(self._read_byte(addr)))
            return 6

        elif opcode == 0x30:  # BMI
            self._branch(self.N)
            return 2

        elif opcode == 0x31:  # AND (zp),Y
            self._and(self._read_byte(self._addr_izy()))
            return 5

        elif opcode == 0x35:  # AND zp,X
            self._and(self._read_byte(self._addr_zpx()))
            return 4

        elif opcode == 0x36:  # ROL zp,X
            addr = self._addr_zpx()
            self._write_byte(addr, self._rol(self._read_byte(addr)))
            return 6

        elif opcode == 0x38:  # SEC
            self.C = True
            return 2

        elif opcode == 0x39:  # AND abs,Y
            self._and(self._read_byte(self._addr_aby()))
            return 4

        elif opcode == 0x3D:  # AND abs,X
            self._and(self._read_byte(self._addr_abx()))
            return 4

        elif opcode == 0x3E:  # ROL abs,X
            addr = self._addr_abx()
            self._write_byte(addr, self._rol(self._read_byte(addr)))
            return 7

        elif opcode == 0x40:  # RTI
            self.set_status(self._pop_byte())
            self.PC = self._pop_word()
            return 6

        elif opcode == 0x41:  # EOR (zp,X)
            self._eor(self._read_byte(self._addr_izx()))
            return 6

        elif opcode == 0x45:  # EOR zp
            self._eor(self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0x46:  # LSR zp
            addr = self._addr_zp()
            self._write_byte(addr, self._lsr(self._read_byte(addr)))
            return 5

        elif opcode == 0x48:  # PHA
            self._push_byte(self.A)
            return 3

        elif opcode == 0x49:  # EOR #
            self._eor(self._read_byte(self._addr_imm()))
            return 2

        elif opcode == 0x4A:  # LSR A
            self.A = self._lsr(self.A)
            return 2

        elif opcode == 0x4C:  # JMP abs
            self.PC = self._fetch_word()
            return 3

        elif opcode == 0x4D:  # EOR abs
            self._eor(self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0x4E:  # LSR abs
            addr = self._addr_abs()
            self._write_byte(addr, self._lsr(self._read_byte(addr)))
            return 6

        elif opcode == 0x50:  # BVC
            self._branch(not self.V)
            return 2

        elif opcode == 0x51:  # EOR (zp),Y
            self._eor(self._read_byte(self._addr_izy()))
            return 5

        elif opcode == 0x55:  # EOR zp,X
            self._eor(self._read_byte(self._addr_zpx()))
            return 4

        elif opcode == 0x56:  # LSR zp,X
            addr = self._addr_zpx()
            self._write_byte(addr, self._lsr(self._read_byte(addr)))
            return 6

        elif opcode == 0x58:  # CLI
            self.I = False
            return 2

        elif opcode == 0x59:  # EOR abs,Y
            self._eor(self._read_byte(self._addr_aby()))
            return 4

        elif opcode == 0x5D:  # EOR abs,X
            self._eor(self._read_byte(self._addr_abx()))
            return 4

        elif opcode == 0x5E:  # LSR abs,X
            addr = self._addr_abx()
            self._write_byte(addr, self._lsr(self._read_byte(addr)))
            return 7

        elif opcode == 0x60:  # RTS
            self.PC = (self._pop_word() + 1) & 0xFFFF
            return 6

        elif opcode == 0x61:  # ADC (zp,X)
            self._adc(self._read_byte(self._addr_izx()))
            return 6

        elif opcode == 0x65:  # ADC zp
            self._adc(self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0x66:  # ROR zp
            addr = self._addr_zp()
            self._write_byte(addr, self._ror(self._read_byte(addr)))
            return 5

        elif opcode == 0x68:  # PLA
            self.A = self._pop_byte()
            self._set_nz(self.A)
            return 4

        elif opcode == 0x69:  # ADC #
            self._adc(self._read_byte(self._addr_imm()))
            return 2

        elif opcode == 0x6A:  # ROR A
            self.A = self._ror(self.A)
            return 2

        elif opcode == 0x6C:  # JMP (abs)
            self.PC = self._addr_ind()
            return 5

        elif opcode == 0x6D:  # ADC abs
            self._adc(self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0x6E:  # ROR abs
            addr = self._addr_abs()
            self._write_byte(addr, self._ror(self._read_byte(addr)))
            return 6

        elif opcode == 0x70:  # BVS
            self._branch(self.V)
            return 2

        elif opcode == 0x71:  # ADC (zp),Y
            self._adc(self._read_byte(self._addr_izy()))
            return 5

        elif opcode == 0x75:  # ADC zp,X
            self._adc(self._read_byte(self._addr_zpx()))
            return 4

        elif opcode == 0x76:  # ROR zp,X
            addr = self._addr_zpx()
            self._write_byte(addr, self._ror(self._read_byte(addr)))
            return 6

        elif opcode == 0x78:  # SEI
            self.I = True
            return 2

        elif opcode == 0x79:  # ADC abs,Y
            self._adc(self._read_byte(self._addr_aby()))
            return 4

        elif opcode == 0x7D:  # ADC abs,X
            self._adc(self._read_byte(self._addr_abx()))
            return 4

        elif opcode == 0x7E:  # ROR abs,X
            addr = self._addr_abx()
            self._write_byte(addr, self._ror(self._read_byte(addr)))
            return 7

        elif opcode == 0x81:  # STA (zp,X)
            self._write_byte(self._addr_izx(), self.A)
            return 6

        elif opcode == 0x84:  # STY zp
            self._write_byte(self._addr_zp(), self.Y)
            return 3

        elif opcode == 0x85:  # STA zp
            self._write_byte(self._addr_zp(), self.A)
            return 3

        elif opcode == 0x86:  # STX zp
            self._write_byte(self._addr_zp(), self.X)
            return 3

        elif opcode == 0x88:  # DEY
            self.Y = (self.Y - 1) & 0xFF
            self._set_nz(self.Y)
            return 2

        elif opcode == 0x8A:  # TXA
            self.A = self.X
            self._set_nz(self.A)
            return 2

        elif opcode == 0x8C:  # STY abs
            self._write_byte(self._addr_abs(), self.Y)
            return 4

        elif opcode == 0x8D:  # STA abs
            self._write_byte(self._addr_abs(), self.A)
            return 4

        elif opcode == 0x8E:  # STX abs
            self._write_byte(self._addr_abs(), self.X)
            return 4

        elif opcode == 0x90:  # BCC
            self._branch(not self.C)
            return 2

        elif opcode == 0x91:  # STA (zp),Y
            self._write_byte(self._addr_izy(), self.A)
            return 6

        elif opcode == 0x94:  # STY zp,X
            self._write_byte(self._addr_zpx(), self.Y)
            return 4

        elif opcode == 0x95:  # STA zp,X
            self._write_byte(self._addr_zpx(), self.A)
            return 4

        elif opcode == 0x96:  # STX zp,Y
            self._write_byte(self._addr_zpy(), self.X)
            return 4

        elif opcode == 0x98:  # TYA
            self.A = self.Y
            self._set_nz(self.A)
            return 2

        elif opcode == 0x99:  # STA abs,Y
            self._write_byte(self._addr_aby(), self.A)
            return 5

        elif opcode == 0x9A:  # TXS
            self.SP = self.X
            return 2

        elif opcode == 0x9D:  # STA abs,X
            self._write_byte(self._addr_abx(), self.A)
            return 5

        elif opcode == 0xA0:  # LDY #
            self.Y = self._read_byte(self._addr_imm())
            self._set_nz(self.Y)
            return 2

        elif opcode == 0xA1:  # LDA (zp,X)
            self.A = self._read_byte(self._addr_izx())
            self._set_nz(self.A)
            return 6

        elif opcode == 0xA2:  # LDX #
            self.X = self._read_byte(self._addr_imm())
            self._set_nz(self.X)
            return 2

        elif opcode == 0xA4:  # LDY zp
            self.Y = self._read_byte(self._addr_zp())
            self._set_nz(self.Y)
            return 3

        elif opcode == 0xA5:  # LDA zp
            self.A = self._read_byte(self._addr_zp())
            self._set_nz(self.A)
            return 3

        elif opcode == 0xA6:  # LDX zp
            self.X = self._read_byte(self._addr_zp())
            self._set_nz(self.X)
            return 3

        elif opcode == 0xA8:  # TAY
            self.Y = self.A
            self._set_nz(self.Y)
            return 2

        elif opcode == 0xA9:  # LDA #
            self.A = self._read_byte(self._addr_imm())
            self._set_nz(self.A)
            return 2

        elif opcode == 0xAA:  # TAX
            self.X = self.A
            self._set_nz(self.X)
            return 2

        elif opcode == 0xAC:  # LDY abs
            self.Y = self._read_byte(self._addr_abs())
            self._set_nz(self.Y)
            return 4

        elif opcode == 0xAD:  # LDA abs
            self.A = self._read_byte(self._addr_abs())
            self._set_nz(self.A)
            return 4

        elif opcode == 0xAE:  # LDX abs
            self.X = self._read_byte(self._addr_abs())
            self._set_nz(self.X)
            return 4

        elif opcode == 0xB0:  # BCS
            self._branch(self.C)
            return 2

        elif opcode == 0xB1:  # LDA (zp),Y
            self.A = self._read_byte(self._addr_izy())
            self._set_nz(self.A)
            return 5

        elif opcode == 0xB4:  # LDY zp,X
            self.Y = self._read_byte(self._addr_zpx())
            self._set_nz(self.Y)
            return 4

        elif opcode == 0xB5:  # LDA zp,X
            self.A = self._read_byte(self._addr_zpx())
            self._set_nz(self.A)
            return 4

        elif opcode == 0xB6:  # LDX zp,Y
            self.X = self._read_byte(self._addr_zpy())
            self._set_nz(self.X)
            return 4

        elif opcode == 0xB8:  # CLV
            self.V = False
            return 2

        elif opcode == 0xB9:  # LDA abs,Y
            self.A = self._read_byte(self._addr_aby())
            self._set_nz(self.A)
            return 4

        elif opcode == 0xBA:  # TSX
            self.X = self.SP
            self._set_nz(self.X)
            return 2

        elif opcode == 0xBC:  # LDY abs,X
            self.Y = self._read_byte(self._addr_abx())
            self._set_nz(self.Y)
            return 4

        elif opcode == 0xBD:  # LDA abs,X
            self.A = self._read_byte(self._addr_abx())
            self._set_nz(self.A)
            return 4

        elif opcode == 0xBE:  # LDX abs,Y
            self.X = self._read_byte(self._addr_aby())
            self._set_nz(self.X)
            return 4

        elif opcode == 0xC0:  # CPY #
            self._cmp(self.Y, self._read_byte(self._addr_imm()))
            return 2

        elif opcode == 0xC1:  # CMP (zp,X)
            self._cmp(self.A, self._read_byte(self._addr_izx()))
            return 6

        elif opcode == 0xC4:  # CPY zp
            self._cmp(self.Y, self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0xC5:  # CMP zp
            self._cmp(self.A, self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0xC6:  # DEC zp
            addr = self._addr_zp()
            self._write_byte(addr, self._dec(self._read_byte(addr)))
            return 5

        elif opcode == 0xC8:  # INY
            self.Y = (self.Y + 1) & 0xFF
            self._set_nz(self.Y)
            return 2

        elif opcode == 0xC9:  # CMP #
            self._cmp(self.A, self._read_byte(self._addr_imm()))
            return 2

        elif opcode == 0xCA:  # DEX
            self.X = (self.X - 1) & 0xFF
            self._set_nz(self.X)
            return 2

        elif opcode == 0xCC:  # CPY abs
            self._cmp(self.Y, self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0xCD:  # CMP abs
            self._cmp(self.A, self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0xCE:  # DEC abs
            addr = self._addr_abs()
            self._write_byte(addr, self._dec(self._read_byte(addr)))
            return 6

        elif opcode == 0xD0:  # BNE
            self._branch(not self.Z)
            return 2

        elif opcode == 0xD1:  # CMP (zp),Y
            self._cmp(self.A, self._read_byte(self._addr_izy()))
            return 5

        elif opcode == 0xD5:  # CMP zp,X
            self._cmp(self.A, self._read_byte(self._addr_zpx()))
            return 4

        elif opcode == 0xD6:  # DEC zp,X
            addr = self._addr_zpx()
            self._write_byte(addr, self._dec(self._read_byte(addr)))
            return 6

        elif opcode == 0xD8:  # CLD
            self.D = False
            return 2

        elif opcode == 0xD9:  # CMP abs,Y
            self._cmp(self.A, self._read_byte(self._addr_aby()))
            return 4

        elif opcode == 0xDD:  # CMP abs,X
            self._cmp(self.A, self._read_byte(self._addr_abx()))
            return 4

        elif opcode == 0xDE:  # DEC abs,X
            addr = self._addr_abx()
            self._write_byte(addr, self._dec(self._read_byte(addr)))
            return 7

        elif opcode == 0xE0:  # CPX #
            self._cmp(self.X, self._read_byte(self._addr_imm()))
            return 2

        elif opcode == 0xE1:  # SBC (zp,X)
            self._sbc(self._read_byte(self._addr_izx()))
            return 6

        elif opcode == 0xE4:  # CPX zp
            self._cmp(self.X, self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0xE5:  # SBC zp
            self._sbc(self._read_byte(self._addr_zp()))
            return 3

        elif opcode == 0xE6:  # INC zp
            addr = self._addr_zp()
            self._write_byte(addr, self._inc(self._read_byte(addr)))
            return 5

        elif opcode == 0xE8:  # INX
            self.X = (self.X + 1) & 0xFF
            self._set_nz(self.X)
            return 2

        elif opcode == 0xE9:  # SBC #
            self._sbc(self._read_byte(self._addr_imm()))
            return 2

        elif opcode == 0xEA:  # NOP
            return 2

        elif opcode == 0xEC:  # CPX abs
            self._cmp(self.X, self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0xED:  # SBC abs
            self._sbc(self._read_byte(self._addr_abs()))
            return 4

        elif opcode == 0xEE:  # INC abs
            addr = self._addr_abs()
            self._write_byte(addr, self._inc(self._read_byte(addr)))
            return 6

        elif opcode == 0xF0:  # BEQ
            self._branch(self.Z)
            return 2

        elif opcode == 0xF1:  # SBC (zp),Y
            self._sbc(self._read_byte(self._addr_izy()))
            return 5

        elif opcode == 0xF5:  # SBC zp,X
            self._sbc(self._read_byte(self._addr_zpx()))
            return 4

        elif opcode == 0xF6:  # INC zp,X
            addr = self._addr_zpx()
            self._write_byte(addr, self._inc(self._read_byte(addr)))
            return 6

        elif opcode == 0xF8:  # SED
            self.D = True
            return 2

        elif opcode == 0xF9:  # SBC abs,Y
            self._sbc(self._read_byte(self._addr_aby()))
            return 4

        elif opcode == 0xFD:  # SBC abs,X
            self._sbc(self._read_byte(self._addr_abx()))
            return 4

        elif opcode == 0xFE:  # INC abs,X
            addr = self._addr_abx()
            self._write_byte(addr, self._inc(self._read_byte(addr)))
            return 7

        else:
            # Undefined opcode - treat as NOP
            return 2
