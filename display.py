"""
Display Subsystem for Apple I Emulator
Provides terminal-style display emulation.

The Apple I display was a 40-column terminal display with
uppercase characters only.

Ported from jscrane/Apple1 (https://github.com/jscrane/Apple1)
"""

import sys
from typing import Optional, Callable, List
from abc import ABC, abstractmethod


class Display(ABC):
    """
    Abstract base class for display implementations.
    """

    def __init__(self, columns: int = 40, rows: int = 24):
        self.columns = columns
        self.rows = rows
        self.cursor_x = 0
        self.cursor_y = 0

    @abstractmethod
    def write(self, char: int):
        """Write a character to the display."""
        pass

    @abstractmethod
    def clear(self):
        """Clear the display."""
        pass

    @abstractmethod
    def status(self, message: str):
        """Display a status message."""
        pass

    def reset(self):
        """Reset the display."""
        self.cursor_x = 0
        self.cursor_y = 0
        self.clear()


class TerminalDisplay(Display):
    """
    Terminal-based display using stdout.

    Emulates the Apple I display behavior:
    - 40 columns, 24 rows
    - Uppercase only
    - CR moves cursor to start of line
    - Backspace/rubout (underscore on Apple I) erases previous char
    """

    def __init__(self, columns: int = 40, rows: int = 24):
        super().__init__(columns, rows)
        self._buffer: List[List[int]] = []
        self._output_callback: Optional[Callable[[str], None]] = None
        self.clear()

    def set_output_callback(self, callback: Callable[[str], None]):
        """Set callback for output (alternative to stdout)."""
        self._output_callback = callback

    def write(self, char: int):
        """
        Write a character to the display.

        Args:
            char: ASCII code (0-127)
        """
        char = char & 0x7F

        if char == 0x0D:  # Carriage return
            self._output('\r\n')
            self.cursor_x = 0
            self.cursor_y += 1
            if self.cursor_y >= self.rows:
                self._scroll()

        elif char == 0x08 or char == 0x7F or char == ord('_'):  # Backspace/DEL/rubout
            if self.cursor_x > 0:
                self.cursor_x -= 1
                self._buffer[self.cursor_y][self.cursor_x] = 0x20
                self._output('\b \b')

        elif 0x20 <= char < 0x7F:  # Printable characters
            # Convert to uppercase
            if 0x61 <= char <= 0x7A:
                char -= 0x20

            self._buffer[self.cursor_y][self.cursor_x] = char
            self._output(chr(char))
            self.cursor_x += 1

            if self.cursor_x >= self.columns:
                self.cursor_x = 0
                self.cursor_y += 1
                self._output('\r\n')
                if self.cursor_y >= self.rows:
                    self._scroll()

    def _output(self, text: str):
        """Output text to terminal or callback."""
        if self._output_callback:
            self._output_callback(text)
        else:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _scroll(self):
        """Scroll the display up one line."""
        self._buffer.pop(0)
        self._buffer.append([0x20] * self.columns)
        self.cursor_y = self.rows - 1

    def clear(self):
        """Clear the display."""
        self._buffer = [[0x20] * self.columns for _ in range(self.rows)]
        self.cursor_x = 0
        self.cursor_y = 0

    def status(self, message: str):
        """Display a status message."""
        self._output(f'\n[{message}]\n')

    def get_screen_text(self) -> str:
        """Get the current screen content as a string."""
        lines = []
        for row in self._buffer:
            line = ''.join(chr(c) if 0x20 <= c < 0x7F else ' ' for c in row)
            lines.append(line.rstrip())
        return '\n'.join(lines)


