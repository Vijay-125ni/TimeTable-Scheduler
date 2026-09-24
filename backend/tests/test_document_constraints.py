import asyncio
import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.endpoints import timetable as timetable_endpoint
from app.core.config import settings
from app.services import document_analysis
from app.services.document_analysis import (analyze_academic_documents,
                                            normalize_extracted_timetable)
from app.services.document_constraints import (
    ExtractedDocument, build_constraint_text_from_documents,
    extract_document_text)


class DocumentConstraintTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "subject_names": ["Mathematics", "Physics", "ML Lab"],
            "class_names": ["CSE A"],
            "faculty_names": [],
            "periods_per_day": 3,
        }

    def test_csv_timetable_rows_generate_fixed_slot_constraints(self):
        content = (
            "Class CSE A\n"
            "Day,Period 1,Period 2,Period 3\n"
            "Monday,Mathematics,Free,Physics\n"
            "Tuesday,Break,ML Lab,Physics\n"
        ).encode()
        document = extract_document_text("existing.csv", content, "text/csv")

        constraints_text, constraints, warnings = build_constraint_text_from_documents(
            [document], self.context
        )

        self.assertFalse(warnings)
        self.assertEqual(len(constraints), 4)
        self.assertIn(
            "For Class CSE A, Mathematics must be on Monday period 1.", constraints_text
        )
        self.assertIn(
            "For Class CSE A, Physics must be on Monday period 3.", constraints_text
        )
        self.assertIn(
            "For Class CSE A, ML Lab must be on Tuesday period 2.", constraints_text
        )

    def test_json_schedule_data_generates_fixed_slot_constraints(self):
        payload = {
            "schedule_data": {
                "class_1": {
                    "class_name": "CSE A",
                    "timetable": {
                        "Monday": [
                            {"period": 1, "subject": "Mathematics"},
                            {"slot_type": "break", "label": "Lunch"},
                            {"period": 2, "subject": "Physics"},
                        ]
                    },
                }
            }
        }
        document = ExtractedDocument(
            filename="generated.json",
            content_type="application/json",
            text=json.dumps(payload),
            extractor="json",
        )

        constraints_text, constraints, warnings = build_constraint_text_from_documents(
            [document], self.context
        )

        self.assertFalse(warnings)
        self.assertEqual(len(constraints), 2)
        self.assertIn(
            "For Class CSE A, Mathematics must be on Monday period 1.", constraints_text
        )
        self.assertIn(
            "For Class CSE A, Physics must be on Monday period 2.", constraints_text
        )

    def test_academic_analysis_expands_merged_context_rows(self):
        document = ExtractedDocument(
            filename="faculty-allocation.csv",
            content_type="text/csv",
            extractor="text",
            text=(
                "Subject Code,Subject Name,Type,L,T,P,C,Faculty,Designation\n"
                "CS101,Data Structures,Blended,3,0,0,3,Dr Rao,Professor\n"
                ",,Lab,0,0,2,1,,\n"
                "PE201,Cloud Computing (Professional Elective I),Theory,3,0,0,3,Prof Meena,Assistant Professor\n"
            ),
        )

        result = analyze_academic_documents([document])
        rows = result["extracted_timetable"]

        self.assertEqual(result["source"], "deterministic")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["course_details"]["subject_code"], "CS101")
        self.assertEqual(rows[0]["course_details"]["subject_name"], "Data Structures")
        self.assertEqual(rows[0]["course_details"]["type"], "Blended")
        self.assertEqual(rows[0]["faculty_assignment"]["full_name"], "Dr Rao")
        self.assertTrue(rows[0]["additional_metadata"]["is_ambiguous_or_split"])
        self.assertTrue(rows[1]["course_details"]["is_elective"])
        self.assertEqual(rows[1]["course_details"]["elective_group"], "Professional Elective I")

    def test_csv_extraction_preserves_leading_blank_cells_for_merged_rows(self):
        document = extract_document_text(
            "faculty-allocation.csv",
            (
                "Subject Code,Subject Name,Type,L,T,P,C,Faculty,Designation\n"
                "CS101,Data Structures,Blended,3,0,0,3,Dr Rao,Professor\n"
                ",,Lab,0,0,2,1,,\n"
            ).encode(),
            "text/csv",
        )

        result = analyze_academic_documents([document])
        rows = result["extracted_timetable"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["course_details"]["subject_code"], "CS101")
        self.assertEqual(rows[0]["course_details"]["subject_name"], "Data Structures")
        self.assertEqual(rows[0]["course_details"]["type"], "Blended")
        self.assertEqual(rows[0]["credit_structure"]["practical_hours_P"], 2)

    def test_academic_analysis_drops_model_header_rows(self):
        normalized, warnings = normalize_extracted_timetable(
            {
                "extracted_timetable": [
                    {
                        "meta": {
                            "row_index": 1,
                            "raw_text_line": "Subject Code,Subject Name,Type,L,T,P,C,Faculty",
                        },
                        "course_details": {
                            "subject_code": None,
                            "subject_name": "Subject Code,Subject Name,Type,L,T,P,C,Faculty",
                            "type": "Unknown",
                            "is_elective": False,
                            "elective_group": None,
                        },
                        "credit_structure": {
                            "lecture_hours_L": 0,
                            "tutorial_hours_T": 0,
                            "practical_hours_P": 0,
                            "total_credits_C": 0,
                        },
                        "faculty_assignment": {"full_name": None, "designation": None},
                        "additional_metadata": {
                            "remarks": None,
                            "is_ambiguous_or_split": False,
                        },
                    },
                    {
                        "meta": {
                            "row_index": 2,
                            "raw_text_line": "CS101,Data Structures,Theory,3,0,0,3,Dr Rao",
                        },
                        "course_details": {
                            "subject_code": "CS101",
                            "subject_name": "Data Structures",
                            "type": "Theory",
                            "is_elective": False,
                            "elective_group": None,
                        },
                        "credit_structure": {
                            "lecture_hours_L": 3,
                            "tutorial_hours_T": 0,
                            "practical_hours_P": 0,
                            "total_credits_C": 3,
                        },
                        "faculty_assignment": {
                            "full_name": "Dr Rao",
                            "designation": None,
                        },
                        "additional_metadata": {
                            "remarks": None,
                            "is_ambiguous_or_split": False,
                        },
                    },
                ]
            }
        )

        self.assertFalse(warnings)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["course_details"]["subject_code"], "CS101")

    def test_academic_analysis_inherits_generic_split_component_names(self):
        normalized, warnings = normalize_extracted_timetable(
            {
                "extracted_timetable": [
                    {
                        "meta": {
                            "row_index": 1,
                            "raw_text_line": "CS101,Data Structures,Blended,3,0,0,3,Dr Rao",
                        },
                        "course_details": {
                            "subject_code": "CS101",
                            "subject_name": "Data Structures",
                            "type": "Blended",
                            "is_elective": False,
                            "elective_group": None,
                        },
                        "credit_structure": {
                            "lecture_hours_L": 3,
                            "tutorial_hours_T": 0,
                            "practical_hours_P": 0,
                            "total_credits_C": 3,
                        },
                        "faculty_assignment": {
                            "full_name": "Dr Rao",
                            "designation": None,
                        },
                        "additional_metadata": {
                            "remarks": None,
                            "is_ambiguous_or_split": False,
                        },
                    },
                    {
                        "meta": {"row_index": 2, "raw_text_line": ",,Lab,0,0,2,1,,"},
                        "course_details": {
                            "subject_code": None,
                            "subject_name": "Lab",
                            "type": "Lab",
                            "is_elective": False,
                            "elective_group": None,
                        },
                        "credit_structure": {
                            "lecture_hours_L": 0,
                            "tutorial_hours_T": 0,
                            "practical_hours_P": 2,
                            "total_credits_C": 1,
                        },
                        "faculty_assignment": {"full_name": None, "designation": None},
                        "additional_metadata": {
                            "remarks": None,
                            "is_ambiguous_or_split": False,
                        },
                    },
                ]
            }
        )

        self.assertFalse(warnings)
        self.assertEqual(normalized[1]["course_details"]["subject_code"], "CS101")
        self.assertEqual(
            normalized[1]["course_details"]["subject_name"], "Data Structures"
        )
        self.assertEqual(normalized[1]["course_details"]["type"], "Lab")
        self.assertTrue(normalized[1]["additional_metadata"]["is_ambiguous_or_split"])

    def test_academic_analysis_prefers_more_structured_deterministic_rows(self):
        document = ExtractedDocument(
            filename="mixed.csv",
            content_type="text/csv",
            extractor="text",
            text=(
                "Class CSE A\n"
                "Day,Period 1,Period 2\n"
                "Monday,Mathematics,Physics\n"
                "Subject Code,Subject Name,Type,L,T,P,C,Faculty,Designation\n"
                "CS101,Data Structures,Blended,3,0,0,3,Dr Rao,Professor\n"
                ",,Lab,0,0,2,1,,\n"
            ),
        )

        original_call = document_analysis._call_local_model
        document_analysis._call_local_model = lambda *args, **kwargs: json.dumps(
            {
                "extracted_timetable": [
                    {
                        "meta": {"row_index": 1, "raw_text_line": "Class CSE A"},
                        "course_details": {
                            "subject_code": None,
                            "subject_name": "Class CSE A",
                            "type": "Unknown",
                            "is_elective": False,
                            "elective_group": None,
                        },
                        "credit_structure": {
                            "lecture_hours_L": 0,
                            "tutorial_hours_T": 0,
                            "practical_hours_P": 0,
                            "total_credits_C": 0,
                        },
                        "faculty_assignment": {"full_name": None, "designation": None},
                        "additional_metadata": {
                            "remarks": None,
                            "is_ambiguous_or_split": False,
                        },
                    }
                ]
            }
        )
        try:
            result = analyze_academic_documents([document], model="qwen-plus", api_key="sk-test")
        finally:
            document_analysis._call_local_model = original_call

        self.assertEqual(result["source"], "deterministic")
        self.assertIn("less structured", " ".join(result["warnings"]))
        self.assertEqual(len(result["extracted_timetable"]), 1)
        self.assertEqual(result["extracted_timetable"][0]["course_details"]["subject_code"], "CS101")


class FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query=None, projection=None):
        return [dict(doc) for doc in self.docs]


class FakeDB:
    def __init__(self):
        self.collections = {
            "faculty": FakeCollection([]),
            "subjects": FakeCollection(
                [
                    {"name": "Mathematics", "code": "MATH", "requires_lab": False},
                    {"name": "Physics", "code": "PHY", "requires_lab": False},
                ]
            ),
            "classes": FakeCollection(
                [
                    {"name": "CSE", "section": "A"},
                ]
            ),
        }

    def __getitem__(self, name):
        return self.collections.get(name, FakeCollection([]))


class FakeUploadFile:
    def __init__(self, filename, content, content_type="text/csv"):
        self.filename = filename
        self._content = content
        self.content_type = content_type

    async def read(self):
        return self._content


class ConstraintUploadEndpointTests(unittest.TestCase):
    def test_upload_endpoint_returns_generated_constraints(self):
        upload = FakeUploadFile(
            "existing.csv",
            b"Class CSE A\nDay,Period 1,Period 2\nMonday,Mathematics,Physics\n",
        )

        previous_model = settings.DOCUMENT_ANALYSIS_MODEL
        settings.DOCUMENT_ANALYSIS_MODEL = None
        try:
            payload = asyncio.run(
                timetable_endpoint.generate_constraints_from_files(
                    files=[upload],
                    periods_per_day=3,
                    db=FakeDB(),
                    current_user={"id": "admin"},
                )
            )
        finally:
            settings.DOCUMENT_ANALYSIS_MODEL = previous_model

        self.assertIn(
            "Mathematics must be on Monday period 1", payload["constraints_text"]
        )
        self.assertGreaterEqual(len(payload["custom_constraints"]), 2)
        self.assertIn("extracted_timetable", payload)
        self.assertIn("document_analysis", payload)
        self.assertEqual(payload["files"][0]["extractor"], "text")

    def test_qwen_api_settings_resolution(self):
        orig_qwen_key = settings.QWEN_API_KEY
        orig_model = settings.DOCUMENT_ANALYSIS_MODEL
        orig_base = settings.DOCUMENT_ANALYSIS_API_BASE
        try:
            settings.QWEN_API_KEY = "sk-qwen-test-key"
            settings.DOCUMENT_ANALYSIS_MODEL = "qwen-plus"
            settings.DOCUMENT_ANALYSIS_API_BASE = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

            self.assertEqual(settings.active_document_analysis_model, "qwen-plus")
            self.assertEqual(settings.active_document_analysis_api_key, "sk-qwen-test-key")
            self.assertEqual(settings.active_document_analysis_api_base, "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
        finally:
            settings.QWEN_API_KEY = orig_qwen_key
            settings.DOCUMENT_ANALYSIS_MODEL = orig_model
            settings.DOCUMENT_ANALYSIS_API_BASE = orig_base


if __name__ == "__main__":
    unittest.main()
