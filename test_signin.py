"""Headless tests for desk_signin (one-click switching). Fake Riot Client and TcNo folders in a temp
dir and fake process lists - the real Riot Client, TcNo, their files and processes are never touched."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
import desk_signin as S

A='a'*64;B='b'*64
class Fake:
    def __init__(self):self.running=[];self.killed=0;self.launched=0
    def procs(self):return list(self.running)
    def kill(self):self.killed+=1;self.running=[n for n in self.running if n not in S.RIOT_PROCS]
    def launch(self):self.launched+=1

class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.root=base/'Riot Client';self.tc=base/'TcNo'
        (self.root/'Data'/'Cookies').mkdir(parents=True);(self.root/'Config').mkdir()
        (self.root/'Config'/'ClientConfiguration.json').write_text('{"big":1}',encoding='utf-8')
        self.f=Fake()
        self.s=S.SignIns(base/'app',root=self.root,procs=self.f.procs,kill=self.f.kill,
                         seal=lambda b:b[::-1],unseal=lambda b:b[::-1],sleep=lambda s:None,tcno=self.tc)
    def sign(self,who,session=True):
        d=self.root/'Data';(d/'RiotGamesPrivateSettings.yaml').write_text(f'tdid: {who}\n',encoding='utf-8')
        (d/'Cookies'/'Cookies').write_bytes(f'cookie-{who}'.encode());(d/'Cookies'/'Cookies-journal').write_bytes(b'j')
        ses=d/'Sessions';ses.mkdir(exist_ok=True)
        for old in ses.glob('*'):old.unlink()
        if session:(ses/f'{who}.session').write_text(who,encoding='utf-8')
        (self.root/'Config'/'RiotClientSettings.yaml').write_text(f'region: {who}\n',encoding='utf-8')
    def state(self):
        d=self.root/'Data'
        return {'yaml':(d/'RiotGamesPrivateSettings.yaml').read_text(encoding='utf-8'),'cookie':(d/'Cookies'/'Cookies').read_bytes(),
                'sessions':sorted(p.name for p in (d/'Sessions').glob('*')),'cfg':(self.root/'Config'/'RiotClientSettings.yaml').read_text(encoding='utf-8')}

class SignIns(Base):
    def test_remember_then_switch_restores_the_whole_signin_like_tcno(self):
        self.sign('alice');self.s.remember(A);self.sign('bob');self.s.remember(B)
        self.assertEqual(set(self.s.saved()),{A,B})
        self.assertNotIn(b'alice',(self.s.dir/f'{A}.bin').read_bytes())     # stored sealed, not as plain text
        self.f.running=['riotclientservices.exe','riot client.exe','explorer.exe']
        self.s.switch(A,self.f.launch)
        self.assertEqual(self.state(),{'yaml':'tdid: alice\n','cookie':b'cookie-alice','sessions':['alice.session'],'cfg':'region: alice\n'})
        self.assertEqual((self.f.killed,self.f.launched),(1,1))
        self.assertTrue((self.root/'Config'/'ClientConfiguration.json').exists())   # unrelated Riot files are left alone
    def test_files_from_the_previous_account_do_not_leak(self):
        self.sign('alice',session=False);self.s.remember(A);self.sign('bob')
        self.s.switch(A,self.f.launch);self.assertEqual(self.state()['sessions'],[])
    def test_refuses_while_valorant_runs_and_changes_nothing(self):
        self.sign('alice');self.s.remember(A);self.sign('bob')
        self.f.running=['valorant-win64-shipping.exe','riotclientservices.exe']
        with self.assertRaisesRegex(RuntimeError,'Quit VALORANT'):self.s.switch(A,self.f.launch)
        self.assertEqual(self.state()['yaml'],'tdid: bob\n');self.assertEqual((self.f.killed,self.f.launched),(0,0))
    def test_riot_client_that_wont_close_is_reported(self):
        self.sign('alice');self.s.remember(A);self.s.kill=lambda:None
        self.f.running=['riotclientservices.exe']
        with self.assertRaisesRegex(RuntimeError,'did not close'):self.s.switch(A,self.f.launch)
        self.assertEqual(self.f.launched,0)
    def test_needs_stay_signed_in_file(self):
        with self.assertRaisesRegex(RuntimeError,'Stay signed in'):self.s.remember(A)
    def test_keep_fresh_only_when_changed_and_forget(self):
        self.sign('alice');self.s.remember(A)
        self.assertFalse(self.s.keep_fresh(A))
        self.sign('alice2');self.assertTrue(self.s.keep_fresh(A))
        self.sign('bob');self.s.switch(A,self.f.launch);self.assertEqual(self.state()['yaml'],'tdid: alice2\n')
        self.assertEqual(self.s.forget()['forgotten'],1);self.assertEqual(self.s.saved(),{})
        with self.assertRaises(ValueError):self.s.switch(A,self.f.launch)
    def test_old_v73_copies_still_switch(self):
        payload={'format':S.FORMAT,'v':1,'files':{'RiotGamesPrivateSettings.yaml':b'tdid: old\n'.hex(),'Cookies/Cookies':b'c-old'.hex()}}
        self.s.dir.mkdir(parents=True);(self.s.dir/f'{A}.bin').write_bytes(json.dumps(payload).encode()[::-1])
        self.sign('bob');self.s.switch(A,self.f.launch);self.assertEqual(self.state()['yaml'],'tdid: old\n')
    def test_switch_keeps_the_unsaved_current_signin_and_can_go_back(self):
        self.sign('alice');self.s.remember(A);self.sign('never-saved')
        self.s.switch(A,self.f.launch);self.assertEqual(self.state()['yaml'],'tdid: alice\n')
        self.assertTrue(self.s.has_previous())
        self.s.undo_switch(self.f.launch);self.assertEqual(self.state()['yaml'],'tdid: never-saved\n')
        self.s.forget();self.assertFalse(self.s.has_previous())
        with self.assertRaises(ValueError):self.s.undo_switch(self.f.launch)
    def test_bad_ref_rejected(self):
        with self.assertRaises(ValueError):self.s.remember('../../evil')

class TcNo(Base):
    def tcno(self,name,who,layout='new'):
        d=self.tc/name
        if layout=='new':                   # what TcNo keeps today: a copy of the whole Data folder under this name
            data=d/'RiotClientPrivateSettings.yaml';(data/'Cookies').mkdir(parents=True);(data/'Sessions').mkdir()
            (data/'RiotGamesPrivateSettings.yaml').write_text(f'tdid: {who}\n',encoding='utf-8')
            (data/'Cookies'/'Cookies').write_bytes(f'cookie-{who}'.encode());(data/'Sessions'/f'{who}.session').write_text(who,encoding='utf-8')
            cfg=d/'RiotClientSettings.yaml';cfg.mkdir();(cfg/'RiotClientSettings.yaml').write_text(f'region: {who}\n',encoding='utf-8')
            (cfg/'ClientConfiguration.json').write_text('{}',encoding='utf-8')
        (d/'TcNoAccSwitcher-ID.instance').parent.mkdir(parents=True,exist_ok=True);(d/'TcNoAccSwitcher-ID.instance').write_text('x',encoding='utf-8')
    def test_lists_and_imports_tcno_accounts(self):
        self.tcno('hii account','hii');self.tcno('IRON','iron');self.tcno('empty','x',layout='none')
        (self.tc/'Shortcuts').mkdir()
        self.assertEqual(self.s.tcno_accounts(),['hii account','IRON'])
        self.s.import_tcno('hii account',A);self.sign('bob')
        self.s.switch(A,self.f.launch)
        self.assertEqual(self.state(),{'yaml':'tdid: hii\n','cookie':b'cookie-hii','sessions':['hii.session'],'cfg':'region: hii\n'})
        self.assertFalse((self.root/'TcNoAccSwitcher-ID.instance').exists())
    def test_unknown_or_escaping_names_are_refused(self):
        self.tcno('IRON','iron')
        for bad in ('nope','../IRON','..'):
            with self.assertRaises(ValueError):self.s.import_tcno(bad,A)
    def test_no_tcno_installed(self):self.assertEqual(self.s.tcno_accounts(),[])

@unittest.skipUnless(sys.platform=='win32','DPAPI is Windows-only')
class Dpapi(unittest.TestCase):
    def test_round_trip_and_tamper(self):
        sealed=S.protect(b'secret-signin');self.assertNotIn(b'secret-signin',sealed)
        self.assertEqual(S.unprotect(sealed),b'secret-signin')
        with self.assertRaises(RuntimeError):S.unprotect(sealed[:-8]+b'x'*8)

class BackendGate(unittest.TestCase):
    def test_remember_rules(self):
        import test_backend as TB
        import tune_backend as BK
        t=TB.Master('test_defaults_to_signed_in_and_can_be_changed');t.setUp();self.addCleanup(t.doCleanups)
        root=t.base/'Riot';(root/'Data').mkdir(parents=True);(root/'Data'/'RiotGamesPrivateSettings.yaml').write_text('x',encoding='utf-8')
        mk=lambda running:BK.Backend(t.config,store_base=t.base/'app',guard=lambda:None,game_running=lambda:running,
                                     signins=S.SignIns(t.base/'app',root=root,seal=bytes,unseal=bytes,tcno=t.base/'none'))
        with self.assertRaisesRegex(RuntimeError,'Sign in to this account'):mk(False).remember_signin(t.ref(TB.BB))
        self.assertIn(t.ref(TB.BB),mk(False).remember_signin(t.ref(TB.BB),confirmed=True)['ref'])     # user confirmed, game closed
        with self.assertRaisesRegex(RuntimeError,'different account'):mk(True).remember_signin(t.ref(TB.BB),confirmed=True)  # A is in game
        be=mk(True);be.remember_signin(t.ref(TB.A));self.assertEqual(set(be.signin_saved()),{t.ref(TB.A),t.ref(TB.BB)})
        self.assertEqual(be.import_tcno([{'name':'missing','ref':t.ref(TB.A)}])['imported'],0)

if __name__=='__main__':
    unittest.main()
