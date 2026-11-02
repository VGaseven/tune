"""Tune visual kit: anti-aliased glowing gradient cards (rendered to PNG in pure Python and
cached), dot-matrix digits, dotted sphere, and canvas-drawn controls (round icon buttons,
pills with a white end circle, toggles). Original code; system fonts only.

Controls never delete or recreate their items on hover/press/focus - they only recolour.
(Recreating items under the pointer re-fires Leave/Enter forever: the 4.0 freeze.)"""
import base64
import math
import struct
import zlib
import tkinter as tk
import tkinter.font as tkfont
from desk_theme import hex_rgb,mix,ICONS

DISPLAY='Segoe UI Variable Display';TEXT='Segoe UI Variable Text';SEMI='Segoe UI Variable Display Semib'
LIME='#D7F24B'

# Card looks sampled from the reference: bright rim glow, dark centre.
CARDS={
 'magenta':dict(stops=[(0,'#C9519F'),(0.28,'#6A2160'),(0.6,'#2E0A27'),(1,'#2A0822')],rim='#D877B8',rim_w=9,k=0.75),
 'blue':dict(stops=[(0,'#3E4FD3'),(1,'#1B2172')],rim='#7A86FF',rim_w=10,k=0.7),
 'gold':dict(stops=[(0,'#D3B17A'),(0.6,'#7A4A6E'),(1,'#4A2260')],rim='#F0D49A',rim_w=10,k=0.7),
 'navy':dict(stops=[(0,'#141A60'),(0.45,'#04051A'),(1,'#0A0E3C')],rim='#6874F2',rim_w=17,k=0.9),
 'slate':dict(stops=[(0,'#101012'),(1,'#2B2B30')],rim='#3E3E46',rim_w=14,k=0.55),
 'indigo':dict(stops=[(0,'#1C2490'),(1,'#121862')],rim='#3E4AD0',rim_w=10,k=0.6),
 'ember':dict(stops=[(0,'#141012'),(0.5,'#4A1810'),(1,'#E4532C')],rim='#FF7347',rim_w=12,k=0.55),
}

def _grad(stops,t):
    for (t0,c0),(t1,c1) in zip(stops,stops[1:]):
        if t<=t1:return mix(c0,c1,0 if t1==t0 else (t-t0)/(t1-t0))
    return stops[-1][1]

def card_png(w,h,r,look,bg):
    """RGB PNG of a rounded card: vertical gradient + exponential rim glow, edges
    anti-aliased against the window background `bg`."""
    w,h=int(w),int(h);spec=CARDS[look];rim=hex_rgb(spec['rim']);bgc=hex_rgb(bg);rw=spec['rim_w'];k=spec['k']
    glow=[k*math.exp(-i/4/rw) for i in range(int(rw*4*6))];top=len(glow)
    hw,hh=w/2,h/2;out=bytearray();hypot=math.hypot;bg_bytes=bytes(bgc)
    interior=-top/4                                         # inside this, glow has faded to nothing
    qxs=[abs(x+0.5-hw)-(hw-r) for x in range(w)]            # column edge-distances, computed once
    for y in range(h):
        base=hex_rgb(_grad(spec['stops'],y/max(1,h-1)));b0,b1,b2=base;base_bytes=bytes(base)
        qy=abs(y+0.5-hh)-(hh-r);corner=qy>0;row=bytearray(b'\x00')
        for qx in qxs:
            d=(hypot(qx,qy) if corner and qx>0 else (qx if qx>qy else qy))-r
            if d<=interior:                                 # deep interior: solid gradient colour
                row+=base_bytes;continue
            a=0.5-d
            if a<=0:row+=bg_bytes;continue
            i=int(-d*4) if d<0 else 0
            if i<top:g=glow[i];col=(b0+(rim[0]-b0)*g,b1+(rim[1]-b1)*g,b2+(rim[2]-b2)*g)
            else:col=base
            if a<1:col=(bgc[0]+(col[0]-bgc[0])*a,bgc[1]+(col[1]-bgc[1])*a,bgc[2]+(col[2]-bgc[2])*a)
            row+=bytes((int(col[0]),int(col[1]),int(col[2])))
        out+=row
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(out),1))+chunk(b'IEND',b'')

