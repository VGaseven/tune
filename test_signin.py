"""Headless tests for desk_signin (one-click switching). Fake Riot Client files in a temp folder and
fake process lists - the real Riot Client, its files and processes are never touched."""
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

class SignIns(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.data=base/'Riot'/'Data';(self.data/'Cookies').mkdir(parents=True)
        self.f=Fake()
        self.s=S.SignIns(base/'app',data_dir=self.data,procs=self.f.procs,kill=self.f.kill,
                         seal=lambda b:b[::-1],unseal=lambda b:b[::-1],sleep=lambda s:None)
    def sign(self,who,cookies=True):
        (self.data/'RiotGamesPrivateSettings.yaml').write_text(f'session: {who}\n',encoding='utf-8')
        if cookies:(self.data/'Cookies'/'Cookies').write_bytes(f'cookie-{who}'.encode())
        else:(self.data/'Cookies'/'Cookies').unlink(missing_ok=True)
    def yaml(self):return (self.data/'RiotGamesPrivateSettings.yaml').read_text(encoding='utf-8')

    def test_remember_then_switch_restores_that_accounts_signin(self):
        self.sign('alice');self.s.remember(A);self.sign('bob');self.s.remember(B)
        self.assertEqual(set(self.s.saved()),{A,B})
        self.assertNotIn(b'alice',(self.s.dir/f'{A}.bin').read_bytes())     # stored sealed, not as plain text
        (self.data/'Cookies'/'Cookies-journal').write_bytes(b'stale')
        self.f.running=['riotclientservices.exe','riot client.exe','explorer.exe']
        self.s.switch(A,self.f.launch)
        self.assertEqual(self.yaml(),'session: alice\n');self.assertEqual((self.data/'Cookies'/'Cookies').read_bytes(),b'cookie-alice')
        self.assertFalse((self.data/'Cookies'/'Cookies-journal').exists())
        self.assertEqual((self.f.killed,self.f.launched),(1,1))
    def test_refuses_while_valorant_runs_and_changes_nothing(self):
        self.sign('alice');self.s.remember(A);self.sign('bob')
        self.f.running=['valorant-win64-shipping.exe','riotclientservices.exe']
        with self.assertRaisesRegex(RuntimeError,'Quit VALORANT'):self.s.switch(A,self.f.launch)
        self.assertEqual(self.yaml(),'session: bob\n');self.assertEqual((self.f.killed,self.f.launched),(0,0))
    def test_riot_client_that_wont_close_is_reported(self):
        self.sign('alice');self.s.remember(A);self.f.kill=lambda:None;self.s.kill=self.f.kill
        self.f.running=['riotclientservices.exe']
        with self.assertRaisesRegex(RuntimeError,'did not close'):self.s.switch(A,self.f.launch)
        self.assertEqual(self.f.launched,0)
    def test_cookies_from_previous_account_do_not_leak(self):
        self.sign('alice',cookies=False);self.s.remember(A);self.sign('bob')
        self.s.switch(A,self.f.launch)
        self.assertFalse((self.data/'Cookies'/'Cookies').exists());self.assertEqual(self.yaml(),'session: alice\n')
    def test_needs_stay_signed_in_file(self):
        with self.assertRaisesRegex(RuntimeError,'Stay signed in'):self.s.remember(A)
    def test_keep_fresh_only_when_changed_and_forget(self):
        self.sign('alice');self.s.remember(A)
        self.assertFalse(self.s.keep_fresh(A))
        self.sign('alice-rotated');self.assertTrue(self.s.keep_fresh(A))
        self.sign('bob');self.s.switch(A,self.f.launch);self.assertEqual(self.yaml(),'session: alice-rotated\n')
        self.assertEqual(self.s.forget()['forgotten'],1);self.assertEqual(self.s.saved(),{})
        with self.assertRaises(ValueError):self.s.switch(A,self.f.launch)
    def test_bad_ref_rejected(self):
        with self.assertRaises(ValueError):self.s.remember('../../evil')

@unittest.skipUnless(sys.platform=='win32','DPAPI is Windows-only')
class Dpapi(unittest.TestCase):
    def test_round_trip_and_tamper(self):
        sealed=S.protect(b'secret-signin');self.assertNotIn(b'secret-signin',sealed)
        self.assertEqual(S.unprotect(sealed),b'secret-signin')
        with self.assertRaises(RuntimeError):S.unprotect(sealed[:-8]+b'x'*8)

class BackendGate(unittest.TestCase):
    def test_remember_only_while_in_game_on_that_account(self):
        import test_backend as TB
        import tune_backend as BK
        t=TB.Master('test_defaults_to_signed_in_and_can_be_changed');t.setUp();self.addCleanup(t.doCleanups)
        data=t.base/'RiotData';data.mkdir();(data/'RiotGamesPrivateSettings.yaml').write_text('x',encoding='utf-8')
        mk=lambda running:BK.Backend(t.config,store_base=t.base/'app',guard=lambda:None,game_running=lambda:running,
                                     signins=S.SignIns(t.base/'app',data_dir=data,seal=bytes,unseal=bytes))
        with self.assertRaisesRegex(RuntimeError,'Start VALORANT'):mk(False).remember_signin(t.ref(TB.A))
        with self.assertRaisesRegex(RuntimeError,'Start VALORANT'):mk(True).remember_signin(t.ref(TB.BB))   # A is the one in game
        be=mk(True);be.remember_signin(t.ref(TB.A));self.assertEqual(list(be.signin_saved()),[t.ref(TB.A)])

if __name__=='__main__':
    unittest.main()
