"""Tune app icon, drawn in code (no external artwork): a lime crosshair inside a tuning dial on a
dark rounded square. Writes webui/icon.png and assets/tune.ico (16-256 px, PNG-in-ICO).

Run:  python tune_icon.py"""
import math
import struct
import zlib
from pathlib import Path

LIME=(215,242,75);PURPLE=(152,135,230);TOP=(44,36,92);BOTTOM=(10,10,16)
SIZES=(16,20,24,32,40,48,64,128,256)


def _mix(a,b,t):return tuple(p+(q-p)*t for p,q in zip(a,b))
def _over(dst,col,a):
    """Composite colour `col` with coverage `a` over premultiplied-free dst (r,g,b,alpha)."""
    r,g,b,da=dst;oa=a+da*(1-a)
    if oa<=0:return (0,0,0,0)
    k=a/oa;return (r+(col[0]-r)*k,g+(col[1]-g)*k,b+(col[2]-b)*k,oa)
def _box(px,py,cx,cy,hw,hh,rad):
    """Signed distance to a rounded rectangle."""
    qx=abs(px-cx)-hw+rad;qy=abs(py-cy)-hh+rad
    return math.hypot(max(qx,0),max(qy,0))+min(max(qx,qy),0)-rad


def sample(x,y,size):
    """Colour+alpha of one point (x,y in 0..1)."""
    px=lambda w:max(w,1.15/size)          # keep strokes at least ~1px at tiny sizes
    out=(0,0,0,0)
    # background: rounded square with a diagonal purple-to-black gradient and a lime glow behind the sight
    if _box(x,y,.5,.5,.5,.5,.23)<=0:
        col=_mix(TOP,BOTTOM,min(1,(x*.55+y*.45)*1.05))
        glow=max(0,1-math.hypot(x-.5,y-.5)/.42)**2*.28
        out=(*_mix(col,LIME,glow),1.0)
    else:return out
    d=math.hypot(x-.5,y-.5);ang=(math.degrees(math.atan2(y-.5,x-.5))+360)%360
    # dial ring: dim purple track, with a lime "tuned" arc from 135deg sweeping 270deg
    ring=abs(d-.335)<=px(.034)/2
    if ring:
        on=(ang-135)%360<=270
        out=_over(out,LIME if on else PURPLE,1.0 if on else .55)
    # end knob of the arc (at 45deg)
    kx=.5+.335*math.cos(math.radians(45));ky=.5+.335*math.sin(math.radians(45))
    if math.hypot(x-kx,y-ky)<=px(.055):out=_over(out,(255,255,255),1.0)
    # crosshair: four arms with a gap, plus a centre dot
    t=px(.052);L=.125;off=.075
    for cx,cy,hw,hh in ((.5,.5-off-L/2,t/2,L/2),(.5,.5+off+L/2,t/2,L/2),(.5-off-L/2,.5,L/2,t/2),(.5+off+L/2,.5,L/2,t/2)):
        if _box(x,y,cx,cy,hw,hh,t/2)<=0:out=_over(out,LIME,1.0)
    if d<=px(.034):out=_over(out,LIME,1.0)
    return out


def rgba(size,ss=4):
    """RGBA rows for a PNG, supersampled ss*ss per pixel for smooth edges."""
    rows=bytearray()
    for j in range(size):
        rows.append(0)
        for i in range(size):
            acc=[0.0,0.0,0.0,0.0]
            for sj in range(ss):
                for si in range(ss):
                    r,g,b,a=sample((i+(si+.5)/ss)/size,(j+(sj+.5)/ss)/size,size)
                    acc[0]+=r*a;acc[1]+=g*a;acc[2]+=b*a;acc[3]+=a
            n=ss*ss;a=acc[3]/n
            rows+=bytes([round(acc[0]/acc[3]) if acc[3] else 0,round(acc[1]/acc[3]) if acc[3] else 0,
                         round(acc[2]/acc[3]) if acc[3] else 0,round(a*255)])
    return bytes(rows)


def png(size):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))
            +chunk(b'IDAT',zlib.compress(rgba(size),9))+chunk(b'IEND',b''))


def ico(sizes=SIZES):
    imgs=[png(s) for s in sizes];head=struct.pack('<HHH',0,1,len(imgs));offset=6+16*len(imgs);dirs=b''
    for s,data in zip(sizes,imgs):
        dirs+=struct.pack('<BBBBHHII',s%256,s%256,0,0,1,32,len(data),offset);offset+=len(data)
    return head+dirs+b''.join(imgs)


if __name__=='__main__':
    root=Path(__file__).resolve().parent
    (root/'assets').mkdir(exist_ok=True)
    (root/'assets'/'tune.ico').write_bytes(ico())
    (root/'webui'/'icon.png').write_bytes(png(256))
    print('wrote assets/tune.ico and webui/icon.png')
