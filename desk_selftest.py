"""Packaged fixture-only self-test for Tune 4.0 (Tune.exe --self-test).
Generated synthetic files in a temporary folder; real VALORANT files are never opened.
Needs NOTEBOOK_TEST_REPORT=<writable .json>; optional NOTEBOOK_TEST_TEMP=<folder>."""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
import capture_model as m
import desk_profiles as dp
from desk_app import App
from desk_theme import VERSION

def run():
    if os.name=='nt' and ctypes.windll.shell32.IsUserAnAdmin():raise RuntimeError('Self-test refuses administrator execution.')
    checks=[]
    with tempfile.TemporaryDirectory(dir=os.environ.get('NOTEBOOK_TEST_TEMP'),prefix='presetdesk40-test-') as temp:
        base=Path(temp);config=base/'Config'
        source=config/'one'/'Windows'/'GameUserSettings.ini';target=config/'two'/'Windows'/'GameUserSettings.ini'
        raw=b'[/Script/ShooterGame.ShooterGameUserSettings]\nbUseVSync=False\nFrameRateLimit=240.0\nSyntheticAccountField=keep\n[ScalabilityGroups]\nsg.TextureQuality=1\nUnrelated=keep\n'
        for p in (source,target):p.parent.mkdir(parents=True);p.write_bytes(raw)
        target.write_bytes(raw.replace(b'Quality=1',b'Quality=0'));before=target.read_bytes()
        source.with_name('RiotUserSettings.ini').write_bytes(b'[Settings]\nEAresFloatSettingName::MouseSensitivity=0.25\n')
        root=tk.Tk();root.withdraw();notices=[]
        try:
            with patch.object(App,'notice',lambda s,t,b:notices.append(b)):
                launched=[];app=App(root,m.Store(base/'appdata'),config,lambda:None,motion=False,launcher=lambda e:launched.append(e))
                assert app.look.name=='dark' and app.save_btn.text=='Set up & save';checks.append('dark default, first-use guide')
                app.show_screen('accounts');assert app.apply_tile.state=='disabled';app.show_screen('save');checks.append('save and accounts screens render')
                with patch.object(app,'choose_source',return_value=(source,'Demo')):path=app.save_settings()
                assert app.save_settings()==path and len(app.items)==1;checks.append('first save and one-tap repeat save')
                assert '0.25' in app.readable(path) and app.items[0][1]['settings']['FrameRateLimit']=='240.0';checks.append('sensitivity kept as reference only')
                with patch.object(app,'choose_source',return_value=(target,'')),patch.object(app,'confirm_changes',return_value=False):app.apply_profile(path)
                assert target.read_bytes()==before;checks.append('cancelled apply writes nothing')
                app.guard=lambda:(_ for _ in ()).throw(RuntimeError('Close VALORANT and Riot Client'))
                app.run(lambda:app.apply_profile(path));assert target.read_bytes()==before and 'Close VALORANT' in notices[-1];app.guard=lambda:None
                checks.append('running game/client blocks apply')
                with patch.object(app,'choose_source',return_value=(target,'')),patch.object(app,'confirm_changes',return_value=True):app.apply_profile(path)
                assert target.read_bytes()==raw and b'SyntheticAccountField=keep' in target.read_bytes();checks.append('confirmed apply with backup, unrelated values kept')
                with patch.object(app,'choose_source',return_value=(target,'')),patch.object(app,'confirm_changes',return_value=True):app.undo_last()
                assert target.read_bytes()==before and source.read_bytes()==raw;checks.append('guarded undo')
                share=base/'share.json'
                with patch.object(app,'ask_text',return_value=''),patch('desk_app.filedialog.asksaveasfilename',return_value=str(share)):app.export_profile(path)
                assert set(json.loads(share.read_text()))=={'format','version','settings'};checks.append('settings-only export')
                bad=base/'bad.json';bad.write_text('{"format":"presetdesk-share","version":1,"settings":{"bUseVSync":"True\\n[X]"}}')
                try:dp.read_import(bad);raise AssertionError('accepted injection')
                except ValueError:checks.append('malicious import rejected')
                app.show_mini();root.update();assert app.selected==path;app.mini.toggle_pin();app.mini.toggle_pin();app.show_full();checks.append('compact view round trip')
                before=app.content.find_all()
                for ctl in app.ui.controls:ctl.hover(True);ctl.hover(False)
                assert app.content.find_all()==before;checks.append('hover never recreates items (freeze regression)')
                app.choose_theme('light');app.choose_theme('dark');checks.append('theme switch')
                import desk_profiles as _dp;game_bytes=target.read_bytes()
                with patch.object(_dp,'riot_client',return_value=None):app.run(app.launch_riot)
                assert launched==[] and 'could not find Riot Client' in notices[-1]
                with patch.object(_dp,'riot_client',return_value=base/'RiotClientServices.exe'):app.launch_riot()
                assert len(launched)==1 and target.read_bytes()==game_bytes;checks.append('switch-account opens Riot Client only, no login/tokens')
                app.close()
            report={'result':'PASS','version':VERSION,'elevated':False,'checks':checks,'live_game_files_touched':False}
            Path(os.environ['NOTEBOOK_TEST_REPORT']).write_text(json.dumps(report,indent=2),encoding='utf-8')
        finally:
            try:root.destroy()
            except tk.TclError:pass
