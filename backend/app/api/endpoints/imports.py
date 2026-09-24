import csv
import io
import json
import os
import re
import urllib.request
import urllib.error
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from ...core.security import get_admin_user, get_tenant_db

router = APIRouter()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/templates")
async def download_templates():
    """Create a ZIP file containing all CSV templates in csv_templates folder."""
    # Base directory of the backend project
    base_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    templates_dir = os.path.join(base_dir, "csv_templates")

    if not os.path.exists(templates_dir):
        raise HTTPException(status_code=404, detail="csv_templates folder not found.")

    # Create zip file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(templates_dir):
            for file in files:
                if file.endswith(".csv") or file.lower() == "readme.md":
                    file_path = os.path.join(root, file)
                    # Add file to zip archive under its filename
                    zip_file.write(file_path, arcname=file)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=csv_templates.zip",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


COMMON_ALIASES = {

    "subject_code": [
        "subjectcode",
        "subcode",
        "code",
        "subject_id",
        "sub_id",
        "subject code",
    ],
    "class_name": ["classname", "class", "clsname", "cls_name", "batch", "class name"],
    "class_section": [
        "classsection",
        "section",
        "sec",
        "class_sec",
        "cls_sec",
        "class section",
        "class_section",
    ],
    "faculty_email": [
        "facultyemail",
        "email",
        "facemail",
        "fac_email",
        "instructor_email",
        "teacher_email",
        "faculty email",
        "faculty_email",
    ],
    "department_code": [
        "departmentcode",
        "deptcode",
        "dept_code",
        "department_id",
        "dept_id",
        "department",
        "department code",
        "department_code",
    ],
    "department_codes": [
        "departmentcodes",
        "deptcodes",
        "dept_codes",
        "departments",
        "department codes",
        "department_codes",
    ],
    "batch_name": [
        "batchname",
        "batch",
        "batch_id",
        "semester",
        "batch name",
        "batch_name",
    ],
    "hours_per_week": [
        "hoursperweek",
        "hours",
        "weekly_hours",
        "periods",
        "hours per week",
        "hours_per_week",
    ],
    "requires_lab": [
        "requireslab",
        "lab",
        "islab",
        "is_lab",
        "requires_lab_session",
        "requires lab",
        "requires_lab",
    ],
    "max_hours_per_week": [
        "maxhoursperweek",
        "max_hours",
        "weekly_limit",
        "max hours per week",
        "max_hours_per_week",
    ],
    "student_count": [
        "studentcount",
        "students",
        "strength",
        "size",
        "class_size",
        "student count",
        "student_count",
    ],
    "name": ["name", "title", "full_name", "full name"],
    "code": ["code", "id", "identifier"],
    "email": ["email", "email_address", "email address"],
    "start_time": ["starttime", "start", "start_time", "start time"],
    "end_time": ["endtime", "end", "end_time", "end time"],
    "period_duration": [
        "periodduration",
        "duration",
        "period_duration",
        "period duration",
    ],
    "room_type": ["roomtype", "type", "room_type", "room type"],
    "capacity": ["capacity", "seats", "strength", "room_capacity", "room capacity"],
    "room_code": [
        "roomcode",
        "room",
        "room_id",
        "assigned_room",
        "room code",
        "room_code",
        "default_room",
    ],
    "section": ["section", "sec", "classsection", "class_section", "class section"],
    "semester": ["semester", "sem", "term"],
    "credits": ["credits", "credit", "credit_hours", "credit hours"],
    "break_times": ["breaktimes", "breaks", "break_times", "break times"],
    "lunch_break": ["lunchbreak", "lunch", "lunch_break", "lunch break"],
    "unavailable_slots": [
        "unavailableslots",
        "unavailable",
        "unavailable_slots",
        "unavailable slots",
        "blocked_slots",
        "blocked slots",
    ],

}

EXPECTED_HEADERS = {
    "departments": ["name", "code"],
    "batches": [
        "name",
        "start_time",
        "end_time",
        "period_duration",
        "break_times",
        "lunch_break",
    ],
    "classes": [
        "name",
        "section",
        "semester",
        "student_count",
        "department_code",
        "batch_name",
        "room_code",
    ],
    "rooms": ["name", "code", "room_type", "capacity", "department_code"],
    "subjects": [
        "name",
        "code",
        "hours_per_week",
        "credits",
        "requires_lab",
        "department_codes",
        "batch_name",
    ],
    "faculty": [
        "name",
        "email",
        "department_code",
        "max_hours_per_week",
        "unavailable_slots",
    ],
    "mappings": [
        "subject_code",
        "class_name",
        "class_section",
        "faculty_email",
        "room_code",
    ],
}

ALLOWED_IMPORT_TYPES = {
    "departments",
    "batches",
    "classes",
    "rooms",
    "subjects",
    "faculty",
    "mappings",
}
IMPORT_ORDER = [
    "departments",
    "batches",
    "rooms",
    "classes",
    "subjects",
    "faculty",
    "mappings",
]
MAX_ISSUES = 50

REQUIRED_HEADERS = {
    "departments": ["name", "code"],
    "batches": ["name"],
    "classes": ["name"],
    "rooms": ["name"],
    "subjects": ["name", "code"],
    "faculty": ["name", "email"],
    "mappings": ["subject_code", "class_name", "faculty_email"],
}


def normalize_string(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def similarity_score(s1: str, s2: str) -> float:
    s1_norm, s2_norm = normalize_string(s1), normalize_string(s2)
    if not s1_norm or not s2_norm:
        return 0.0
    if s1_norm == s2_norm:
        return 1.0
    if s1_norm in s2_norm or s2_norm in s1_norm:
        return 0.85

    # Simple edit distance
    len_s1, len_s2 = len(s1_norm), len(s2_norm)
    matrix = [[0] * (len_s2 + 1) for _ in range(len_s1 + 1)]
    for i in range(len_s1 + 1):
        matrix[i][0] = i
    for j in range(len_s2 + 1):
        matrix[0][j] = j
    for i in range(1, len_s1 + 1):
        for j in range(1, len_s2 + 1):
            cost = 0 if s1_norm[i - 1] == s2_norm[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j - 1] + cost
            )
    dist = matrix[len_s1][len_s2]
    return 1.0 - (dist / max(len_s1, len_s2))


def map_headers(uploaded_headers: List[str], import_type: str) -> dict:
    """
    Returns a mapping dict: target_header_name -> uploaded_header_name
    or raises HTTPException if a required header is missing.
    """
    expected = EXPECTED_HEADERS.get(import_type, [])
    required = REQUIRED_HEADERS.get(import_type, [])
    mapping = {}
    used_headers = set()

    duplicate_headers = []
    seen_headers = set()
    for header in uploaded_headers:
        normalized = normalize_string(header)
        if not normalized:
            continue
        if normalized in seen_headers:
            duplicate_headers.append(header)
        seen_headers.add(normalized)

    if duplicate_headers:
        raise HTTPException(
            status_code=400,
            detail=f"Duplicate CSV column(s): {', '.join(duplicate_headers)}. Please keep each column name unique.",
        )

    for target in expected:
        best_score = 0.0
        best_header = None

        # 1. Match via defined aliases
        target_aliases = COMMON_ALIASES.get(target, [])
        normalized_aliases = {normalize_string(a) for a in target_aliases}
        normalized_aliases.add(normalize_string(target))
        for h in uploaded_headers:
            if h in used_headers:
                continue
            h_norm = normalize_string(h)
            if h_norm in normalized_aliases:
                best_score = 1.0
                best_header = h
                break

        # 2. Fallback to similarity
        if best_score < 1.0:
            for h in uploaded_headers:
                if h in used_headers:
                    continue
                score = similarity_score(h, target)
                if score > best_score:
                    best_score = score
                    best_header = h

        # Apply matched header if confidence is high enough
        if best_header and best_score >= 0.65:
            mapping[target] = best_header
            used_headers.add(best_header)

    # Check for missing required headers
    missing = []
    for req in required:
        if req not in mapping:
            missing.append(req)

    if missing:
        # Provide suggestions
        detail = (
            f"Missing required column(s): {', '.join(missing)} for type '{import_type}'.\n"
            f"Uploaded headers were: {', '.join(uploaded_headers)}.\n"
            "Please ensure your CSV matches the template layout."
        )
        raise HTTPException(status_code=400, detail=detail)

    return mapping


