#!/usr/bin/env python3
"""
Test Suite for Apple I Emulator

Tests the various components of the emulator:
- CPU6502 instruction execution
- Memory operations
- PIA functionality
- Integration tests
"""

import unittest
from cpu6502 import CPU6502
from memory import Memory, RAM, ROM
from pia import Apple1PIA, PIA
from display import ScreenBuffer
from keyboard import BufferedKeyboard
from roms import WOZ_MONITOR, get_woz_monitor
from apple1 import Apple1


class TestMemory(unittest.TestCase):
    """Test memory operations."""

    def test_ram_read_write(self):
        """Test basic RAM read/write."""
        ram = RAM(256, base=0x0000)
        ram.write(0x0000, 0x42)
        self.assertEqual(ram.read(0x0000), 0x42)

    def test_ram_bounds(self):
        """Test RAM bounds checking."""
        ram = RAM(256, base=0x0100)
        ram.write(0x0100, 0xAB)
        ram.write(0x01FF, 0xCD)
        self.assertEqual(ram.read(0x0100), 0xAB)
        self.assertEqual(ram.read(0x01FF), 0xCD)

    def test_rom_readonly(self):
        """Test that ROM is read-only."""
        rom = ROM(bytes([0x12, 0x34, 0x56]), base=0xF000)
        self.assertEqual(rom.read(0xF000), 0x12)
        self.assertEqual(rom.read(0xF001), 0x34)
        rom.write(0xF000, 0xFF)  # Should be ignored
        self.assertEqual(rom.read(0xF000), 0x12)

    def test_memory_mapping(self):
        """Test memory device mapping."""
        mem = Memory()
        ram = RAM(256, base=0x0000)
        rom = ROM(bytes([0xEA, 0x60]), base=0xFF00)

        mem.add_device(ram)
        mem.add_device(rom)

        # Test RAM
        mem.write(0x0000, 0x42)
        self.assertEqual(mem.read(0x0000), 0x42)

        # Test ROM
        self.assertEqual(mem.read(0xFF00), 0xEA)
        self.assertEqual(mem.read(0xFF01), 0x60)