class ScreenBuffer(Display):
    """
    In-memory screen buffer for headless operation or GUI integration.
    """

    def __init__(self, columns: int = 40, rows: int = 24):
        super().__init__(columns, rows)
        self._buffer: List[List[int]] = []
        self._output_log: List[int] = []
        self.clear()

    def write(self, char: int):
        """Write a character to the buffer."""
        char = char & 0x7F
        self._output_log.append(char)

        if char == 0x0D:  # Carriage return
            self.cursor_x = 0
            self.cursor_y += 1
            if self.cursor_y >= self.rows:
                self._scroll()

        elif char == 0x08 or char == 0x7F:  # Backspace
            if self.cursor_x > 0:
                self.cursor_x -= 1
                self._buffer[self.cursor_y][self.cursor_x] = 0x20

        elif 0x20 <= char < 0x7F:  # Printable
            if 0x61 <= char <= 0x7A:
                char -= 0x20
            self._buffer[self.cursor_y][self.cursor_x] = char
            self.cursor_x += 1
            if self.cursor_x >= self.columns:
                self.cursor_x = 0
                self.cursor_y += 1
                if self.cursor_y >= self.rows:
                    self._scroll()

    def _scroll(self):
        """Scroll up one line."""
        self._buffer.pop(0)
        self._buffer.append([0x20] * self.columns)
        self.cursor_y = self.rows - 1

    def clear(self):
        """Clear the buffer."""
        self._buffer = [[0x20] * self.columns for _ in range(self.rows)]
        self._output_log = []
        self.cursor_x = 0
        self.cursor_y = 0

    def status(self, message: str):
        """Log a status message."""
        for char in f'[{message}]\r':
            self._output_log.append(ord(char))

    def get_line(self, row: int) -> str:
        """Get a single line of text."""
        if 0 <= row < self.rows:
            return ''.join(chr(c) for c in self._buffer[row])
        return ''

    def get_char(self, row: int, col: int) -> int:
        """Get a character at position."""
        if 0 <= row < self.rows and 0 <= col < self.columns:
            return self._buffer[row][col]
        return 0x20

    def get_output_log(self) -> str:
        """Get all output as a string."""
        return ''.join(chr(c) if 0x20 <= c < 0x7F or c in (0x0D, 0x0A) else ''
                       for c in self._output_log)

    def get_screen_text(self) -> str:
        """Get the current screen content as a string."""
        lines = []
        for row in self._buffer:
            line = ''.join(chr(c) if 0x20 <= c < 0x7F else ' ' for c in row)
            lines.append(line.rstrip())
        return '\n'.join(lines)


class CursesDisplay(Display):
    """
    Curses-based display for full-screen terminal operation.
    Provides a more authentic Apple I experience with cursor and screen management.
    """

    def __init__(self, columns: int = 40, rows: int = 24):
        super().__init__(columns, rows)
        self._screen = None
        self._buffer: List[List[int]] = []
        self.clear()

    def init_curses(self):
        """Initialize curses mode."""
        import curses
        self._screen = curses.initscr()
        curses.noecho()
        curses.cbreak()
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        self._screen.attron(curses.color_pair(1))
        self._screen.clear()

    def cleanup_curses(self):
        """Cleanup curses mode."""
        if self._screen:
            import curses
            curses.nocbreak()
            curses.echo()
            curses.endwin()
            self._screen = None

    def write(self, char: int):
        """Write a character using curses."""
        char = char & 0x7F

        if char == 0x0D:
            self.cursor_x = 0
            self.cursor_y += 1
            if self.cursor_y >= self.rows:
                self._scroll()

        elif char == 0x08 or char == 0x7F:
            if self.cursor_x > 0:
                self.cursor_x -= 1
                self._buffer[self.cursor_y][self.cursor_x] = 0x20
                if self._screen:
                    self._screen.addch(self.cursor_y, self.cursor_x, ' ')

        elif 0x20 <= char < 0x7F:
            if 0x61 <= char <= 0x7A:
                char -= 0x20
            self._buffer[self.cursor_y][self.cursor_x] = char
            if self._screen:
                self._screen.addch(self.cursor_y, self.cursor_x, char)
            self.cursor_x += 1
            if self.cursor_x >= self.columns:
                self.cursor_x = 0
                self.cursor_y += 1
                if self.cursor_y >= self.rows:
                    self._scroll()

        if self._screen:
            self._screen.move(self.cursor_y, self.cursor_x)
            self._screen.refresh()

    def _scroll(self):
        """Scroll the display."""
        self._buffer.pop(0)
        self._buffer.append([0x20] * self.columns)
        self.cursor_y = self.rows - 1
        if self._screen:
            self._screen.scroll()

    def clear(self):
        """Clear the display."""
        self._buffer = [[0x20] * self.columns for _ in range(self.rows)]
        self.cursor_x = 0
        self.cursor_y = 0
        if self._screen:
            self._screen.clear()
            self._screen.refresh()

    def status(self, message: str):
        """Display status in the last row."""
        if self._screen:
            self._screen.addstr(self.rows, 0, f'[{message}]')
            self._screen.refresh()

    def get_screen_text(self) -> str:
        """Get the current screen content as a string."""
        lines = []
        for row in self._buffer:
            line = ''.join(chr(c) if 0x20 <= c < 0x7F else ' ' for c in row)
            lines.append(line.rstrip())
        return '\n'.join(lines)
