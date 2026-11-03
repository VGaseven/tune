"""Preset Desk 4.0 tests. Synthetic fixtures only; no live VALORANT files or processes."""
import json
import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
import capture_model as m
import desk_profiles as dp
import desk_theme
from desk_app import App,load_theme
from desk_skin import PillButton,RoundButton,Toggle,UI,card_png,draw_matrix
from test_capture import FIXTURE
from test_reference import RAW

def walk(w):return [c for x in w.winfo_children() for c in [x,*walk(x)]]

class DeskBase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('NOTEBOOK_TEST_TEMP'));self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.config=self.base/'Config'   # resolve 8.3 short names (CI runner) so they match the app's scanned paths
        self.source=self.config/'one'/'Windows'/'GameUserSettings.ini';self.target=self.config/'two'/'Windows'/'GameUserSettings.ini'
        for p in (self.source,self.target):p.parent.mkdir(parents=True);p.write_bytes(FIXTURE)
        self.source.with_name('RiotUserSettings.ini').write_bytes(RAW)
        self.root=tk.Tk();self.root.withdraw();self.addCleanup(self.destroy)
        self.app=self.make()
        self.notices=[];patcher=patch.object(App,'notice',lambda s,t,b:self.notices.append((t,b)));patcher.start();self.addCleanup(patcher.stop)
    def make(self,store=None):
        return App(self.root,store or m.Store(self.base/'appdata'),self.config,lambda:None,motion=False)
    def destroy(self):
        try:self.app.close()
        except tk.TclError:pass
        try:self.root.destroy()
        except tk.TclError:pass
    def save(self,label='Main',source=None,force=False):
        with patch.object(self.app,'choose_source',return_value=(source or self.source,label)):return self.app.save_settings(force)
    def changed_target(self):
        values=m.parse(FIXTURE)[2].copy();values['sg.TextureQuality']='0';self.target.write_bytes(m.merge(FIXTURE,values));return self.target.read_bytes()
    def apply(self,confirm=True,target=None,path=None):
        with patch.object(self.app,'choose_source',return_value=(target or self.target,'')),patch.object(self.app,'confirm_changes',return_value=confirm) as c:
            result=self.app.apply_profile(path);return result,c
    def hidden_dialogs(self,inspect):
        """Real dialog widgets, withdrawn; `inspect(win)` drives them instead of the user."""
        original=self.app.dialog
        def dialog(title):
            win,frame=original(title);win.withdraw();return win,frame
        def wait(win,focus=None):inspect(win)
        return patch.object(self.app,'dialog',side_effect=dialog),patch.object(self.app,'wait',side_effect=wait)

