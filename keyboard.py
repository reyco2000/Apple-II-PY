"""
Keyboard Input Handler for Apple I Emulator

Provides keyboard input handling for the emulator with support for
both blocking and non-blocking input modes.

The Apple I keyboard was uppercase only and used CR (not LF) for newlines.
"""

import sys
from typing import Optional, Callable, List
from abc import ABC, abstractmethod


class Keyboard(ABC):
    """
    Abstract base class for keyboard input.
    """

    @abstractmethod
    def get_key(self) -> Optional[int]:
        """Get a key if available, None otherwise."""
        pass

    @abstractmethod
    def has_key(self) -> bool:
        """Check if a key is available."""
        pass

    def reset(self):
        """Reset the keyboard state."""
        pass


class BufferedKeyboard(Keyboard):
    """
    Simple buffered keyboard for programmatic input.
    """

    def __init__(self):
        self._buffer: List[int] = []

    def queue_key(self, key: int):
        """Queue a single key."""
        # Convert lowercase to uppercase
        if 0x61 <= key <= 0x7A:
            key -= 0x20
        # Convert LF to CR
        if key == 0x0A:
            key = 0x0D
        self._buffer.append(key & 0x7F)

    def queue_string(self, s: str):
        """Queue a string of characters."""
        for char in s:
            self.queue_key(ord(char))

    def get_key(self) -> Optional[int]:
        """Get the next key from the buffer."""
        if self._buffer:
            return self._buffer.pop(0)
        return None

    def has_key(self) -> bool:
        """Check if keys are available."""
        return len(self._buffer) > 0

    def reset(self):
        """Clear the buffer."""
        self._buffer = []


class TerminalKeyboard(Keyboard):
    """
    Terminal-based keyboard using stdin.
    Supports both blocking and non-blocking modes.
    Works on both Windows and Unix/Linux/macOS.
    """

    def __init__(self, blocking: bool = False):
        self._blocking = blocking
        self._buffer: List[int] = []
        self._old_settings = None
        self._is_windows = sys.platform == 'win32'

    def _setup_terminal(self):
        """Set up terminal for raw input."""
        if self._is_windows:
            return  # No setup needed on Windows
        try:
            import tty
            import termios
            fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        except (ImportError, AttributeError):
            pass

    def _restore_terminal(self):
        """Restore terminal settings."""
        if self._is_windows:
            return  # No restore needed on Windows
        if self._old_settings:
            try:
                import termios
                fd = sys.stdin.fileno()
                termios.tcsetattr(fd, termios.TCSADRAIN, self._old_settings)
            except (ImportError, AttributeError):
                pass

    def get_key(self) -> Optional[int]:
        """Get a key from stdin."""
        # First check buffer
        if self._buffer:
            return self._buffer.pop(0)

        if self._is_windows:
            return self._get_key_windows()
        else:
            return self._get_key_unix()

    def _get_key_windows(self) -> Optional[int]:
        """Get key on Windows using msvcrt."""
        try:
            import msvcrt
            if self._blocking:
                char = msvcrt.getch()
                if char:
                    return self._convert_key(char[0])
            else:
                if msvcrt.kbhit():
                    char = msvcrt.getch()
                    if char:
                        return self._convert_key(char[0])
        except ImportError:
            pass
        return None

    def _get_key_unix(self) -> Optional[int]:
        """Get key on Unix using select."""
        if self._blocking:
            char = sys.stdin.read(1)
            if char:
                return self._convert_key(ord(char))
        else:
            # Non-blocking read
            if self._key_available():
                char = sys.stdin.read(1)
                if char:
                    return self._convert_key(ord(char))
        return None

    def _key_available(self) -> bool:
        """Check if a key is available."""
        if self._is_windows:
            try:
                import msvcrt
                return msvcrt.kbhit()
            except ImportError:
                return False
        else:
            try:
                import select
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                return bool(readable)
            except (ValueError, OSError):
                return False

    def has_key(self) -> bool:
        """Check if a key is available."""
        if self._buffer:
            return True
        return self._key_available()

    def _convert_key(self, key: int) -> int:
        """Convert key to Apple I format."""
        # Uppercase conversion
        if 0x61 <= key <= 0x7A:
            key -= 0x20
        # LF to CR
        if key == 0x0A:
            key = 0x0D
        return key & 0x7F

    def queue_key(self, key: int):
        """Queue a key for later retrieval."""
        self._buffer.append(self._convert_key(key))

    def queue_string(self, s: str):
        """Queue a string."""
        for char in s:
            self.queue_key(ord(char))


class CursesKeyboard(Keyboard):
    """
    Curses-based keyboard for use with CursesDisplay.
    """

    def __init__(self, screen=None):
        self._screen = screen
        self._buffer: List[int] = []

    def set_screen(self, screen):
        """Set the curses screen for input."""
        self._screen = screen
        if screen:
            screen.nodelay(True)  # Non-blocking input
            screen.keypad(True)

    def get_key(self) -> Optional[int]:
        """Get a key using curses."""
        if self._buffer:
            return self._buffer.pop(0)

        if self._screen:
            try:
                key = self._screen.getch()
                if key != -1:
                    return self._convert_key(key)
            except Exception:
                pass

        return None

    def has_key(self) -> bool:
        """Check if a key is available."""
        if self._buffer:
            return True
        # Curses doesn't have a clean way to peek without consuming
        return False

    def _convert_key(self, key: int) -> int:
        """Convert curses key to Apple I format."""
        import curses

        # Handle special keys
        if key == curses.KEY_BACKSPACE or key == 127:
            return 0x08
        if key == curses.KEY_ENTER or key == 10:
            return 0x0D

        # Only allow ASCII
        if key > 127:
            return 0

        # Uppercase conversion
        if 0x61 <= key <= 0x7A:
            key -= 0x20

        return key & 0x7F

    def queue_key(self, key: int):
        """Queue a key."""
        if 0x61 <= key <= 0x7A:
            key -= 0x20
        if key == 0x0A:
            key = 0x0D
        self._buffer.append(key & 0x7F)

    def queue_string(self, s: str):
        """Queue a string."""
        for char in s:
            self.queue_key(ord(char))


def get_keyboard(mode: str = 'buffered') -> Keyboard:
    """
    Factory function to create a keyboard instance.

    Args:
        mode: 'buffered', 'terminal', or 'curses'

    Returns:
        Keyboard instance
    """
    if mode == 'terminal':
        return TerminalKeyboard()
    elif mode == 'curses':
        return CursesKeyboard()
    else:
        return BufferedKeyboard()