def _decode_csv_content(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(
        status_code=400, detail="Could not decode CSV file. Please upload a UTF-8 CSV."
    )


def _read_csv_rows(
    content: bytes,
) -> Tuple[List[str], List[Tuple[int, Dict[str, str]]]]:
    text = _decode_csv_content(content)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = [h.strip() for h in (reader.fieldnames or []) if h and h.strip()]
    rows = []
    for row_number, row in enumerate(reader, start=2):
        cleaned = {}
        for key, value in row.items():
            key = (key or "").strip()
            if not key:
                continue
            if isinstance(value, list):
                value = ";".join(str(item) for item in value if item is not None)
            cleaned[key] = ("" if value is None else str(value)).strip()
        rows.append((row_number, cleaned))
    return headers, rows


def _guess_import_type(filename: str) -> Optional[str]:
    base_name = os.path.basename(filename or "").lower()
    if not base_name.endswith(".csv"):
        return None

    stem = os.path.splitext(base_name)[0]
    stem = re.sub(r"\s*\(\d+\)$", "", stem)
    for suffix in ("_template", "-template", " template"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]

    aliases = {
        "department": "departments",
        "departments": "departments",
        "batch": "batches",
        "batches": "batches",
        "class": "classes",
        "classes": "classes",
        "room": "rooms",
        "rooms": "rooms",
        "subject": "subjects",
        "subjects": "subjects",
        "faculty": "faculty",
        "faculties": "faculty",
        "mapping": "mappings",
        "mappings": "mappings",
        "faculty_mapping": "mappings",
        "faculty_mappings": "mappings",
    }
    normalized_stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    if normalized_stem in aliases:
        return aliases[normalized_stem]

    tokens = [token for token in normalized_stem.split("_") if token]
    token_set = set(tokens)
    if "faculty" in token_set and ({"mapping", "mappings"} & token_set):
        return "mappings"
    for token in tokens:
        if token in aliases:
            return aliases[token]
    return None


def _empty_result(import_type: str) -> Dict[str, Any]:
    return {
        "imported": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "type": import_type,
        "warnings": [],
        "errors": [],
        "warning_count": 0,
        "error_count": 0,
    }


def _record_issue(
    result: Dict[str, Any], bucket: str, row_number: Optional[int], message: str
):
    count_key = "error_count" if bucket == "errors" else "warning_count"
    result[count_key] += 1
    if len(result[bucket]) < MAX_ISSUES:
        issue = {"message": message}
        if row_number is not None:
            issue["row"] = row_number
        result[bucket].append(issue)


def _row_value(row: Dict[str, str], key: str) -> str:
    return (row.get(key) or "").strip()


def _require_value(
    row: Dict[str, str], key: str, row_number: int, result: Dict[str, Any]
) -> Optional[str]:
    value = _row_value(row, key)
    if not value:
        _record_issue(result, "errors", row_number, f"Missing required value '{key}'.")
        return None
    return value


def _parse_int(
    value: str,
    default: int,
    result: Dict[str, Any],
    row_number: int,
    field: str,
    min_value: Optional[int] = None,
) -> int:
    if value == "":
        return default
    try:
        number = float(value)
        if not number.is_integer():
            raise ValueError
        parsed = int(number)
        if min_value is not None and parsed < min_value:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        min_hint = (
            f" greater than or equal to {min_value}" if min_value is not None else ""
        )
        _record_issue(
            result,
            "warnings",
            row_number,
            f"Invalid integer for '{field}'{min_hint}: '{value}'. Used {default}.",
        )
        return default


def _parse_bool(
    value: str,
    result: Dict[str, Any],
    row_number: int,
    field: str,
    default: bool = False,
) -> bool:
    if value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on", "lab", "required"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    _record_issue(
        result,
        "warnings",
        row_number,
        f"Invalid boolean for '{field}': '{value}'. Used {default}.",
    )
    return default


def _parse_time(
    value: str, default: str, result: Dict[str, Any], row_number: int, field: str
) -> str:
    if value == "":
        return default
    match = re.match(r"^(\d{1,2}):(\d{2})$", value.strip())
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    _record_issue(
        result,
        "warnings",
        row_number,
        f"Invalid time for '{field}': '{value}'. Used {default}.",
    )
    return default


def _parse_json_field(
    value: str,
    default: Any,
    expected_type: type,
    result: Dict[str, Any],
    row_number: int,
    field: str,
) -> Any:
    if value == "":
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        _record_issue(
            result,
            "warnings",
            row_number,
            f"Invalid JSON for '{field}'. Used default value.",
        )
        return default
    if not isinstance(parsed, expected_type):
        _record_issue(
            result,
            "warnings",
            row_number,
            f"JSON field '{field}' must be {expected_type.__name__}. Used default value.",
        )
        return default
    return parsed


def _lookup_value(value: str) -> str:
    return (value or "").strip().casefold()


def _find_one_by_any(
    db, collection_name: str, fields: List[str], value: str
) -> Optional[dict]:
    value = (value or "").strip()
    if not value:
        return None
    collection = db[collection_name]
    for field in fields:
        doc = collection.find_one({field: value})
        if doc:
            return doc

    needle = _lookup_value(value)
    for doc in collection.find({}):
        for field in fields:
            if _lookup_value(str(doc.get(field) or "")) == needle:
                return doc
    return None


def _find_department(db, code_or_name: str) -> Optional[dict]:
    return _find_one_by_any(db, "departments", ["code", "name"], code_or_name)


def _find_batch(db, name: str) -> Optional[dict]:
    return _find_one_by_any(db, "batches", ["name"], name)


def _find_room(db, code_or_name: str) -> Optional[dict]:
    return _find_one_by_any(db, "rooms", ["code", "name"], code_or_name)


def _find_faculty(db, query_str: str) -> Optional[dict]:
    if not query_str:
        return None
    return _find_one_by_any(db, "faculty", ["email", "name"], query_str)


def _find_class(db, name: str, section: str = "") -> Optional[dict]:
    name = (name or "").strip()
    section = (section or "").strip()
    if not name:
        return None

    query = {"name": name}
    if section:
        query["section"] = section
    doc = db["classes"].find_one(query)
    if doc:
        return doc

    name_norm = _lookup_value(name)
    section_norm = _lookup_value(section)
    for class_doc in db["classes"].find({}):
        if _lookup_value(str(class_doc.get("name") or "")) != name_norm:
            continue
        if (
            section
            and _lookup_value(str(class_doc.get("section") or "")) != section_norm
        ):
            continue
        return class_doc
    return None


def _find_core_subject(db, code: str) -> Optional[dict]:
    code = (code or "").strip()
    if not code:
        return None

    exact_queries = [
        {"code": code, "source_subject_id": {"$exists": False}, "class_id": None},
        {"code": code, "source_subject_id": {"$exists": False}},
        {"code": code},
    ]
    for query in exact_queries:
        doc = db["subjects"].find_one(query)
        if doc:
            return doc

    code_norm = _lookup_value(code)
    fallback = None
    for subject in db["subjects"].find({}):
        if _lookup_value(str(subject.get("code") or "")) != code_norm:
            continue
        if subject.get("source_subject_id"):
            continue
        if not subject.get("class_id"):
            return subject
        fallback = fallback or subject
    return fallback


