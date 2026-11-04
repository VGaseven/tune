"""Tests for desk_crosshair - the local crosshair-code library. No tkinter, no game files,
no network: it only validates/stores share strings and parses a best-effort preview."""
import tempfile
import unittest
from pathlib import Path
import desk_crosshair as X

CODE="0;P;c;5;h;0;0l;4;0o;2;0a;1;d;1;z;2"

class Validate(unittest.TestCase):
    def test_accepts_a_real_code(self):self.assertEqual(X.validate_code("  "+CODE+"  "),CODE)
    def test_rejects_junk(self):
        for bad in ["",None,"no-semicolon-here","x"*600,"0;c;5;<script>"]:
            with self.assertRaises(ValueError):X.validate_code(bad)

class Parse(unittest.TestCase):
    def test_parses_preview_fields(self):
        p=X.parse_code(CODE)
        self.assertEqual(p["color"],"#00FFFF");self.assertTrue(p["dot"]);self.assertEqual(p["dot_size"],2)
        self.assertEqual(p["inner_length"],4);self.assertEqual(p["inner_offset"],2);self.assertTrue(p["inner"])
    def test_custom_color_and_bad_input(self):
        self.assertEqual(X.parse_code("0;c;8;u;FF8800;d;0")["color"],"#FF8800")
        self.assertIsNone(X.parse_code("not a code"))

class LibraryCRUD(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.lib=X.Library(self.tmp.name)
    def test_add_list_delete_persist(self):
        e=self.lib.add("My main",CODE,tags=["Pros","main"],notes="clean dot")
        self.assertEqual(len(self.lib.list()),1);self.assertEqual(e["name"],"My main");self.assertEqual(e["tags"],["Pros","main"])
        fresh=X.Library(self.tmp.name)  # reloads from disk
        self.assertEqual(len(fresh.list()),1)
        self.lib.delete(e["id"]);self.assertEqual(self.lib.list(),[])
    def test_add_rejects_bad_code_and_caps_tags(self):
        with self.assertRaises(ValueError):self.lib.add("x","bogus")
        e=self.lib.add("Many",CODE,tags=[str(i) for i in range(20)])
        self.assertEqual(len(e["tags"]),8)
    def test_update(self):
        e=self.lib.add("A",CODE)
        self.lib.update(e["id"],name="B")
        self.assertEqual(self.lib.list()[0]["name"],"B")
        with self.assertRaises(ValueError):self.lib.update("missing",name="C")

class Gallery(unittest.TestCase):
    def test_every_preset_is_a_valid_code_with_a_preview(self):
        names=[n for n,_,_ in X.PRESETS];self.assertEqual(len(names),len(set(names)))
        for n,code,_ in X.PRESETS:
            self.assertEqual(X.validate_code(code),code,n);self.assertIsNotNone(X.preview(code),n)
    def test_preview_reads_primary_section_and_defaults(self):
        p=X.preview("0;P;c;1;h;0;0l;4;A;c;7;0l;9")
        self.assertEqual(p["color"],"#00FF00");self.assertEqual(p["inner"]["length"],4);self.assertFalse(p["outline"])
        d=X.preview("0;P");self.assertTrue(d["outline"]);self.assertEqual(d["inner"]["length"],6)   # VALORANT defaults
        self.assertIsNone(X.preview("hello"))
    def test_gallery_lists_presets_and_mine(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            lib=X.Library(d);lib.add("Mine",X.PRESETS[0][1])
            g=X.gallery(lib);self.assertEqual(len(g["presets"]),len(X.PRESETS));self.assertEqual(g["mine"][0]["name"],"Mine")
            self.assertTrue(all(s["url"].startswith("https://") for s in g["sites"]))
    def test_account_profile_becomes_a_code_that_previews_the_same(self):
        import json,desk_master as D
        prof={"primary":{"color":{"r":0,"g":255,"b":255,"a":255},"bUseCustomColor":False,"bHasOutline":True,"outlineThickness":1,"outlineOpacity":0.5,
              "bDisplayCenterDot":True,"centerDotSize":2,"centerDotOpacity":1,
              "innerLines":{"bShowLines":True,"lineThickness":2,"lineLength":4,"lineLengthVertical":4,"bAllowVertScaling":False,"lineOffset":3,"opacity":1},
              "outerLines":{"bShowLines":False,"lineThickness":2,"lineLength":2,"lineLengthVertical":2,"bAllowVertScaling":False,"lineOffset":10,"opacity":0.35}},
              "profileName":"Test"}
        vals={"EAresStringSettingName::SavedCrosshairProfileData":json.dumps({"currentProfile":0,"profiles":[prof]})}
        code=D.crosshair_code(vals);p=X.preview(code);a=D.crosshair(vals)
        self.assertTrue(code.startswith("0;P;c;5;"))
        self.assertEqual(p["color"].lower(),a["color"].lower());self.assertEqual(p["dot"],a["dot"]);self.assertEqual(p["inner"]["offset"],3)
        custom=json.loads(json.dumps(prof));custom["primary"]["bUseCustomColor"]=True;custom["primary"]["colorCustom"]={"r":215,"g":242,"b":75,"a":255}
        c2=D.crosshair_code({"EAresStringSettingName::SavedCrosshairProfileData":json.dumps({"currentProfile":0,"profiles":[custom]})})
        self.assertIn(";c;8;u;D7F24BFF;",c2);self.assertEqual(X.preview(c2)["color"],"#D7F24B")
        self.assertIsNone(D.crosshair_code({}))

class Window(unittest.TestCase):
    def test_colorref_is_bgr(self):
        import desk_window as W
        self.assertEqual(W.colorref("#0d0c16"),0x160c0d);self.assertEqual(W.darken("no window has this title 123"),[])

if __name__=="__main__":
    unittest.main()
