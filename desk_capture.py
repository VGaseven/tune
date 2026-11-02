"""Developer tool: capture this app's own windows to PNG (GDI BitBlt + zlib). Not shipped in the EXE."""
import ctypes
from ctypes import wintypes as w
import struct
import zlib

user=ctypes.WinDLL('user32');gdi=ctypes.WinDLL('gdi32');dwm=ctypes.WinDLL('dwmapi')
user.GetDC.restype=w.HDC;user.GetDC.argtypes=[w.HWND];user.ReleaseDC.argtypes=[w.HWND,w.HDC]
gdi.CreateCompatibleDC.restype=w.HDC;gdi.CreateCompatibleDC.argtypes=[w.HDC]
gdi.CreateCompatibleBitmap.restype=w.HBITMAP;gdi.CreateCompatibleBitmap.argtypes=[w.HDC,ctypes.c_int,ctypes.c_int]
gdi.SelectObject.restype=w.HGDIOBJ;gdi.SelectObject.argtypes=[w.HDC,w.HGDIOBJ]
gdi.BitBlt.argtypes=[w.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.HDC,ctypes.c_int,ctypes.c_int,w.DWORD]
gdi.GetDIBits.argtypes=[w.HDC,w.HBITMAP,w.UINT,w.UINT,ctypes.c_void_p,ctypes.c_void_p,w.UINT]
gdi.DeleteObject.argtypes=[w.HGDIOBJ];gdi.DeleteDC.argtypes=[w.HDC]
dwm.DwmGetWindowAttribute.argtypes=[w.HWND,w.DWORD,ctypes.c_void_p,w.DWORD]

class BIH(ctypes.Structure):
    _fields_=[('biSize',w.DWORD),('biWidth',w.LONG),('biHeight',w.LONG),('biPlanes',w.WORD),('biBitCount',w.WORD),('biCompression',w.DWORD),
              ('biSizeImage',w.DWORD),('biXPelsPerMeter',w.LONG),('biYPelsPerMeter',w.LONG),('biClrUsed',w.DWORD),('biClrImportant',w.DWORD)]

def grab(x,y,width,height):
    """Returns RGB bytes of a screen rectangle."""
    screen=user.GetDC(None);mem=gdi.CreateCompatibleDC(screen);bmp=gdi.CreateCompatibleBitmap(screen,width,height);old=gdi.SelectObject(mem,bmp)
    try:
        if not gdi.BitBlt(mem,0,0,width,height,screen,x,y,0x00CC0020|0x40000000):raise OSError('Screen capture failed (desktop locked or unavailable).')
        info=BIH(ctypes.sizeof(BIH),width,-height,1,32,0,0,0,0,0,0);buf=ctypes.create_string_buffer(width*height*4)
        if not gdi.GetDIBits(mem,bmp,0,height,buf,ctypes.byref(info),0):raise OSError('Could not read captured pixels.')
    finally:
        gdi.SelectObject(mem,old);gdi.DeleteObject(bmp);gdi.DeleteDC(mem);user.ReleaseDC(None,screen)
    raw=buf.raw;rgb=bytearray(width*height*3);rgb[0::3]=raw[2::4];rgb[1::3]=raw[1::4];rgb[2::3]=raw[0::4]
    return bytes(rgb)

def bounds(tk_window):
    """Visible window bounds (including title bar) for a Tk toplevel."""
    hwnd=int(tk_window.wm_frame(),16);r=w.RECT()
    if dwm.DwmGetWindowAttribute(hwnd,9,ctypes.byref(r),ctypes.sizeof(r)):user.GetWindowRect(hwnd,ctypes.byref(r))
    return r.left,r.top,r.right-r.left,r.bottom-r.top

def write_png(path,width,height,rgb):
    stride=width*3;rows=b''.join(b'\x00'+rgb[i*stride:(i+1)*stride] for i in range(height))
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    with open(path,'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))

user.GetForegroundWindow.restype=w.HWND;user.WindowFromPoint.restype=w.HWND;user.WindowFromPoint.argtypes=[w.POINT]
user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)];user.GetAncestor.restype=w.HWND;user.GetAncestor.argtypes=[w.HWND,w.UINT]

