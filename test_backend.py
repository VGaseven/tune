"""Headless tests for tune_backend (no tkinter, no network, no pywebview). Synthetic VALORANT
config files in a temp dir prove listing works game-open, saved labels surface on accounts, hints
parse, apply copies only the video keys and is undoable, and apply is blocked when the guard fires."""
import tempfile
import unittest
from pathlib import Path
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
        res=self.be.save(self.file(A),'DAISY')
        self.assertFalse(res['replaced']);self.assertGreaterEqual(res['n'],3)
        by={a['account']:a for a in self.be.accounts()}
        self.assertEqual(by[f'{A}-eu']['saved'],'DAISY');self.assertIsNotNone(by[f'{A}-eu']['last_saved'])
        self.assertEqual(len(self.be.profiles()),1)
    def test_apply_copies_only_video_setting_and_is_undoable(self):
        saved=self.be.save(self.file(A),'DAISY')
        out=self.be.apply(saved['path'],self.file(BB))
        self.assertEqual(out['applied'],1);self.assertIsNotNone(out['backup'])
        self.assertIn(b'sg.TextureQuality=3',Path(self.file(BB)).read_bytes())   # 0 -> 3
        self.assertIn(b'ResolutionSizeX=1920',Path(self.file(BB)).read_bytes())  # untouched key kept
    def test_apply_is_noop_when_already_equal(self):
        saved=self.be.save(self.file(A),'DAISY')
        self.be.apply(saved['path'],self.file(BB))
        self.assertEqual(self.be.apply(saved['path'],self.file(BB))['applied'],0)

class Settings(Base):
    def test_account_settings_lists_named_values(self):
        rows=self.be.account_settings(self.file(A))
        names={r['name']:r['value'] for r in rows}
        self.assertEqual(names.get('Textures'),'3');self.assertEqual(names.get('VSync'),'Off')

class Guard(Base):
    def test_apply_blocked_when_guard_reports_game_open(self):
        saved=self.be.save(self.file(A),'X')
        def boom():raise RuntimeError('game open')
        self.be.guard=boom
        with self.assertRaises(RuntimeError):self.be.apply(saved['path'],self.file(BB))

if __name__=='__main__':
    unittest.main()