def _find_existing_subject_mapping(
    db, subject: dict, source_id: str, class_id: str
) -> Optional[dict]:
    for existing in db["subjects"].find({"class_id": class_id}):
        if str(existing.get("source_subject_id") or "") == str(source_id):
            return existing
        if str(existing.get("_id")) == str(source_id):
            return existing
        if (
            not existing.get("source_subject_id")
            and existing.get("code") == subject.get("code")
            and existing.get("name") == subject.get("name")
            and existing.get("requires_lab", False)
            == subject.get("requires_lab", False)
        ):
            return existing
    return None


def _mark_saved(result: Dict[str, Any], inserted: bool):
    result["imported"] += 1
    result["inserted" if inserted else "updated"] += 1


def _save_document(
    db,
    collection_name: str,
    existing: Optional[dict],
    document: dict,
    result: Dict[str, Any],
    on_insert: Optional[dict] = None,
):
    now = _utcnow()
    update_doc = {**document, "updated_at": now}
    if existing:
        db[collection_name].update_one({"_id": existing["_id"]}, {"$set": update_doc})
        _mark_saved(result, inserted=False)
        return existing["_id"]

    insert_doc = {**(on_insert or {}), **document, "created_at": now}
    insert_result = db[collection_name].insert_one(insert_doc)
    _mark_saved(result, inserted=True)
    return insert_result.inserted_id