class FirstUseAndSave(DeskBase):
    def texts(self):
        cv=self.app.content;return [cv.itemcget(i,'text') for i in cv.find_all() if cv.type(i)=='text']
    def test_first_use_empty_state(self):
        self.assertEqual(self.app.screen,'save');self.assertEqual(self.app.save_btn.text,'Set up & save');self.assertIn('No account',self.texts())
        self.assertIn('Settings',self.texts());self.assertIn('Accounts',self.texts())   # tab bar is present
        self.app.show_screen('accounts');self.assertIn('No profiles yet',self.texts());self.assertEqual(self.app.apply_tile.state,'disabled')
        self.assertEqual(self.app.look.name,'dark');self.assertEqual(self.root.cget('bg'),desk_theme.PALETTES['dark']['bg'])
    def test_one_primary_save_action_on_main_screen(self):
        pills=[c for c in self.app.ui.controls if isinstance(c,PillButton) and not c.name.startswith('Tab:')]
        self.assertEqual([p.name for p in pills],['Save']);self.assertEqual(self.app.save_btn.text,'Set up & save')
    def test_save_then_one_tap_repeat_updates_same_profile(self):
        first=self.save();self.assertEqual(len(self.app.items),1)
        self.assertEqual(self.app.acct['label'],'Main');self.assertIn('Main',self.texts());self.assertEqual(self.app.save_btn.text,'Save settings')
        s=self.app.last_saved;self.assertEqual((s['label'],s['n'],s['ref']),('Main',4,3));self.assertIn('Textures',s['names'])
        with patch.object(self.app,'choose_source',side_effect=AssertionError('must reuse remembered source')):second=self.app.save_settings()
        self.assertEqual(first,second);self.assertEqual(len(self.app.items),1);self.assertEqual(self.source.read_bytes(),FIXTURE)
    def test_change_source_always_asks(self):
        self.save()
        with patch.object(self.app,'choose_source',return_value=None) as choose:self.app.save_settings(True);choose.assert_called_once()
    def test_cancelled_setup_changes_nothing(self):
        with patch.object(self.app,'choose_source',return_value=None):self.app.save_settings()
        self.assertEqual(self.app.items,[]);self.assertFalse((self.app.store.base/'source-labels.json').exists());self.assertIn('cancelled',self.app.status.get())
    def test_failed_save_preserves_previous_profile(self):
        path=self.save();before=path.read_bytes()
        self.source.write_bytes(b'not an ini at all')
        self.app.run(self.app.save_settings)
        self.assertEqual(path.read_bytes(),before);self.assertEqual(len(self.app.items),1);self.assertTrue(self.notices);self.assertFalse(self.app.busy)
    def test_no_sources_and_inaccessible_folder_are_reported(self):
        empty=App(self.root,m.Store(self.base/'other'),self.base/'Missing',lambda:None,motion=False)
        empty.run(empty.save_settings);self.assertIn('No VALORANT settings files',self.notices[-1][1])
        with patch('capture_model.discover',side_effect=PermissionError('Access is denied')):self.app.run(self.app.save_settings)
        self.assertIn('denied',self.notices[-1][1]);self.assertEqual(self.app.items,[])
    def test_setup_dialog_requires_explicit_folder_and_label(self):
        seen={}
        def drive(win):
            ws=walk(win);box=next(w for w in ws if isinstance(w,tk.Listbox));entry=next(w for w in ws if isinstance(w,tk.Entry))
            seen['preselected']=box.curselection();rows=box.get(0,'end');seen['rows']=rows
            self.app.ok_button.invoke();self.assertTrue(win.winfo_exists())
            box.selection_set(0);box.event_generate('<<ListboxSelect>>');self.app.ok_button.invoke();self.assertTrue(win.winfo_exists())
            entry.insert(0,'Main account');self.app.ok_button.invoke()
        a,b=self.hidden_dialogs(drive)
        with a,b:result=self.app.choose_source([self.source,self.target],'save')
        self.assertEqual(seen['preselected'],());self.assertEqual(result,(self.source,'Main account'))
        self.assertTrue(all('Unnamed account' in r for r in seen['rows']))
    def test_repeated_clicks_do_not_reenter(self):
        calls=[]
        def action():
            calls.append(1);self.assertEqual(self.app.save_btn.state,'disabled');self.app.run(lambda:calls.append(2))
        self.app.run(action);self.assertEqual(calls,[1]);self.assertEqual(self.app.save_btn.state,'normal')
        with patch.object(self.app,'choose_source',return_value=None) as choose:
            for _ in range(3):self.app.save_btn.invoke()
        self.assertEqual(choose.call_count,3);self.assertFalse(self.app.busy);self.assertEqual(self.app.items,[])

class SignedInAccount(DeskBase):
    A='0aec6e15-90a1-4b2c-8d3e-111111111111';B='21c9f7c6-a7b2-4c3d-9e4f-222222222222'
    def accounts(self,signed):
        made={}
        for uid in (self.A,self.B):
            for sub in ('Windows','WindowsClient'):
                p=self.config/f'{uid}-eu'/sub/'GameUserSettings.ini';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(FIXTURE)
            made[uid]=self.config/f'{uid}-eu'/'Windows'/'GameUserSettings.ini'
        shared=self.config/'WindowsClient'/'GameUserSettings.ini';shared.parent.mkdir(parents=True,exist_ok=True);shared.write_bytes(FIXTURE)
        logs=self.base/'Logs';logs.mkdir(exist_ok=True)
        (logs/'ShooterGame.log').write_text(f'[x]LogShooterGameUserSettings: Logged in user changed: {self.B}\n[y]LogPlatformCommon: query {self.A}\n'
                                            f'[z]LogShooterGameUserSettings: Logged in user changed: {signed}\n',encoding='utf-8')
        return made
    def test_signed_in_comes_from_latest_login_line_only(self):
        self.accounts(self.A);self.assertEqual(dp.signed_in(self.config),self.A)
        (self.base/'Logs'/'ShooterGame.log').write_text('no login line, mentions '+self.A*50)
        self.assertIsNone(dp.signed_in(self.config));self.assertIsNone(dp.signed_in(self.base/'missing'/'Config'))
    def test_one_row_per_account_and_shared_folders_hidden(self):
        made=self.accounts(self.A);paths=self.app.scan()
        self.assertIn(made[self.A],paths);self.assertIn(made[self.B],paths)
        self.assertFalse(any(p.parent.name=='WindowsClient' and dp.account_of(p,self.config) in (f'{self.A}-eu',f'{self.B}-eu') for p in paths))
        self.assertFalse(any(dp.account_of(p,self.config) is None for p in paths))
    def test_save_uses_signed_in_account_and_asks_name_only_once(self):
        made=self.accounts(self.A);self.app.refresh()
        self.assertEqual((self.app.acct['label'],self.app.acct['signed'],self.app.save_btn.text),(None,True,'Save this account'))
        with patch.object(self.app,'choose_source',return_value=(made[self.A],'DAISY')) as ask:self.app.save_settings();ask.assert_called_once()
        self.assertEqual(self.app.acct['label'],'DAISY');self.assertTrue(self.app.acct['saved']);self.assertEqual(self.app.save_btn.text,'Update save')
        with patch.object(self.app,'choose_source',side_effect=AssertionError('named already')):self.app.save_settings()
        # Switching accounts in VALORANT: Save follows the game, never the old remembered folder.
        self.accounts(self.B);self.app.refresh();self.assertEqual(self.app.save_btn.text,'Save this account')
        with patch.object(self.app,'choose_source',return_value=None) as ask:self.app.save_settings();ask.assert_called_once()
        self.assertEqual(len(self.app.items),1)
    def test_save_dialog_preselects_signed_in_but_apply_does_not(self):
        made=self.accounts(self.B);paths=self.app.scan();seen=[]
        def look(win):
            box=next(w for w in walk(win) if isinstance(w,tk.Listbox));seen.append((box.curselection(),box.get(0,'end')));win.destroy()
        a,b=self.hidden_dialogs(look)
        with a,b:
            self.app.choose_source(paths,'save');self.app.choose_source(paths,'apply',m.capture(made[self.A],'X',self.config,lambda:None))
        i=paths.index(made[self.B]);self.assertEqual(seen[0][0],(i,));self.assertIn('signed in',seen[0][1][i])
        self.assertEqual(seen[1][0],());self.assertIn('signed in',seen[1][1][i])

