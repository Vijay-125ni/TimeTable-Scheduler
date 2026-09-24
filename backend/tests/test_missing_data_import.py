import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.endpoints.imports import _import_csv_data, _import_departments, _import_faculty, _import_subjects


class FakeCollection:
    def __init__(self, name):
        self.name = name
        self.docs = []
        self.next_id = 1

    def insert_one(self, document):
        doc = dict(document)
        doc.setdefault("_id", f"{self.name}_{self.next_id}")
        self.next_id += 1
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    def find_one(self, query=None):
        query = query or {}
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    def find(self, query=None, projection=None):
        query = query or {}
        return [doc for doc in self.docs if self._matches(doc, query)]

    def update_one(self, query, update):
        doc = self.find_one(query)
        if not doc:
            return SimpleNamespace(matched_count=0, modified_count=0)
        if "$set" in update:
            doc.update(update["$set"])
        return SimpleNamespace(matched_count=1, modified_count=1)

    def _matches(self, doc, query):
        for key, expected in (query or {}).items():
            if key == "$or":
                if not any(self._matches(doc, branch) for branch in expected):
                    return False
                continue
            if doc.get(key) != expected:
                return False
        return True


class FakeDB:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, item):
        if item not in self.collections:
            self.collections[item] = FakeCollection(item)
        return self.collections[item]


class TestMissingDataImport(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()

    def test_import_department_with_missing_code_saves_record(self):
        csv_content = b"name,code\nComputer Science,\n"
        res = _import_csv_data("departments", csv_content, self.db)
        
        self.assertEqual(res["imported"], 1)
        dept = self.db["departments"].find_one({"name": "Computer Science"})
        self.assertIsNotNone(dept)
        self.assertEqual(dept.get("code"), "")

    def test_import_faculty_with_missing_email_saves_record(self):
        csv_content = b"name,email\nDr. John Smith,\n"
        res = _import_csv_data("faculty", csv_content, self.db)

        self.assertEqual(res["imported"], 1)
        fac = self.db["faculty"].find_one({"name": "Dr. John Smith"})
        self.assertIsNotNone(fac)
        self.assertEqual(fac.get("email"), "")

    def test_import_subject_with_missing_code_saves_record(self):
        csv_content = b"name,code,hours_per_week\nMathematics,,4\n"
        res = _import_csv_data("subjects", csv_content, self.db)

        self.assertEqual(res["imported"], 1)
        subj = self.db["subjects"].find_one({"name": "Mathematics"})
        self.assertIsNotNone(subj)
        self.assertTrue(subj.get("code", "").startswith("MISSING_"))


if __name__ == "__main__":
    unittest.main()