def dots_png(w,h,step,color,bg):
    """Opaque PNG of the dot-grid background (single-pixel dots on bg). Built by poking pixels,
    so it is fast even full-window, and lets the UI draw the background as one cached image
    instead of ~1700 canvas items per redraw."""
    w,h=int(w),int(h);step=max(2,int(step));dc=bytes(hex_rgb(color));rowbg=bytes(hex_rgb(bg))*w
    rows=[bytearray(rowbg) for _ in range(h)];cx=step//2;xs=list(range(cx,w,step))
    for y in range(cx,h,step):
        r=rows[y]
        for x in xs:r[x*3:x*3+3]=dc
    raw=b''.join(b'\x00'+bytes(r) for r in rows)
    def chunk(k,d):return struct.pack('>I',len(d))+k+d+struct.pack('>I',zlib.crc32(k+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,1))+chunk(b'IEND',b'')

class Images:
    """Per-window cache so each card size/look and background is rendered once."""
    def __init__(self,root):self.root=root;self.cache={}
    def card(self,w,h,r,look,bg):
        key=('card',int(w),int(h),int(r),look,bg)
        if key not in self.cache:self.cache[key]=tk.PhotoImage(master=self.root,data=base64.b64encode(card_png(w,h,r,look,bg)))
        return self.cache[key]
    def background(self,w,h,step,color,bg):
        key=('bg',int(w),int(h),int(step),color,bg)
        if key not in self.cache:self.cache[key]=tk.PhotoImage(master=self.root,data=base64.b64encode(dots_png(w,h,step,color,bg)))
        return self.cache[key]

# 5x7 dot-matrix glyphs (hollow, airy strokes like the reference numerals).
GLYPHS={
 '0':['.###.','#...#','#...#','#...#','#...#','#...#','.###.'],'1':['..#..','.##..','..#..','..#..','..#..','..#..','.###.'],
 '2':['.###.','#...#','....#','...#.','..#..','.#...','#####'],'3':['####.','....#','....#','.###.','....#','....#','####.'],
 '4':['...#.','..##.','.#.#.','#..#.','#####','...#.','...#.'],'5':['#####','#....','####.','....#','....#','#...#','.###.'],
 '6':['.###.','#....','#....','####.','#...#','#...#','.###.'],'7':['#####','....#','...#.','..#..','..#..','..#..','..#..'],
 '8':['.###.','#...#','#...#','.###.','#...#','#...#','.###.'],'9':['.###.','#...#','#...#','.####','....#','....#','.###.'],
 '.':['.','.','.','.','.','.','#'],'-':['.....','.....','.....','.###.','.....','.....','.....'],
 ' ':['..','..','..','..','..','..','..'],'O':['.###.','#...#','#...#','#...#','#...#','#...#','.###.'],
 'n':['.....','.....','####.','#...#','#...#','#...#','#...#'],'f':['..##.','.#...','####.','.#...','.#...','.#...','.#...'],
}
SPACING=3.1   # cell pitch / dot radius: airy dots like the reference numerals
def matrix_width(text,dot):
    step=dot*SPACING;return sum((len(GLYPHS.get(ch,GLYPHS[' '])[0])+1)*step for ch in text)-step
def draw_matrix(cv,text,cx,cy,dot,color,tags=()):
    """Centred dot-matrix text; each lit cell is a small circle."""
    step=dot*SPACING;x=cx-matrix_width(text,dot)/2;y0=cy-3*step
    for ch in text:
        rows=GLYPHS.get(ch,GLYPHS[' '])
        for j,row in enumerate(rows):
            for i,c in enumerate(row):
                if c=='#':px,py=x+i*step,y0+j*step;cv.create_oval(px-dot,py-dot,px+dot,py+dot,fill=color,outline='',tags=tags)
        x+=(len(rows[0])+1)*step

