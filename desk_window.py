"""Window chrome: give Tune's native Windows title bar the app's dark colour instead of white.

Uses the documented DWM window attributes (Windows 10 1809+ dark mode, Windows 11 caption and
text colours). Purely cosmetic: if Windows doesn't support an attribute, it is skipped silently."""
from __future__ import annotations
import ctypes
import os

DARK_MODE=20          # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 2004+ / 11)
DARK_MODE_OLD=19      # same attribute on Windows 10 1809-1909
CAPTION=35            # DWMWA_CAPTION_COLOR (Windows 11)
TEXT=36               # DWMWA_TEXT_COLOR (Windows 11)
BORDER=34             # DWMWA_BORDER_COLOR (Windows 11)


def colorref(hex_color):
    """'#07070c' -> COLORREF (0x00BBGGRR)."""
    h=hex_color.lstrip('#');r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return b<<16|g<<8|r


def find_window(title,pid=None):
    """Top-level window of this process with exactly this title, or None."""
    user32=ctypes.windll.user32;pid=pid or os.getpid();found=[]
    PROC=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
    def cb(hwnd,_):
        n=user32.GetWindowTextLengthW(hwnd)
        if n:
            buf=ctypes.create_unicode_buffer(n+1);user32.GetWindowTextW(hwnd,buf,n+1)
            owner=ctypes.c_ulong();user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
            if buf.value==title and owner.value==pid:found.append(hwnd);return False
        return True
    user32.EnumWindows(PROC(cb),0)
    return found[0] if found else None


def style(hwnd,caption='#0d0c16',text='#e6e6ee',border='#1c1a2c'):
    """Apply dark title-bar attributes to hwnd. Returns the attributes Windows accepted."""
    dwm=ctypes.windll.dwmapi;ok=[]
    def setattr_(attr,value):
        v=ctypes.c_int(value)
        if dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd),attr,ctypes.byref(v),ctypes.sizeof(v))==0:ok.append(attr)
    setattr_(DARK_MODE,1)
    if DARK_MODE not in ok:setattr_(DARK_MODE_OLD,1)
    setattr_(CAPTION,colorref(caption));setattr_(TEXT,colorref(text));setattr_(BORDER,colorref(border))
    return ok


def darken(title):
    """Find Tune's window by its title and darken its title bar. Never raises."""
    try:
        hwnd=find_window(title)
        return style(hwnd) if hwnd else []
    except Exception:
        return []
