"""Original app icon (gradient rounded square with a dot grid), generated in code: PNG for Tk,
ICO for the EXE. No external artwork."""
import base64
import math
import struct
import zlib
from desk_theme import GRADIENT,hex_rgb

def rgba(size):
    a,b=hex_rgb(GRADIENT[0]),hex_rgb(GRADIENT[1]);r=size*0.24;out=bytearray()
    step=size/5;dot=max(1.0,size*0.055)
    for y in range(size):
        out.append(0)
        for x in range(size):
            # Rounded-square coverage with 1px antialiasing at the corners.
            cx=min(max(x+0.5,r),size-r);cy=min(max(y+0.5,r),size-r);d=math.hypot(x+0.5-cx,y+0.5-cy)
            alpha=max(0.0,min(1.0,r-d+0.5)) if d>0 else 1.0
            t=(x+y)/(2*size-2);col=[round(p+(q-p)*t) for p,q in zip(a,b)]
            gx=(x+0.5-step*1.5)/step;gy=(y+0.5-step*1.5)/step
            if 0<=round(gx)<=2 and 0<=round(gy)<=2 and math.hypot((gx-round(gx))*step,(gy-round(gy))*step)<dot:col=[255,255,255]
            out+=bytes(col)+bytes([round(alpha*255)])
    return bytes(out)

def png(size):
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rgba(size),9))+chunk(b'IEND',b'')

def photo(root,size=32):
    import tkinter as tk
    return tk.PhotoImage(master=root,data=base64.b64encode(png(size)))

def write_ico(path,sizes=(16,32,48,256)):
    images=[png(s) for s in sizes];offset=6+16*len(images);head=struct.pack('<HHH',0,1,len(images));body=b''
    for s,data in zip(sizes,images):
        head+=struct.pack('<BBBBHHII',s%256,s%256,0,0,1,32,len(data),offset+len(body));body+=data
    with open(path,'wb') as f:f.write(head+body)

if __name__=='__main__':
    import sys;write_ico(sys.argv[1])
