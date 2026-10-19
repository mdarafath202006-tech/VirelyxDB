import tempfile
import unittest
from pathlib import Path
from virelyxdb import VirelyxDB

class VirelyxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = VirelyxDB(self.tmp.name)
        self.db.create_table("users", {"id":"int", "name":"str", "active":"bool"})

    def tearDown(self):
        self.tmp.cleanup()

    def test_crud_and_indexed_select(self):
        self.db.insert("users", {"id":1, "name":"Asha", "active":True})
        self.db.insert("users", {"id":2, "name":"Ravi", "active":False})
        self.assertEqual(self.db.select("users", ("name", "Asha"))[0]["id"], 1)
        self.assertEqual(self.db.update("users", ("id", 2), {"active":True}), 1)
        self.assertEqual(len(self.db.select("users", ("active", True))), 2)
        self.assertEqual(self.db.delete("users", ("id", 1)), 1)
        self.assertEqual(len(self.db.select("users")), 1)

    def test_reopen_persists_data(self):
        self.db.insert("users", {"id":1, "name":"Asha", "active":True})
        reopened = VirelyxDB(self.tmp.name)
        self.assertEqual(reopened.select("users")[0]["name"], "Asha")

    def test_schema_validation(self):
        with self.assertRaises(ValueError):
            self.db.insert("users", {"id":"wrong", "name":"Asha", "active":True})
        with self.assertRaises(ValueError):
            self.db.create_table("bad", {"x":"unknown"})

    def test_wal_recovery_replays_snapshot(self):
        self.db.insert("users", {"id":9, "name":"Recovered", "active":True})
        state = self.db.state
        self.db.db_path.write_text('{"version":1,"tables":{}}', encoding="utf-8")
        self.db.wal_path.write_text(__import__("json").dumps({"kind":"snapshot","state":state})+"\n", encoding="utf-8")
        reopened = VirelyxDB(self.tmp.name)
        self.assertEqual(reopened.select("users")[0]["name"], "Recovered")

if __name__ == "__main__":
    unittest.main()