class SettingsSnapshot(DeskBase):
    def test_settings_tab_shows_saved_snapshot_not_live_until_save(self):
        src=self.source
        with patch.object(self.app,'choose_source',return_value=(src,'Main')):self.app.save_settings()
        saved=dict(self.app.acct['values']);self.assertTrue(self.app.acct['saved']);self.assertTrue(saved)
        v=m.parse(FIXTURE)[2].copy();v['sg.TextureQuality']='0';src.write_bytes(m.merge(FIXTURE,v))  # game changes its file
        self.app.refresh()
        self.assertEqual(self.app.acct['values'],saved)                      # display does NOT auto-update
        with patch.object(self.app,'choose_source',return_value=(src,'Main')):self.app.save_settings()
        self.assertEqual(self.app.acct['values']['sg.TextureQuality'],'0')    # only Save updates it
    def test_tab_bar_switches_screens(self):
        self.app.show_screen('save');tabs=[c for c in self.app.ui.controls if c.name.startswith('Tab:')]
        self.assertEqual(len(tabs),2)
        next(c for c in tabs if 'Accounts' in c.name).invoke();self.assertEqual(self.app.screen,'accounts')
        next(c for c in self.app.ui.controls if 'Settings' in c.name).invoke();self.assertEqual(self.app.screen,'save')
    def test_background_is_one_cached_image_not_many_dots(self):
        self.app.show_screen('save');cv=self.app.content
        imgs=[i for i in cv.find_all() if cv.type(i)=='image']
        self.assertTrue(imgs);self.assertLess(sum(1 for i in cv.find_all() if cv.type(i)=='oval'),400)  # dot grid no longer per-item

class RiotLauncher(DeskBase):
    def write_manifest(self,pd,payload):
        (pd/'Riot Games').mkdir(parents=True,exist_ok=True)
        (pd/'Riot Games'/'RiotClientInstalls.json').write_text(json.dumps(payload))
    def test_riot_client_detection_is_strict(self):
        pd=self.base/'PD';exe=self.base/'RC'/'RiotClientServices.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'x')
        with patch.dict(os.environ,{'PROGRAMDATA':str(pd)}):
            self.assertIsNone(dp.riot_client())                                   # no manifest yet
            self.write_manifest(pd,{'rc_default':str(exe)});self.assertEqual(dp.riot_client(),exe)
            self.write_manifest(pd,{'rc_live':str(self.base/'RC'/'nope.exe')});self.assertIsNone(dp.riot_client())  # file missing
            wrong=self.base/'RC'/'Tune.exe';wrong.write_bytes(b'x');self.write_manifest(pd,{'rc_live':str(wrong)});self.assertIsNone(dp.riot_client())  # wrong exe
            self.write_manifest(pd,{'rc_live':123});self.assertIsNone(dp.riot_client())                             # not a string
            (pd/'Riot Games'/'RiotClientInstalls.json').write_text('{broken');self.assertIsNone(dp.riot_client())   # bad json
    def test_launch_opens_client_and_touches_no_game_files(self):
        exe=self.base/'RC'/'RiotClientServices.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'x')
        launched=[];self.app.launcher=lambda e:launched.append(e);before=self.source.read_bytes()
        with patch('desk_profiles.riot_client',return_value=exe):self.app.launch_riot()
        self.assertEqual(launched,[exe]);self.assertIn('Riot',self.app.status.get());self.assertEqual(self.source.read_bytes(),before)
    def test_launch_without_client_tells_user_and_starts_nothing(self):
        launched=[];self.app.launcher=lambda e:launched.append(e)
        with patch('desk_profiles.riot_client',return_value=None):self.app.run(self.app.launch_riot)
        self.assertEqual(launched,[]);self.assertIn('could not find Riot Client',self.notices[-1][1])
    def test_menu_offers_switch_account(self):
        m=self.app.build_menu();labels=[m.entrycget(i,'label') for i in range(m.index('end')+1) if m.type(i)=='command']
        self.assertTrue(any('Switch account' in l for l in labels))

