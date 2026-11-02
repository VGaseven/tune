import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import capture_model as m

FIXTURE=b'; synthetic only\r\n[/Script/ShooterGame.ShooterGameUserSettings]\r\nbUseVSync=False\r\nFrameRateLimit=0.000000\r\nResolutionSizeX=1920\r\nSyntheticAccountField=keep-me\r\n[ScalabilityGroups]\r\nsg.TextureQuality=3\r\nsg.ShadowQuality=2\r\nUnknownFutureSetting=keep\r\n'

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('NOTEBOOK_TEST_TEMP'));self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'Config'
        self.source=self.root/'source-fixture'/'WindowsClient'/'GameUserSettings.ini'
        self.target=self.root/'target-fixture'/'WindowsClient'/'GameUserSettings.ini'
        for p in (self.source,self.target):p.parent.mkdir(parents=True);p.write_bytes(FIXTURE)
        self.guard=lambda:None
        self.store=m.Store(self.base/'appdata')
        self.profile=m.capture(self.source,'My label',self.root,self.guard)
    def apply(self,values,raw=None):return m.apply(self.target,values,raw or self.target.read_bytes(),self.store.base/'backups',self.root,self.guard)
    def test_capture_one_action_actual_values_and_provenance(self):
        path=self.store.save(self.profile)
        saved=m.import_profile(path)
        self.assertEqual(saved['settings']['sg.TextureQuality'],'3')
        self.assertEqual(saved['settings']['bUseVSync'],'False')
        self.assertEqual(saved['provenance']['source_sha256'],m.sha(FIXTURE))
        self.assertEqual(saved['provenance']['label_source'],'user-assigned')
        self.assertEqual(self.source.read_bytes(),FIXTURE)
        self.assertNotIn('SyntheticAccountField',path.read_text())
        self.assertNotIn(str(self.source),path.read_text())
    def test_no_defaults_for_missing_sensitivity(self):
        self.assertNotIn('sensitivity',self.profile['settings'])
        self.assertIn('Not present',self.profile['availability']['sensitivity'])
    def test_unsupported_sensitivity_not_copied(self):
        self.source.write_bytes(FIXTURE+b'MouseSensitivity=0.5\r\n')
        data=m.capture(self.source,'Label',self.root,self.guard)
        self.assertIn('unsupported',data['availability']['sensitivity'])
        self.assertNotIn('MouseSensitivity',data['settings'])
    def test_empty_label_and_empty_capture_rejected(self):
        for label in ['', ' ', 'a\nb']:
            with self.assertRaises(ValueError):m.capture(self.source,label,self.root,self.guard)
        with self.assertRaises(ValueError):m.parse(b'[/Script/ShooterGame.ShooterGameUserSettings]\r\n')
    def test_directory_blank_and_external_targets_rejected(self):
        external=self.base/'GameUserSettings.ini';external.write_bytes(FIXTURE)
        for p in ['', '.', self.root,external]:
            with self.subTest(path=p),self.assertRaises(ValueError):m.validate_target(p,self.root)
    def test_discovery_does_not_infer_active_account(self):
        paths=m.discover(self.root,self.guard)
        self.assertEqual(paths,sorted(paths,key=lambda p:str(p).lower()))
        self.assertEqual(len(paths),2)
    def test_merge_preserves_unknown_identity_and_resolution(self):
        self.assertEqual(m.merge(FIXTURE,{'sg.TextureQuality':'0'}),FIXTURE.replace(b'sg.TextureQuality=3',b'sg.TextureQuality=0'))
    def test_missing_target_key_rejected(self):
        with self.assertRaises(ValueError):m.merge(FIXTURE,{'sg.ReflectionQuality':'1'})
    def test_invalid_value_and_duplicate_rejected(self):
        for value in ['4','-1','0\nInjected=1',True]:
            with self.assertRaises(ValueError):m.merge(FIXTURE,{'sg.TextureQuality':value})
        with self.assertRaises(ValueError):m.parse(FIXTURE+b'sg.TextureQuality=1\r\n')
    def test_encoding_preserved(self):
        for enc,bom in [('utf-8',b''),('utf-8-sig',b''),('utf-16-le',b'\xff\xfe'),('utf-16-be',b'\xfe\xff')]:
            raw=bom+FIXTURE.decode().encode(enc)
            expected=bom+FIXTURE.decode().replace('sg.TextureQuality=3','sg.TextureQuality=0').encode(enc)
            self.assertEqual(m.merge(raw,{'sg.TextureQuality':'0'}),expected)
    def test_backup_undo_and_repeat(self):
        backup=self.apply({'sg.TextureQuality':'0'})
        record=m.read_json(backup)
        self.assertEqual(record['before'],{'sg.TextureQuality':'3'})
        self.assertNotIn('SyntheticAccountField',backup.read_text())
        self.assertNotIn(str(self.target),backup.read_text())
        self.assertIsNone(self.apply({'sg.TextureQuality':'0'}))
        raw,values,delta=m.undo_preview(self.target,backup,self.root,self.guard)
        self.apply(values,raw)
        self.assertEqual(self.target.read_bytes(),FIXTURE)
    def test_undo_wrong_target_and_newer_change_rejected(self):
        backup=self.apply({'sg.TextureQuality':'0'})
        with self.assertRaises(ValueError):m.undo_preview(self.source,backup,self.root,self.guard)
        self.target.write_bytes(self.target.read_bytes().replace(b'sg.TextureQuality=0',b'sg.TextureQuality=1'))
        with self.assertRaises(ValueError):m.undo_preview(self.target,backup,self.root,self.guard)
    def test_stale_preview_rejected(self):
        self.target.write_bytes(FIXTURE+b'; changed\r\n')
        with self.assertRaises(ValueError):self.apply({'sg.TextureQuality':'0'},FIXTURE)
    def test_process_block_and_unknown_state_fail_closed(self):
        for names in [['VALORANT-Win64-Shipping.exe'],['RiotClientServices.exe'],['Riot Client.exe']]:
            with patch('capture_model.process_names',return_value=names),self.assertRaises(RuntimeError):m.ensure_closed()
        with patch('capture_model.process_names',side_effect=RuntimeError('restricted')),self.assertRaises(RuntimeError):m.ensure_closed()
    def test_capture_and_write_do_not_access_file_if_guard_blocks(self):
        def block():raise RuntimeError('running')
        with patch('capture_model.read_bytes') as reader,self.assertRaises(RuntimeError):m.capture(self.source,'x',self.root,block)
        reader.assert_not_called()
        with self.assertRaises(RuntimeError):m.apply(self.target,{'sg.TextureQuality':'0'},FIXTURE,self.base/'backups',self.root,block)
        self.assertEqual(self.target.read_bytes(),FIXTURE)
    def test_failed_backup_prevents_game_write(self):
        with patch('capture_model.write_json',side_effect=PermissionError('fixture')),self.assertRaises(PermissionError):self.apply({'sg.TextureQuality':'0'})
        self.assertEqual(self.target.read_bytes(),FIXTURE)
    def test_failed_replace_keeps_file(self):
        with patch('capture_model.os.replace',side_effect=PermissionError('fixture')),self.assertRaises(PermissionError):m.atomic(self.target,b'bad')
        self.assertEqual(self.target.read_bytes(),FIXTURE)
    def test_import_rejects_path_instructions_and_bad_schema(self):
        p=self.base/'bad.json'
        for data in [dict(self.profile,target='../../x.ini'),dict(self.profile,settings={'path':'x'}),{'version':2,'fields':{}}]:
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):m.import_profile(p)
    def test_local_labels_are_not_paths(self):
        self.store.label(self.source,'daisy / label')
        self.assertEqual(self.store.bindings()[m.source_id(self.source)],'daisy / label')
        self.assertNotIn(str(self.source),(self.store.base/'source-labels.json').read_text())
    def test_remembered_choice_is_explicit_not_latest_file(self):
        self.store.remember(self.source)
        self.assertEqual(self.store.last_source(),m.source_id(self.source))
        self.assertNotIn(str(self.source),(self.store.base/'selection.json').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
