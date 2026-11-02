import copy
import tempfile
import os
from pathlib import Path
import unittest
import capture_model as m
import sensitivity_reference as s
from test_capture import FIXTURE

RAW=b'[Settings]\r\nEAresFloatSettingName::MouseSensitivity=0.250000000\r\nEAresFloatSettingName::MouseSensitivityADS=0.8\r\nEAresFloatSettingName::MouseSensitivityZoomed=1.0\r\nPrivateUnrelated=never export\r\n'

class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('NOTEBOOK_TEST_TEMP'));self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'Config';self.path=self.root/'fixture'/'Windows'/'GameUserSettings.ini';self.path.parent.mkdir(parents=True);self.path.write_bytes(FIXTURE)
        self.sibling=self.path.with_name('RiotUserSettings.ini');self.sibling.write_bytes(RAW)
    def capture(self):return m.capture(self.path,'Fixture',self.root,lambda:None)
    def test_capture_actual_reference_with_provenance(self):
        data=self.capture();m.validate_profile(data)
        self.assertEqual(len(data['reference']['values']),3)
        self.assertEqual(data['reference']['source_sha256'],m.sha(RAW))
        self.assertNotIn('PrivateUnrelated',str(data));self.assertEqual(self.sibling.read_bytes(),RAW)
    def test_missing_values_do_not_default_or_search_other_folders(self):
        self.sibling.unlink();data=self.capture();self.assertNotIn('reference',data)
        other=self.root/'other'/'Windows';other.mkdir(parents=True);(other/'RiotUserSettings.ini').write_bytes(RAW)
        self.assertNotIn('reference',self.capture())
    def test_unknown_fields_unsafe_paths_and_invalid_values_rejected(self):
        data=self.capture()
        for key,value in [('path','../secret'),('values',{'EAresFloatSettingName::MouseSensitivity':'NaN'}),('values',{'unknown':'1'})]:
            bad=copy.deepcopy(data);bad['reference'][key]=value
            with self.assertRaises(ValueError):m.validate_profile(bad)
    def test_duplicate_and_invalid_values_fail_closed(self):
        for raw in (RAW+ b'EAresFloatSettingName::MouseSensitivity=1\n',RAW.replace(b'0.250000000',b'NaN'),RAW+b'[Settings]\n'):
            with self.assertRaises(ValueError):s.parse(raw)
    def test_transfer_never_includes_reference_keys(self):
        data=self.capture();before=self.sibling.read_bytes()
        raw,delta=m.preview(self.path,data,self.root,lambda:None)
        self.assertTrue(all(k in m.SECTIONS for k,a,b in delta))
        m.apply(self.path,data['settings'],raw,Path(self.temp.name)/'backups',self.root,lambda:None)
        self.assertEqual(self.sibling.read_bytes(),before)
    def test_legacy_profile_and_repeat_capture(self):
        one=self.capture();two=self.capture();self.assertEqual(one['reference'],two['reference'])
        del one['reference'];m.validate_profile(one)
    def test_reference_changed_during_capture_rejected(self):
        calls=[]
        def guard():
            calls.append(1)
            if len(calls)==2:self.sibling.write_bytes(RAW.replace(b'0.250000000',b'0.2'))
        with self.assertRaises(ValueError):m.capture(self.path,'Fixture',self.root,guard)

if __name__=='__main__':unittest.main()
