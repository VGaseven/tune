"""Headless tests for desk_update (no network, no real Tune.exe): a fake release and fake
downloads in a temp folder prove the checks that decide whether an update is ever installed."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import desk_update as U

NEW=b'MZ'+b'n'*1_200_000
GOOD=hashlib.sha256(NEW).hexdigest()
BASE='https://github.com/VGaseven/tune/releases/download/v9.9/'
def release(exe_url=BASE+'Tune.exe',size=len(NEW),tag='v9.9'):
    return {'tag_name':tag,'assets':[{'name':'Tune.exe','browser_download_url':exe_url,'size':size},
                                     {'name':'Tune.exe.sha256.txt','browser_download_url':BASE+'Tune.exe.sha256.txt','size':66}]}

class Update(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.exe=Path(self.tmp.name)/'Tune.exe';self.exe.write_bytes(b'MZ old version')
    def run_update(self,rel=None,body=NEW,sums=GOOD.upper().encode()+b'\r\n',newer=lambda t:True):
        def fetch(url,dest,agent,progress=None):
            Path(dest).write_bytes(body);progress and progress(len(body),len(body));return hashlib.sha256(body).hexdigest()
        return U.update('Tune/test',exe=self.exe,get=lambda url,agent:rel or release(),fetch=fetch,newer=newer,read=lambda url,agent:sums)
    def leftovers(self):return sorted(p.name for p in self.exe.parent.iterdir())

    def test_verified_update_swaps_in_new_exe_and_keeps_old_for_cleanup(self):
        self.assertEqual(self.run_update(),self.exe)
        self.assertEqual(self.exe.read_bytes(),NEW)
        self.assertEqual(self.leftovers(),['Tune.exe','Tune.old.exe'])
        U.cleanup(self.exe);self.assertEqual(self.leftovers(),['Tune.exe'])
    def test_checksum_mismatch_changes_nothing(self):
        with self.assertRaisesRegex(RuntimeError,'checksum'):self.run_update(sums=b'0'*64)
        self.assertEqual(self.exe.read_bytes(),b'MZ old version');self.assertEqual(self.leftovers(),['Tune.exe'])
    def test_link_from_elsewhere_is_refused(self):
        with self.assertRaisesRegex(RuntimeError,"own GitHub"):self.run_update(rel=release(exe_url='https://evil.example/Tune.exe'))
        self.assertEqual(self.exe.read_bytes(),b'MZ old version')
    def test_incomplete_download_is_refused(self):
        with self.assertRaisesRegex(RuntimeError,'incomplete'):self.run_update(body=b'<html>not found</html>')
        self.assertEqual(self.leftovers(),['Tune.exe'])
    def test_not_newer_is_refused(self):
        with self.assertRaisesRegex(RuntimeError,'latest'):self.run_update(newer=lambda t:False)
    def test_missing_assets_refused(self):
        with self.assertRaises(RuntimeError):U.pick_assets({'assets':[]})
    def test_checksum_file_formats(self):
        self.assertEqual(U.expected_hash(GOOD.upper().encode()+b'\r\n'),GOOD)
        self.assertEqual(U.expected_hash(('﻿'+GOOD.upper()+'\r\n').encode('utf-16-le')),GOOD)
        with self.assertRaises(RuntimeError):U.expected_hash(b'nope')
    def test_install_rolls_back_if_swap_fails(self):
        new=self.exe.with_name('Tune.exe.download');new.write_bytes(NEW)
        real=Path.replace
        def flaky(self_,target):
            if self_.name=='Tune.exe.download':raise OSError('locked')
            return real(self_,target)
        with mock.patch.object(Path,'replace',flaky),self.assertRaises(OSError):U.install(new,self.exe)
        self.assertEqual(self.exe.read_bytes(),b'MZ old version')

class Restart(unittest.TestCase):
    def test_new_version_starts_fresh_not_inside_the_old_one(self):
        env=U.clean_env({'PATH':'x','_MEIPASS2':'C:/old','_PYI_APPLICATION_HOME_DIR':'C:/old','_PYI_PARENT_PROCESS_LEVEL':'1'})
        self.assertEqual(env['PATH'],'x');self.assertEqual(env['PYINSTALLER_RESET_ENVIRONMENT'],'1')
        self.assertFalse([k for k in env if k.startswith(('_PYI','_MEIPASS'))])
        seen={}
        U.restart(Path('C:/apps/Tune.exe'),popen=lambda args,**kw:seen.update(args=args,**kw))
        self.assertEqual(seen['args'],[str(Path('C:/apps/Tune.exe'))]);self.assertEqual(seen['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')

class Handoff(unittest.TestCase):
    def test_new_window_signals_and_old_one_sees_it(self):
        with tempfile.TemporaryDirectory() as d:
            flag=Path(d)/'tune-handoff-1.ready';env={U.HANDOFF:str(flag)}
            self.assertFalse(U.wait_ready(flag,timeout=0.05,sleep=lambda s:None))
            self.assertTrue(U.signal_ready(env));self.assertNotIn(U.HANDOFF,env)
            self.assertTrue(U.wait_ready(flag,timeout=1));self.assertFalse(flag.exists())
            self.assertFalse(U.signal_ready({}));self.assertFalse(U.signal_ready({U.HANDOFF:str(Path(d)/'evil.exe')}))
    def test_geometry_passes_only_sane_values(self):
        self.assertEqual(U.geometry({U.GEOMETRY:'100,50,1140,800'}),(100,50,1140,800))
        for bad in ('','1,2,3','0,0,10,10','a,b,c,d'):self.assertIsNone(U.geometry({U.GEOMETRY:bad}))
    def test_restart_passes_handoff_to_the_new_tune(self):
        seen={};U.restart(Path('C:/apps/Tune.exe'),popen=lambda a,**kw:seen.update(kw),extra={U.HANDOFF:'x.ready',U.GEOMETRY:'1,2,900,700'})
        self.assertEqual(seen['env'][U.HANDOFF],'x.ready');self.assertEqual(seen['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')

class Icon(unittest.TestCase):
    def test_app_icon_is_a_valid_multi_size_ico(self):
        import struct
        raw=(Path(__file__).resolve().parent/'assets'/'tune.ico').read_bytes()
        reserved,kind,n=struct.unpack('<HHH',raw[:6]);self.assertEqual((reserved,kind),(0,1))
        sizes=sorted(raw[6+16*i] or 256 for i in range(n));self.assertEqual(sizes[0],16);self.assertEqual(sizes[-1],256)
        for i in range(n):
            ln,off=struct.unpack('<II',raw[6+16*i+8:6+16*i+16]);self.assertEqual(raw[off:off+8],bytes([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]))

if __name__=='__main__':
    unittest.main()
