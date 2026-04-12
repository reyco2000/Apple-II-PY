import tkinter as tk
import threading
import time
import os
import math
from display import ScreenBuffer
from keyboard import BufferedKeyboard

class DialKnob(tk.Canvas):
    """Custom rotary knob widget for Tkinter."""
    def __init__(self, parent, width=70, height=80, min_val=0, max_val=100, is_switch=False, command=None, label="BRIGHTNESS", label_left="", label_right="", **kwargs):
        super().__init__(parent, width=width, height=height, **kwargs)
        self.min_val = min_val
        self.max_val = max_val
        self.is_switch = is_switch
        self.value = min_val
        self._internal_val = min_val
        self.command = command
        self.radius = 20
        self.center = (width/2, height/2 - 10)
        self.label = label
        self.label_left = label_left
        self.label_right = label_right
        self._height = height
        
        self.start_angle = math.pi * 0.75 
        self.end_angle = math.pi * 2.25 
        
        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)
        self.draw()
        
    def _on_click(self, event):
        self.last_y = event.y
        
    def _on_drag(self, event):
        dy = self.last_y - event.y
        change = (dy * 2) if not self.is_switch else (dy * 0.05)
        self.set(self._internal_val + change)
        self.last_y = event.y
        
    def set(self, val):
        self._internal_val = max(self.min_val, min(self.max_val, val))
        v = round(self._internal_val) if self.is_switch else self._internal_val
        if getattr(self, '_first_draw', True) or v != self.value:
            self._first_draw = False
            self.value = v
            self.draw()
            if self.command:
                self.command(self.value)
            
    def draw(self):
        self.delete("all")
        c_x, c_y = self.center
        r = self.radius
        
        # Shadow cast below the knob
        self.create_oval(c_x-r+3, c_y-r+3, c_x+r+3, c_y+r+3, fill="#020202", outline="")
        # Silver outer rim
        self.create_oval(c_x-r, c_y-r, c_x+r, c_y+r, fill="#444444", outline="#222222")
        
        # Inner black plastic dial
        in_r = r - 4
        self.create_oval(c_x-in_r, c_y-in_r, c_x+in_r, c_y+in_r, fill="#1a1a1a", outline="#111111")
        
        # Radial grip lines
        for i in range(0, 360, 20):
            rad = math.radians(i)
            x1 = c_x + math.cos(rad) * in_r
            y1 = c_y + math.sin(rad) * in_r
            x2 = c_x + math.cos(rad) * r
            y2 = c_y + math.sin(rad) * r
            self.create_line(x1, y1, x2, y2, fill="#666666", width=1)
            
        # Center metallic cap
        cap_r = r - 12
        self.create_oval(c_x-cap_r, c_y-cap_r, c_x+cap_r, c_y+cap_r, fill="#333333", outline="#555555")

        pct = (self.value - self.min_val) / (self.max_val - self.min_val)
        if (self.max_val - self.min_val) == 0: pct = 0
        current_angle = self.start_angle + pct * (self.end_angle - self.start_angle)
        
        # White painted indicator line extending from the cap
        ix = c_x + math.cos(current_angle) * (r - 2)
        iy = c_y + math.sin(current_angle) * (r - 2)
        inner_x = c_x + math.cos(current_angle) * cap_r
        inner_y = c_y + math.sin(current_angle) * cap_r
        self.create_line(inner_x, inner_y, ix, iy, fill="#eeeeee", width=3, capstyle=tk.ROUND)
        
        # Title below knob
        self.create_text(c_x, self._height - 10, text=self.label, fill="#aaaaaa", font=("Courier", 8, "bold"))
        
        if self.label_left:
            self.create_text(c_x - r - 8, c_y + r + 2, text=self.label_left, fill="#aaaaaa", font=("Courier", 6, "bold"))
        if self.label_right:
            self.create_text(c_x + r + 8, c_y + r + 2, text=self.label_right, fill="#aaaaaa", font=("Courier", 6, "bold"))

