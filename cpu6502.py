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

    def _invalid_opcode(self):
        return 2

    def _build_opcode_table(self):
        self._opcodes = [self._invalid_opcode] * 256
        self._opcodes[0x00] = self._op_00
        self._opcodes[0x01] = self._op_01
        self._opcodes[0x05] = self._op_05
        self._opcodes[0x06] = self._op_06
        self._opcodes[0x08] = self._op_08
        self._opcodes[0x09] = self._op_09
        self._opcodes[0x0A] = self._op_0a
        self._opcodes[0x0D] = self._op_0d
        self._opcodes[0x0E] = self._op_0e
        self._opcodes[0x10] = self._op_10
        self._opcodes[0x11] = self._op_11
        self._opcodes[0x15] = self._op_15
        self._opcodes[0x16] = self._op_16
        self._opcodes[0x18] = self._op_18
        self._opcodes[0x19] = self._op_19
        self._opcodes[0x1D] = self._op_1d
        self._opcodes[0x1E] = self._op_1e
        self._opcodes[0x20] = self._op_20
        self._opcodes[0x21] = self._op_21
        self._opcodes[0x24] = self._op_24
        self._opcodes[0x25] = self._op_25
        self._opcodes[0x26] = self._op_26
        self._opcodes[0x28] = self._op_28
        self._opcodes[0x29] = self._op_29
        self._opcodes[0x2A] = self._op_2a
        self._opcodes[0x2C] = self._op_2c
        self._opcodes[0x2D] = self._op_2d
        self._opcodes[0x2E] = self._op_2e
        self._opcodes[0x30] = self._op_30
        self._opcodes[0x31] = self._op_31
        self._opcodes[0x35] = self._op_35
        self._opcodes[0x36] = self._op_36
        self._opcodes[0x38] = self._op_38
        self._opcodes[0x39] = self._op_39
        self._opcodes[0x3D] = self._op_3d
        self._opcodes[0x3E] = self._op_3e
        self._opcodes[0x40] = self._op_40
        self._opcodes[0x41] = self._op_41
        self._opcodes[0x45] = self._op_45
        self._opcodes[0x46] = self._op_46
        self._opcodes[0x48] = self._op_48
        self._opcodes[0x49] = self._op_49
        self._opcodes[0x4A] = self._op_4a
        self._opcodes[0x4C] = self._op_4c
        self._opcodes[0x4D] = self._op_4d
        self._opcodes[0x4E] = self._op_4e
        self._opcodes[0x50] = self._op_50
        self._opcodes[0x51] = self._op_51
        self._opcodes[0x55] = self._op_55
        self._opcodes[0x56] = self._op_56
        self._opcodes[0x58] = self._op_58
        self._opcodes[0x59] = self._op_59
        self._opcodes[0x5D] = self._op_5d
        self._opcodes[0x5E] = self._op_5e
        self._opcodes[0x60] = self._op_60
        self._opcodes[0x61] = self._op_61
        self._opcodes[0x65] = self._op_65
        self._opcodes[0x66] = self._op_66
        self._opcodes[0x68] = self._op_68
        self._opcodes[0x69] = self._op_69
        self._opcodes[0x6A] = self._op_6a
        self._opcodes[0x6C] = self._op_6c
        self._opcodes[0x6D] = self._op_6d
        self._opcodes[0x6E] = self._op_6e
        self._opcodes[0x70] = self._op_70
        self._opcodes[0x71] = self._op_71
        self._opcodes[0x75] = self._op_75
        self._opcodes[0x76] = self._op_76
        self._opcodes[0x78] = self._op_78
        self._opcodes[0x79] = self._op_79
        self._opcodes[0x7D] = self._op_7d
        self._opcodes[0x7E] = self._op_7e
        self._opcodes[0x81] = self._op_81
        self._opcodes[0x84] = self._op_84
        self._opcodes[0x85] = self._op_85
        self._opcodes[0x86] = self._op_86
        self._opcodes[0x88] = self._op_88
        self._opcodes[0x8A] = self._op_8a
        self._opcodes[0x8C] = self._op_8c
        self._opcodes[0x8D] = self._op_8d
        self._opcodes[0x8E] = self._op_8e
        self._opcodes[0x90] = self._op_90
        self._opcodes[0x91] = self._op_91
        self._opcodes[0x94] = self._op_94
        self._opcodes[0x95] = self._op_95
        self._opcodes[0x96] = self._op_96
        self._opcodes[0x98] = self._op_98
        self._opcodes[0x99] = self._op_99
        self._opcodes[0x9A] = self._op_9a
        self._opcodes[0x9D] = self._op_9d
        self._opcodes[0xA0] = self._op_a0
        self._opcodes[0xA1] = self._op_a1
        self._opcodes[0xA2] = self._op_a2
        self._opcodes[0xA4] = self._op_a4
        self._opcodes[0xA5] = self._op_a5
        self._opcodes[0xA6] = self._op_a6
        self._opcodes[0xA8] = self._op_a8
        self._opcodes[0xA9] = self._op_a9
        self._opcodes[0xAA] = self._op_aa
        self._opcodes[0xAC] = self._op_ac
        self._opcodes[0xAD] = self._op_ad
        self._opcodes[0xAE] = self._op_ae
        self._opcodes[0xB0] = self._op_b0
        self._opcodes[0xB1] = self._op_b1
        self._opcodes[0xB4] = self._op_b4
        self._opcodes[0xB5] = self._op_b5
        self._opcodes[0xB6] = self._op_b6
        self._opcodes[0xB8] = self._op_b8
        self._opcodes[0xB9] = self._op_b9
        self._opcodes[0xBA] = self._op_ba
        self._opcodes[0xBC] = self._op_bc
        self._opcodes[0xBD] = self._op_bd
        self._opcodes[0xBE] = self._op_be
        self._opcodes[0xC0] = self._op_c0
        self._opcodes[0xC1] = self._op_c1
        self._opcodes[0xC4] = self._op_c4
        self._opcodes[0xC5] = self._op_c5
        self._opcodes[0xC6] = self._op_c6
        self._opcodes[0xC8] = self._op_c8
        self._opcodes[0xC9] = self._op_c9
        self._opcodes[0xCA] = self._op_ca
        self._opcodes[0xCC] = self._op_cc
        self._opcodes[0xCD] = self._op_cd
        self._opcodes[0xCE] = self._op_ce
        self._opcodes[0xD0] = self._op_d0
        self._opcodes[0xD1] = self._op_d1
        self._opcodes[0xD5] = self._op_d5
        self._opcodes[0xD6] = self._op_d6
        self._opcodes[0xD8] = self._op_d8
        self._opcodes[0xD9] = self._op_d9
        self._opcodes[0xDD] = self._op_dd
        self._opcodes[0xDE] = self._op_de
        self._opcodes[0xE0] = self._op_e0
        self._opcodes[0xE1] = self._op_e1
        self._opcodes[0xE4] = self._op_e4
        self._opcodes[0xE5] = self._op_e5
        self._opcodes[0xE6] = self._op_e6
        self._opcodes[0xE8] = self._op_e8
        self._opcodes[0xE9] = self._op_e9
        self._opcodes[0xEA] = self._op_ea
        self._opcodes[0xEC] = self._op_ec
        self._opcodes[0xED] = self._op_ed
        self._opcodes[0xEE] = self._op_ee
        self._opcodes[0xF0] = self._op_f0
        self._opcodes[0xF1] = self._op_f1
        self._opcodes[0xF5] = self._op_f5
        self._opcodes[0xF6] = self._op_f6
        self._opcodes[0xF8] = self._op_f8
        self._opcodes[0xF9] = self._op_f9
        self._opcodes[0xFD] = self._op_fd
        self._opcodes[0xFE] = self._op_fe


    def _op_00(self):
        self._brk()
        return 7

    def _op_01(self):
        self._ora(self._read_byte(self._addr_izx()))
        return 6

    def _op_05(self):
        self._ora(self._read_byte(self._addr_zp()))
        return 3

    def _op_06(self):
        addr = self._addr_zp()
        self._write_byte(addr, self._asl(self._read_byte(addr)))
        return 5

    def _op_08(self):
        self._push_byte(self.get_status() | self.FLAG_B)
        return 3

    def _op_09(self):
        self._ora(self._read_byte(self._addr_imm()))
        return 2

    def _op_0a(self):
        self.A = self._asl(self.A)
        return 2

    def _op_0d(self):
        self._ora(self._read_byte(self._addr_abs()))
        return 4

    def _op_0e(self):
        addr = self._addr_abs()
        self._write_byte(addr, self._asl(self._read_byte(addr)))
        return 6

    def _op_10(self):
        self._branch(not self.N)
        return 2

    def _op_11(self):
        self._ora(self._read_byte(self._addr_izy()))
        return 5

    def _op_15(self):
        self._ora(self._read_byte(self._addr_zpx()))
        return 4

    def _op_16(self):
        addr = self._addr_zpx()
        self._write_byte(addr, self._asl(self._read_byte(addr)))
        return 6

    def _op_18(self):
        self.C = False
        return 2

    def _op_19(self):
        self._ora(self._read_byte(self._addr_aby()))
        return 4

    def _op_1d(self):
        self._ora(self._read_byte(self._addr_abx()))
        return 4

    def _op_1e(self):
        addr = self._addr_abx()
        self._write_byte(addr, self._asl(self._read_byte(addr)))
        return 7

    def _op_20(self):
        addr = self._fetch_word()
        self._push_word((self.PC - 1) & 0xFFFF)
        self.PC = addr
        return 6

    def _op_21(self):
        self._and(self._read_byte(self._addr_izx()))
        return 6

    def _op_24(self):
        self._bit(self._read_byte(self._addr_zp()))
        return 3

    def _op_25(self):
        self._and(self._read_byte(self._addr_zp()))
        return 3

    def _op_26(self):
        addr = self._addr_zp()
        self._write_byte(addr, self._rol(self._read_byte(addr)))
        return 5

    def _op_28(self):
        self.set_status(self._pop_byte())
        return 4

    def _op_29(self):
        self._and(self._read_byte(self._addr_imm()))
        return 2

    def _op_2a(self):
        self.A = self._rol(self.A)
        return 2

    def _op_2c(self):
        self._bit(self._read_byte(self._addr_abs()))
        return 4

    def _op_2d(self):
        self._and(self._read_byte(self._addr_abs()))
        return 4

    def _op_2e(self):
        addr = self._addr_abs()
        self._write_byte(addr, self._rol(self._read_byte(addr)))
        return 6

    def _op_30(self):
        self._branch(self.N)
        return 2

    def _op_31(self):
        self._and(self._read_byte(self._addr_izy()))
        return 5

    def _op_35(self):
        self._and(self._read_byte(self._addr_zpx()))
        return 4

    def _op_36(self):
        addr = self._addr_zpx()
        self._write_byte(addr, self._rol(self._read_byte(addr)))
        return 6

    def _op_38(self):
        self.C = True
        return 2

    def _op_39(self):
        self._and(self._read_byte(self._addr_aby()))
        return 4

    def _op_3d(self):
        self._and(self._read_byte(self._addr_abx()))
        return 4

    def _op_3e(self):
        addr = self._addr_abx()
        self._write_byte(addr, self._rol(self._read_byte(addr)))
        return 7

    def _op_40(self):
        self.set_status(self._pop_byte())
        self.PC = self._pop_word()
        return 6

    def _op_41(self):
        self._eor(self._read_byte(self._addr_izx()))
        return 6

    def _op_45(self):
        self._eor(self._read_byte(self._addr_zp()))
        return 3

    def _op_46(self):
        addr = self._addr_zp()
        self._write_byte(addr, self._lsr(self._read_byte(addr)))
        return 5

    def _op_48(self):
        self._push_byte(self.A)
        return 3

    def _op_49(self):
        self._eor(self._read_byte(self._addr_imm()))
        return 2

    def _op_4a(self):
        self.A = self._lsr(self.A)
        return 2

    def _op_4c(self):
        self.PC = self._fetch_word()
        return 3

    def _op_4d(self):
        self._eor(self._read_byte(self._addr_abs()))
        return 4

    def _op_4e(self):
        addr = self._addr_abs()
        self._write_byte(addr, self._lsr(self._read_byte(addr)))
        return 6

    def _op_50(self):
        self._branch(not self.V)
        return 2

    def _op_51(self):
        self._eor(self._read_byte(self._addr_izy()))
        return 5

    def _op_55(self):
        self._eor(self._read_byte(self._addr_zpx()))
        return 4

    def _op_56(self):
        addr = self._addr_zpx()
        self._write_byte(addr, self._lsr(self._read_byte(addr)))
        return 6

    def _op_58(self):
        self.I = False
        return 2

    def _op_59(self):
        self._eor(self._read_byte(self._addr_aby()))
        return 4

    def _op_5d(self):
        self._eor(self._read_byte(self._addr_abx()))
        return 4

    def _op_5e(self):
        addr = self._addr_abx()
        self._write_byte(addr, self._lsr(self._read_byte(addr)))
        return 7

    def _op_60(self):
        self.PC = (self._pop_word() + 1) & 0xFFFF
        return 6

    def _op_61(self):
        self._adc(self._read_byte(self._addr_izx()))
        return 6

    def _op_65(self):
        self._adc(self._read_byte(self._addr_zp()))
        return 3

    def _op_66(self):
        addr = self._addr_zp()
        self._write_byte(addr, self._ror(self._read_byte(addr)))
        return 5

    def _op_68(self):
        self.A = self._pop_byte()
        self._set_nz(self.A)
        return 4

    def _op_69(self):
        self._adc(self._read_byte(self._addr_imm()))
        return 2

    def _op_6a(self):
        self.A = self._ror(self.A)
        return 2

    def _op_6c(self):
        self.PC = self._addr_ind()
        return 5

    def _op_6d(self):
        self._adc(self._read_byte(self._addr_abs()))
        return 4

    def _op_6e(self):
        addr = self._addr_abs()
        self._write_byte(addr, self._ror(self._read_byte(addr)))
        return 6

    def _op_70(self):
        self._branch(self.V)
        return 2

    def _op_71(self):
        self._adc(self._read_byte(self._addr_izy()))
        return 5

    def _op_75(self):
        self._adc(self._read_byte(self._addr_zpx()))
        return 4

    def _op_76(self):
        addr = self._addr_zpx()
        self._write_byte(addr, self._ror(self._read_byte(addr)))
        return 6

    def _op_78(self):
        self.I = True
        return 2

    def _op_79(self):
        self._adc(self._read_byte(self._addr_aby()))
        return 4

    def _op_7d(self):
        self._adc(self._read_byte(self._addr_abx()))
        return 4

    def _op_7e(self):
        addr = self._addr_abx()
        self._write_byte(addr, self._ror(self._read_byte(addr)))
        return 7

    def _op_81(self):
        self._write_byte(self._addr_izx(), self.A)
        return 6

    def _op_84(self):
        self._write_byte(self._addr_zp(), self.Y)
        return 3

    def _op_85(self):
        self._write_byte(self._addr_zp(), self.A)
        return 3

    def _op_86(self):
        self._write_byte(self._addr_zp(), self.X)
        return 3

    def _op_88(self):
        self.Y = (self.Y - 1) & 0xFF
        self._set_nz(self.Y)
        return 2

    def _op_8a(self):
        self.A = self.X
        self._set_nz(self.A)
        return 2

    def _op_8c(self):
        self._write_byte(self._addr_abs(), self.Y)
        return 4

    def _op_8d(self):
        self._write_byte(self._addr_abs(), self.A)
        return 4

    def _op_8e(self):
        self._write_byte(self._addr_abs(), self.X)
        return 4

    def _op_90(self):
        self._branch(not self.C)
        return 2

    def _op_91(self):
        self._write_byte(self._addr_izy(), self.A)
        return 6

    def _op_94(self):
        self._write_byte(self._addr_zpx(), self.Y)
        return 4

    def _op_95(self):
        self._write_byte(self._addr_zpx(), self.A)
        return 4

    def _op_96(self):
        self._write_byte(self._addr_zpy(), self.X)
        return 4

    def _op_98(self):
        self.A = self.Y
        self._set_nz(self.A)
        return 2

    def _op_99(self):
        self._write_byte(self._addr_aby(), self.A)
        return 5

    def _op_9a(self):
        self.SP = self.X
        return 2

    def _op_9d(self):
        self._write_byte(self._addr_abx(), self.A)
        return 5

    def _op_a0(self):
        self.Y = self._read_byte(self._addr_imm())
        self._set_nz(self.Y)
        return 2

    def _op_a1(self):
        self.A = self._read_byte(self._addr_izx())
        self._set_nz(self.A)
        return 6

    def _op_a2(self):
        self.X = self._read_byte(self._addr_imm())
        self._set_nz(self.X)
        return 2

    def _op_a4(self):
        self.Y = self._read_byte(self._addr_zp())
        self._set_nz(self.Y)
        return 3

    def _op_a5(self):
        self.A = self._read_byte(self._addr_zp())
        self._set_nz(self.A)
        return 3

    def _op_a6(self):
        self.X = self._read_byte(self._addr_zp())
        self._set_nz(self.X)
        return 3

    def _op_a8(self):
        self.Y = self.A
        self._set_nz(self.Y)
        return 2

    def _op_a9(self):
        self.A = self._read_byte(self._addr_imm())
        self._set_nz(self.A)
        return 2

    def _op_aa(self):
        self.X = self.A
        self._set_nz(self.X)
        return 2

    def _op_ac(self):
        self.Y = self._read_byte(self._addr_abs())
        self._set_nz(self.Y)
        return 4

    def _op_ad(self):
        self.A = self._read_byte(self._addr_abs())
        self._set_nz(self.A)
        return 4

    def _op_ae(self):
        self.X = self._read_byte(self._addr_abs())
        self._set_nz(self.X)
        return 4

    def _op_b0(self):
        self._branch(self.C)
        return 2

    def _op_b1(self):
        self.A = self._read_byte(self._addr_izy())
        self._set_nz(self.A)
        return 5

    def _op_b4(self):
        self.Y = self._read_byte(self._addr_zpx())
        self._set_nz(self.Y)
        return 4

    def _op_b5(self):
        self.A = self._read_byte(self._addr_zpx())
        self._set_nz(self.A)
        return 4

    def _op_b6(self):
        self.X = self._read_byte(self._addr_zpy())
        self._set_nz(self.X)
        return 4

    def _op_b8(self):
        self.V = False
        return 2

    def _op_b9(self):
        self.A = self._read_byte(self._addr_aby())
        self._set_nz(self.A)
        return 4

    def _op_ba(self):
        self.X = self.SP
        self._set_nz(self.X)
        return 2

    def _op_bc(self):
        self.Y = self._read_byte(self._addr_abx())
        self._set_nz(self.Y)
        return 4

    def _op_bd(self):
        self.A = self._read_byte(self._addr_abx())
        self._set_nz(self.A)
        return 4

    def _op_be(self):
        self.X = self._read_byte(self._addr_aby())
        self._set_nz(self.X)
        return 4

    def _op_c0(self):
        self._cmp(self.Y, self._read_byte(self._addr_imm()))
        return 2

    def _op_c1(self):
        self._cmp(self.A, self._read_byte(self._addr_izx()))
        return 6

    def _op_c4(self):
        self._cmp(self.Y, self._read_byte(self._addr_zp()))
        return 3

    def _op_c5(self):
        self._cmp(self.A, self._read_byte(self._addr_zp()))
        return 3

    def _op_c6(self):
        addr = self._addr_zp()
        self._write_byte(addr, self._dec(self._read_byte(addr)))
        return 5

    def _op_c8(self):
        self.Y = (self.Y + 1) & 0xFF
        self._set_nz(self.Y)
        return 2

    def _op_c9(self):
        self._cmp(self.A, self._read_byte(self._addr_imm()))
        return 2

    def _op_ca(self):
        self.X = (self.X - 1) & 0xFF
        self._set_nz(self.X)
        return 2

    def _op_cc(self):
        self._cmp(self.Y, self._read_byte(self._addr_abs()))
        return 4

    def _op_cd(self):
        self._cmp(self.A, self._read_byte(self._addr_abs()))
        return 4

    def _op_ce(self):
        addr = self._addr_abs()
        self._write_byte(addr, self._dec(self._read_byte(addr)))
        return 6

    def _op_d0(self):
        self._branch(not self.Z)
        return 2

    def _op_d1(self):
        self._cmp(self.A, self._read_byte(self._addr_izy()))
        return 5

    def _op_d5(self):
        self._cmp(self.A, self._read_byte(self._addr_zpx()))
        return 4

    def _op_d6(self):
        addr = self._addr_zpx()
        self._write_byte(addr, self._dec(self._read_byte(addr)))
        return 6

    def _op_d8(self):
        self.D = False
        return 2

    def _op_d9(self):
        self._cmp(self.A, self._read_byte(self._addr_aby()))
        return 4

    def _op_dd(self):
        self._cmp(self.A, self._read_byte(self._addr_abx()))
        return 4

    def _op_de(self):
        addr = self._addr_abx()
        self._write_byte(addr, self._dec(self._read_byte(addr)))
        return 7

    def _op_e0(self):
        self._cmp(self.X, self._read_byte(self._addr_imm()))
        return 2

    def _op_e1(self):
        self._sbc(self._read_byte(self._addr_izx()))
        return 6

    def _op_e4(self):
        self._cmp(self.X, self._read_byte(self._addr_zp()))
        return 3

    def _op_e5(self):
        self._sbc(self._read_byte(self._addr_zp()))
        return 3

    def _op_e6(self):
        addr = self._addr_zp()
        self._write_byte(addr, self._inc(self._read_byte(addr)))
        return 5

    def _op_e8(self):
        self.X = (self.X + 1) & 0xFF
        self._set_nz(self.X)
        return 2

    def _op_e9(self):
        self._sbc(self._read_byte(self._addr_imm()))
        return 2

    def _op_ea(self):
        return 2

    def _op_ec(self):
        self._cmp(self.X, self._read_byte(self._addr_abs()))
        return 4

    def _op_ed(self):
        self._sbc(self._read_byte(self._addr_abs()))
        return 4

    def _op_ee(self):
        addr = self._addr_abs()
        self._write_byte(addr, self._inc(self._read_byte(addr)))
        return 6

    def _op_f0(self):
        self._branch(self.Z)
        return 2

    def _op_f1(self):
        self._sbc(self._read_byte(self._addr_izy()))
        return 5

    def _op_f5(self):
        self._sbc(self._read_byte(self._addr_zpx()))
        return 4

    def _op_f6(self):
        addr = self._addr_zpx()
        self._write_byte(addr, self._inc(self._read_byte(addr)))
        return 6

    def _op_f8(self):
        self.D = True
        return 2

    def _op_f9(self):
        self._sbc(self._read_byte(self._addr_aby()))
        return 4

    def _op_fd(self):
        self._sbc(self._read_byte(self._addr_abx()))
        return 4

    def _op_fe(self):
        addr = self._addr_abx()
        self._write_byte(addr, self._inc(self._read_byte(addr)))
        return 7


    def _execute(self, opcode: int) -> int:
        return self._opcodes[opcode]()
