"""Tests for desk_rank - the optional online rank/card lookup. No network and no tkinter: the
HTTP fetcher is always injected, so these run anywhere (including CI) and prove the module
degrades to 'offline' on every failure and never writes the API key to disk."""
import json
import os
import tempfile
import unittest
from pathlib import Path
import desk_rank as R

PUUID='0aec6e15-90a1-4b2c-8d3e-111111111111'
ACCOUNT={'data':{'name':'daisy','tag':'EU1','card':{'id':'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'}}}
MMR={'data':{'current_data':{'currenttierpatched':'Immortal 2','ranking_in_tier':42,
                             'images':{'small':'http://x/s.png','large':'http://x/l.png'}}}}
def feed(url):return ACCOUNT if 'account' in url else MMR

class Region(unittest.TestCase):
    def test_region_from_folder(self):
        self.assertEqual(R.region_from_folder(PUUID+'-eu'),'eu')
        self.assertEqual(R.region_from_folder(PUUID+'-NA'),'na')
        self.assertIsNone(R.region_from_folder(PUUID))          # no region suffix
        self.assertIsNone(R.region_from_folder(PUUID+'-zz'))    # not a real region

class Key(unittest.TestCase):
    def setUp(self):self._old=os.environ.pop('TUNE_RANK_KEY',None)
    def tearDown(self):
        os.environ.pop('TUNE_RANK_KEY',None)
        if self._old is not None:os.environ['TUNE_RANK_KEY']=self._old
    def test_precedence_env_then_file_then_default(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(R.resolve_key(d),'')               # nothing set anywhere
            (Path(d)/'rankkey.txt').write_text('fromfile',encoding='utf-8')
            self.assertEqual(R.resolve_key(d),'fromfile')
            os.environ['TUNE_RANK_KEY']='fromenv'
            self.assertEqual(R.resolve_key(d),'fromenv')        # env wins

class Lookup(unittest.TestCase):
    def test_online_then_cache_and_no_key_on_disk(self):
        calls=[]
        def fetch(url):calls.append(url);return feed(url)
        with tempfile.TemporaryDirectory() as d:
            out=R.lookup(PUUID,'eu',key='SECRETKEY123',cache_dir=d,fetch=fetch)
            self.assertEqual(out['source'],'online')
            self.assertEqual((out['name'],out['tag'],out['rank'],out['rr']),('daisy','EU1','Immortal 2',42))
            self.assertIn('largeart.png',out['card_url']);self.assertEqual(R.display(out),'daisy#EU1')
            self.assertEqual(R.rank_label(out),'Immortal 2');self.assertEqual(len(calls),2)
            again=R.lookup(PUUID,'eu',key='SECRETKEY123',cache_dir=d,fetch=fetch)
            self.assertEqual(again['source'],'cache');self.assertEqual(len(calls),2)   # served from cache
            self.assertNotIn('SECRETKEY123',(Path(d)/f'{PUUID}.json').read_text(encoding='utf-8'))
    def test_offline_without_key(self):
        out=R.lookup(PUUID,'eu',key='',fetch=feed)
        self.assertEqual(out['source'],'offline');self.assertIsNone(out['name']);self.assertEqual(R.rank_label(out),'')
    def test_offline_on_network_error(self):
        def boom(url):raise R.RankError('network')
        self.assertEqual(R.lookup(PUUID,'eu',key='k',fetch=boom)['source'],'offline')
    def test_bad_puuid_never_fetches(self):
        hit=[]
        R.lookup('not-a-uuid','eu',key='k',fetch=lambda u:hit.append(u) or feed(u))
        self.assertEqual(hit,[])
    def test_name_and_card_without_region_even_if_mmr_absent(self):
        out=R.lookup(PUUID,'zz',key='k',fetch=feed)   # unknown region -> skip MMR, keep account
        self.assertEqual(out['name'],'daisy');self.assertIsNone(out['rank']);self.assertEqual(out['source'],'online')
    def test_cache_expires_and_refetches(self):
        with tempfile.TemporaryDirectory() as d:
            R.lookup(PUUID,'eu',key='k',cache_dir=d,fetch=feed)
            f=Path(d)/f'{PUUID}.json';rec=json.loads(f.read_text(encoding='utf-8'));rec['at']=0;f.write_text(json.dumps(rec),encoding='utf-8')
            calls=[]
            R.lookup(PUUID,'eu',key='k',cache_dir=d,fetch=lambda u:calls.append(u) or feed(u))
            self.assertTrue(calls)   # stale cache was ignored

if __name__=='__main__':
    unittest.main()
