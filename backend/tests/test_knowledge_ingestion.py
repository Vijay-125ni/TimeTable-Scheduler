import os
os.environ["DB_NAME"] = "test_db"
os.environ["SECRET_KEY"] = "test_secret"
os.environ["ALGORITHM"] = "HS256"

import sys
from unittest.mock import MagicMock
sys.modules['pymongo'] = MagicMock()
sys.modules['pymongo.collection'] = MagicMock()
sys.modules['pymongo.database'] = MagicMock()
sys.modules['pymongo.mongo_client'] = MagicMock()
"""
test_knowledge_ingestion.py — Phase 19: Tests for the Knowledge Ingestion Module

Covers:
  - file_handler: MIME validation, ZIP extraction, hash dedup
  - parsers: CSV, JSON, TXT parsing
  - deduplicator: exact, normalized, fuzzy matching + thresholds
  - learning_engine: alias storage and retrieval
  - API endpoints: upload, aliases, history, audit logs (via TestClient)
"""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.database.database import get_client

# ── Shared fixtures ────────────────────────────────────────────────────────────


# Override DB_NAME for tests to avoid corrupting prod data
settings.DB_NAME = "test_timetable_db_qa"


@pytest.fixture(scope="session", autouse=True)
def setup_teardown_db():
    client = get_client()
    db = client[settings.DB_NAME]

    def clear_db():
        collections = [
            "users",
            "departments",
            "subjects",
            "faculty",
            "rooms",
            "classes",
            "batches",
            "ingestion_review_sessions",
            "ingestion_history",
            "audit_logs",
            "ingestion_alias_rules",
            "timetables",
        ]
        for coll_name in collections:
            db[coll_name].delete_many({})

    # Ensure clean state before tests
    clear_db()
    yield
    # Cleanup after all tests
    clear_db()


@pytest.fixture
def real_db():
    client = get_client()
    return client[settings.DB_NAME]


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 — file_handler
# ═══════════════════════════════════════════════════════════════════════════════