class ApplyAndUndo(DeskBase):
    def test_destination_and_preview_cancel_do_not_write(self):
        self.save();before=self.changed_target()
        with patch.object(self.app,'choose_source',return_value=None):self.app.apply_profile(self.app.selected)
        self.apply(confirm=False);self.assertEqual(self.target.read_bytes(),before);self.assertFalse((self.app.store.base/'backups').exists())
    def test_apply_writes_only_allowlisted_values_with_backup(self):
        self.save();self.changed_target()
        backup,confirm=self.apply();self.assertEqual(confirm.call_count,1)
        self.assertEqual(self.target.read_bytes(),FIXTURE);self.assertTrue(backup.is_file())
        record=json.loads(backup.read_text());self.assertEqual(set(record['before']),{'sg.TextureQuality'})
        for keep in (b'SyntheticAccountField=keep-me',b'UnknownFutureSetting=keep',b'ResolutionSizeX=1920'):self.assertIn(keep,self.target.read_bytes())
        self.assertEqual(self.source.read_bytes(),FIXTURE);self.assertIn('Reopen',''.join(b for _,b in self.notices).replace('open VALORANT','Reopen'))
    def test_already_matching_target_is_a_no_op(self):
        self.save();_,confirm=self.apply();confirm.assert_not_called();self.assertIn('already matches',self.app.status.get())
    def test_target_changed_after_preview_is_rejected(self):
        self.save();self.changed_target()
        def edit(*a):self.target.write_bytes(self.target.read_bytes()+b'; newer\r\n');return True
        with patch.object(self.app,'choose_source',return_value=(self.target,'')),patch.object(self.app,'confirm_changes',side_effect=edit):
            with self.assertRaises(ValueError):self.app.apply_profile(self.app.selected)
        self.assertIn(b'; newer',self.target.read_bytes())
    def test_running_game_blocks_every_apply_route(self):
        self.save();before=self.changed_target()
        def blocked():raise RuntimeError('Close VALORANT and Riot Client normally, then try again.')
        self.app.guard=blocked;card_path=self.app.selected
        self.app.show_screen('accounts')
        def keyboard():                     # Tab to the Apply tile, press Return
            self.app.ui.set_focus(self.app.apply_tile);self.app.ui.activate()
        routes=[lambda:self.app.run(lambda:self.app.apply_profile(card_path)),lambda:self.app.apply_tile.invoke(),keyboard,
                lambda:(self.app.show_mini(),self.app.mini.apply.invoke()),lambda:self.app.run(self.app.undo_last)]
        with patch.object(self.app,'choose_source',side_effect=AssertionError('no dialog when blocked')):
            for route in routes:
                count=len(self.notices);route();self.root.update()
                self.assertEqual(len(self.notices),count+1);self.assertIn('Close VALORANT',self.notices[-1][1])
        self.assertEqual(self.target.read_bytes(),before);self.assertEqual(len(self.app.items),1)
    def test_save_works_while_game_open_but_apply_does_not(self):
        def blocked():raise RuntimeError('Close VALORANT and Riot Client normally, then try again.')
        self.app.guard=blocked;before=self.target.read_bytes()
        path=self.save();self.assertTrue(path.is_file());self.assertTrue(self.app.last_saved['open'])  # saved with the game "open"
        self.assertEqual(self.source.read_bytes(),FIXTURE)                                             # Save only read, never wrote
        self.app.run(lambda:self.app.apply_profile(path))
        self.assertIn('keeps its settings in memory',self.notices[-1][1]);self.assertEqual(self.target.read_bytes(),before)
        self.app.guard=lambda:None;self.save();self.assertFalse(self.app.last_saved['open'])
    def test_guard_rechecked_at_write_time(self):
        self.save();before=self.changed_target();state={'n':0}
        def guard():
            state['n']+=1
            if state['n']>3:raise RuntimeError('Riot Client started')
        self.app.guard=guard
        with self.assertRaises(RuntimeError):self.apply()
        self.assertEqual(self.target.read_bytes(),before)
    def test_destination_dialog_marks_source_and_preselects_nothing(self):
        self.save();profile=self.app.profile(self.app.selected);seen={}
        def look(win):
            box=next(w for w in walk(win) if isinstance(w,tk.Listbox));seen['sel']=box.curselection();seen['rows']=box.get(0,'end');win.destroy()
        a,b=self.hidden_dialogs(look)
        with a,b:self.assertIsNone(self.app.choose_source([self.source,self.target],'apply',profile))
        self.assertEqual(seen['sel'],());self.assertIn('saved from here',seen['rows'][0]);self.assertNotIn('saved from here',seen['rows'][1])
    def test_confirm_dialog_cancel_returns_false(self):
        a,b=self.hidden_dialogs(lambda win:win.destroy())
        with a,b:self.assertFalse(self.app.confirm_changes(self.target,[('bUseVSync','False','True')],'Apply','Alt'))
    def test_undo_restores_newest_matching_backup_and_guards_conflicts(self):
        self.save();before=self.changed_target();self.apply()
        with patch.object(self.app,'choose_source',return_value=(self.target,'')),patch.object(self.app,'confirm_changes',return_value=True):
            self.app.undo_last()
        self.assertEqual(self.target.read_bytes(),before)
        self.apply();values=m.parse(FIXTURE)[2].copy();values['sg.TextureQuality']='1';newer=m.merge(FIXTURE,values);self.target.write_bytes(newer)
        with patch.object(self.app,'choose_source',return_value=(self.target,'')),patch.object(self.app,'confirm_changes',return_value=True):
            with self.assertRaises(ValueError):self.app.undo_last()
        self.assertEqual(self.target.read_bytes(),newer)
        with patch.object(self.app,'choose_source',return_value=(self.source,'')):
            with self.assertRaises(ValueError):self.app.undo_last()
    def test_interrupted_write_lock_blocks_second_writer(self):
        self.save();before=self.changed_target();(self.app.store.base/'backups').mkdir(parents=True,exist_ok=True)
        (self.app.store.base/'backups'/'write.lock').write_text('')
        with self.assertRaises(RuntimeError):self.apply()
        self.assertEqual(self.target.read_bytes(),before)

