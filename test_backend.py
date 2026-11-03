"""Headless tests for tune_backend (no tkinter, no network, no pywebview). Synthetic VALORANT
config files in a temp dir prove listing works game-open, saved labels surface on accounts, hints
parse, apply copies only the video keys and is undoable, and apply is blocked when the guard fires."""
import os
import tempfile
import unittest
from pathlib import Path
import capture_model as model
import tune_backend as B

A='0aec6e15-90a1-4b2c-8d3e-111111111111'
BB='21c9f7c6-a7b2-4c3d-9e4f-222222222222'
FIX=(b'; synthetic only\r\n[/Script/ShooterGame.ShooterGameUserSettings]\r\n'
     b'bUseVSync=False\r\nFrameRateLimit=0.000000\r\nResolutionSizeX=1920\r\nResolutionSizeY=1080\r\n'
     b'[ScalabilityGroups]\r\nsg.TextureQuality=3\r\nsg.ShadowQuality=2\r\n')
def fixture(tex):return FIX.replace(b'sg.TextureQuality=3',b'sg.TextureQuality='+str(tex).encode())

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.config=self.base/'Config'
        for uid,tex in ((A,3),(BB,0)):
            p=self.config/f'{uid}-eu'/'Windows'/'GameUserSettings.ini';p.parent.mkdir(parents=True);p.write_bytes(fixture(tex))
        (self.base/'Logs').mkdir()
        (self.base/'Logs'/'ShooterGame.log').write_text(f'LogShooterGameUserSettings: Logged in user changed: {A}\n',encoding='utf-8')
        self.be=B.Backend(self.config,store_base=self.base/'app',guard=lambda:None)
    def file(self,uid):return str(self.config/f'{uid}-eu'/'Windows'/'GameUserSettings.ini')
    def ref(self,uid):return model.source_id(Path(self.file(uid)))

class Accounts(Base):
    def test_lists_both_with_signed_in_region_and_hints(self):
        by={a['account']:a for a in self.be.accounts()}
        self.assertEqual(set(by),{f'{A}-eu',f'{BB}-eu'})
        self.assertTrue(by[f'{A}-eu']['signed_in']);self.assertFalse(by[f'{BB}-eu']['signed_in'])
        self.assertEqual(by[f'{A}-eu']['region'],'eu');self.assertEqual(by[f'{A}-eu']['puuid'],A)
        self.assertEqual(by[f'{A}-eu']['hints']['resolution'],'1920×1080')
        self.assertEqual(by[f'{A}-eu']['hints']['vsync'],'Off');self.assertIn('fps',by[f'{A}-eu']['hints'])
        self.assertIsNone(by[f'{A}-eu']['saved'])   # nothing saved yet

class SaveApply(Base):
    def test_save_surfaces_label_on_account(self):
        res=self.be.save(self.ref(A),'DAISY')
        self.assertFalse(res['replaced']);self.assertGreaterEqual(res['n'],3)
        by={a['account']:a for a in self.be.accounts()}
        self.assertEqual(by[f'{A}-eu']['saved'],'DAISY');self.assertIsNotNone(by[f'{A}-eu']['last_saved'])
        self.assertEqual(len(self.be.profiles()),1)
    def test_apply_copies_only_video_setting_and_is_undoable(self):
        saved=self.be.save(self.ref(A),'DAISY')
        out=self.be.apply(Path(saved['path']).name,self.ref(BB))
        self.assertEqual(out['applied'],1);self.assertIsNotNone(out['backup'])
        self.assertIn(b'sg.TextureQuality=3',Path(self.file(BB)).read_bytes())   # 0 -> 3
        self.assertIn(b'ResolutionSizeX=1920',Path(self.file(BB)).read_bytes())  # untouched key kept
    def test_apply_is_noop_when_already_equal(self):
        saved=self.be.save(self.ref(A),'DAISY')
        pid=Path(saved['path']).name
        self.be.apply(pid,self.ref(BB))
        self.assertEqual(self.be.apply(pid,self.ref(BB))['applied'],0)