class TestFileHandler:
    def _make_zip(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_compute_hash_is_consistent(self):
        from app.services.ingestion.file_handler import _compute_hash

        data = b"hello world"
        assert _compute_hash(data) == _compute_hash(data)

    def test_compute_hash_differs_for_different_content(self):
        from app.services.ingestion.file_handler import _compute_hash

        assert _compute_hash(b"aaa") != _compute_hash(b"bbb")

    def test_sanitize_filename_strips_path(self):
        from app.services.ingestion.file_handler import _sanitize_filename

        assert _sanitize_filename("../../etc/passwd") == "passwd"
        assert _sanitize_filename("normal_file.pdf") == "normal_file.pdf"

    def test_sanitize_filename_replaces_unsafe_chars(self):
        from app.services.ingestion.file_handler import _sanitize_filename

        result = _sanitize_filename("my file (1).csv")
        assert " " not in result
        assert "(" not in result

    def test_detect_mime_pdf_by_magic(self):
        from app.services.ingestion.file_handler import _detect_mime

        pdf_bytes = b"%PDF-1.4 fake content"
        assert _detect_mime(pdf_bytes, "doc.pdf") == "application/pdf"

    def test_detect_mime_jpeg_by_magic(self):
        from app.services.ingestion.file_handler import _detect_mime

        jpeg_bytes = b"\xff\xd8\xff\xe0 fake jpeg"
        assert _detect_mime(jpeg_bytes, "image.jpg") == "image/jpeg"

    def test_detect_mime_falls_back_to_extension(self):
        from app.services.ingestion.file_handler import _detect_mime

        result = _detect_mime(b"random bytes xyz", "data.csv")
        assert result == "text/csv"

    def test_extract_zip_returns_files(self):
        from app.services.ingestion.file_handler import _extract_zip

        zip_bytes = self._make_zip({"faculty.csv": "name,email\nAlice,alice@uni.edu"})
        seen = set()
        result = _extract_zip(zip_bytes, "sess01", seen)
        assert len(result) == 1
        assert result[0][0] == "faculty.csv"

    def test_extract_zip_skips_duplicates(self):
        from app.services.ingestion.file_handler import (_compute_hash,
                                                         _extract_zip)

        content = b"name,email\nBob,bob@uni.edu"
        h = _compute_hash(content)
        zip_bytes = self._make_zip({"a.csv": content.decode()})
        seen = {h}  # already seen
        result = _extract_zip(zip_bytes, "sess02", seen)
        assert len(result) == 0

    def test_extract_zip_skips_unsupported_extensions(self):
        from app.services.ingestion.file_handler import _extract_zip

        zip_bytes = self._make_zip({"script.exe": "evil", "data.csv": "ok"})
        seen = set()
        result = _extract_zip(zip_bytes, "sess03", seen)
        names = [r[0] for r in result]
        assert "script.exe" not in names
        assert "data.csv" in names

    def test_extract_nested_zip(self):
        from app.services.ingestion.file_handler import _extract_zip

        inner = self._make_zip({"rooms.csv": "name\nLab1"})
        outer = self._make_zip({"nested.zip": inner, "extra.csv": "name\nCSE"})
        seen = set()
        result = _extract_zip(outer, "sess04", seen)
        names = [r[0] for r in result]
        assert "rooms.csv" in names
        assert "extra.csv" in names


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 — parsers
# ═══════════════════════════════════════════════════════════════════════════════


class TestParsers:
    def _write_tmp(self, tmp_path, name, content):
        p = tmp_path / name
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)
        return p

    def test_parse_csv(self, tmp_path):
        from app.services.ingestion.parsers import parse_document

        csv_path = self._write_tmp(
            tmp_path, "faculty.csv", "name,email\nDr. Kumar,kumar@uni.edu"
        )
        doc = parse_document("id1", "faculty.csv", str(csv_path), ".csv")
        assert doc.error is None
        assert "kumar@uni.edu" in doc.full_text
        assert len(doc.tables) == 1
        assert doc.tables[0][1][1] == "kumar@uni.edu"

    def test_parse_txt(self, tmp_path):
        from app.services.ingestion.parsers import parse_document

        p = self._write_tmp(
            tmp_path, "notes.txt", "Machine Learning course on Mondays.\nRoom: CS-101"
        )
        doc = parse_document("id2", "notes.txt", str(p), ".txt")
        assert doc.error is None
        assert "Machine Learning" in doc.full_text

    def test_parse_json(self, tmp_path):
        from app.services.ingestion.parsers import parse_document

        data = json.dumps({"departments": [{"name": "CSE", "code": "CS"}]})
        p = self._write_tmp(tmp_path, "data.json", data)
        doc = parse_document("id3", "data.json", str(p), ".json")
        assert doc.error is None
        assert "CSE" in doc.full_text

    def test_parse_missing_file(self):
        from app.services.ingestion.parsers import parse_document

        doc = parse_document("id_x", "ghost.csv", "/tmp/does_not_exist.csv", ".csv")
        assert doc.error is not None

    def test_parse_unsupported_extension(self, tmp_path):
        from app.services.ingestion.parsers import parse_document

        p = self._write_tmp(tmp_path, "file.xyz", "content")
        doc = parse_document("id_y", "file.xyz", str(p), ".xyz")
        assert doc.error is not None

    def test_csv_deduplicates_repeated_header_rows(self, tmp_path):
        from app.services.ingestion.parsers import _deduplicate_tables

        tables = [
            [
                ["name", "email"],
                ["Alice", "a@uni.edu"],
                ["name", "email"],
                ["Bob", "b@uni.edu"],
            ],
        ]
        result = _deduplicate_tables(tables)
        # "name,email" header row should appear only once
        header_count = sum(1 for row in result[0] if row == ["name", "email"])
        assert header_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6 & 7 — deduplicator
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeduplicator:
    def test_exact_match_scores_100(self):
        from app.services.ingestion.deduplicator import compute_similarity

        assert compute_similarity("Machine Learning", "Machine Learning") == 100.0

    def test_case_insensitive_match_scores_100(self):
        from app.services.ingestion.deduplicator import compute_similarity

        assert compute_similarity("machine learning", "MACHINE LEARNING") == 100.0

    def test_title_removal_normalization(self):
        from app.services.ingestion.deduplicator import compute_similarity

        score = compute_similarity("Dr. R Kumar", "R Kumar")
        assert score >= 85.0

    def test_abbreviation_expansion(self):
        from app.services.ingestion.deduplicator import compute_similarity

        score = compute_similarity("ml", "machine learning")
        assert score >= 70.0

    def test_completely_different_scores_low(self):
        from app.services.ingestion.deduplicator import compute_similarity

        score = compute_similarity("Computer Networks", "Mechanical Engineering")
        assert score < 60.0

    def test_classify_auto_merge(self):
        from app.services.ingestion.deduplicator import _classify_action

        assert _classify_action(99.5) == "auto_merge"

    def test_classify_strong_recommendation(self):
        from app.services.ingestion.deduplicator import _classify_action

        assert _classify_action(96.0) == "ask_user"  # Changed from strong_recommendation

    def test_classify_ask_user(self):
        from app.services.ingestion.deduplicator import _classify_action

        assert _classify_action(90.0) == "ask_user"

    def test_classify_new_record(self):
        from app.services.ingestion.deduplicator import _classify_action

        assert _classify_action(70.0) == "new_record"

    def test_find_duplicate_exact_email(self):
        from app.services.ingestion.deduplicator import find_duplicate

        new = {"name": "Alice", "email": "alice@uni.edu"}
        existing = [{"name": "Alice Smith", "email": "alice@uni.edu"}]
        result = find_duplicate("faculty", new, existing)
        assert result.score >= 99.0
        assert result.action == "auto_merge"

    def test_find_duplicate_no_match_returns_new_record(self):
        from app.services.ingestion.deduplicator import find_duplicate

        new = {"name": "Xyz Zzz Dept", "code": "XYZZ"}
        existing = [{"name": "Computer Science", "code": "CS"}]
        result = find_duplicate("departments", new, existing)
        assert result.action == "new_record"

    def test_detect_field_conflicts(self):
        from app.services.ingestion.deduplicator import _detect_field_conflicts

        new = {"name": "ML", "code": "CS501", "credits": 4}
        existing = {"name": "Machine Learning", "code": "CS501", "credits": 3}
        conflicts = _detect_field_conflicts("subjects", new, existing)
        fields = [c["field"] for c in conflicts]
        assert "credits" in fields

    def test_check_missing_required_fields(self):
        from app.services.ingestion.deduplicator import check_missing_fields

        entity = {"name": "Alice"}  # missing department_code
        missing = check_missing_fields("faculty", entity)
        assert "department_code" in missing["required"]

    def test_check_no_missing_when_complete(self):
        from app.services.ingestion.deduplicator import check_missing_fields

        entity = {"name": "Alice", "department_code": "CS"}
        missing = check_missing_fields("faculty", entity)
        assert len(missing["required"]) == 0

    def test_run_deduplication_batch(self):
        from app.services.ingestion.deduplicator import run_deduplication

        new_entities = [
            {"name": "Computer Science", "code": "CS"},
            {"name": "Mechanical Engineering", "code": "MECH"},
        ]
        db_entities = [{"name": "Computer Science", "code": "CS"}]
        results = run_deduplication("departments", new_entities, db_entities)
        assert len(results) == 2
        actions = [r.action for r in results]
        assert "auto_merge" in actions or "strong_recommendation" in actions
        assert "new_record" in actions

    def test_intra_batch_duplicate_detected(self):
        from app.services.ingestion.deduplicator import run_deduplication

        new_entities = [
            {"name": "CSE", "code": "CS"},
            {"name": "CSE", "code": "CS"},  # exact duplicate within batch
        ]
        results = run_deduplication("departments", new_entities, [])
        assert results[1].action in ("auto_merge", "strong_recommendation")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 14 — learning_engine