class AccountsManagement(DeskBase):
    def test_many_profiles_duplicates_and_long_names(self):
        long='L'*80
        for i,label in enumerate(['Main','Main',long]):
            p=self.config/f'acc{i}'/'Windows'/'GameUserSettings.ini';p.parent.mkdir(parents=True);p.write_bytes(FIXTURE);self.save(label,p,True)
        self.assertEqual(len(self.app.items),3);self.assertEqual(sorted(n for n in self.app.names if n.startswith('Main')),['Main (1)','Main (2)'])
        self.assertEqual(sorted(d['label'] for _,d in self.app.items).count('Main'),2)
        self.app.show_screen('accounts');W=self.app.drawn[0];cv=self.app.content
        for k in range(3):
            self.app.pick(k);x0,_,x1,_=cv.bbox(next(i for i in cv.find_all() if cv.type(i)=='text' and cv.itemcget(i,'font').endswith('12') and cv.itemcget(i,'text').startswith(('L','Main'))))
            self.assertGreaterEqual(x0,0);self.assertLessEqual(x1,W)      # long names are shortened, never clipped off-window
        self.app.step_profile(-9);self.assertEqual(self.app.selected,self.app.items[0][0]);self.app.step_profile(9);self.assertEqual(self.app.selected,self.app.items[2][0])
    def test_rename_duplicate_delete(self):
        path=self.save()
        with patch.object(self.app,'ask_text',return_value='Renamed main'):self.app.rename_profile(path)
        self.assertEqual(self.app.items[0][1]['label'],'Renamed main');self.assertEqual(dp.remembered(self.app.store)[1],'Renamed main')
        for bad in ('','x'*81,'two\nlines'):
            with patch.object(self.app,'ask_text',return_value=bad):
                with self.assertRaises(ValueError):self.app.rename_profile(path)
        with patch.object(self.app,'ask_text',return_value=None):self.app.rename_profile(path)
        self.app.duplicate_profile(path);self.assertEqual(len(self.app.items),2);self.assertTrue(any(d['label'].endswith('copy') for _,d in self.app.items))
        with patch.object(self.app,'ask_yes',return_value=False):self.app.delete_profile(path)
        self.assertEqual(len(self.app.items),2)
        with patch.object(self.app,'ask_yes',return_value=True):self.app.delete_profile(path)
        self.assertEqual(len(self.app.items),1);self.assertEqual(len(list((self.app.store.base/'deleted').glob('*.json'))),1)
        with self.assertRaises(ValueError):dp.delete(self.app.store,self.source)
    def test_export_is_settings_only_and_cancellable(self):
        path=self.save();dest=self.base/'share.json'
        with patch.object(self.app,'ask_text',return_value=None):self.app.export_profile(path)
        with patch.object(self.app,'ask_text',return_value='Friend'),patch('desk_app.filedialog.asksaveasfilename',return_value=''):self.app.export_profile(path)
        self.assertFalse(dest.exists())
        with patch.object(self.app,'ask_text',return_value='Friend'),patch('desk_app.filedialog.asksaveasfilename',return_value=str(self.base)):
            with self.assertRaises(ValueError):self.app.export_profile(path)
        with patch.object(self.app,'ask_text',return_value=''),patch('desk_app.filedialog.asksaveasfilename',return_value=str(dest)):self.app.export_profile(path)
        data=json.loads(dest.read_text());self.assertEqual(set(data),{'format','version','settings'})
        text=dest.read_text()
        for secret in ('Main','source_ref','sha256',str(self.base),'Sensitivity','0.25'):self.assertNotIn(secret,text)
    def test_import_share_and_legacy_profile(self):
        share=self.base/'s.json';share.write_text(json.dumps({'format':'presetdesk-share','version':1,'label':'Friend','settings':{'sg.TextureQuality':'2'}}))
        with patch('desk_app.filedialog.askopenfilename',return_value=str(share)):saved=self.app.import_profile()
        data=self.app.profile(saved);self.assertTrue(dp.is_shared(data));self.assertEqual(saved.parent.name,'profiles');self.assertEqual(self.app.screen,'accounts')
        legacy=self.base/'legacy.json';legacy.write_text(json.dumps(m.capture(self.source,'Old',self.config,lambda:None)))
        with patch('desk_app.filedialog.askopenfilename',return_value=str(legacy)):self.app.import_profile()
        with patch('desk_app.filedialog.askopenfilename',return_value=''):self.app.import_profile()
        self.assertEqual(len(self.app.items),2)
        # shared profiles still apply only through the guarded flow
        self.changed_target();self.apply(path=saved);self.assertIn(b'sg.TextureQuality=2',self.target.read_bytes())
    def test_malicious_imports_rejected(self):
        good={'format':'presetdesk-share','version':1,'settings':{'bUseVSync':'True'}}
        cases=[dict(good,version=2),dict(good,extra='x'),dict(good,path='..\\..\\Windows'),dict(good,settings={'bUseVSync':'True\n[Hack]\nX=1'}),
               dict(good,settings={'sg.TextureQuality':'4'}),dict(good,settings={'FrameRateLimit':'99999'}),dict(good,settings={'MouseSensitivity':'1'}),
               dict(good,settings={}),dict(good,label='bad\nlabel'),dict(good,label=5),dict(good,settings={'bUseVSync':True}),[1,2]]
        for i,case in enumerate(cases):
            p=self.base/f'bad{i}.json';p.write_text(json.dumps(case))
            with self.assertRaises(ValueError,msg=str(case)):dp.read_import(p)
        big=self.base/'big.json';big.write_text(json.dumps(dict(good,label='x'*10))[:-1]+' '*20000+'}')
        dup=self.base/'dup.json';dup.write_text('{"format":"presetdesk-share","version":1,"version":1,"settings":{"bUseVSync":"True"}}')
        txt=self.base/'p.txt';txt.write_text(json.dumps(good));bad=self.base/'bad.json';bad.write_bytes(b'\xff\xfe\x00garbage')
        for p in (big,dup,txt,self.base,bad,''):
            with self.assertRaises(ValueError):dp.read_import(p)
        self.assertEqual(self.app.items,[])
    def test_profiles_live_under_each_windows_users_localappdata(self):
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.base/'UserA')}):a=m.Store().base
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.base/'UserB')}):b=m.Store().base
        self.assertNotEqual(a,b);self.assertEqual(a,self.base/'UserA'/'PresetDesk')
    def test_details_distinguish_applied_reference_and_manual(self):
        path=self.save();text=self.app.readable(path)
        self.assertIn('your label, not a verified Riot ID',text);self.assertIn('reference only, never applied',text);self.assertIn('manual',text)
        self.assertIn('Not in this profile (manual)',text)

