import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.endpoints.imports import (IMPORT_ORDER, _guess_import_type,
                                       _import_csv_data, map_headers)


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

    def find_one(self, query):
        for doc in self.docs:
            if self._matches(doc, query):
                return doc
        return None

    def find(self, query=None):
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

            if isinstance(expected, dict):
                if "$exists" in expected:
                    if (key in doc) != expected["$exists"]:
                        return False
                    continue
                if "$in" in expected:
                    if doc.get(key) not in expected["$in"]:
                        return False
                    continue

            if expected is None:
                if doc.get(key) is not None:
                    return False
            elif doc.get(key) != expected:
                return False
        return True


class FakeDB:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection(name)
        return self.collections[name]


class CsvImportTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.template_dir = BACKEND_DIR / "csv_templates"

    def import_template(self, import_type):
        filename = f"{import_type}_template.csv"
        if import_type == "faculty":
            filename = "faculty_template.csv"
        result = _import_csv_data(
            import_type, (self.template_dir / filename).read_bytes(), self.db
        )
        self.assertEqual(result["error_count"], 0, result)
        self.assertEqual(result["warning_count"], 0, result)
        return result

    def test_templates_import_cleanly_and_are_idempotent(self):
        for import_type in IMPORT_ORDER:
            self.import_template(import_type)

        collection_counts = {
            name: len(collection.docs)
            for name, collection in self.db.collections.items()
        }
        self.assertEqual(collection_counts["departments"], 5)
        self.assertEqual(collection_counts["batches"], 2)
        self.assertEqual(collection_counts["rooms"], 4)
        self.assertEqual(collection_counts["classes"], 3)
        self.assertEqual(collection_counts["faculty"], 3)
        self.assertEqual(collection_counts["subjects"], 6)

        batch_a = self.db["batches"].find_one({"name": "Batch A"})
        self.assertEqual(batch_a["break_times"], [{"start": "11:00", "end": "11:15"}])
        self.assertEqual(batch_a["lunch_break"], {"start": "13:00", "end": "14:00"})

        class_a = self.db["classes"].find_one(
            {"name": "B.Tech 1st Year", "section": "A"}
        )
        class_b = self.db["classes"].find_one(
            {"name": "B.Tech 1st Year", "section": "B"}
        )
        class_it = self.db["classes"].find_one(
            {"name": "B.Tech 3rd Year", "section": "A"}
        )
        self.assertEqual(
            class_a["room_id"], self.db["rooms"].find_one({"code": "R101"})["_id"]
        )
        self.assertEqual(
            class_b["room_id"], self.db["rooms"].find_one({"code": "R102"})["_id"]
        )
        self.assertEqual(
            class_it["room_id"], self.db["rooms"].find_one({"code": "R301"})["_id"]
        )

        for import_type in IMPORT_ORDER:
            result = self.import_template(import_type)
            self.assertEqual(result["inserted"], 0, result)

        self.assertEqual(
            collection_counts,
            {
                name: len(collection.docs)
                for name, collection in self.db.collections.items()
            },
        )

    def test_bad_rows_return_diagnostics_without_blocking_valid_rows(self):
        _import_csv_data("departments", b"name,code\nComputer Science,CS\n", self.db)

        result = _import_csv_data(
            "rooms",
            b"name,code,room_type,capacity,department_code\n,EMPTY,lecture,10,CS\nRoom Bad,RB,lecture,abc,CS\n",
            self.db,
        )

        self.assertEqual(result["imported"], 2)
        self.assertTrue(result["warning_count"] >= 1)
        self.assertEqual(self.db["rooms"].find_one({"code": "RB"})["capacity"], 0)

    def test_header_mapping_does_not_reuse_one_column_for_optional_fields(self):
        mapping = map_headers(["code", "class", "email"], "mappings")
        self.assertEqual(mapping["subject_code"], "code")
        self.assertEqual(mapping["class_name"], "class")
        self.assertEqual(mapping["faculty_email"], "email")
        self.assertNotIn("room_code", mapping)

    def test_header_mapping_maps_generic_code_to_department_code_for_classes_and_faculty(self):
        mapping_classes = map_headers(['name', 'section', 'semester', 'student_count', 'code', 'batch_name', 'room_code'], 'classes')
        self.assertEqual(mapping_classes['department_code'], 'code')

        mapping_faculty = map_headers(['name', 'email', 'code', 'max_hours_per_week', 'unavailable_slots'], 'faculty')
        self.assertEqual(mapping_faculty['department_code'], 'code')

    def test_folder_file_type_guessing_handles_common_names(self):
        self.assertEqual(
            _guess_import_type("departments_template (1).csv"), "departments"
        )
        self.assertEqual(_guess_import_type("spring-faculty-mappings.csv"), "mappings")
        self.assertEqual(_guess_import_type("rooms.csv"), "rooms")
        self.assertIsNone(_guess_import_type("notes.txt"))


if __name__ == "__main__":
    unittest.main()
