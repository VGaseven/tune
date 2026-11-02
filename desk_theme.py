"""Preset Desk 4 visual tokens. Original palette and drawing helpers; system fonts only."""
import ctypes
import os

VERSION='5.2';NAME='Tune'   # data folder stays %LOCALAPPDATA%\PresetDesk so 3.x profiles keep working
# Near-black canvas, white headings, muted grey copy, indigo actions, magenta->purple hero
# gradient and a smaller coral accent card, per the user's written description of the reference.
PALETTES={
 'dark':{'dots':'#1C1C22','chip':'#1A1A1F','chiphover':'#26262D','bg':'#000000','surface':'#141418','surface2':'#1D1D23','hover':'#26262E','stroke':'#2C2C35',
         'text':'#FFFFFF','muted':'#A1A1AA','faint':'#71717A','disabled':'#1A1A1F','disabledtext':'#7A7A84',
         'accent':'#4F46E5','accenthover':'#5B54F0','accenttext':'#FFFFFF','focus':'#A5B4FC',
         'coral':'#FF8A65','coraltext':'#1A0E09','danger':'#F87171','tabsel':'#FFFFFF','tabseltext':'#09090B'},
 'light':{'dots':'#D2D2DA','chip':'#E4E4EA','chiphover':'#D8D8E0','bg':'#F3F3F6','surface':'#FFFFFF','surface2':'#E9E9EE','hover':'#DDDDE4','stroke':'#D4D4DC',
         'text':'#0B0B0F','muted':'#52525B','faint':'#6B6B75','disabled':'#E4E4E9','disabledtext':'#6B6B75',
         'accent':'#4F46E5','accenthover':'#4338CA','accenttext':'#FFFFFF','focus':'#4338CA',
         'coral':'#FF8A65','coraltext':'#1A0E09','danger':'#B91C1C','tabsel':'#0B0B0F','tabseltext':'#FFFFFF'},
}
GRADIENT=('#B5179E','#5B21B6')   # magenta -> purple; white text stays >=4.5:1 across the ramp
FONT='Segoe UI';SEMIBOLD='Segoe UI Semibold'
ICONS={'more':('','...'),'mini':('','_'),'expand':('','[ ]'),'pin':('','^'),'unpin':('','v'),
       'pinned':('','^'),'back':('','<'),'menu':('','='),'info':('','i'),'refresh':('','R'),
       'check':('','v'),'people':('','@'),'arrow':('','>'),'prev':('','<'),'next':('','>'),'apply':('','>'),'close':('','x')}

def hex_rgb(h):return tuple(int(h[i:i+2],16) for i in (1,3,5))
def mix(a,b,t):
    a,b=hex_rgb(a),hex_rgb(b);return '#%02X%02X%02X'%tuple(round(x+(y-x)*t) for x,y in zip(a,b))
def luminance(h):
    c=[v/255 for v in hex_rgb(h)];c=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in c]
    return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2]
def contrast(a,b):
    a,b=sorted((luminance(a),luminance(b)));return (b+0.05)/(a+0.05)

def icon_font(root):
    import tkinter.font as tkfont
    families=set(tkfont.families(root))
    return next((f for f in ('Segoe Fluent Icons','Segoe MDL2 Assets') if f in families),None)

def title_bar(win,dark):
    """Asks Windows to draw this app's own title bar dark/light. Cosmetic; failures are ignored."""
    if os.name!='nt':return
    try:
        win.update_idletasks();hwnd=int(win.wm_frame(),16);value=ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd),20,ctypes.byref(value),ctypes.sizeof(value))
    except (OSError,AttributeError,ValueError):pass

def reduced_motion():
    """True when Windows 'Animation effects' is off. Unknown -> reduced (no motion)."""
    if os.name!='nt':return True
    try:
        enabled=ctypes.c_int(1)
        if not ctypes.windll.user32.SystemParametersInfoW(0x1042,0,ctypes.byref(enabled),0):return True
        return not enabled.value
    except (OSError,AttributeError):return True
