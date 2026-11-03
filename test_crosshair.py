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

if __name__=="__main__":
    unittest.main()