class LEDIndicator(tk.Canvas):
    """Realistic Red LED indicator."""
    def __init__(self, parent, size=24, is_on=True, **kwargs):
        super().__init__(parent, width=size, height=size, **kwargs)
        self.size = size
        self.is_on = bool(is_on)
        self.draw()
        
    def set(self, is_on):
        self.is_on = bool(is_on)
        self.draw()
        
    def draw(self):
        self.delete("all")
        s = self.size
        # Outer silver housing
        self.create_oval(2, 2, s-2, s-2, fill="#777777", outline="#222222")
        self.create_oval(3, 3, s-3, s-3, fill="#333333", outline="")
        
        if self.is_on:
            self.create_oval(4, 4, s-4, s-4, fill="#ff0000", outline="#aa0000")
            self.create_oval(s//2-2, s//2-2, s//2+4, s//2+4, fill="#ff6666", outline="")
            self.create_oval(6, 6, 9, 9, fill="#ffffff", outline="") # glass reflection
        else:
            self.create_oval(4, 4, s-4, s-4, fill="#440000", outline="#220000")
            self.create_oval(6, 6, 8, 8, fill="#663333", outline="")

class ToggleSwitch(tk.Canvas):
    """Realistic retro horizontal toggle/elbow switch."""
    def __init__(self, parent, width=100, height=80, is_on=True, command=None, label="POWER", label_left="OFF", label_right="ON", **kwargs):
        super().__init__(parent, width=width, height=height, **kwargs)
        self.value = 1 if is_on else 0
        self.command = command
        self.center = (width/2, height/2 - 5)
        self.label = label
        self.label_left = label_left
        self.label_right = label_right
        self._height = height
        
        self.bind("<Button-1>", self._on_click)
        self.draw()
        
    def _on_click(self, event):
        self.value = 1 - self.value
        self.draw()
        if self.command:
            self.command(self.value)
            
    def set(self, val):
        self.value = val
        self.draw()
        
    def draw(self):
        self.delete("all")
        c_x, c_y = self.center
        
        # Base plate (Metallic hex nut)
        br = 16
        self.create_oval(c_x-br-2, c_y-br-2, c_x+br+2, c_y+br+2, fill="#020202", outline="") # Shadow
        self.create_oval(c_x-br, c_y-br, c_x+br, c_y+br, fill="#666666", outline="#333333")
        self.create_oval(c_x-br+3, c_y-br+3, c_x+br-3, c_y+br-3, fill="#222222", outline="#000000") # inner socket hole
        
        # The bat (elbow lever)
        if self.value == 1:
            # Pointing RIGHT (ON)
            self.create_polygon(c_x, c_y, c_x+25, c_y-10, c_x+25, c_y+10, fill="#050505")
            self.create_polygon(c_x, c_y-4, c_x+28, c_y-6, c_x+28, c_y+6, c_x, c_y+4, fill="#cccccc", outline="#aaaaaa")
            self.create_oval(c_x+23, c_y-6, c_x+33, c_y+6, fill="#dddddd", outline="#bbbbbb")
            self.create_oval(c_x+28, c_y-2, c_x+31, c_y+1, fill="#ffffff", outline="") 
        else:
            # Pointing LEFT (OFF)
            self.create_polygon(c_x, c_y, c_x-25, c_y-10, c_x-25, c_y+10, fill="#050505")
            self.create_polygon(c_x, c_y-4, c_x-28, c_y-6, c_x-28, c_y+6, c_x, c_y+4, fill="#999999", outline="#777777")
            self.create_oval(c_x-33, c_y-6, c_x-23, c_y+6, fill="#aaaaaa", outline="#888888")
            self.create_oval(c_x-28, c_y-2, c_x-25, c_y+1, fill="#cccccc", outline="") 
            
        self.create_oval(c_x-5, c_y-7, c_x+5, c_y+7, fill="#888888", outline="#555555")

        self.create_text(c_x, self._height - 10, text=self.label, fill="#aaaaaa", font=("Courier", 8, "bold"))
        if self.label_left:
            self.create_text(c_x - 35, c_y, text=self.label_left, fill="#aaaaaa", font=("Courier", 6, "bold"))
        if self.label_right:
            self.create_text(c_x + 35, c_y, text=self.label_right, fill="#aaaaaa", font=("Courier", 6, "bold"))

class Apple1GUI:
    """Tkinter-based GUI for Apple I generating display from ROM."""
    def __init__(self, apple1_instance):
        self.apple1 = apple1_instance
        self.root = tk.Tk()
        self.root.title("Apple I Emulator - Composite Display")
        self.root.configure(bg="#050505")
        self.root.resizable(False, False)
        
        self.scale = 3
        self.char_width = 7 * self.scale
        self.char_height = 8 * self.scale
        
        self.padding = 60
        self.w = 40 * self.char_width
        self.h = 24 * self.char_height
        
        canvas_w = self.w + (self.padding * 2)
        canvas_h = self.h + (self.padding * 2)
        
        self.canvas = tk.Canvas(self.root, width=canvas_w, height=canvas_h, bg="#050505", highlightthickness=0)
        self.canvas.pack(padx=20, pady=(20, 10))
        
        # Build the physical phosphor tube shape below the text
        self.screen_bg_color = "#050505"
        margin = 20 # Inner margin between text and tube edge
        r = 50 # Screen corner rounding radius
        
        x0 = self.padding - margin
        y0 = self.padding - margin
        w = self.w + (margin * 2)
        h = self.h + (margin * 2)
        
        self.canvas.create_rectangle(x0+r, y0, x0+w-r, y0+h, fill=self.screen_bg_color, outline="", tags="screen_tube")
        self.canvas.create_rectangle(x0, y0+r, x0+w, y0+h-r, fill=self.screen_bg_color, outline="", tags="screen_tube")
        self.canvas.create_oval(x0, y0, x0+r*2, y0+r*2, fill=self.screen_bg_color, outline="", tags="screen_tube")
        self.canvas.create_oval(x0+w-r*2, y0, x0+w, y0+r*2, fill=self.screen_bg_color, outline="", tags="screen_tube")
        self.canvas.create_oval(x0, y0+h-r*2, x0+r*2, y0+h, fill=self.screen_bg_color, outline="", tags="screen_tube")
        self.canvas.create_oval(x0+w-r*2, y0+h-r*2, x0+w, y0+h, fill=self.screen_bg_color, outline="", tags="screen_tube")
        
        # Add control frame
        self.control_frame = tk.Frame(self.root, bg="#050505")
        self.control_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 20), padx=30)
        
        # Left side knobs
        self.knob_frame = tk.Frame(self.control_frame, bg="#050505")
        self.knob_frame.pack(side=tk.LEFT)
        
        # Power LED
        self.power_led = LEDIndicator(self.knob_frame, size=24, bg="#050505", highlightthickness=0)
        self.power_led.pack(side=tk.LEFT, padx=(0, 10))
        
        self.power_switch = ToggleSwitch(self.knob_frame, width=100, height=80, is_on=True, 
                                         label="POWER", label_left="OFF", label_right="ON", bg="#050505", highlightthickness=0, 
                                         command=self._on_power_toggle, cursor="hand2")
        self.power_switch.pack(side=tk.LEFT, padx=(0, 20))
        
        self.bright_scale = DialKnob(self.knob_frame, width=80, height=80, bg="#050505", highlightthickness=0, command=self._on_brightness, cursor="hand2")
        self.bright_scale.pack(side=tk.LEFT, padx=10)
        self.bright_scale.set(10) # Default to 10% phosphor green
        
        # Right side action buttons
        self.btn_frame = tk.Frame(self.control_frame, bg="#050505")
        self.btn_frame.pack(side=tk.RIGHT)
        
        btn_opts = {"bg": "#222222", "fg": "#33ff33", "activebackground": "#33ff33", "activeforeground": "black", "font": ("Courier", 10), "relief": tk.FLAT, "cursor": "hand2"}
        tk.Button(self.btn_frame, text="Reset", command=self._on_reset, **btn_opts).pack(side=tk.LEFT, padx=10)
        tk.Button(self.btn_frame, text="Paste Code", command=self._on_paste_window, **btn_opts).pack(side=tk.LEFT, padx=10)
        
        self.char_images = {}
        self._load_charmap()
        
        self.screen_items = [[None for _ in range(40)] for _ in range(24)]
        self.last_buffer = [[-1 for _ in range(40)] for _ in range(24)]
        
        for y in range(24):
            for x in range(40):
                self.screen_items[y][x] = self.canvas.create_image(
                    self.padding + (x * self.char_width), 
                    self.padding + (y * self.char_height), 
                    anchor="nw", image=self.char_images[32]
                )
                
        # Draw CRT interlaced scanlines across the entire tube bounding box
        tube_margin = 20
        sx = self.padding - tube_margin
        ex = self.padding + self.w + tube_margin
        sy = self.padding - tube_margin
        ey = self.padding + self.h + tube_margin
        
        for raster_y in range(sy, ey, 4):
            self.canvas.create_line(sx, raster_y, ex, raster_y, fill="#040404", width=1)
                
        self.root.bind("<Key>", self._on_key)
        self.root.bind("<Control-v>", self._on_paste)
        self.root.bind("<Control-V>", self._on_paste)
        
        # Handle graceful shutdown
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.apple1.running = False
        self.root.destroy()
        
    def _load_charmap(self):
        rom_path = os.path.join(os.path.dirname(__file__), 'charmap.rom')
        with open(rom_path, 'rb') as f:
            data = f.read()
            
        fg = "#33ff33"
        for i in range(128):
            start = i * 8
            if start + 8 > len(data): break
            
            img = tk.PhotoImage(width=7, height=8)
            img.blank() # Set natively transparent
            for row in range(8):
                byte = data[start + row]
                for col in range(7):
                    bit = (byte >> col) & 1
                    if bit:
                        img.put(fg, (col, row))
                        
            self.char_images[i] = img.zoom(self.scale, self.scale)
            
        # Add a solid block cursor image
        img_cursor = tk.PhotoImage(width=7, height=8)
        img_cursor.blank()
        for row in range(8):
            for col in range(7):
                img_cursor.put(fg, (col, row))
        self.char_images['CURSOR'] = img_cursor.zoom(self.scale, self.scale)

    def _on_key(self, event):
        keysym = event.keysym
        char = event.char
        
        apple1_key = None
        if keysym == "Return":
            apple1_key = 0x0D
        elif keysym == "BackSpace":
            apple1_key = 0x5F  # Apple I uses '_' for rubout
        elif keysym == "Escape":
            apple1_key = 0x1B
        elif len(char) == 1:
            val = ord(char.upper()) # Apple 1 is UPPERCASE only
            if 0x20 <= val <= 0x7E:
                apple1_key = val
                
        if apple1_key is not None:
            self.apple1.keyboard.queue_key(apple1_key)
            return "break"
            
    def _on_paste(self, event):
        try:
            text = self.root.clipboard_get()
            for char in text:
                val = ord(char.upper())
                if char == '\n' or char == '\r':
                    self.apple1.keyboard.queue_key(0x0D)
                elif 0x20 <= val <= 0x7E:
                    self.apple1.keyboard.queue_key(val)
        except tk.TclError:
            pass # clipboard is empty or unsupported
        return "break"
        
    def _on_power_toggle(self, val):
        # Hardware exit
        if val == 0:
            self.power_led.set(False)
            self.root.update()
            time.sleep(0.1) # brief delay to allow user to visually perceive the LED shutting off
            self.apple1.running = False
            self.root.destroy()
            
    def _on_brightness(self, val):
        # Adjust CRT tube glow behind the transparent mask
        brightness = int(val)
        g = 5 + int((brightness / 100.0) * 80)  # Primary green tube bloom
        r = 5 + int((brightness / 100.0) * 15)  # Slight phosphor artifacts
        b = 5 + int((brightness / 100.0) * 15)
        color = f"#{r:02x}{g:02x}{b:02x}"
        self.canvas.itemconfig("screen_tube", fill=color)
    def _on_reset(self):
        self.apple1.reset()
        for y in range(24):
            for x in range(40):
                self.last_buffer[y][x] = -1

    def _on_paste_window(self):
        paste_win = tk.Toplevel(self.root)
        paste_win.title("Paste Apple I Code")
        paste_win.configure(bg="#050505")
        paste_win.geometry("600x450")
        
        tk.Label(paste_win, text="Type/Paste your BASIC or hex code below:", bg="#050505", fg="#33ff33", font=("Courier", 10)).pack(side=tk.TOP, pady=(10, 0))
        
        btn_frame = tk.Frame(paste_win, bg="#050505")
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 20), padx=20)
        
        text_area = tk.Text(paste_win, wrap=tk.WORD, bg="#222222", fg="#33ff33", insertbackground="#33ff33", font=("Courier", 10))
        text_area.pack(side=tk.TOP, expand=True, fill=tk.BOTH, padx=20, pady=10)
        
        def submit():
            code = text_area.get("1.0", tk.END)
            for char in code:
                val = ord(char.upper())
                if char == '\n' or char == '\r':
                    self.apple1.keyboard.queue_key(0x0D)
                elif 0x20 <= val <= 0x7E:
                    self.apple1.keyboard.queue_key(val)
            paste_win.destroy()
            
        def paste_clip():
            try:
                text = self.root.clipboard_get()
                text_area.insert(tk.INSERT, text)
            except tk.TclError:
                pass
                
        def close_win():
            paste_win.destroy()
            
        btn_opts = {"bg": "#222222", "fg": "#33ff33", "activebackground": "#33ff33", "activeforeground": "black", "font": ("Courier", 10, "bold"), "relief": tk.FLAT, "cursor": "hand2"}
        tk.Button(btn_frame, text="Cancel", command=close_win, **btn_opts).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Paste from Clipboard", command=paste_clip, **btn_opts).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Send & Close", command=submit, **btn_opts).pack(side=tk.RIGHT, padx=5)
            
    def refresh(self):
        # Scan screen buffer and refresh tiles
        for y in range(24):
            for x in range(40):
                c = self.apple1.display.get_char(y, x)
                
                # Render hardware blinking cursor
                if y == self.apple1.display.cursor_y and x == self.apple1.display.cursor_x:
                    if int(time.time() * 2) % 2 == 0:
                        c = 'CURSOR'
                
                if c != self.last_buffer[y][x]:
                    self.canvas.itemconfigure(self.screen_items[y][x], image=self.char_images.get(c, self.char_images[32]))
                    self.last_buffer[y][x] = c
                    
        self.root.after(16, self.refresh)

    def run(self):
        # Configure emulator display/iO for background processing
        self.apple1.keyboard = BufferedKeyboard()
        self.apple1.display = ScreenBuffer()
        
        # Override output handler
        self.apple1.pia.set_display_callback(lambda c: self.apple1.display.write(c))
        
        # Thread main run loop for the CPU
        cpu_thread = threading.Thread(target=self.apple1.run, daemon=True)
        cpu_thread.start()
        
        self.root.after(16, self.refresh)
        self.root.mainloop()