class ViewsAndTheme(DeskBase):
    def test_mini_preserves_selection_cycles_pins_and_expands(self):
        a=self.save('A');b=self.save('B',self.target,True);self.app.selected=a;self.app.refresh()
        self.app.show_mini();self.root.update()
        # Same window, compact layout: no extra toplevel, full content hidden, key actions shown.
        self.assertIs(self.app.mini.win,self.root);self.assertFalse([w for w in self.root.winfo_children() if isinstance(w,tk.Toplevel)])
        self.assertEqual(self.app.content.winfo_manager(),'');self.assertEqual(self.app.mini.frame.winfo_manager(),'pack')
        self.assertEqual((self.app.mini.save.text,self.app.mini.apply.text),('Save','Apply'))
        self.assertEqual(self.app.selected,a);self.assertEqual(self.app.mini.name_text,'A')
        self.app.mini.cycle(1);self.assertEqual(self.app.selected,b);self.app.mini.cycle(1);self.assertEqual(self.app.selected,a)
        pinned=self.app.prefs['pin_mini'];self.app.mini.toggle_pin()
        self.assertEqual(bool(self.app.mini.win.attributes('-topmost')),not pinned);self.app.mini.toggle_pin()
        with patch.object(self.app,'choose_source',side_effect=AssertionError('compact Save reuses the remembered source')):self.app.mini.save.invoke()
        self.assertEqual(len(self.app.items),2);self.assertEqual(self.app.selected,b)  # B was the last-used source
        self.app.show_full();self.assertEqual(self.app.view,'full');self.assertEqual(self.app.selected,b)
        self.assertEqual(self.app.content.winfo_manager(),'pack');self.assertEqual(self.app.mini.frame.winfo_manager(),'')
        self.assertEqual(dp.load_prefs(self.app.prefs_path)['view'],'full')
        self.app.toggle_view();self.assertEqual(self.app.view,'mini');self.app.toggle_view();self.assertEqual(self.app.view,'full')
        self.app.choose_theme('light');self.app.show_mini();self.app.choose_theme('dark')
        self.assertEqual(self.app.content.winfo_manager(),'');self.assertEqual(self.app.mini.frame.winfo_manager(),'pack')
    def test_view_and_pin_restore_after_restart(self):
        self.app.show_mini();self.app.mini.toggle_pin();self.app.close()
        self.root=tk.Tk();self.root.withdraw();app=self.make()
        self.assertEqual(app.view,'mini');self.assertEqual(bool(app.mini.win.attributes('-topmost')),app.prefs['pin_mini'])
    def test_offscreen_and_corrupt_preferences_recover(self):
        self.app.close();prefs=dict(dp.PREFS,full=[440,640,-90000,-90000]);path=self.base/'appdata'/'desk-window.json';path.write_text(json.dumps(prefs))
        self.root=tk.Tk();self.root.withdraw();app=self.make();self.root.update_idletasks()
        from desktop_mode import work_areas
        w,h,x,y=[int(v) for v in self.root.geometry().replace('x','+').split('+')]
        self.assertTrue(any(l<=x and t<=y and x+w<=r and y+h<=b for l,t,r,b in work_areas(self.root)),(x,y,w,h))
        app.close();path.write_text('{broken');self.assertEqual(dp.load_prefs(path),dp.PREFS)
        for bad in (dict(dp.PREFS,view='overlay'),dict(dp.PREFS,full=[1,2,3]),dict(dp.PREFS,pin_mini='yes'),dict(dp.PREFS,extra=1)):
            path.write_text(json.dumps(bad));self.assertEqual(dp.load_prefs(path),dp.PREFS)
    def test_close_is_idempotent(self):
        with patch.object(self.root,'destroy') as d:self.app.close();self.app.close();d.assert_called_once()
    def test_theme_persists_and_rebuild_keeps_state(self):
        path=self.save();self.app.show_screen('accounts');self.app.choose_theme('light')
        self.assertEqual(load_theme(self.app.store.base/'theme.json'),'light');self.assertEqual(self.app.selected,path);self.assertEqual(self.app.screen,'accounts')
        self.assertEqual(self.root.cget('bg'),desk_theme.PALETTES['light']['bg'])
        (self.app.store.base/'theme.json').write_text('{"version":1,"theme":"neon"}');self.assertEqual(load_theme(self.app.store.base/'theme.json'),'dark')
    def test_contrast_of_text_on_every_surface(self):
        C=desk_theme.contrast
        for c in desk_theme.PALETTES.values():
            for bg in ('bg','surface','surface2'):self.assertGreaterEqual(C(c['text'],c[bg]),7,bg);self.assertGreaterEqual(C(c['muted'],c[bg]),4.5,bg)
            self.assertGreaterEqual(C(c['accenttext'],c['accent']),4.5);self.assertGreaterEqual(C(c['coraltext'],c['coral']),4.5)
            self.assertGreaterEqual(C(c['disabledtext'],c['disabled']),3);self.assertGreaterEqual(C(c['tabseltext'],c['tabsel']),7)
            self.assertGreaterEqual(C(c['danger'],c['surface2']),4.5);self.assertGreaterEqual(C(c['faint'],c['surface']),3)
        for end in desk_theme.GRADIENT:self.assertGreaterEqual(C('#FFFFFF',end),4.5)
    def test_control_states(self):
        cv=tk.Canvas(self.root,bg='#000000');ui=UI(cv,self.app.look);calls=[]
        made=[RoundButton(ui,'R',30,30,40,'menu',lambda:calls.append(1),'#1A1A1F','#FFFFFF','#26262D'),
              PillButton(ui,'P',10,80,200,48,'Go',lambda:calls.append(1),'#1E2357','#FFFFFF','#283071','check'),
              Toggle(ui,'T',10,150,44,26,False,lambda v:calls.append(v))]
        for w in made:
            item=w.track if isinstance(w,Toggle) else w.bg;fill=lambda:cv.itemcget(item,'fill')
            normal=fill();w.hover(True);self.assertNotEqual(fill(),normal)        # hover
            w.press();w.release();w.hover(False)                                   # click
            self.assertEqual(cv.itemcget(w.ring,'outline'),'');ui.set_focus(w);self.assertNotEqual(cv.itemcget(w.ring,'outline'),'')  # focus ring
            w.set_state('disabled');w.invoke();ui.activate();w.set_state('normal')  # disabled ignores input
        self.assertEqual(calls,[1,1,True])
        self.assertEqual(ui.move(1),'break');self.assertIs(ui.focus,made[0])        # Tab order wraps
        self.app.show_screen('accounts');self.assertEqual(self.app.screen,'accounts');self.app.show_screen('save');self.assertEqual(self.app.screen,'save')
        with self.assertRaises(ValueError):self.app.show_screen('other')
    def test_hover_recolours_without_recreating_items(self):
        # Regression: recreating canvas items under the pointer re-fired Leave/Enter forever (4.0 freeze).
        self.root.update_idletasks()
        for screen in ('save','accounts'):
            self.app.show_screen(screen);cv=self.app.content;before=cv.find_all()
            for c in self.app.ui.controls:
                for step in (lambda:c.hover(True),c.press,lambda:c.hover(False),lambda:setattr(c,'pressed',False)):step()
            self.assertEqual(cv.find_all(),before)
    def test_rendered_card_and_dot_matrix(self):
        png=card_png(60,40,12,'navy','#000000');self.assertTrue(png.startswith(b'\x89PNG'))
        cv=tk.Canvas(self.root);draw_matrix(cv,'240',100,50,2,'#FFFFFF');self.assertGreater(len(cv.find_all()),20)
    def test_motion_respects_reduced_preference(self):
        self.assertIsInstance(desk_theme.reduced_motion(),bool)
        with patch.object(self.root,'attributes') as attr:self.app.motion=False;self.app.fade(self.root);attr.assert_not_called()