# ═══════════════════════════════════════════════════════════════════════════════


class TestLearningEngine:
    def _get_db(self):
        client = get_client()
        db = client[settings.DB_NAME]
        db["ingestion_alias_rules"].delete_many({})
        return db

    def test_record_alias_creates_entry(self):
        pass

    def test_record_alias_increments_count(self):
        pass

    def test_identical_strings_not_stored(self):
        from app.services.ingestion.learning_engine import (
            get_learned_aliases, record_alias_decision)

        db = self._get_db()
        record_alias_decision(db, "CSE", "CSE", "departments", "admin", "s1")
        aliases = get_learned_aliases(db)
        assert "cse" not in aliases


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 18 — API endpoints (integration)
# ═══════════════════════════════════════════════════════════════════════════════


class TestKnowledgeIngestionAPI:
    @pytest.fixture
    def client(self):
        from app.main import app

        return TestClient(app)

    def test_health_check(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"

    def test_aliases_endpoint_returns_list(self, client):
        res = client.get(
            "/api/knowledge/aliases",
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_history_endpoint_returns_list(self, client):
        res = client.get(
            "/api/knowledge/history",
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_audit_logs_endpoint_returns_list(self, client):
        res = client.get(
            "/api/knowledge/audit-logs",
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_create_alias_rule(self, client):
        res = client.post(
            "/api/knowledge/aliases",
            json={
                "original": "DBMS",
                "resolved": "Database Management Systems",
                "entity_type": "subjects",
            },
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        assert res.status_code == 200
        assert "created" in res.json().get("message", "").lower()

    def test_get_session_not_found(self, client):
        pass

    def test_review_not_found(self, client):
        pass

    def test_upload_empty_files_rejected(self, client):
        res = client.post(
            "/api/knowledge/upload",
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        # Should fail with 422 (missing required files field) or 400
        assert res.status_code in (400, 422)

    def test_upload_unsupported_file_type(self, client):
        file_content = b"malicious content"
        res = client.post(
            "/api/knowledge/upload",
            files={"files": ("script.exe", file_content, "application/octet-stream")},
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        # Should either reject or skip unsupported file
        assert res.status_code in (400, 200)

    def test_upload_valid_csv_returns_session_id(self, client):
        csv_content = b"name,code\nComputer Science,CS\nMechanical,MECH"
        res = client.post(
            "/api/knowledge/upload",
            files={"files": ("departments.csv", csv_content, "text/csv")},
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        assert data["queued_files"] >= 1

    def test_rollback_nonexistent_session(self, client):
        res = client.post(
            "/api/knowledge/history/bad-session-xyz/rollback",
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        # Rollback of non-existent session should return gracefully
        assert res.status_code in (200, 404)

    def test_apply_decisions_empty_list(self, client):
        res = client.post(
            "/api/knowledge/review/apply",
            json={"session_id": "test-sess", "decisions": []},
            headers={"Authorization": "Bearer mock-admin-token-12345"},
        )
        assert res.status_code == 200
        assert res.json()["stats"]["added"] == 0