def draw_sphere(cv,cx,cy,R,step,dot,bg,tags=()):
    """Halftone sphere: dots fill a circle, larger/brighter towards the upper centre."""
    n=int(R/step)+1
    for j in range(-n,n+1):
        for i in range(-n,n+1):
            x,y=cx+i*step,cy+j*step;d=math.hypot(i*step,j*step)/R
            if d>1:continue
            light=max(0.0,1-math.hypot(i*step,(j*step+R*0.2))/(R*1.15))
            if d>0.82 and (i+j)%2:continue                 # thinner, ragged edge like the reference
            s=dot*(0.55+0.6*light);col=mix(bg,'#FFFFFF',0.25+0.75*light*(1-d*0.5))
            cv.create_oval(x-s,y-s,x+s,y+s,fill=col,outline='',tags=tags)

def dot_field(cv,w,h,step,color,tags=('bgdots',)):
    for y in range(step//2,int(h),step):
        for x in range(step//2,int(w),step):cv.create_rectangle(x,y,x+1,y+1,fill=color,outline='',tags=tags)

def fit(cv,text,font,width):
    """Shortens text with an ellipsis so it fits `width` pixels."""
    f=tkfont.Font(cv,font=font)
    if f.measure(text)<=width:return text
    while text and f.measure(text+'…')>width:text=text[:-1]
    return text+'…'

def rounded(cv,x,y,w,h,r,**kw):
    r=min(r,w/2,h/2)
    return cv.create_polygon(x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,x+w-r,y+h,x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y,smooth=True,splinesteps=24,**kw)

class UI:
    """Focus, hover and click handling for controls drawn on one canvas."""
    def __init__(self,canvas,look):
        self.cv=canvas;self.look=look;self.controls=[];self.focus=None
        canvas.configure(takefocus=True)
        canvas.bind('<Tab>',lambda e:self.move(1));canvas.bind('<Shift-Tab>',lambda e:self.move(-1))
        canvas.bind('<Return>',self.activate);canvas.bind('<space>',self.activate)
        canvas.bind('<FocusOut>',lambda e:self.set_focus(None,keep=True))
    def reset(self):
        for c in self.controls:
            try:c._tip_cancel()
            except (AttributeError,tk.TclError):pass
        self.controls=[];self.focus=None
    def add(self,c):
        self.controls.append(c);cv=self.cv;t=c.tag
        cv.tag_bind(t,'<Enter>',lambda e:c.hover(True));cv.tag_bind(t,'<Leave>',lambda e:c.hover(False))
        cv.tag_bind(t,'<ButtonPress-1>',lambda e:c.press());cv.tag_bind(t,'<ButtonRelease-1>',lambda e:c.release())
        return c
    def find(self,name):return next((c for c in self.controls if c.name==name),None)
    def move(self,d):
        live=[c for c in self.controls if c.state!='disabled']
        if not live:return 'break'
        i=(live.index(self.focus)+d)%len(live) if self.focus in live else (0 if d>0 else len(live)-1)
        self.set_focus(live[i]);return 'break'
    def set_focus(self,c,keep=False):
        if self.focus is not None and self.focus in self.controls:self.focus.focused=False;self.focus.paint()
        if keep:return
        self.focus=c
        if c:c.focused=True;c.paint()
    def activate(self,e=None):
        if self.focus is not None and self.focus.state!='disabled':self.focus.invoke()
        return 'break'

class Control:
    def __init__(self,ui,name,command):
        self.ui=ui;self.cv=ui.cv;self.name=name;self.command=command;self.state='normal'
        self.over=self.pressed=self.focused=False;self.tag='ctl%d'%id(self);self.tip_text=None
    def hover(self,v):
        self.over=v;self.pressed=self.pressed and v
        self.cv.configure(cursor='hand2' if v and self.state!='disabled' else '');self.paint()
        self._tip_schedule() if v else self._tip_cancel()
    # ----- hover tooltip (a tiny Toplevel; never a canvas item, so it can't cause redraw loops) -----
    def _tip_schedule(self):
        self._tip_cancel()
        if self.tip_text and self.state!='disabled':self._tip_job=self.cv.after(500,self._tip_show)
    def _tip_cancel(self):
        j=getattr(self,'_tip_job',None)
        if j:
            try:self.cv.after_cancel(j)
            except tk.TclError:pass
            self._tip_job=None
        w=getattr(self,'_tip_win',None)
        if w:
            try:w.destroy()
            except tk.TclError:pass
            self._tip_win=None
    def _tip_show(self):
        self._tip_job=None
        if not self.cv.winfo_exists() or self.state=='disabled' or not self.over:return
        try:box=self.cv.bbox(getattr(self,'bg',None) or getattr(self,'track',self.tag))
        except tk.TclError:box=None
        if not box:return
        c=self.ui.look.c
        win=self._tip_win=tk.Toplevel(self.cv);win.wm_overrideredirect(True)
        try:win.attributes('-topmost',True)
        except tk.TclError:pass
        tk.Label(win,text=self.tip_text,bg=c['surface2'],fg=c['text'],font=(TEXT,9),padx=8,pady=4,bd=0).pack()
        win.update_idletasks()
        x=self.cv.winfo_rootx()+(box[0]+box[2])//2-win.winfo_reqwidth()//2
        y=self.cv.winfo_rooty()+box[3]+6;win.wm_geometry(f'+{max(0,x)}+{y}')
    def press(self):
        self._tip_cancel()
        if self.state!='disabled':self.pressed=True;self.paint()
    def release(self):
        hit=self.pressed and self.over;self.pressed=False;self.paint()
        if hit:self.invoke()
    def invoke(self):
        if self.state!='disabled' and self.command:return self.command()
    def set_state(self,s):self.state=s;self.paint()

class RoundButton(Control):
    """Dark circle with an icon glyph (header buttons, card buttons)."""
    def __init__(self,ui,name,cx,cy,d,icon,command,fill,fg,hover,ring='#A5B4FC'):
        super().__init__(ui,name,command);cv=self.cv;self.colors=(fill,fg,hover,ring);r=d/2;self.tip_text=name
        glyph,fallback=ICONS[icon];font=(ui.look.icons,int(d/3.4)) if ui.look.icons else (SEMI,int(d/4))
        self.ring=cv.create_oval(cx-r-3,cy-r-3,cx+r+3,cy+r+3,outline='',width=2,tags=(self.tag,))
        self.bg=cv.create_oval(cx-r,cy-r,cx+r,cy+r,fill=fill,outline='',tags=(self.tag,))
        self.glyph=cv.create_text(cx,cy,text=glyph if ui.look.icons else fallback,font=font,fill=fg,tags=(self.tag,))
        ui.add(self);self.paint()
    def set_icon(self,icon):
        glyph,fallback=ICONS[icon];self.cv.itemconfigure(self.glyph,text=glyph if self.ui.look.icons else fallback)
    def paint(self):
        fill,fg,hover,ring=self.colors;off=self.state=='disabled'
        self.cv.itemconfigure(self.bg,fill=mix(fill,'#000000',0.3) if off else (hover if self.over or self.pressed else fill))
        self.cv.itemconfigure(self.glyph,fill=mix(fg,fill,0.6) if off else fg)
        self.cv.itemconfigure(self.ring,outline=ring if self.focused else '')

class PillButton(Control):
    """Capsule with label and an optional white end circle holding an icon (reference 'Finish Test')."""
    def __init__(self,ui,name,x,y,w,h,text,command,fill,fg,hover,end_icon=None,ring='#A5B4FC',font=None):
        super().__init__(ui,name,command);cv=self.cv;self.colors=(fill,fg,hover,ring);self.text=text
        self.ring=rounded(cv,x-3,y-3,w+6,h+6,(h+6)/2,fill='',outline='',width=2,tags=(self.tag,))
        self.bg=rounded(cv,x,y,w,h,h/2,fill=fill,outline='',tags=(self.tag,))
        pad=h*0.12;ex=x+w-h/2 if end_icon else x+w/2
        self.label=cv.create_text((x+(w-h)/2 if end_icon else x+w/2),y+h/2,text=text,font=font or (TEXT,11),fill=fg,tags=(self.tag,))
        self.end=self.endglyph=None
        if end_icon:
            r=h/2-pad;self.end=cv.create_oval(ex-r,y+h/2-r,ex+r,y+h/2+r,fill='#FFFFFF',outline='',tags=(self.tag,))
            glyph,fallback=ICONS[end_icon]
            self.endglyph=cv.create_text(ex,y+h/2,text=glyph if ui.look.icons else fallback,font=(ui.look.icons or SEMI,int(h/4.2)),fill='#09090B',tags=(self.tag,))
        ui.add(self);self.paint()
    def set_text(self,text):self.text=text;self.cv.itemconfigure(self.label,text=text)
    def paint(self):
        fill,fg,hover,ring=self.colors;off=self.state=='disabled'
        self.cv.itemconfigure(self.bg,fill=mix(fill,'#000000',0.35) if off else (hover if self.over or self.pressed else fill))
        self.cv.itemconfigure(self.label,fill=mix(fg,fill,0.55) if off else fg)
        if self.end:self.cv.itemconfigure(self.end,fill='#6B6B75' if off else ('#E6E6EA' if self.pressed else '#FFFFFF'))
        self.cv.itemconfigure(self.ring,outline=ring if self.focused else '')

class Toggle(Control):
    """Small capsule switch (reference 'Training')."""
    def __init__(self,ui,name,x,y,w,h,value,command,on='#D7F24B',off='#2A2F7A',knob='#FFFFFF',ring='#A5B4FC'):
        super().__init__(ui,name,command);cv=self.cv;self.value=value;self.geo=(x,y,w,h);self.colors=(on,off,knob,ring)
        self.ring=rounded(cv,x-3,y-3,w+6,h+6,(h+6)/2,fill='',outline='',width=2,tags=(self.tag,))
        self.track=rounded(cv,x,y,w,h,h/2,fill=off,outline='',tags=(self.tag,))
        self.knob=cv.create_oval(0,0,1,1,fill=knob,outline='',tags=(self.tag,));ui.add(self);self.paint()
    def invoke(self):
        if self.state=='disabled':return
        self.value=not self.value;self.paint()
        if self.command:return self.command(self.value)
    def paint(self):
        x,y,w,h=self.geo;on,off,knob,ring=self.colors;p=h*0.14;r=h/2-p
        cx=x+w-h/2 if self.value else x+h/2
        self.cv.coords(self.knob,cx-r,y+h/2-r,cx+r,y+h/2+r)
        self.cv.itemconfigure(self.track,fill=mix(on if self.value else off,'#FFFFFF',0.12) if self.over else (on if self.value else off))
        self.cv.itemconfigure(self.knob,fill='#09090B' if self.value else knob)
        self.cv.itemconfigure(self.ring,outline=ring if self.focused else '')

class Button(tk.Canvas):
    """Self-sizing capsule button for dialogs. Redraws fully, but hover/press are bound at the
    widget level (not on items), so a redraw never re-fires Enter/Leave - no freeze."""
    def __init__(self,parent,look,text,command,kind='secondary',end_icon=None,min_width=0):
        self.look=look;self.command=command;self.kind=kind;self.label=text;self.end_icon=end_icon
        self.state='normal';self.over=self.pressed=self.focused=False
        super().__init__(parent,bg=parent.cget('bg'),bd=0,highlightthickness=0,takefocus=True,cursor='hand2')
        self.font=tkfont.Font(self,family=TEXT,size=11);px=look.px;self.h=px(42)
        self.configure(width=max(min_width,self.font.measure(text)+px(46)+(self.h if end_icon else 0)),height=self.h+px(6))
        self.bind('<Enter>',lambda e:self._set(over=True));self.bind('<Leave>',lambda e:self._set(over=False,pressed=False))
        self.bind('<ButtonPress-1>',lambda e:self._press());self.bind('<ButtonRelease-1>',self._release)
        self.bind('<FocusIn>',lambda e:self._set(focused=True));self.bind('<FocusOut>',lambda e:self._set(focused=False,pressed=False))
        self.bind('<space>',self._key);self.bind('<Return>',self._key);self.bind('<Configure>',lambda e:self.draw());self.draw()
    def _set(self,**kw):
        for k,v in kw.items():setattr(self,k,v)
        self.configure(cursor='hand2' if self.state!='disabled' else 'arrow');self.draw()
    def _press(self):
        if self.state!='disabled':self.focus_set();self.pressed=True;self.draw()
    def _release(self,e):
        hit=self.pressed and 0<=e.x<=self.winfo_width() and 0<=e.y<=self.winfo_height();self.pressed=False;self.draw()
        if hit:self.invoke()
    def _key(self,e=None):self.invoke();return 'break'
    def invoke(self):
        if self.state!='disabled' and self.command:return self.command()
    def set_state(self,s):self.state=s;self._set()
    def colors(self):
        c=self.look.c
        if self.state=='disabled':return mix(c['surface'],c['bg'],0.4),c['disabledtext']
        if self.kind=='primary':return (c['accenthover'] if self.over or self.pressed else c['accent']),'#FFFFFF'
        if self.kind=='danger':return ('#DD5636' if self.over or self.pressed else '#C9472A'),'#FFFFFF'
        return (c['chiphover'] if self.over or self.pressed else c['chip']),c['text']
    def draw(self):
        self.delete('all');px=self.look.px;w=max(self.winfo_width(),int(self.cget('width')));h=max(self.winfo_height(),int(self.cget('height')))
        fill,fg=self.colors();bh=self.h;y=(h-bh)/2;x=px(2);bw=w-px(4);dy=1 if self.pressed else 0
        if self.focused:rounded(self,x-px(1),y-px(1),bw+px(2),bh+px(2),(bh+px(2))/2,fill='',outline=self.look.c['focus'],width=px(2))
        rounded(self,x,y,bw,bh,bh/2,fill=fill,outline='')
        if self.end_icon:
            r=bh/2-px(6);ex=x+bw-bh/2;self.create_oval(ex-r,y+bh/2-r,ex+r,y+bh/2+r,fill='#FFFFFF',outline='')
            glyph,fb=ICONS[self.end_icon];self.create_text(ex,y+bh/2+dy,text=glyph if self.look.icons else fb,font=(self.look.icons or SEMI,12),fill='#09090B')
            self.create_text(x+(bw-bh)/2+px(6),y+bh/2+dy,text=self.label,font=self.font,fill=fg)
        else:self.create_text(w/2,y+bh/2+dy,text=self.label,font=self.font,fill=fg)

class Hotspot(Control):
    """Makes already-drawn content (a card image and its text) clickable; draws only a focus/
    hover outline. Items belonging to other controls inside the area are left alone."""
    def __init__(self,ui,name,x,y,w,h,r,command,hover_outline):
        super().__init__(ui,name,command);self.colors=hover_outline;cv=self.cv
        for item in cv.find_enclosed(x-1,y-1,x+w+1,y+h+1):
            if not any(t.startswith('ctl') for t in cv.gettags(item)) and 'bgdots' not in cv.gettags(item):cv.addtag_withtag(self.tag,item)
        self.shape=rounded(cv,x-2,y-2,w+4,h+4,r+2,fill='',outline='',width=2,tags=(self.tag,))
        ui.add(self);self.paint()
    def paint(self):
        self.cv.itemconfigure(self.shape,outline=self.colors if (self.over or self.focused) and self.state!='disabled' else '')