class Scaling(unittest.TestCase):
    def test_layout_at_100_125_150_percent(self):
        for scale in (1,1.25,1.5):
            with tempfile.TemporaryDirectory(dir=os.environ.get('NOTEBOOK_TEST_TEMP')) as temp:
                root=tk.Tk();root.withdraw();root.tk.call('tk','scaling',96/72*scale)
                try:
                    app=App(root,m.Store(Path(temp)),Path(temp)/'Config',lambda:None,motion=False);root.update_idletasks()
                    self.assertAlmostEqual(app.minimum[0],400*scale,delta=3*scale);self.assertAlmostEqual(app.minimum[1],680*scale,delta=3*scale)   # tolerate px-rounding at fractional DPI
                    self.assertGreaterEqual(app.content.winfo_reqheight(),1);self.assertLessEqual(app.content.winfo_reqwidth()+2*app.look.px(20),app.minimum[0]+app.look.px(40))
                    def height(ctl):b=app.content.bbox(ctl.bg);return b[3]-b[1]
                    for ctl in (app.more,app.save_btn):self.assertGreaterEqual(height(ctl),round(44*scale))   # comfortable click targets
                    self.assertLessEqual(app.content.bbox(app.save_btn.bg)[2],app.drawn[0])
                    app.show_mini();root.update_idletasks();self.assertLess(app.mini.frame.winfo_reqwidth(),round(470*scale))
                    b=app.mini.frame.bbox(app.mini.apply.bg);self.assertGreaterEqual(b[3]-b[1],round(40*scale))
                    app.close()
                finally:
                    try:root.destroy()
                    except tk.TclError:pass

if __name__=='__main__':unittest.main()
