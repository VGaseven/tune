"""Developer tool: real Preset Desk windows driven with SYNTHETIC data for screenshots.
Uses a temporary fake config folder; never reads or writes real VALORANT files.
Usage: python desk_demo.py OUTPUT_DIR [scale]"""
import ctypes
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
import capture_model as m
import desk_profiles as dp
from desk_app import App
from desk_capture import shot_window,spare_origin

QUALITY=sorted(m.QUALITY)
def ini(level,vsync,fps):
    q=''.join(f'{k}={level}\r\n' for k in QUALITY)
    return (f'; synthetic demo file\r\n[/Script/ShooterGame.ShooterGameUserSettings]\r\nbUseVSync={vsync}\r\nFrameRateLimit={fps}\r\n'
            f'ResolutionSizeX=1920\r\nDemoAccountField=keep\r\n[ScalabilityGroups]\r\n{q}DemoUnrelated=keep\r\n').encode()

def world(base):
    cfg=base/'Config';paths={}
    for folder,data in [('demo-account-a',ini(1,'False','240.000000')),('demo-account-b',ini(3,'True','0.000000')),('demo-account-c',ini(2,'False','144.000000'))]:
        p=cfg/folder/'Windows'/'GameUserSettings.ini';p.parent.mkdir(parents=True);p.write_bytes(data);paths[folder]=p
    (cfg/'demo-account-a'/'Windows'/'RiotUserSettings.ini').write_bytes(b'[Settings]\r\nEAresFloatSettingName::MouseSensitivity=0.35\r\nEAresFloatSettingName::MouseSensitivityADS=1.0\r\n')
    return cfg,paths

def main(out,scale=1.0):
    # Captures are window renders (PrintWindow) of this app only, never screen pixels, so other
    # windows - including a game in front - cannot appear in them. No focus is forced.
    if os.name=='nt':ctypes.windll.shcore.SetProcessDpiAwareness(1)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='presetdesk-demo-') as t:
        base=Path(t);cfg,paths=world(base);store=m.Store(base/'appdata')
        root=tk.Tk()
        if scale!=1.0:root.tk.call('tk','scaling',float(root.tk.call('tk','scaling'))*scale)
        app=App(root,store,cfg,lambda:None,motion=False);suffix='' if scale==1.0 else f'-scale{int(scale*100)}'
        ox,oy=spare_origin(root);root.geometry(f'+{ox}+{oy}');root.update();root.after(300);root.update()
        def snap(win,name):
            for _ in range(12):root.update();root.after(40)
            print(name,shot_window(win,str(out/(name+suffix+'.png'))))
        snap(root,'01-save-first-use')
        with patch.object(app,'choose_source',return_value=(paths['demo-account-a'],'Main - Ascendant')):app.save_settings()
        snap(root,'02-save-confirmation')
        with patch.object(app,'choose_source',return_value=(paths['demo-account-b'],'Smurf EU')):app.save_settings(True)
        share=base/'friend.json';share.write_text('{"format":"presetdesk-share","version":1,"label":"Friend preset (shared)","settings":{"sg.TextureQuality":"2","bUseVSync":"False","FrameRateLimit":"165.000000"}}')
        with patch('desk_app.filedialog.askopenfilename',return_value=str(share)):app.import_profile()
        app.selected=next(p for p,d in app.items if d['label']=='Main - Ascendant');app.refresh();app.show_screen('accounts')
        snap(root,'03-accounts-selected')
        def in_dialog(action):
            def step():
                win=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.winfo_ismapped() and not w.overrideredirect()][-1]
                action(win)
            root.after(600,step)
        def destination(win):
            box=next(x for x in walk(win) if isinstance(x,tk.Listbox));box.selection_set(1);box.event_generate('<<ListboxSelect>>')
            snap(win,'04-apply-destination');app.ok_button.invoke()
        def confirm(win):snap(win,'05-apply-review');win.destroy()
        in_dialog(destination)
        orig=app.confirm_changes
        def confirm_wrap(*a):in_dialog(confirm);return orig(*a)
        with patch.object(app,'confirm_changes',side_effect=confirm_wrap):app.apply_profile()
        app.show_mini();root.geometry(f'+{ox}+{oy}');snap(root,'06-compact-view');app.show_full()
        if scale==1.0:
            app.choose_theme('light');app.show_screen('accounts');snap(root,'07-accounts-light-theme');app.choose_theme('dark')
            app.show_screen('save');app.selected=None;app.refresh()
        app.close()

def backdrop(root,rect):
    """Plain black window behind the app so captures never include the real desktop."""
    x,y,wd,ht=rect;b=tk.Toplevel(root);b.overrideredirect(True);b.configure(bg='#000000');b.geometry(f'{wd}x{ht}+{x}+{y}')
    b.update();root.lift();return b

def walk(w):return [c for x in w.winfo_children() for c in [x,*walk(x)]]

if __name__=='__main__':main(sys.argv[1],float(sys.argv[2]) if len(sys.argv)>2 else 1.0)
