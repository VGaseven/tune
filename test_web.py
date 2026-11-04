"""Tests for the pywebview bridge (tune_web.Api). No pywebview needed: webview is imported lazily
inside main(), so importing tune_web here is safe. A fake backend proves the {'ok':...} envelope,
argument pass-through and error capture."""
import unittest
import tune_web

class FakeBackend:
    def __init__(self):self.calls=[]
    def accounts(self):return [{"account":"x"}]
    def profiles(self):return []
    def rank(self,puuid,region=None):self.calls.append((puuid,region));return {"source":"offline"}
    def save(self,path,label):return {"label":label,"replaced":False}
    def apply(self,profile_path,target_path):return {"applied":1}
    def riot_client(self):return None

class Bridge(unittest.TestCase):
    def setUp(self):self.be=FakeBackend();self.api=tune_web.Api(self.be)
    def test_ok_envelope_and_passthrough(self):
        self.assertEqual(self.api.accounts(),{"ok":True,"data":[{"account":"x"}]})
        self.api.rank("p1","eu");self.assertEqual(self.be.calls[-1],("p1","eu"))
        self.assertEqual(self.api.save("P","Main")["data"]["label"],"Main")
        self.assertEqual(self.api.apply("prof","tgt")["data"]["applied"],1)
    def test_error_is_captured_not_raised(self):
        class Bad:
            def accounts(self):raise RuntimeError("game is open")
        r=tune_web.Api(Bad()).accounts()
        self.assertFalse(r["ok"]);self.assertIn("game is open",r["error"])
    def test_update_check_compares_versions(self):
        self.assertTrue(tune_web.newer('v9.1',tune_web.VERSION));self.assertFalse(tune_web.newer('v1.0',tune_web.VERSION))
        self.assertFalse(tune_web.newer('nonsense',tune_web.VERSION));self.assertTrue(tune_web.newer('v7.10','7.9'))
        r=self.api.check_update(fetch=lambda:{'tag_name':'v99.0','html_url':'https://example.invalid/r'})
        self.assertTrue(r['ok']);self.assertTrue(r['data']['newer']);self.assertEqual(r['data']['latest'],'99.0')
        def down():raise OSError('offline')
        self.assertFalse(self.api.check_update(fetch=down)['ok'])
    def test_launch_riot_without_client(self):
        r=self.api.launch_riot()
        self.assertFalse(r["ok"]);self.assertIn("Riot Client",r["error"])

if __name__=="__main__":
    unittest.main()