RIOT=('[Settings]\r\nEAresFloatSettingName::MouseSensitivity={s}\r\nEAresBoolSettingName::HasSeenSettingsTutorial={seen}\r\nEAresStringSettingName::CrosshairProfileName={x}\r\nLocalSettingsVersion=7\r\n')
class Master(Base):
    def setUp(self):
        super().setUp()
        for uid,s,seen,x in ((A,'0.163','True','frog'),(BB,'0.5','False','old')):
            Path(self.file(uid)).with_name('RiotUserSettings.ini').write_text(RIOT.format(s=s,seen=seen,x=x),encoding='utf-8',newline='')
    def riot(self,uid):return Path(self.file(uid)).with_name('RiotUserSettings.ini').read_text(encoding='utf-8')
    def test_defaults_to_signed_in_and_can_be_changed(self):
        self.assertEqual(self.be.master_ref(),self.ref(A))
        self.be.set_master(self.ref(BB));self.assertEqual(self.be.master_ref(),self.ref(BB))
        self.assertTrue({a['ref']:a for a in self.be.accounts()}[self.ref(BB)]['is_master'])
    def test_apply_master_copies_prefs_and_video_verifies_and_keeps_state_flags(self):
        self.assertFalse(self.be.sync_report(self.ref(BB))['in_sync'])
        out=self.be.apply_master(self.ref(BB))
        self.assertTrue(out['verified']);self.assertGreaterEqual(out['changed'],3)
        r=self.riot(BB)
        self.assertIn('MouseSensitivity=0.163',r);self.assertIn('CrosshairProfileName=frog',r)
        self.assertIn('HasSeenSettingsTutorial=False',r)                 # account-state flag untouched
        self.assertIn(b'sg.TextureQuality=3',Path(self.file(BB)).read_bytes())
        self.assertIn('MouseSensitivity=0.163',self.riot(A))               # main only read
        rep=self.be.sync_report(self.ref(BB));self.assertTrue(rep['in_sync']);self.assertTrue(rep['applied_at'])
    def test_restore_puts_files_back(self):
        before=self.riot(BB);self.be.apply_master(self.ref(BB))
        self.be.restore_backup(self.ref(BB));self.assertEqual(self.riot(BB),before)
    def test_refuses_main_as_target_and_when_game_open(self):
        with self.assertRaises(ValueError):self.be.apply_master(self.ref(A))
        def busy():raise RuntimeError('open')
        be=B.Backend(self.config,store_base=self.base/'app',guard=busy)
        with self.assertRaises(RuntimeError):be.apply_master(self.ref(BB))
        self.assertIn('MouseSensitivity=0.5',self.riot(BB))
    def test_missing_target_file_is_created_from_main(self):
        Path(self.file(BB)).with_name('RiotUserSettings.ini').unlink()
        self.assertTrue(self.be.apply_master(self.ref(BB))['verified'])
        self.assertIn('MouseSensitivity=0.163',self.riot(BB))
    def test_blank_video_stub_gets_main_video_file(self):
        Path(self.file(BB)).write_bytes(bytes([13,10]))
        out=self.be.apply_master(self.ref(BB));self.assertTrue(out['verified']);self.assertIsNone(out['video_note'])
        self.assertEqual(Path(self.file(BB)).read_bytes(),Path(self.file(A)).read_bytes())
    def test_master_summary_reads_sens(self):
        m=self.be.master();self.assertEqual(m['sens'],0.163);self.assertEqual(m['game_settings'],2)

class Settings(Base):
    def test_account_settings_lists_named_values(self):
        rows=self.be.account_settings(self.ref(A))
        names={r['name']:r['value'] for r in rows}
        self.assertEqual(names.get('Textures'),'3');self.assertEqual(names.get('VSync'),'Off')

class Bulk(Base):
    def test_apply_to_all_and_share_roundtrip(self):
        saved=self.be.save(self.ref(A),"MAIN");pid=Path(saved["path"]).name
        out=self.be.apply_to_all(pid)
        self.assertEqual(out["targets"],1);self.assertEqual(out["changed"],1)   # only B differs
        self.assertIn(b"sg.TextureQuality=3",Path(self.file(BB)).read_bytes())
        code=self.be.share_code(pid)
        self.assertIn("presetdesk-share",code)
        imp=self.be.share_import(code)
        self.assertGreaterEqual(imp["n"],2);self.assertEqual(imp["label"],"MAIN")

class RankKey(Base):
    def setUp(self):
        super().setUp();self._old=os.environ.pop('TUNE_RANK_KEY',None)
    def tearDown(self):
        if self._old is not None:os.environ['TUNE_RANK_KEY']=self._old
    def test_set_status_and_clear(self):
        self.assertFalse(self.be.rank_key_status()['set'])
        with self.assertRaises(ValueError):self.be.set_rank_key('')
        self.be.set_rank_key('HDEV-1234-5678-ABCD-0000')
        self.assertTrue(self.be.rank_key_status()['set'])
        self.be.clear_rank_key();self.assertFalse(self.be.rank_key_status()['set'])

class Guard(Base):
    def test_apply_blocked_when_guard_reports_game_open(self):
        saved=self.be.save(self.ref(A),'X')
        def boom():raise RuntimeError('game open')
        self.be.guard=boom
        with self.assertRaises(RuntimeError):self.be.apply(Path(saved['path']).name,self.ref(BB))

if __name__=='__main__':
    unittest.main()