class TestCPU6502(unittest.TestCase):
    """Test 6502 CPU operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.memory = Memory()
        self.ram = RAM(0x10000, base=0x0000)  # 64KB RAM for testing
        self.memory.add_device(self.ram)
        self.cpu = CPU6502(self.memory)

    def test_reset(self):
        """Test CPU reset."""
        # Set reset vector
        self.memory.write(0xFFFC, 0x00)
        self.memory.write(0xFFFD, 0x80)

        self.cpu.reset()
        self.assertEqual(self.cpu.PC, 0x8000)
        self.assertTrue(self.cpu.I)  # Interrupt disable set

    def test_lda_immediate(self):
        """Test LDA immediate addressing."""
        self.memory.write(0x8000, 0xA9)  # LDA #
        self.memory.write(0x8001, 0x42)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x42)
        self.assertFalse(self.cpu.Z)
        self.assertFalse(self.cpu.N)

    def test_lda_zero_flag(self):
        """Test LDA sets zero flag."""
        self.memory.write(0x8000, 0xA9)  # LDA #
        self.memory.write(0x8001, 0x00)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x00)
        self.assertTrue(self.cpu.Z)

    def test_lda_negative_flag(self):
        """Test LDA sets negative flag."""
        self.memory.write(0x8000, 0xA9)  # LDA #
        self.memory.write(0x8001, 0x80)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x80)
        self.assertTrue(self.cpu.N)

    def test_sta_zeropage(self):
        """Test STA zero page addressing."""
        self.memory.write(0x8000, 0xA9)  # LDA #$42
        self.memory.write(0x8001, 0x42)
        self.memory.write(0x8002, 0x85)  # STA $10
        self.memory.write(0x8003, 0x10)

        self.cpu.PC = 0x8000
        self.cpu.step()
        self.cpu.step()

        self.assertEqual(self.memory.read(0x0010), 0x42)

    def test_adc(self):
        """Test ADC instruction."""
        self.memory.write(0x8000, 0xA9)  # LDA #$10
        self.memory.write(0x8001, 0x10)
        self.memory.write(0x8002, 0x18)  # CLC
        self.memory.write(0x8003, 0x69)  # ADC #$05
        self.memory.write(0x8004, 0x05)

        self.cpu.PC = 0x8000
        self.cpu.step()  # LDA
        self.cpu.step()  # CLC
        self.cpu.step()  # ADC

        self.assertEqual(self.cpu.A, 0x15)
        self.assertFalse(self.cpu.C)

    def test_adc_with_carry(self):
        """Test ADC with carry set."""
        self.cpu.A = 0x10
        self.cpu.C = True

        self.memory.write(0x8000, 0x69)  # ADC #$05
        self.memory.write(0x8001, 0x05)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x16)  # 0x10 + 0x05 + 1

    def test_adc_overflow(self):
        """Test ADC overflow (carry out)."""
        self.cpu.A = 0xFF
        self.cpu.C = False

        self.memory.write(0x8000, 0x69)  # ADC #$01
        self.memory.write(0x8001, 0x01)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x00)
        self.assertTrue(self.cpu.C)
        self.assertTrue(self.cpu.Z)

    def test_sbc(self):
        """Test SBC instruction."""
        self.cpu.A = 0x10
        self.cpu.C = True  # No borrow

        self.memory.write(0x8000, 0xE9)  # SBC #$05
        self.memory.write(0x8001, 0x05)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x0B)

    def test_inx(self):
        """Test INX instruction."""
        self.cpu.X = 0x41

        self.memory.write(0x8000, 0xE8)  # INX

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.X, 0x42)

    def test_dex(self):
        """Test DEX instruction."""
        self.cpu.X = 0x01

        self.memory.write(0x8000, 0xCA)  # DEX

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.X, 0x00)
        self.assertTrue(self.cpu.Z)

    def test_jmp_absolute(self):
        """Test JMP absolute addressing."""
        self.memory.write(0x8000, 0x4C)  # JMP $9000
        self.memory.write(0x8001, 0x00)
        self.memory.write(0x8002, 0x90)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.PC, 0x9000)

    def test_jsr_rts(self):
        """Test JSR and RTS instructions."""
        # JSR $9000
        self.memory.write(0x8000, 0x20)
        self.memory.write(0x8001, 0x00)
        self.memory.write(0x8002, 0x90)

        # RTS at $9000
        self.memory.write(0x9000, 0x60)

        # NOP at $8003
        self.memory.write(0x8003, 0xEA)

        self.cpu.PC = 0x8000
        self.cpu.SP = 0xFF

        self.cpu.step()  # JSR
        self.assertEqual(self.cpu.PC, 0x9000)

        self.cpu.step()  # RTS
        self.assertEqual(self.cpu.PC, 0x8003)

    def test_branch_bne(self):
        """Test BNE (branch if not equal)."""
        self.cpu.Z = False

        self.memory.write(0x8000, 0xD0)  # BNE +$05
        self.memory.write(0x8001, 0x05)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.PC, 0x8007)  # 0x8002 + 5

    def test_branch_beq_not_taken(self):
        """Test BEQ when not taken."""
        self.cpu.Z = False

        self.memory.write(0x8000, 0xF0)  # BEQ +$05
        self.memory.write(0x8001, 0x05)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.PC, 0x8002)  # Branch not taken

    def test_push_pull(self):
        """Test PHA and PLA instructions."""
        self.cpu.A = 0x42
        self.cpu.SP = 0xFF

        self.memory.write(0x8000, 0x48)  # PHA
        self.memory.write(0x8001, 0xA9)  # LDA #$00
        self.memory.write(0x8002, 0x00)
        self.memory.write(0x8003, 0x68)  # PLA

        self.cpu.PC = 0x8000
        self.cpu.step()  # PHA
        self.assertEqual(self.cpu.SP, 0xFE)
        self.assertEqual(self.memory.read(0x01FF), 0x42)

        self.cpu.step()  # LDA #$00
        self.assertEqual(self.cpu.A, 0x00)

        self.cpu.step()  # PLA
        self.assertEqual(self.cpu.A, 0x42)
        self.assertEqual(self.cpu.SP, 0xFF)

    def test_and(self):
        """Test AND instruction."""
        self.cpu.A = 0xFF

        self.memory.write(0x8000, 0x29)  # AND #$0F
        self.memory.write(0x8001, 0x0F)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x0F)

    def test_ora(self):
        """Test ORA instruction."""
        self.cpu.A = 0xF0

        self.memory.write(0x8000, 0x09)  # ORA #$0F
        self.memory.write(0x8001, 0x0F)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0xFF)

    def test_eor(self):
        """Test EOR instruction."""
        self.cpu.A = 0xFF

        self.memory.write(0x8000, 0x49)  # EOR #$AA
        self.memory.write(0x8001, 0xAA)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x55)

    def test_asl_accumulator(self):
        """Test ASL accumulator."""
        self.cpu.A = 0x40

        self.memory.write(0x8000, 0x0A)  # ASL A

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x80)
        self.assertFalse(self.cpu.C)
        self.assertTrue(self.cpu.N)

    def test_lsr_accumulator(self):
        """Test LSR accumulator."""
        self.cpu.A = 0x02

        self.memory.write(0x8000, 0x4A)  # LSR A

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertEqual(self.cpu.A, 0x01)
        self.assertFalse(self.cpu.C)

    def test_cmp(self):
        """Test CMP instruction."""
        self.cpu.A = 0x42

        self.memory.write(0x8000, 0xC9)  # CMP #$42
        self.memory.write(0x8001, 0x42)

        self.cpu.PC = 0x8000
        self.cpu.step()

        self.assertTrue(self.cpu.Z)
        self.assertTrue(self.cpu.C)


class TestPIA(unittest.TestCase):
    """Test PIA operations."""

    def test_pia_reset(self):
        """Test PIA reset."""
        pia = PIA(base=0xD010)
        pia.write(0xD010, 0xFF)
        pia.reset()
        self.assertEqual(pia.DDRA, 0x00)
        self.assertEqual(pia.CRA, 0x00)

    def test_apple1_pia_keyboard(self):
        """Test Apple I PIA keyboard input."""
        pia = Apple1PIA(base=0xD010)

        # Initialize PIA (like Woz Monitor does at startup)
        # Set CRA bit 2 to select data register instead of DDR
        pia.write(0xD011, 0x07)  # CRA = 0x07 (enables data register access)

        # Simulate key press
        pia.key_press(ord('A'))

        # Read keyboard status
        status = pia.read(0xD011)
        self.assertTrue(status & 0x80)  # Key ready

        # Read key data
        data = pia.read(0xD010)
        self.assertEqual(data & 0x7F, ord('A'))

    def test_apple1_pia_display(self):
        """Test Apple I PIA display output."""
        pia = Apple1PIA(base=0xD010)
        output = []

        pia.set_display_callback(lambda c: output.append(c))

        # Enable display output
        pia.write(0xD013, 0x04)  # Set bit 2 in CRB
        pia.write(0xD012, ord('H'))

        self.assertEqual(output, [ord('H')])


class TestApple1Integration(unittest.TestCase):
    """Integration tests for the Apple I emulator."""

    def test_emulator_creation(self):
        """Test basic emulator creation."""
        apple1 = Apple1(ram_size=4096)
        self.assertIsNotNone(apple1.cpu)
        self.assertIsNotNone(apple1.memory)
        self.assertIsNotNone(apple1.pia)

    def test_emulator_reset(self):
        """Test emulator reset."""
        apple1 = Apple1()
        apple1.reset()
        # After reset, PC should be at reset vector (Woz Monitor entry)
        self.assertEqual(apple1.cpu.PC, 0xFF00)

    def test_load_program(self):
        """Test loading a program."""
        apple1 = Apple1()

        # Simple program: LDA #$42, STA $00, BRK
        program = bytes([0xA9, 0x42, 0x85, 0x00, 0x00])
        apple1.load_program(program, 0x0300)

        self.assertEqual(apple1.memory.read(0x0300), 0xA9)
        self.assertEqual(apple1.memory.read(0x0301), 0x42)

    def test_run_simple_program(self):
        """Test running a simple program."""
        apple1 = Apple1()

        # LDA #$42, STA $00, LDA #$00, LDA $00
        program = bytes([
            0xA9, 0x42,  # LDA #$42
            0x85, 0x00,  # STA $00
            0xA9, 0x00,  # LDA #$00
            0xA5, 0x00,  # LDA $00
        ])
        apple1.load_program(program, 0x0300)
        apple1.set_pc(0x0300)

        # Execute instructions
        apple1.step()  # LDA #$42
        self.assertEqual(apple1.cpu.A, 0x42)

        apple1.step()  # STA $00
        self.assertEqual(apple1.memory.read(0x0000), 0x42)

        apple1.step()  # LDA #$00
        self.assertEqual(apple1.cpu.A, 0x00)

        apple1.step()  # LDA $00
        self.assertEqual(apple1.cpu.A, 0x42)


class TestDisplay(unittest.TestCase):
    """Test display functionality."""

    def test_screen_buffer(self):
        """Test screen buffer output."""
        buffer = ScreenBuffer()

        buffer.write(ord('H'))
        buffer.write(ord('I'))

        output = buffer.get_output_log()
        self.assertIn('H', output)
        self.assertIn('I', output)

    def test_carriage_return(self):
        """Test carriage return handling."""
        buffer = ScreenBuffer()

        buffer.write(ord('A'))
        buffer.write(0x0D)  # CR
        buffer.write(ord('B'))

        self.assertEqual(buffer.cursor_y, 1)
        self.assertEqual(buffer.cursor_x, 1)


class TestKeyboard(unittest.TestCase):
    """Test keyboard functionality."""

    def test_buffered_keyboard(self):
        """Test buffered keyboard."""
        kbd = BufferedKeyboard()

        kbd.queue_key(ord('A'))
        self.assertTrue(kbd.has_key())

        key = kbd.get_key()
        self.assertEqual(key, ord('A'))
        self.assertFalse(kbd.has_key())

    def test_lowercase_conversion(self):
        """Test lowercase to uppercase conversion."""
        kbd = BufferedKeyboard()

        kbd.queue_key(ord('a'))
        key = kbd.get_key()
        self.assertEqual(key, ord('A'))

    def test_string_queue(self):
        """Test queuing a string."""
        kbd = BufferedKeyboard()

        kbd.queue_string("HELLO")

        result = ""
        while kbd.has_key():
            result += chr(kbd.get_key())

        self.assertEqual(result, "HELLO")


if __name__ == '__main__':
    unittest.main()