def owner_pid(hwnd):
    pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid));return pid.value

def game_in_front():
    """True when the foreground window belongs to VALORANT (read-only check)."""
    import capture_model
    hwnd=user.GetForegroundWindow()
    if not hwnd:return False
    pid=owner_pid(hwnd);names={}
    import subprocess
    out=subprocess.run(['tasklist','/FI',f'PID eq {pid}','/FO','CSV','/NH'],capture_output=True,text=True).stdout
    return 'valorant' in out.lower()

def spare_origin(root,margin=60):
    """Top-left point on a monitor that does NOT show the foreground window (e.g. the game),
    so demo windows open on the other display. Falls back to the primary work area."""
    from desktop_mode import work_areas
    areas=work_areas(root);hwnd=user.GetForegroundWindow();r=w.RECT()
    if hwnd and len(areas)>1 and user.GetWindowRect(hwnd,ctypes.byref(r)):
        cx,cy=(r.left+r.right)//2,(r.top+r.bottom)//2
        free=[a for a in areas if not (a[0]<=cx<a[2] and a[1]<=cy<a[3])]
        if free:return free[0][0]+margin,free[0][1]+margin
    return areas[0][0]+margin,areas[0][1]+margin

def only_ours(x,y,wd,ht):
    """Every sampled point of the rectangle must show a window of this process; otherwise
    something else (a game, another app) is covering it and the capture is refused."""
    import os
    me=os.getpid()
    for fx in (0.1,0.5,0.9):
        for fy in (0.1,0.5,0.9):
            h=user.WindowFromPoint(w.POINT(int(x+wd*fx),int(y+ht*fy)))
            if not h or owner_pid(user.GetAncestor(h,2))!=me:return False
    return True

user.PrintWindow.argtypes=[w.HWND,w.HDC,w.UINT];user.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]

def render(tk_window,update=True):
    """Asks Windows to render THIS window into a bitmap (PrintWindow, full content). Works
    while other windows (e.g. a game) cover it, and never reads other windows' pixels.
    Returns (width, height, rgb, (left, top)) cropped to the visible frame."""
    if update:tk_window.update()
    hwnd=int(tk_window.wm_frame(),16);r=w.RECT();user.GetWindowRect(hwnd,ctypes.byref(r))
    vx,vy,vw,vh=bounds(tk_window);fw,fh=r.right-r.left,r.bottom-r.top
    screen=user.GetDC(None);mem=gdi.CreateCompatibleDC(screen);bmp=gdi.CreateCompatibleBitmap(screen,fw,fh);old=gdi.SelectObject(mem,bmp)
    try:
        if not user.PrintWindow(hwnd,mem,2):raise OSError('PrintWindow failed.')
        info=BIH(ctypes.sizeof(BIH),fw,-fh,1,32,0,0,0,0,0,0);buf=ctypes.create_string_buffer(fw*fh*4)
        gdi.GetDIBits(mem,bmp,0,fh,buf,ctypes.byref(info),0)
    finally:
        gdi.SelectObject(mem,old);gdi.DeleteObject(bmp);gdi.DeleteDC(mem);user.ReleaseDC(None,screen)
    raw=buf.raw;ox,oy=vx-r.left,vy-r.top;rgb=bytearray(vw*vh*3)
    for j in range(vh):
        row=raw[((oy+j)*fw+ox)*4:((oy+j)*fw+ox+vw)*4]
        line=bytearray(vw*3);line[0::3]=row[2::4];line[1::3]=row[1::4];line[2::3]=row[0::4];rgb[j*vw*3:(j+1)*vw*3]=line
    return vw,vh,bytes(rgb),(vx,vy)

def shot_window(tk_window,path):
    wd,ht,rgb,_=render(tk_window);write_png(path,wd,ht,rgb);return (wd,ht)

def shot(tk_window,path):
    tk_window.update();x,y,wd,ht=bounds(tk_window)
    if not only_ours(x,y,wd,ht):raise RuntimeError('Another window covers the app; capture refused.')
    write_png(path,wd,ht,grab(x,y,wd,ht));return (wd,ht)
