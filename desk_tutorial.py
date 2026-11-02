"""Developer tool: records a ~15 s tutorial of the REAL Tune UI driven by a script with
SYNTHETIC data (temporary fake config folder). Frames are composed from PrintWindow renders
of this app's own windows on black, so no screen pixels (desktop, games) are ever captured.
Usage: python desk_tutorial.py OUT.mp4 FFMPEG"""
import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk
import capture_model as m
from desk_app import App
from desk_capture import render,spare_origin
from desk_demo import world,walk

FPS=10;SECONDS=15;W,H=600,880;MARGIN=40

def main(out,ffmpeg):
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    with tempfile.TemporaryDirectory(prefix='tune-tutorial-') as t:
        base=Path(t);cfg,paths=world(base);store=m.Store(base/'appdata')
        # One existing profile, no remembered source, so the Save tab still shows first use.
        store.save(m.capture(paths['demo-account-b'],'Smurf EU',cfg,lambda:None))
        root=tk.Tk();app=App(root,store,cfg,lambda:None,motion=False);ox,oy=spare_origin(root);root.geometry(f'+{ox}+{oy}');root.update()
        def dialogs():return [w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.winfo_ismapped()]
        def dialog():return dialogs()[-1]
        def pick(i):
            box=next(x for x in walk(dialog()) if isinstance(x,tk.Listbox));box.selection_clear(0,'end');box.selection_set(i);box.event_generate('<<ListboxSelect>>')
        def type_label(text):
            e=next(x for x in walk(dialog()) if isinstance(x,tk.Entry));e.delete(0,'end')
            for i,ch in enumerate(text):root.after(70*i,lambda ch=ch:e.insert('end',ch))
        def press_text(text):next(x for x in walk(dialog()) if getattr(x,'label',None)==text).invoke()
        def select_saved():
            path=app.selected;app.selected=None
            app.pick(next((k for k,(p,_) in enumerate(app.items) if p==path),0))
        steps=[(1.2,lambda:app.run(app.save_settings)),(2.0,lambda:pick(0)),(2.5,lambda:type_label('Main')),(3.6,lambda:app.ok_button.invoke()),
               (5.4,lambda:app.show_screen('accounts')),(6.3,select_saved),
               (7.2,lambda:app.run(app.apply_profile)),(8.0,lambda:pick(1)),(8.8,lambda:app.ok_button.invoke()),(10.4,lambda:press_text('Apply now')),
               (11.6,lambda:press_text('OK')),(12.0,lambda:app.run(app.show_mini)),(13.0,lambda:app.mini.cycle(1)),(14.1,lambda:app.run(app.show_full))]
        for at,fn in steps:root.after(int(at*1000),fn)
        frames=[]
        def compose():
            """Root window plus open dialogs, each a PrintWindow render, placed relative to root."""
            frame=bytearray(W*H*3);rw,rh,rgb,(ox,oy)=render(root,update=False);layers=[(rw,rh,rgb,(ox,oy))]
            for d in dialogs():layers.append(render(d,update=False))
            for lw,lh,data,(lx,ly) in layers:
                x0,y0=lx-ox+MARGIN,ly-oy+MARGIN
                for j in range(max(0,-y0),min(lh,H-y0)):
                    cx0=max(0,-x0);cx1=min(lw,W-x0)
                    if cx1>cx0:frame[((y0+j)*W+x0+cx0)*3:((y0+j)*W+x0+cx1)*3]=data[(j*lw+cx0)*3:(j*lw+cx1)*3]
            return bytes(frame)
        import time;start=time.perf_counter()
        def tick(i=0):
            if i>=FPS*SECONDS:app.close();return
            try:frames.append(compose())
            except (OSError,tk.TclError):frames.append(frames[-1] if frames else bytes(W*H*3))
            # Keep frames on the real-time clock so the video matches the scripted timeline.
            root.after(max(1,int((start+(i+1)/FPS-time.perf_counter())*1000)),lambda:tick(i+1))
        root.after(0,tick);root.mainloop()
        enc=subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
                            '-vf',"drawtext=fontfile='C\\:/Windows/Fonts/segoeui.ttf':text='Tune - synthetic demo data, scripted input':fontcolor=0xA1A1AA:fontsize=15:x=(w-tw)/2:y=h-26",
                            '-r','30','-c:v','libx264','-pix_fmt','yuv420p','-crf','20','-movflags','+faststart',str(out)],input=b''.join(frames))
        if enc.returncode:raise RuntimeError('Encoding failed')
        print('frames',len(frames))

if __name__=='__main__':main(sys.argv[1],sys.argv[2])