def _split_codes(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[;,]", value) if item.strip()]


def _normalize_rows(
    headers: List[str],
    raw_rows: List[Tuple[int, Dict[str, str]]],
    import_type: str,
    result: Dict[str, Any],
) -> List[Tuple[int, Dict[str, str]]]:
    if not headers:
        raise HTTPException(
            status_code=400, detail="The uploaded CSV has no header row."
        )
    if not raw_rows:
        result["message"] = "The uploaded CSV file is empty."
        return []

    header_mapping = map_headers(headers, import_type)
    rows = []
    for row_number, raw_row in raw_rows:
        norm_row = {}
        for target_key, uploaded_key in header_mapping.items():
            norm_row[target_key] = raw_row.get(uploaded_key, "").strip()
        if not any(value for value in norm_row.values()):
            result["skipped"] += 1
            continue
        rows.append((row_number, norm_row))
    if not rows:
        result["message"] = "The uploaded CSV file has no data rows."
    return rows


def _import_departments(
    db, rows: List[Tuple[int, Dict[str, str]]], result: Dict[str, Any]
):
    for row_number, row in rows:
        name = _row_value(row, "name")
        code = _row_value(row, "code")
        if not name and not code:
            result["skipped"] += 1
            continue
        if not name:
            name = "[Missing Name]"
            _record_issue(result, "warnings", row_number, "Department name is missing.")
        if not code:
            code = ""
            _record_issue(result, "warnings", row_number, "Department code is missing.")
        existing = _find_department(db, code) if code else None
        _save_document(
            db, "departments", existing, {"name": name, "code": code}, result
        )


def _import_batches(db, rows: List[Tuple[int, Dict[str, str]]], result: Dict[str, Any]):
    for row_number, row in rows:
        name = _row_value(row, "name")
        if not name:
            name = "[Missing Name]"
            _record_issue(result, "warnings", row_number, "Batch name is missing.")
        document = {
            "name": name,
            "start_time": _parse_time(
                _row_value(row, "start_time"), "09:00", result, row_number, "start_time"
            ),
            "end_time": _parse_time(
                _row_value(row, "end_time"), "17:00", result, row_number, "end_time"
            ),
            "period_duration": _parse_int(
                _row_value(row, "period_duration"),
                60,
                result,
                row_number,
                "period_duration",
                min_value=1,
            ),
            "break_times": _parse_json_field(
                _row_value(row, "break_times"),
                [],
                list,
                result,
                row_number,
                "break_times",
            ),
            "lunch_break": _parse_json_field(
                _row_value(row, "lunch_break"),
                {},
                dict,
                result,
                row_number,
                "lunch_break",
            ),
        }
        existing = _find_batch(db, name)
        _save_document(db, "batches", existing, document, result)


def _import_rooms(db, rows: List[Tuple[int, Dict[str, str]]], result: Dict[str, Any]):
    for row_number, row in rows:
        name = _row_value(row, "name")
        code = _row_value(row, "code")
        if not name and not code:
            result["skipped"] += 1
            continue
        if not name:
            name = f"[Missing Room Name {row_number}]"
            _record_issue(result, "warnings", row_number, "Room name is missing.")
        if not code:
            code = ""
            _record_issue(result, "warnings", row_number, "Room code is missing.")

        dept = _find_department(db, _row_value(row, "department_code")) if _row_value(row, "department_code") else None
        if _row_value(row, "department_code") and not dept:
            _record_issue(
                result,
                "warnings",
                row_number,
                f"Department '{_row_value(row, 'department_code')}' not found for room '{name}'.",
            )

        room_type = (_row_value(row, "room_type") or "lecture").lower()
        if room_type not in {"lecture", "lab", "seminar"}:
            room_type = "lecture"

        document = {
            "name": name,
            "code": code,
            "room_type": room_type,
            "capacity": _parse_int(
                _row_value(row, "capacity"),
                0,
                result,
                row_number,
                "capacity",
                min_value=0,
            ),
            "department_id": str(dept["_id"]) if dept else None,
        }
        existing = _find_room(db, code or name)
        _save_document(db, "rooms", existing, document, result)


def _import_classes(db, rows: List[Tuple[int, Dict[str, str]]], result: Dict[str, Any]):
    for row_number, row in rows:
        name = _row_value(row, "name")
        if not name:
            name = f"[Missing Class Name {row_number}]"
            _record_issue(result, "warnings", row_number, "Class name is missing.")

        dept = _find_department(db, _row_value(row, "department_code")) if _row_value(row, "department_code") else None
        batch = _find_batch(db, _row_value(row, "batch_name")) if _row_value(row, "batch_name") else None
        room = _find_room(db, _row_value(row, "room_code")) if _row_value(row, "room_code") else None

        section = _row_value(row, "section")
        document = {
            "name": name,
            "section": section,
            "semester": _parse_int(
                _row_value(row, "semester"),
                1,
                result,
                row_number,
                "semester",
                min_value=1,
            ),
            "student_count": _parse_int(
                _row_value(row, "student_count"),
                0,
                result,
                row_number,
                "student_count",
                min_value=0,
            ),
            "department_id": str(dept["_id"]) if dept else None,
            "batch_id": str(batch["_id"]) if batch else None,
            "room_id": str(room["_id"]) if room else None,
        }
        existing = _find_class(db, name, section)
        _save_document(db, "classes", existing, document, result)


def _import_subjects(
    db, rows: List[Tuple[int, Dict[str, str]]], result: Dict[str, Any]
):
    for row_number, row in rows:
        name = _row_value(row, "name")
        code = _row_value(row, "code")
        if not name and not code:
            result["skipped"] += 1
            continue
        if not name:
            name = f"[Missing Subject Name {row_number}]"
            _record_issue(result, "warnings", row_number, "Subject name is missing.")
        if not code:
            code = f"MISSING_{row_number}"
            _record_issue(result, "warnings", row_number, "Subject code is missing.")

        department_ids = []
        for department_code in _split_codes(_row_value(row, "department_codes")):
            dept = _find_department(db, department_code)
            if dept:
                department_ids.append(str(dept["_id"]))

        batch = _find_batch(db, _row_value(row, "batch_name")) if _row_value(row, "batch_name") else None

        document = {
            "name": name,
            "code": code,
            "hours_per_week": _parse_int(
                _row_value(row, "hours_per_week"),
                0,
                result,
                row_number,
                "hours_per_week",
                min_value=0,
            ),
            "credits": _parse_int(
                _row_value(row, "credits"),
                3,
                result,
                row_number,
                "credits",
                min_value=0,
            ),
            "requires_lab": _parse_bool(
                _row_value(row, "requires_lab"), result, row_number, "requires_lab"
            ),
            "department_ids": department_ids,
            "department_id": department_ids[0] if department_ids else None,
            "batch_id": str(batch["_id"]) if batch else None,
        }
        existing = _find_core_subject(db, code)
        _save_document(
            db,
            "subjects",
            existing,
            document,
            result,
            on_insert={"class_id": None, "faculty_id": None},
        )


def _import_faculty(db, rows: List[Tuple[int, Dict[str, str]]], result: Dict[str, Any]):
    for row_number, row in rows:
        name = _row_value(row, "name")
        email = _row_value(row, "email")
        if not name and not email:
            result["skipped"] += 1
            continue
        if not name:
            name = f"[Missing Faculty Name {row_number}]"
            _record_issue(result, "warnings", row_number, "Faculty name is missing.")
        if not email:
            email = ""
            _record_issue(result, "warnings", row_number, "Faculty email is missing.")
        else:
            email = email.lower()

        dept = _find_department(db, _row_value(row, "department_code")) if _row_value(row, "department_code") else None

        document = {
            "name": name,
            "email": email,
            "department_id": str(dept["_id"]) if dept else None,
            "max_hours_per_week": _parse_int(
                _row_value(row, "max_hours_per_week"),
                20,
                result,
                row_number,
                "max_hours_per_week",
                min_value=0,
            ),
            "unavailable_slots": _parse_json_field(
                _row_value(row, "unavailable_slots"),
                [],
                list,
                result,
                row_number,
                "unavailable_slots",
            ),
        }
        existing = _find_faculty(db, email or name)
        _save_document(db, "faculty", existing, document, result)


def _import_mappings(
    db, rows: List[Tuple[int, Dict[str, str]]], result: Dict[str, Any]
):
    for row_number, row in rows:
        subject_code = _row_value(row, "subject_code")
        class_name = _row_value(row, "class_name")
        faculty_email = _row_value(row, "faculty_email")
        if not subject_code and not class_name and not faculty_email:
            result["skipped"] += 1
            continue

        subj = _find_core_subject(db, subject_code) if subject_code else None
        cls = _find_class(db, class_name, _row_value(row, "class_section")) if class_name else None
        fac = _find_faculty(db, faculty_email) if faculty_email else None
        room = _find_room(db, _row_value(row, "room_code")) if _row_value(row, "room_code") else None

        if not subj and subject_code:
            doc = {"name": f"Subject {subject_code}", "code": subject_code, "credits": 3, "requires_lab": False}
            existing = _find_core_subject(db, subject_code)
            subj_id = _save_document(db, "subjects", existing, doc, result, on_insert={"class_id": None, "faculty_id": None})
            subj = db["subjects"].find_one({"_id": subj_id})

        if not cls and class_name:
            doc = {"name": class_name, "section": _row_value(row, "class_section")}
            existing = _find_class(db, class_name, _row_value(row, "class_section"))
            cls_id = _save_document(db, "classes", existing, doc, result)
            cls = db["classes"].find_one({"_id": cls_id})

        if not fac and faculty_email:
            doc = {"name": faculty_email.split('@')[0].capitalize(), "email": faculty_email.lower()}
            existing = _find_faculty(db, faculty_email)
            fac_id = _save_document(db, "faculty", existing, doc, result)
            fac = db["faculty"].find_one({"_id": fac_id})

        if subj and cls:
            class_id = str(cls["_id"])
            faculty_id = str(fac["_id"]) if fac else None
            if room:
                db["classes"].update_one(
                    {"_id": cls["_id"]},
                    {"$set": {"room_id": str(room["_id"]), "updated_at": _utcnow()}},
                )

            source_id = subj.get("source_subject_id") or str(subj["_id"])
            document = {
                "name": subj.get("name") or "",
                "code": subj.get("code") or "",
                "hours_per_week": subj.get("hours_per_week"),
                "credits": subj.get("credits", 3),
                "requires_lab": subj.get("requires_lab", False),
                "department_id": subj.get("department_id"),
                "department_ids": subj.get("department_ids")
                or ([subj.get("department_id")] if subj.get("department_id") else []),
                "batch_id": subj.get("batch_id"),
                "class_id": class_id,
                "faculty_id": faculty_id,
                "source_subject_id": source_id,
            }
            existing = _find_existing_subject_mapping(db, subj, source_id, class_id)
            _save_document(db, "subjects", existing, document, result)


IMPORT_HANDLERS = {
    "departments": _import_departments,
    "batches": _import_batches,
    "classes": _import_classes,
    "rooms": _import_rooms,
    "subjects": _import_subjects,
    "faculty": _import_faculty,
    "mappings": _import_mappings,
}


def _import_csv_data(import_type: str, content: bytes, db) -> Dict[str, Any]:
    result = _empty_result(import_type)
    headers, raw_rows = _read_csv_rows(content)
    rows = _normalize_rows(headers, raw_rows, import_type, result)
    if rows:
        IMPORT_HANDLERS[import_type](db, rows, result)
    if result["error_count"] > len(result["errors"]):
        result["message"] = (
            f"{result.get('message', '')} Showing first {MAX_ISSUES} errors.".strip()
        )
    if result["warning_count"] > len(result["warnings"]):
        result["message"] = (
            f"{result.get('message', '')} Showing first {MAX_ISSUES} warnings.".strip()
        )
    if "message" not in result:
        parts = [f"Imported {result['imported']} {import_type} row(s)."]
        if result["skipped"]:
            parts.append(f"Skipped {result['skipped']} row(s).")
        if result["warning_count"]:
            parts.append(f"{result['warning_count']} warning(s).")
        if result["error_count"]:
            parts.append(f"{result['error_count']} error(s).")
        result["message"] = " ".join(parts)
    return result


async def _import_upload_file(import_type: str, file: UploadFile, db) -> Dict[str, Any]:
    import_type = (import_type or "").strip().lower()
    if import_type not in ALLOWED_IMPORT_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Unsupported import type: {import_type}"
        )
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    content = await file.read()
    if not content:
        result = _empty_result(import_type)
        result["message"] = "The uploaded CSV file is empty."
        return result

    try:
        return _import_csv_data(import_type, content, db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV Parsing Error: {str(e)}")


@router.post("/upload")
async def upload_csv(
    type: str = Form(...),
    file: UploadFile = File(...),
    db=Depends(get_tenant_db),
    _current_user: dict = Depends(get_admin_user),
):
    """Upload a CSV and import data. Form param `type` selects which importer to run.
    Supported types: departments, batches, classes, rooms, subjects, faculty, mappings
    """
    result = await _import_upload_file(type, file, db)
    return JSONResponse(result)


@router.post("/upload-folder")
async def upload_csv_folder(
    files: List[UploadFile] = File(...),
    db=Depends(get_tenant_db),
    _current_user: dict = Depends(get_admin_user),
):
    """Upload a folder worth of CSV files and import recognized files in dependency order."""
    file_by_type = {}
    results = []

    for file in files:
        import_type = _guess_import_type(file.filename)
        if not import_type:
            results.append(
                {
                    "file": file.filename,
                    "type": None,
                    "status": "skipped",
                    "message": "Not a recognized CSV import file.",
                }
            )
            continue
        if import_type in file_by_type:
            results.append(
                {
                    "file": file.filename,
                    "type": import_type,
                    "status": "skipped",
                    "message": f"Duplicate {import_type} CSV. The first matching file was used.",
                }
            )
            continue
        file_by_type[import_type] = file

    total_imported = 0
    processed = 0

    for import_type in IMPORT_ORDER:
        file = file_by_type.get(import_type)
        if not file:
            continue

        try:
            data = await _import_upload_file(import_type, file, db)
            imported = int(data.get("imported") or 0)
            total_imported += imported
            processed += 1
            status = "partial" if data.get("error_count") else "success"
            results.append(
                {
                    "file": file.filename,
                    "type": import_type,
                    "status": status,
                    "imported": imported,
                    "inserted": data.get("inserted", 0),
                    "updated": data.get("updated", 0),
                    "skipped": data.get("skipped", 0),
                    "warnings": data.get("warnings", []),
                    "errors": data.get("errors", []),
                    "warning_count": data.get("warning_count", 0),
                    "error_count": data.get("error_count", 0),
                    "message": data.get("message")
                    or f"Imported {imported} {import_type}.",
                }
            )
        except HTTPException as exc:
            results.append(
                {
                    "file": file.filename,
                    "type": import_type,
                    "status": "failed",
                    "message": exc.detail,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "file": file.filename,
                    "type": import_type,
                    "status": "failed",
                    "message": str(exc),
                }
            )

    missing = [
        import_type for import_type in IMPORT_ORDER if import_type not in file_by_type
    ]
    failed = [item for item in results if item.get("status") == "failed"]
    partial = [item for item in results if item.get("status") == "partial"]

    return JSONResponse(
        {
            "imported": total_imported,
            "processed": processed,
            "failed": len(failed),
            "partial": len(partial),
            "missing": missing,
            "results": results,
        }
    )


# ── Document Entity Extraction and Filling ──────────────────────────────────────

ACADEMIC_EXTRACTOR_SYSTEM_PROMPT = """You are a STRICT academic data extractor.

## ABSOLUTE RULES — NEVER VIOLATE THESE

1. **EXTRACT ONLY.** You may ONLY output data that is EXPLICITLY and LITERALLY present in the provided document text/image.
2. **NO HALLUCINATION.** Do NOT invent, guess, assume, infer, or generate ANY data that is not directly written in the document. This includes names, codes, times, numbers, or any other value.
3. **NO EXAMPLES.** Do NOT use placeholder values such as "faculty@university.edu", "DEPT_CODE", "SUBJ101", "Room 101", or any example-like strings. If the real value is not in the document, use "" (empty string) or null.
4. **NO MOCK DATA.** Do NOT fill in "reasonable" defaults or "typical" values. Leave every field empty ("") if it cannot be found verbatim in the source document.
5. **MISSING = EMPTY.** If a field (code, section, department, batch, room, etc.) is not explicitly stated in the document, set it to "" or null. Do not construct or fabricate it.

## Task

Analyze the provided document and extract ONLY entities that are explicitly mentioned. Map them into the JSON structure below.

## Output Format

Return ONLY a single raw JSON object — no markdown fences, no reasoning text, no notes, no explanation.

{
  "departments": [
    {"name": "<exact name from doc>", "code": "<exact code from doc or ''>"}
  ],
  "batches": [
    {"name": "<exact name from doc>", "start_time": "<exact start time e.g. '09:00' or ''>", "end_time": "<exact end time e.g. '16:30' or ''>", "period_duration": <number of minutes e.g. 50 or 60>, "break_times": "<exact break times e.g. '11:00-11:15' or ''>", "lunch_break": "<exact lunch break time e.g. '13:00-14:00' or ''>"}
  ],
  "classes": [
    {"name": "<exact name from doc>", "section": "<exact section from doc or ''>", "department_code": "<exact code from doc or ''>", "batch_name": "<exact name from doc or ''>", "semester": <number or null>, "student_count": <number or 0>}
  ],
  "rooms": [
    {"name": "<exact name from doc>", "code": "<exact code from doc or ''>", "room_type": "lecture", "capacity": <number or 0>, "department_code": "<exact code from doc or ''>"}
  ],
  "subjects": [
    {"name": "<exact name from doc>", "code": "<exact code from doc or ''>", "hours_per_week": <number or 0>, "requires_lab": false, "department_codes": "<exact code from doc or ''>", "batch_name": "<exact name from doc or ''>"}
  ],
  "faculty": [
    {"name": "<exact name from doc>", "email": "<exact email from doc or ''>", "department_code": "<exact code from doc or ''>"}
  ],
  "mappings": [
    {"subject_code": "<exact code from doc or ''>", "class_name": "<exact name from doc>", "class_section": "<exact section from doc or ''>", "faculty_email": "<exact email from doc or ''>", "room_code": "<exact code from doc or ''>"}
  ]
}

## Additional Rules

- For batches: Look at timetable period column/row slot headers or schedule headers to extract start_time (e.g. '09:00'), end_time (e.g. '16:30'), period_duration (e.g. 50 or 60), break_times (e.g. '11:00-11:15'), and lunch_break (e.g. '13:00-14:00').
- room_type must be one of: ["lecture", "lab", "seminar"]. Default to "lecture" only if the room is mentioned but its type is not specified.
- If the document contains NO information for a category (e.g. no rooms mentioned), return an empty list [] for that key.
- Do NOT output any markdown code blocks, reasoning, commentary, or extra text. Output ONLY the raw JSON object.
"""


def _split_text_into_chunks(text: str, max_chars: int = 8000) -> list:
    """Split document text into chunks, preferring to split on 'Sheet:' boundaries.

    For multi-sheet Excel files, the text contains lines like 'Sheet: SheetName'.
    We group text by sheets and create chunks that fit within max_chars,
    combining small sheets together and splitting large sheets if needed.
    """
    import re
    # Split on 'Sheet:' headers (produced by the xlsx extractor)
    sheet_pattern = re.compile(r'^Sheet:\s+', re.MULTILINE)
    parts = sheet_pattern.split(text)
    headers = sheet_pattern.findall(text)

    # If no sheet headers found, just split the text by size
    if len(parts) <= 1:
        chunks = []
        for i in range(0, len(text), max_chars):
            chunks.append(text[i:i + max_chars])
        return chunks if chunks else [text]

    # Rebuild sheet sections: first part is pre-header content, rest are sheets
    sections = []
    if parts[0].strip():
        sections.append(parts[0].strip())
    for i, part in enumerate(parts[1:], 0):
        header = headers[i] if i < len(headers) else "Sheet: "
        sections.append(f"{header}{part}".strip())

    # Group sections into chunks that fit within max_chars
    chunks = []
    current_chunk = ""
    for section in sections:
        if not section.strip():
            continue
        # If adding this section would exceed the limit
        if current_chunk and len(current_chunk) + len(section) + 2 > max_chars:
            chunks.append(current_chunk)
            # If the section itself is too large, split it
            if len(section) > max_chars:
                for i in range(0, len(section), max_chars):
                    chunks.append(section[i:i + max_chars])
                current_chunk = ""
            else:
                current_chunk = section
        else:
            current_chunk = f"{current_chunk}\n\n{section}".strip() if current_chunk else section

    if current_chunk.strip():
        chunks.append(current_chunk)

    return chunks if chunks else [text[:max_chars]]


def _dedupe_extracted_list(items: list) -> list:
    """Remove duplicate dicts from a list, preserving order.

    Uses a JSON serialization of sorted keys for comparison.
    """
    import json
    seen = set()
    unique = []
    for item in items:
        if isinstance(item, dict):
            # Normalize: lowercase name/code fields for comparison
            key_parts = []
            for k in sorted(item.keys()):
                v = item.get(k, "")
                if isinstance(v, str):
                    key_parts.append(f"{k}={v.strip().lower()}")
                else:
                    key_parts.append(f"{k}={v}")
            key = "|".join(key_parts)
        else:
            key = json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


@router.post('/extract-academic-data')
async def extract_academic_data(
    file: UploadFile = File(...),
    qwen_api_key: Optional[str] = Form(None),
    db=Depends(get_tenant_db),
    _current_user: dict = Depends(get_admin_user),
):
    """
    Extract academic data from a document (image/PDF) using OCR and Qwen API concurrently.
    Returns a stream of NDJSON progress updates and the final merged structured entities.
    """
    from ...core.config import settings
    from ...services.document_constraints import extract_document_text
    import urllib.request
    import json
    import asyncio
    import base64
    import io
    import threading
    from typing import Optional

    content = await file.read()
    if len(content) > settings.DOCUMENT_UPLOAD_MAX_FILE_BYTES:
        limit_mb = settings.DOCUMENT_UPLOAD_MAX_FILE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"{file.filename or 'Uploaded file'} is larger than the {limit_mb} MB limit.",
        )

    async def generate_progress():
        main_queue = asyncio.Queue()
        active_tasks = 0

        # Try to extract images for Qwen Vision
        ext = (file.filename or "").lower().split(".")[-1]
        images_base64 = []
        if ext in {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tif', 'tiff'}:
            images_base64.append(base64.b64encode(content).decode('utf-8'))
        elif ext == 'pdf':
            try:
                from pdf2image import convert_from_bytes
                pages = await asyncio.to_thread(convert_from_bytes, content, first_page=1, last_page=settings.DOCUMENT_OCR_MAX_PAGES)
                for page in pages:
                    buffer = io.BytesIO()
                    page.save(buffer, format="JPEG")
                    images_base64.append(base64.b64encode(buffer.getvalue()).decode('utf-8'))
            except Exception as e:
                await main_queue.put(("data", json.dumps({"status": "log", "text": f"\n[System] PDF to image conversion failed (will fallback to text): {e}\n"}) + "\n"))

        doc_text_result = {"text": "", "warnings": [], "extractor": "none"}
        extracted_data_result = {
            "departments": [], "batches": [], "classes": [], "rooms": [],
            "subjects": [], "faculty": [], "mappings": []
        }
        
        async def ocr_task():
            try:
                await main_queue.put(("data", json.dumps({"status": "progress", "progress": 10, "message": "[PaddleOCR] Running extraction..."}) + "\n"))
                doc = await asyncio.to_thread(
                    extract_document_text,
                    file.filename or "uploaded-file",
                    content,
                    file.content_type,
                    max_chars=settings.DOCUMENT_TEXT_MAX_CHARS,
                    ocr_max_pages=settings.DOCUMENT_OCR_MAX_PAGES,
                )
                doc_text_result["text"] = doc.text
                doc_text_result["warnings"] = list(doc.warnings)
                doc_text_result["extractor"] = doc.extractor
                await main_queue.put(("data", json.dumps({"status": "log", "text": f"\n[PaddleOCR] Extracted {len(doc.text)} characters.\n"}) + "\n"))
            except Exception as e:
                await main_queue.put(("data", json.dumps({"status": "log", "text": f"\n[PaddleOCR] Failed: {e}\n"}) + "\n"))
            finally:
                # Mark done, in case Qwen is waiting for text
                if not doc_text_result["text"]:
                    doc_text_result["text"] = " " # unblock qwen
                await main_queue.put(("task_done", "ocr"))

        async def qwen_task(images, wait_for_text=False):
            try:
                active_key = qwen_api_key or settings.active_document_analysis_api_key
                model_name = settings.active_document_analysis_model or "qwen-plus"
                api_base = settings.active_document_analysis_api_base.rstrip("/")
                
                timeout = max(settings.DOCUMENT_ANALYSIS_TIMEOUT_SECONDS, 900)
                
                chunks = []
                is_image = False
                if images:
                    chunks = images
                    is_image = True
                else:
                    if wait_for_text:
                        # Wait for OCR task to finish to get the text
                        while not doc_text_result["text"]:
                            await asyncio.sleep(0.5)
                        chunks = _split_text_into_chunks(doc_text_result["text"], 4000)
                    else:
                        chunks = _split_text_into_chunks(doc_text_result["text"], 4000)

                if not chunks or (not is_image and not chunks[0].strip()):
                    await main_queue.put(("data", json.dumps({"status": "log", "text": "\n[Qwen] No data to process.\n"}) + "\n"))
                    return

                for i, chunk in enumerate(chunks):
                    progress_pct = 30 + int(60 * (i / len(chunks)))
                    await main_queue.put(("data", json.dumps({"status": "progress", "progress": progress_pct, "message": f"[Qwen API] Processing part {i+1}/{len(chunks)}..."}) + "\n"))
                    
                    messages = [{"role": "system", "content": ACADEMIC_EXTRACTOR_SYSTEM_PROMPT}]
                    if is_image:
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract ONLY the academic entities that are explicitly and literally visible in this document image. Do NOT invent, guess, or hallucinate any values. Any field not clearly present in the image must be set to \"\" or null. Return ONLY a valid JSON object with no extra text."},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{chunk}"}}
                            ]
                        })
                    else:
                        messages.append({
                            "role": "user",
                            "content": (
                                "Extract ONLY the academic entities that are explicitly and literally present in the following document text. "
                                "Do NOT invent, guess, infer, or hallucinate any values. "
                                "If a field (email, code, section, department, batch, room, etc.) is not clearly stated in the text, set it to \"\" or null. "
                                "Return ONLY a valid JSON object with no extra text.\n\n"
                                f"{chunk}"
                            )
                        })

                    payload = {
                        "model": model_name,
                        "stream": True,
                        "temperature": 0.0,
                        "max_tokens": 8192,
                        "response_format": {"type": "json_object"},
                        "messages": messages
                    }
                    endpoint = f"{api_base}/chat/completions" if not api_base.endswith("/chat/completions") else api_base

                    req_data = json.dumps(payload).encode("utf-8")
                    req = urllib.request.Request(
                        endpoint,
                        data=req_data,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    if active_key:
                        req.add_header("Authorization", f"Bearer {active_key}")

                    stream_queue = asyncio.Queue()
                    loop = asyncio.get_running_loop()
                    def run_sync_stream():
                        try:
                            with urllib.request.urlopen(req, timeout=timeout) as response:
                                for line in response:
                                    if line.strip():
                                        asyncio.run_coroutine_threadsafe(stream_queue.put(("stream_data", line)), loop)
                            asyncio.run_coroutine_threadsafe(stream_queue.put(("stream_done", None)), loop)
                        except Exception as e:
                            asyncio.run_coroutine_threadsafe(stream_queue.put(("stream_error", e)), loop)

                    threading.Thread(target=run_sync_stream, daemon=True).start()
                    
                    content_str = ""
                    while True:
                        msg_type, data = await stream_queue.get()
                        if msg_type == "stream_done":
                            break
                        elif msg_type == "stream_error":
                            raise data
                        elif msg_type == "stream_data":
                            try:
                                token = ""
                                data_str = data.decode("utf-8").strip() if isinstance(data, bytes) else data.strip()
                                if not data_str:
                                    continue
                                
                                if data_str.startswith("data: "):
                                    data_str = data_str[6:]
                                if data_str == "[DONE]":
                                    continue
                                
                                chunk_obj = json.loads(data_str)
                                choices = chunk_obj.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    token = delta.get("content", "")
                                
                                if token:
                                    content_str += token
                                    await main_queue.put(("data", json.dumps({"status": "log", "text": token}) + "\n"))
                            except Exception:
                                pass
                                
                    content_str = content_str.strip()
                    import re as _re
                    content_str = _re.sub(r'<think>.*?</think>', '', content_str, flags=_re.DOTALL).strip()
                    content_str = _re.sub(r'^```(?:json)?\s*', '', content_str).strip()
                    content_str = _re.sub(r'\s*```$', '', content_str).strip()

                    try:
                        parsed = json.loads(content_str)
                    except json.JSONDecodeError:
                        json_start = content_str.find('{')
                        json_end = content_str.rfind('}')
                        if json_start != -1 and json_end != -1:
                            try:
                                parsed = json.loads(content_str[json_start:json_end + 1])
                            except json.JSONDecodeError as inner_e:
                                doc_text_result["warnings"].append(
                                    f"Chunk {i+1}: Qwen model returned invalid JSON ({inner_e}). "
                                    "Try again or check file input."
                                )
                                continue
                        else:
                            doc_text_result["warnings"].append(f"Chunk {i+1}: Could not parse JSON from Qwen response.")
                            continue

                    for key in extracted_data_result.keys():
                        if key in parsed and isinstance(parsed[key], list):
                            extracted_data_result[key].extend(parsed[key])
                        elif key == "faculty" and "faculties" in parsed and isinstance(parsed["faculties"], list):
                            extracted_data_result["faculty"].extend(parsed["faculties"])
                            
            except urllib.error.HTTPError as http_err:
                error_body = http_err.read().decode("utf-8", errors="replace") if hasattr(http_err, 'read') else str(http_err)
                await main_queue.put(("data", json.dumps({"status": "error", "error": f"[Qwen API] HTTP {http_err.code}: {error_body[:500]}"}) + "\n"))
            except urllib.error.URLError as url_err:
                await main_queue.put(("data", json.dumps({"status": "error", "error": f"[Qwen API] Cannot connect to Qwen API ({api_base}). Reason: {url_err.reason}"}) + "\n"))
            except Exception as e:
                await main_queue.put(("data", json.dumps({"status": "error", "error": f"[Qwen API] Error: {e}"}) + "\n"))
            finally:
                await main_queue.put(("task_done", "qwen"))

        try:
            await main_queue.put(("data", json.dumps({"status": "progress", "progress": 5, "message": f"Processing file: {file.filename} ({len(content)} bytes)"}) + "\n"))
            
            # Start Tasks
            asyncio.create_task(ocr_task())
            active_tasks += 1
            
            if images_base64:
                asyncio.create_task(qwen_task(images_base64, wait_for_text=False))
                active_tasks += 1
            else:
                asyncio.create_task(qwen_task([], wait_for_text=True))
                active_tasks += 1
                
            import sys
            # Consume from main_queue
            while active_tasks > 0 or not main_queue.empty():
                try:
                    msg_type, data = await asyncio.wait_for(main_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if active_tasks == 0:
                        break
                    continue

                if msg_type == "data":
                    try:
                        parsed_data = json.loads(data.strip())
                        status = parsed_data.get("status")
                        if status == "log":
                            sys.stdout.write(parsed_data.get("text", ""))
                            sys.stdout.flush()
                        elif status == "progress":
                            print(f"\n[AI EXTRACTOR {parsed_data.get('progress')}%] {parsed_data.get('message')}", flush=True)
                        elif status == "error":
                            print(f"\n[AI EXTRACTOR ERROR] {parsed_data.get('error')}", flush=True)
                    except Exception:
                        pass
                    yield data
                elif msg_type == "task_done":
                    active_tasks -= 1
                    
            print("\n[AI EXTRACTOR 95%] Merging and deduplicating results...", flush=True)
            yield json.dumps({"status": "progress", "progress": 95, "message": "Merging and deduplicating results..."}) + "\n"
            
            # Post-process faculty: generate dummy email if missing
            faculty_email_map = {}
            for idx, fac in enumerate(extracted_data_result.get("faculty", []), start=1):
                fac_name = (fac.get("name") or "").strip()
                fac_email = (fac.get("email") or "").strip()
                if not fac_email:
                    if fac_name:
                        clean_name = _re.sub(r'[^a-zA-Z0-9_]', '.', fac_name.lower().replace(' ', '.')).strip('.')
                        clean_name = _re.sub(r'\.+', '.', clean_name)
                        fac_email = f"{clean_name}@institution.edu" if clean_name else f"faculty_{idx}@institution.edu"
                    else:
                        fac_email = f"faculty_{idx}@institution.edu"
                    fac["email"] = fac_email
                if fac_name:
                    faculty_email_map[fac_name.lower()] = fac_email

            # Post-process mappings: ensure faculty_email is populated if missing
            for m in extracted_data_result.get("mappings", []):
                if not m.get("faculty_email"):
                    fac_name = (m.get("faculty_name") or "").strip().lower()
                    if fac_name in faculty_email_map:
                        m["faculty_email"] = faculty_email_map[fac_name]

            for key in extracted_data_result:
                extracted_data_result[key] = _dedupe_extracted_list(extracted_data_result[key])

            total_extracted = sum(len(v) for v in extracted_data_result.values())
            print(f"\n[AI EXTRACTOR SUCCESS] Extracted {total_extracted} items from {file.filename}\n", flush=True)

            yield json.dumps({
                "status": "success",
                "data": {
                    "extracted_data": extracted_data_result,
                    "warnings": doc_text_result["warnings"],
                    "filename": file.filename,
                    "extractor": doc_text_result["extractor"]
                }
            }) + "\n"

        except Exception as general_exc:
            print(f"\n[AI EXTRACTOR UNEXPECTED ERROR] {str(general_exc)}\n", flush=True)
            yield json.dumps({"status": "error", "error": f"Unexpected error: {str(general_exc)}"}) + "\n"
            
    return StreamingResponse(generate_progress(), media_type="application/x-ndjson")


@router.post('/download-filled-templates')
async def download_filled_templates(data: dict):
    """
    Generate and download a ZIP file of CSV templates pre-filled with the extracted data.
    """
    import csv
    import io
    import zipfile
    from fastapi.responses import StreamingResponse

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for import_type in IMPORT_ORDER:
            headers = []
            if import_type == 'departments':
                headers = ['name', 'code']
            elif import_type == 'batches':
                headers = ['name', 'start_time', 'end_time', 'period_duration', 'break_times', 'lunch_break']
            elif import_type == 'rooms':
                headers = ['name', 'code', 'room_type', 'capacity', 'department_code']
            elif import_type == 'classes':
                headers = ['name', 'section', 'semester', 'student_count', 'department_code', 'batch_name', 'room_code']
            elif import_type == 'subjects':
                headers = ['name', 'code', 'hours_per_week', 'requires_lab', 'department_codes', 'batch_name']
            elif import_type == 'faculty':
                headers = ['name', 'email', 'department_code']
            elif import_type == 'mappings':
                headers = ['subject_code', 'class_name', 'class_section', 'faculty_email', 'room_code']

            items = data.get(import_type, [])
            if not items and import_type == 'faculty' and 'faculties' in data:
                items = data.get('faculties', [])

            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow(headers)

            for item in items:
                row = []
                for h in headers:
                    val = item.get(h, '')
                    if isinstance(val, bool):
                        val = str(val).lower()
                    row.append(val)
                writer.writerow(row)

            csv_content = csv_buffer.getvalue()
            zip_file.writestr(f"{import_type}_template.csv", csv_content)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type='application/zip',
        headers={
            'Content-Disposition': 'attachment; filename=extracted_academic_templates.zip',
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        }
    )


@router.post('/import-extracted-data')
async def import_extracted_data(data: dict, db=Depends(get_tenant_db), _current_user: dict = Depends(get_admin_user)):
    """
    Directly import the extracted JSON data into the database.
    Runs the existing CSV import handlers sequentially to ensure integrity.
    """
    results = {}
    total_imported = 0
    total_skipped = 0
    total_warnings = 0
    total_errors = 0

    for import_type in IMPORT_ORDER:
        items = data.get(import_type, [])
        if not items and import_type == 'faculty' and 'faculties' in data:
            items = data.get('faculties', [])

        if not items:
            continue

        rows = []
        for index, item in enumerate(items, start=1):
            row_dict = {}
            for k, v in item.items():
                row_dict[str(k)] = str(v) if v is not None else ""
            rows.append((index, row_dict))

        result = _empty_result(import_type)
        try:
            IMPORT_HANDLERS[import_type](db, rows, result)
            total_imported += result.get('imported', 0)
            total_skipped += result.get('skipped', 0)
            total_warnings += result.get('warning_count', 0)
            total_errors += result.get('error_count', 0)
            results[import_type] = result
        except Exception as e:
            results[import_type] = {
                "status": "failed",
                "message": f"Import failed: {str(e)}"
            }
            total_errors += 1

    return {
        "status": "completed",
        "imported": total_imported,
        "skipped": total_skipped,
        "warning_count": total_warnings,
        "error_count": total_errors,
        "results": results
    }

def _extract_excel_data(content: bytes) -> dict:
    import openpyxl
    import io

    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    
    extracted_data_result = {
        "departments": [], "batches": [], "classes": [], "rooms": [],
        "subjects": [], "faculty": [], "mappings": []
    }
    warnings = []

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        
        # Guess import type from sheet name
        import_type = _guess_import_type(sheet_name + ".csv")
        if not import_type or import_type not in extracted_data_result:
            warnings.append(f"Sheet '{sheet_name}' was skipped because it did not match any known import type.")
            continue

        # Extract rows
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            warnings.append(f"Sheet '{sheet_name}' is empty.")
            continue

        # Find header row (first row with any data)
        header_row_idx = -1
        for i, row in enumerate(rows):
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            warnings.append(f"Sheet '{sheet_name}' has no headers.")
            continue

        headers = [str(cell).strip() if cell is not None else "" for cell in rows[header_row_idx]]
        
        try:
            # map_headers throws HTTPException if required headers are missing
            header_mapping = map_headers(headers, import_type)
        except HTTPException as e:
            warnings.append(f"Sheet '{sheet_name}': {e.detail}")
            continue

        # Process data rows
        for row_idx in range(header_row_idx + 1, len(rows)):
            row = rows[row_idx]
            
            # Skip if row is completely empty
            if not any(cell is not None and str(cell).strip() != "" for cell in row):
                continue

            raw_row = {}
            for col_idx, header in enumerate(headers):
                if col_idx < len(row):
                    cell_val = row[col_idx]
                    raw_row[header] = str(cell_val).strip() if cell_val is not None else ""
                else:
                    raw_row[header] = ""

            norm_row = {}
            for target_key, uploaded_key in header_mapping.items():
                norm_row[target_key] = raw_row.get(uploaded_key, '').strip()

            extracted_data_result[import_type].append(norm_row)

    # Deduplicate extracted lists
    for key in extracted_data_result:
        extracted_data_result[key] = _dedupe_extracted_list(extracted_data_result[key])

    return {
        "extracted_data": extracted_data_result,
        "warnings": warnings,
        "extractor": "excel"
    }


@router.post('/extract-excel-data')
async def extract_excel_data(
    file: UploadFile = File(...),
    db=Depends(get_tenant_db),
    _current_user: dict = Depends(get_admin_user),
):
    """
    Extract data from an uploaded Excel file, strictly mapping to templates without AI hallucinations.
    Skips empty rows and maps each sheet.
    """
    import asyncio

    if file.filename and not (file.filename.lower().endswith('.xlsx') or file.filename.lower().endswith('.xls')):
        raise HTTPException(status_code=400, detail="Only .xlsx or .xls files are supported for Excel extraction.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        data = await asyncio.to_thread(_extract_excel_data, content)
        data["filename"] = file.filename
        
        return {
            "status": "success",
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process Excel file: {str(e)}")


@router.get("/missing-data-summary")
async def get_missing_data_summary(db=Depends(get_tenant_db), _current_user: dict = Depends(get_admin_user)):
    """
    Scans database collections and returns summary of records with missing or incomplete fields.
    """
    # 1. Departments missing code or name
    depts = list(db["departments"].find())
    missing_depts = [
        {"id": str(d["_id"]), "name": d.get("name") or "[Missing Name]", "missing": [f for f in ["code", "name"] if not d.get(f) or not str(d.get(f)).strip()]}
        for d in depts if not d.get("code") or not str(d.get("code")).strip() or not d.get("name") or not str(d.get("name")).strip()
    ]

    # 2. Batches missing name or start_time/end_time
    batches = list(db["batches"].find())
    missing_batches = [
        {"id": str(b["_id"]), "name": b.get("name") or "[Missing Name]", "missing": [f for f in ["name", "start_time", "end_time"] if not b.get(f) or not str(b.get(f)).strip()]}
        for b in batches if not b.get("name") or not str(b.get("name")).strip() or not b.get("start_time") or not b.get("end_time")
    ]

    # 3. Classes missing section, department_id, or batch_id
    classes = list(db["classes"].find())
    missing_classes = [
        {"id": str(c["_id"]), "name": c.get("name") or "[Missing Name]", "missing": [f[1] for f in [("name", "name"), ("department_id", "department"), ("batch_id", "batch")] if not c.get(f[0]) or not str(c.get(f[0])).strip()]}
        for c in classes if not c.get("name") or not str(c.get("name")).strip() or not c.get("department_id") or not c.get("batch_id")
    ]

    # 4. Rooms missing code, capacity, or department_id
    rooms = list(db["rooms"].find())
    missing_rooms = [
        {"id": str(r["_id"]), "name": r.get("name") or "[Missing Name]", "missing": [f for f in ["name", "code", "capacity", "department_id"] if not r.get(f) or not str(r.get(f)).strip()]}
        for r in rooms if not r.get("name") or not str(r.get("name")).strip() or not r.get("code") or not r.get("capacity") or not r.get("department_id")
    ]

    # 5. Subjects missing code, hours_per_week, or department_ids
    subjects = list(db["subjects"].find())
    missing_subjects = [
        {"id": str(s["_id"]), "name": s.get("name") or "[Missing Name]", "missing": [f[1] for f in [("name", "name"), ("code", "code"), ("hours_per_week", "hours_per_week"), ("department_id", "department")] if not s.get(f[0]) or (isinstance(s.get(f[0]), str) and not s.get(f[0]).strip())]}
        for s in subjects if not s.get("name") or not str(s.get("name")).strip() or not s.get("code") or not str(s.get("code")).strip() or not s.get("hours_per_week") or not (s.get("department_ids") or s.get("department_id"))
    ]

    # 6. Faculty missing email or department_id
    faculty = list(db["faculty"].find())
    missing_faculty = [
        {"id": str(f["_id"]), "name": f.get("name") or "[Missing Name]", "missing": [field for field in ["name", "email", "department_id"] if not f.get(field) or not str(f.get(field)).strip()]}
        for f in faculty if not f.get("name") or not str(f.get("name")).strip() or not f.get("email") or not str(f.get("email")).strip() or not f.get("department_id")
    ]

    # 7. Mappings (Subjects missing class_id or faculty_id)
    unmapped_subjects = [
        {"id": str(s["_id"]), "name": s.get("name") or s.get("code") or "[Missing Name]", "missing": [f[1] for f in [("class_id", "class_id"), ("faculty_id", "faculty_id")] if not s.get(f[0])]}
        for s in subjects if not s.get("class_id") or not s.get("faculty_id")
    ]

    total_missing = (
        len(missing_depts) + len(missing_batches) + len(missing_classes) +
        len(missing_rooms) + len(missing_subjects) + len(missing_faculty) +
        len(unmapped_subjects)
    )

    return {
        "has_missing": total_missing > 0,
        "total_missing": total_missing,
        "details": {
            "departments": {"count": len(missing_depts), "items": missing_depts},
            "batches": {"count": len(missing_batches), "items": missing_batches},
            "classes": {"count": len(missing_classes), "items": missing_classes},
            "rooms": {"count": len(missing_rooms), "items": missing_rooms},
            "subjects": {"count": len(missing_subjects), "items": missing_subjects},
            "faculty": {"count": len(missing_faculty), "items": missing_faculty},
            "mappings": {"count": len(unmapped_subjects), "items": unmapped_subjects},
        }
    }


