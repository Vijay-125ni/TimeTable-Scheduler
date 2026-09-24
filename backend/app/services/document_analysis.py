import csv
import io
import json
import re
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openai import OpenAI

from .document_constraints import ExtractedDocument

COURSE_TYPES = {"Theory", "Lab", "Blended", "Project", "Seminar", "Unknown"}

SYSTEM_PROMPT = """You are an advanced, fail-safe Multimodal Data Extraction and Layout Analysis Engine. Your objective is to parse academic timetable, syllabus, faculty allocation, or course documents and convert them into a perfectly normalized, production-ready JSON dataset.

You must maintain absolute data integrity, capturing implicit structural relationships caused by merged cells, multi-tier rows, or shared headers.
Do not include reasoning, chain-of-thought, explanations, markdown, or commentary. Return the final JSON only.

1. COMPREHENSIVE EXTRACTION PROTOCOLS
- ZERO OMISSIONS: Every single cell, row, column, text snippet, and footnote must be extracted. Do not summarize, truncate, or skip lines.
- MERGED CELL RESOLUTION: If a single Subject Code or Subject Name spans vertically across multiple rows, duplicate the parent context into each child object so every entry is fully self-contained.
- If a Faculty Name or Room Number spans across multiple rows or columns, accurately attribute that entity to all corresponding sessions.
- TEXT SANITIZATION: Clean trailing punctuation and OCR artifacts such as random dots or pipes, but preserve structural labels such as "(Professional Elective I)".

2. DATA FIELD MAPPING AND NORMALIZATION
- L -> Lecture hours as integer.
- T -> Tutorial hours as integer.
- P -> Practical / Laboratory hours as integer.
- C -> Total credits as integer.
- Type must be exactly one of: ["Theory", "Lab", "Blended", "Project", "Seminar", "Unknown"].

3. STRICT JSON SCHEMA OUTPUT
Return ONLY a valid JSON object containing an array named "extracted_timetable".
Each object must strictly follow this structure:
{
  "meta": {
    "row_index": integer,
    "raw_text_line": "string"
  },
  "course_details": {
    "subject_code": "string or null",
    "subject_name": "string",
    "type": "string",
    "is_elective": boolean,
    "elective_group": "string or null"
  },
  "credit_structure": {
    "lecture_hours_L": integer,
    "tutorial_hours_T": integer,
    "practical_hours_P": integer,
    "total_credits_C": integer
  },
  "faculty_assignment": {
    "full_name": "string or null",
    "designation": "string or null"
  },
  "additional_metadata": {
    "remarks": "string or null",
    "is_ambiguous_or_split": boolean
  }
}

4. PIPELINE EXECUTION STEPS
1. PRE-SCAN: Analyze the layout coordinates and tabular structure from the extracted text.
2. ROW-BY-ROW PARSE: Process from top-left to bottom-right. Split tracks such as V-QUANTZ and V-VERBAL into distinct JSON objects while inheriting shared parent fields.
3. LOGICAL VALIDATION: Validate credit structure and put discrepancies in remarks.
4. FINAL RENDER: Emit the clean, fully expanded JSON payload.
"""

OLLAMA_SYSTEM_PROMPT = """Extract academic timetable/syllabus/faculty-allocation rows into JSON only.
Preserve every row. Expand merged or blank child rows by inheriting previous subject code, subject name, type, faculty, and designation when needed.
Clean OCR artifacts but keep labels like "(Professional Elective I)".
Type enum: Theory, Lab, Blended, Project, Seminar, Unknown.
Return exactly: {"extracted_timetable":[{"meta":{"row_index":1,"raw_text_line":"..."},"course_details":{"subject_code":null,"subject_name":"...","type":"Unknown","is_elective":false,"elective_group":null},"credit_structure":{"lecture_hours_L":0,"tutorial_hours_T":0,"practical_hours_P":0,"total_credits_C":0},"faculty_assignment":{"full_name":null,"designation":null},"additional_metadata":{"remarks":null,"is_ambiguous_or_split":false}}]}.
No markdown. No explanations. No reasoning."""


def merge_duplicate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge duplicate timetable rows based on subject_code and subject_name."""
    import copy
    merged: List[Dict[str, Any]] = []

    def rows_match(r1: Dict[str, Any], r2: Dict[str, Any]) -> bool:
        det1 = r1.get("course_details", {})
        det2 = r2.get("course_details", {})
        
        c1 = (det1.get("subject_code") or "").strip().upper()
        c2 = (det2.get("subject_code") or "").strip().upper()
        
        n1 = (det1.get("subject_name") or "").strip().lower()
        n2 = (det2.get("subject_name") or "").strip().lower()
        
        if c1 and c2:
            return c1 == c2
        if not c1 and not c2:
            return n1 == n2 if n1 else False
        if n1 and n2:
            return n1 == n2
        return False

    for row in rows:
        match_found = False
        for existing in merged:
            if rows_match(existing, row):
                # Merge row into existing
                ext_det = existing.get("course_details", {})
                cur_det = row.get("course_details", {})
                if not ext_det.get("subject_code") and cur_det.get("subject_code"):
                    ext_det["subject_code"] = cur_det["subject_code"]
                if not ext_det.get("subject_name") and cur_det.get("subject_name"):
                    ext_det["subject_name"] = cur_det["subject_name"]
                
                t1 = ext_det.get("type") or "Unknown"
                t2 = cur_det.get("type") or "Unknown"
                if t1 == "Unknown":
                    ext_det["type"] = t2
                elif t2 != "Unknown" and t1 != t2:
                    if (t1 == "Theory" and t2 == "Lab") or (t1 == "Lab" and t2 == "Theory"):
                        ext_det["type"] = "Blended"

                ext_det["is_elective"] = ext_det.get("is_elective", False) or cur_det.get("is_elective", False)
                if not ext_det.get("elective_group") and cur_det.get("elective_group"):
                    ext_det["elective_group"] = cur_det["elective_group"]

                ext_cred = existing.get("credit_structure", {})
                cur_cred = row.get("credit_structure", {})
                for field in ("lecture_hours_L", "tutorial_hours_T", "practical_hours_P", "total_credits_C"):
                    v1 = ext_cred.get(field) or 0
                    v2 = cur_cred.get(field) or 0
                    if v1 == v2:
                        ext_cred[field] = v1
                    else:
                        ext_cred[field] = v1 + v2

                ext_fac = existing.get("faculty_assignment", {})
                cur_fac = row.get("faculty_assignment", {})
                
                f1 = ext_fac.get("full_name") or ""
                f2 = cur_fac.get("full_name") or ""
                
                def parse_names(name_str):
                    if not name_str:
                        return []
                    return [n.strip() for n in re.split(r'[,;/]|\band\b', name_str) if n.strip()]
                    
                names1 = parse_names(f1)
                names2 = parse_names(f2)
                merged_names = []
                for name in (names1 + names2):
                    if name not in merged_names:
                        merged_names.append(name)
                ext_fac["full_name"] = ", ".join(merged_names) if merged_names else None
                
                d1 = ext_fac.get("designation") or ""
                d2 = cur_fac.get("designation") or ""
                desig1 = parse_names(d1)
                desig2 = parse_names(d2)
                merged_desig = []
                for des in (desig1 + desig2):
                    if des not in merged_desig:
                        merged_desig.append(des)
                ext_fac["designation"] = ", ".join(merged_desig) if merged_desig else None

                ext_meta = existing.get("additional_metadata", {})
                cur_meta = row.get("additional_metadata", {})
                r1 = ext_meta.get("remarks") or ""
                r2 = cur_meta.get("remarks") or ""
                rems1 = [r.strip() for r in re.split(r'\. ', r1) if r.strip()]
                rems2 = [r.strip() for r in re.split(r'\. ', r2) if r.strip()]
                merged_rems = []
                for rem in (rems1 + rems2):
                    if rem not in merged_rems:
                        merged_rems.append(rem)
                
                merge_note = "Merged duplicate records."
                if merge_note not in merged_rems:
                    merged_rems.append(merge_note)
                ext_meta["remarks"] = ". ".join(merged_rems)
                ext_meta["is_ambiguous_or_split"] = ext_meta.get("is_ambiguous_or_split", False) or cur_meta.get("is_ambiguous_or_split", False)
                
                match_found = True
                break
        
        if not match_found:
            merged.append(copy.deepcopy(row))
            
    return merged


def analyze_academic_documents(
    documents: Iterable[ExtractedDocument],
    *,
    model: Optional[str] = "qwen-plus",
    api_base: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    api_key: Optional[str] = None,
    timeout_seconds: int = 120,
    max_chars: int = 60_000,
) -> Dict[str, Any]:
    """Return normalized academic rows, using Qwen API model when configured."""
    docs = list(documents)
    warnings: List[str] = []
    deterministic_rows = _deterministic_extract(docs)

    if model and api_key:
        try:
            raw = _call_local_model(
                docs,
                model=model,
                api_base=api_base,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                max_chars=max_chars,
            )
            parsed = _parse_json_payload(raw)
            normalized, normalize_warnings = normalize_extracted_timetable(parsed)
            warnings.extend(normalize_warnings)
            if normalized:
                model_score = _analysis_quality_score(normalized)
                deterministic_score = _analysis_quality_score(deterministic_rows)
                if deterministic_rows and deterministic_score > model_score:
                    warnings.append(
                        "Qwen document model output was less structured than deterministic extraction; used deterministic rows."
                    )
                    return {
                        "source": "deterministic",
                        "model": model,
                        "extracted_timetable": merge_duplicate_rows(deterministic_rows),
                        "warnings": warnings,
                    }
                return {
                    "source": "qwen-api",
                    "model": model,
                    "extracted_timetable": merge_duplicate_rows(normalized),
                    "warnings": warnings,
                }
            warnings.append("Qwen document model returned no usable timetable rows; used deterministic fallback.")
        except Exception as exc:
            warnings.append(f"Qwen document model failed: {exc}. Used deterministic fallback.")
    else:
        warnings.append(
            "Qwen API key is not configured. Set QWEN_API_KEY to enable Qwen-based document extraction."
        )

    return {
        "source": "deterministic",
        "model": model,
        "extracted_timetable": merge_duplicate_rows(deterministic_rows),
        "warnings": warnings,
    }


def normalize_extracted_timetable(
    payload: Any,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    rows = _payload_rows(payload)
    normalized: List[Dict[str, Any]] = []
    inherited: Dict[str, Any] = {}

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            warnings.append(f"Skipped non-object row at index {index}.")
            continue

        item, used_inheritance = _normalize_row(row, index, inherited)
        course = item["course_details"]
        raw_line = item["meta"]["raw_text_line"]

        if _is_header_like_item(item):
            continue
        if not course["subject_name"] and not course["subject_code"] and not raw_line:
            warnings.append(f"Skipped empty row at index {index}.")
            continue
        if not course["subject_name"]:
            course["subject_name"] = raw_line or course["subject_code"] or "Unknown"
            item["additional_metadata"]["is_ambiguous_or_split"] = True

        item["additional_metadata"]["is_ambiguous_or_split"] = bool(
            item["additional_metadata"]["is_ambiguous_or_split"] or used_inheritance
        )
        _append_credit_warning(item)
        normalized.append(item)
        _update_inherited_context(inherited, item)

    return normalized, warnings


def _call_local_model(
    documents: List[ExtractedDocument],
    *,
    model: str,
    api_base: str,
    api_key: str,
    timeout_seconds: int,
    max_chars: int,
) -> str:
    client = OpenAI(api_key=api_key or "local", base_url=api_base.rstrip("/"), timeout=timeout_seconds)
    user_prompt = _build_user_prompt(documents, max_chars=max_chars)
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 2048,
    }
    try:
        response = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception:
        response = client.chat.completions.create(**kwargs)
    return _strip_markdown(response.choices[0].message.content or "")


def _build_user_prompt(documents: List[ExtractedDocument], *, max_chars: int) -> str:
    parts: List[str] = []
    remaining = max_chars
    for index, document in enumerate(documents, start=1):
        if remaining <= 0:
            break
        text = document.text[:remaining]
        remaining -= len(text)
        parts.append(
            "\n".join(
                [
                    f"DOCUMENT {index}",
                    f"filename: {document.filename}",
                    f"content_type: {document.content_type or 'unknown'}",
                    f"local_extractor: {document.extractor}",
                    "extracted_text:",
                    text,
                ]
            )
        )
    return (
        "/no_think\n"
        "Analyze the following locally extracted document text. Preserve row order and infer merged-cell "
        "relationships from repeated blanks, table spacing, and shared headings. Return ONLY the strict JSON object.\n\n"
        + "\n\n---\n\n".join(parts)
    )


def _parse_json_payload(text: str) -> Any:
    cleaned = _strip_markdown(text)
    try:
        return json.loads(cleaned)
    except Exception:
        decoder = json.JSONDecoder()
        start_positions = [idx for idx, ch in enumerate(cleaned) if ch in "[{"]
        for start in start_positions:
            try:
                value, _ = decoder.raw_decode(cleaned[start:])
                return value
            except Exception:
                continue
    raise ValueError("Model did not return valid JSON.")


def _payload_rows(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("extracted_timetable", "timetable", "rows", "courses", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_row(
    row: Dict[str, Any], index: int, inherited: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool]:
    meta = _as_dict(row.get("meta"))
    details = _as_dict(
        row.get("course_details") or row.get("course") or row.get("subject")
    )
    credits = _as_dict(row.get("credit_structure") or row.get("credits"))
    faculty = _as_dict(row.get("faculty_assignment") or row.get("faculty"))
    extra = _as_dict(row.get("additional_metadata") or row.get("metadata"))

    raw_line = _clean_value(meta.get("raw_text_line") or row.get("raw_text_line") or "")
    row_index = _int_value(meta.get("row_index"), default=index)

    subject_code = _clean_nullable(
        details.get("subject_code")
        or details.get("course_code")
        or row.get("subject_code")
        or row.get("code")
    )
    subject_name = _clean_value(
        details.get("subject_name")
        or details.get("course_name")
        or details.get("name")
        or row.get("subject_name")
        or row.get("name")
    )
    course_type = _normalize_type(
        details.get("type") or row.get("type") or row.get("course_type")
    )

    faculty_name = _clean_nullable(
        faculty.get("full_name")
        or faculty.get("name")
        or row.get("faculty")
        or row.get("faculty_name")
    )
    designation = _clean_nullable(faculty.get("designation") or row.get("designation"))
    faculty_name, inferred_designation = _split_faculty_designation(faculty_name)
    designation = designation or inferred_designation

    inherited_keys = []
    if not subject_code and inherited.get("subject_code"):
        subject_code = inherited["subject_code"]
        inherited_keys.append("subject_code")
    if not subject_name and inherited.get("subject_name"):
        subject_name = inherited["subject_name"]
        inherited_keys.append("subject_name")
    elif (
        _is_generic_component_name(subject_name)
        and inherited.get("subject_name")
        and _looks_like_split_component(raw_line)
    ):
        subject_name = inherited["subject_name"]
        inherited_keys.append("subject_name")
    if (
        course_type == "Unknown"
        and inherited.get("type")
        and _looks_like_split_component(raw_line)
    ):
        course_type = inherited["type"]
        inherited_keys.append("type")
    if not faculty_name and inherited.get("faculty_name"):
        faculty_name = inherited["faculty_name"]
        inherited_keys.append("faculty")
    if not designation and inherited.get("designation"):
        designation = inherited["designation"]
        inherited_keys.append("designation")

    elective_group = _clean_nullable(
        details.get("elective_group") or row.get("elective_group")
    )
    if not elective_group:
        elective_group = _extract_elective_group(subject_name)
    is_elective = _bool_value(
        details.get("is_elective"),
        default=bool(elective_group or _contains_elective(subject_name)),
    )

    remarks = _clean_nullable(extra.get("remarks") or row.get("remarks"))
    if inherited_keys:
        remarks = _join_remarks(
            remarks, f"Inherited merged-cell context: {', '.join(inherited_keys)}."
        )

    item = {
        "meta": {
            "row_index": row_index,
            "raw_text_line": raw_line,
        },
        "course_details": {
            "subject_code": subject_code,
            "subject_name": subject_name,
            "type": course_type,
            "is_elective": is_elective,
            "elective_group": elective_group,
        },
        "credit_structure": {
            "lecture_hours_L": _int_value(
                credits.get("lecture_hours_L")
                or credits.get("L")
                or row.get("L")
                or row.get("lecture_hours")
            ),
            "tutorial_hours_T": _int_value(
                credits.get("tutorial_hours_T")
                or credits.get("T")
                or row.get("T")
                or row.get("tutorial_hours")
            ),
            "practical_hours_P": _int_value(
                credits.get("practical_hours_P")
                or credits.get("P")
                or row.get("P")
                or row.get("practical_hours")
            ),
            "total_credits_C": _int_value(
                credits.get("total_credits_C")
                or credits.get("C")
                or row.get("C")
                or row.get("credits")
            ),
        },
        "faculty_assignment": {
            "full_name": faculty_name,
            "designation": designation,
        },
        "additional_metadata": {
            "remarks": remarks,
            "is_ambiguous_or_split": _bool_value(
                extra.get("is_ambiguous_or_split") or row.get("is_ambiguous_or_split"),
                default=False,
            ),
        },
    }
    return item, bool(inherited_keys)


def _deterministic_extract(documents: List[ExtractedDocument]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    row_number = 0
    inherited: Dict[str, Any] = {}

    for document in documents:
        header_map: Optional[Dict[str, int]] = None
        for raw_line in document.text.splitlines():
            line = raw_line.strip(" ")
            if not line.strip():
                continue
            cells = _split_cells(line)
            maybe_header = _header_map(cells)
            if maybe_header:
                header_map = maybe_header
                continue

            row_data = _row_from_cells(cells, header_map, line)
            if not row_data and _looks_like_footnote(line):
                row_data = {
                    "raw_text_line": line,
                    "subject_name": line,
                    "remarks": line,
                    "type": "Unknown",
                    "is_ambiguous_or_split": True,
                }
            if not row_data:
                continue

            row_number += 1
            row_data["meta"] = {"row_index": row_number, "raw_text_line": line}
            item, used_inheritance = _normalize_row(row_data, row_number, inherited)
            if used_inheritance:
                item["additional_metadata"]["is_ambiguous_or_split"] = True
            _append_credit_warning(item)
            rows.append(item)
            _update_inherited_context(inherited, item)

    return rows


def _row_from_cells(
    cells: List[str], header_map: Optional[Dict[str, int]], raw_line: str
) -> Optional[Dict[str, Any]]:
    if header_map:
        row = {
            "subject_code": _cell(cells, header_map.get("subject_code")),
            "subject_name": _cell(cells, header_map.get("subject_name")),
            "type": _cell(cells, header_map.get("type")),
            "L": _cell(cells, header_map.get("L")),
            "T": _cell(cells, header_map.get("T")),
            "P": _cell(cells, header_map.get("P")),
            "C": _cell(cells, header_map.get("C")),
            "faculty": _cell(cells, header_map.get("faculty")),
            "designation": _cell(cells, header_map.get("designation")),
            "remarks": _cell(cells, header_map.get("remarks")),
            "raw_text_line": raw_line,
        }
        if any(
            row.get(key)
            for key in (
                "subject_code",
                "subject_name",
                "faculty",
                "L",
                "T",
                "P",
                "C",
                "remarks",
            )
        ):
            return row
        return None

    if len(cells) < 2:
        return None

    numeric_positions = [idx for idx, cell in enumerate(cells) if _is_int_like(cell)]
    if not numeric_positions and not _looks_like_course_code(cells[0]):
        return None

    row: Dict[str, Any] = {"raw_text_line": raw_line}
    if _looks_like_course_code(cells[0]):
        row["subject_code"] = cells[0]
        row["subject_name"] = cells[1] if len(cells) > 1 else ""
        rest_start = 2
    else:
        row["subject_name"] = cells[0]
        rest_start = 1

    type_index = next(
        (
            idx
            for idx in range(rest_start, len(cells))
            if _normalize_type(cells[idx]) != "Unknown"
        ),
        None,
    )
    if type_index is not None:
        row["type"] = cells[type_index]

    numbers = [cells[idx] for idx in numeric_positions]
    for key, value in zip(("L", "T", "P", "C"), numbers[-4:]):
        row[key] = value

    faculty_candidates = [
        cell
        for idx, cell in enumerate(cells[rest_start:], start=rest_start)
        if idx not in numeric_positions
        and idx != type_index
        and _looks_like_faculty(cell)
    ]
    if faculty_candidates:
        row["faculty"] = faculty_candidates[-1]

    return row


def _header_map(cells: List[str]) -> Optional[Dict[str, int]]:
    mapping: Dict[str, int] = {}
    for index, cell in enumerate(cells):
        normalized = _header_token(cell)
        if normalized in {"subjectcode", "coursecode", "subcode", "code"}:
            mapping.setdefault("subject_code", index)
        elif normalized in {
            "subjectname",
            "coursename",
            "coursetitle",
            "subject",
            "title",
            "name",
        }:
            mapping.setdefault("subject_name", index)
        elif normalized in {"type", "component", "category", "mode"}:
            mapping.setdefault("type", index)
        elif normalized == "l":
            mapping["L"] = index
        elif normalized == "t":
            mapping["T"] = index
        elif normalized == "p":
            mapping["P"] = index
        elif normalized in {"c", "credits", "credit"}:
            mapping["C"] = index
        elif normalized in {
            "faculty",
            "facultyname",
            "staff",
            "staffname",
            "instructor",
            "teacher",
        }:
            mapping.setdefault("faculty", index)
        elif normalized in {"designation", "role", "position"}:
            mapping.setdefault("designation", index)
        elif normalized in {"remarks", "remark", "notes", "note"}:
            mapping.setdefault("remarks", index)

    useful = {"subject_code", "subject_name", "faculty", "L", "T", "P", "C"}
    return mapping if len(useful & mapping.keys()) >= 2 else None


def _split_cells(line: str) -> List[str]:
    if "\t" in line:
        return [_clean_value(cell) for cell in line.split("\t")]
    if "|" in line:
        return [_clean_value(cell) for cell in line.strip("|").split("|")]
    if "," in line:
        try:
            return [_clean_value(cell) for cell in next(csv.reader(io.StringIO(line)))]
        except Exception:
            return [_clean_value(cell) for cell in line.split(",")]
    return [_clean_value(cell) for cell in re.split(r"\s{2,}", line) if cell.strip()]


def _cell(cells: List[str], index: Optional[int]) -> str:
    if index is None or index < 0 or index >= len(cells):
        return ""
    return cells[index]


def _append_credit_warning(item: Dict[str, Any]) -> None:
    credits = item["credit_structure"]
    l_value = credits["lecture_hours_L"]
    t_value = credits["tutorial_hours_T"]
    p_value = credits["practical_hours_P"]
    c_value = credits["total_credits_C"]
    if not any((l_value, t_value, p_value, c_value)):
        return

    expected_values = {l_value + t_value + p_value}
    if p_value:
        expected_values.add(l_value + t_value + round(p_value / 2))
    if c_value and c_value not in expected_values:
        expected_text = " or ".join(str(value) for value in sorted(expected_values))
        item["additional_metadata"]["remarks"] = _join_remarks(
            item["additional_metadata"]["remarks"],
            f"Credit check: C={c_value} does not match expected {expected_text} from L/T/P.",
        )
        item["additional_metadata"]["is_ambiguous_or_split"] = True


def _analysis_quality_score(rows: List[Dict[str, Any]]) -> int:
    score = 0
    for row in rows:
        details = row.get("course_details", {})
        credits = row.get("credit_structure", {})
        faculty = row.get("faculty_assignment", {})
        subject_name = details.get("subject_name")
        subject_code = details.get("subject_code")

        if subject_code:
            score += 4
        if subject_name and not _is_generic_component_name(subject_name):
            score += 2
        if details.get("type") and details.get("type") != "Unknown":
            score += 2
        if any(
            credits.get(key, 0)
            for key in (
                "lecture_hours_L",
                "tutorial_hours_T",
                "practical_hours_P",
                "total_credits_C",
            )
        ):
            score += 3
        if faculty.get("full_name"):
            score += 2
        if faculty.get("designation"):
            score += 1
        if details.get("is_elective"):
            score += 1
    return score


def _update_inherited_context(context: Dict[str, Any], item: Dict[str, Any]) -> None:
    details = item["course_details"]
    faculty = item["faculty_assignment"]
    for source, target in (
        ("subject_code", "subject_code"),
        ("subject_name", "subject_name"),
        ("type", "type"),
    ):
        if details.get(source):
            context[target] = details[source]
    if faculty.get("full_name"):
        context["faculty_name"] = faculty["full_name"]
    if faculty.get("designation"):
        context["designation"] = faculty["designation"]


def _clean_value(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", " ").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[|:;,\-. ]+", "", text)
    text = re.sub(r"[|:;,\-. ]+$", "", text)
    return text.strip()


def _clean_nullable(value: Any) -> Optional[str]:
    cleaned = _clean_value(value)
    if not cleaned or cleaned.lower() in {
        "null",
        "none",
        "nil",
        "na",
        "n/a",
        "-",
        "--",
    }:
        return None
    return cleaned


def _int_value(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default
    return int(float(match.group(0)))


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_type(value: Any) -> str:
    text = _clean_value(value).lower()
    if not text:
        return "Unknown"
    if any(word in text for word in ("blend", "integrated", "combined")):
        return "Blended"
    if any(word in text for word in ("lab", "practical", "laboratory")):
        return "Lab"
    if "project" in text:
        return "Project"
    if "seminar" in text:
        return "Seminar"
    if any(word in text for word in ("theory", "lecture", "lect")):
        return "Theory"
    value_title = text.title()
    return value_title if value_title in COURSE_TYPES else "Unknown"


def _contains_elective(text: Any) -> bool:
    return "elective" in _clean_value(text).lower()


def _extract_elective_group(text: Any) -> Optional[str]:
    cleaned = _clean_value(text)
    parenthetical = re.search(r"\(([^)]*elective[^)]*)\)", cleaned, flags=re.IGNORECASE)
    if parenthetical:
        return _clean_value(parenthetical.group(1))
    inline = re.search(
        r"((?:professional\s+)?elective\s+[ivxlcdm0-9]+)", cleaned, flags=re.IGNORECASE
    )
    return _clean_value(inline.group(1)) if inline else None


def _split_faculty_designation(
    value: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    parts = [part.strip() for part in re.split(r"[,;/]", value, maxsplit=1)]
    if len(parts) == 2 and _looks_like_designation(parts[1]):
        return _clean_nullable(parts[0]), _clean_nullable(parts[1])
    return value, None


def _join_remarks(existing: Optional[str], addition: str) -> str:
    if existing and addition in existing:
        return existing
    return f"{existing} {addition}".strip() if existing else addition


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strip_markdown(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


def _header_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _is_int_like(value: str) -> bool:
    return bool(re.fullmatch(r"\s*\d+(?:\.0)?\s*", str(value or "")))


def _looks_like_course_code(value: str) -> bool:
    text = _clean_value(value)
    return bool(re.search(r"[A-Za-z]{2,}[-_/]?\d|[A-Za-z]+\d+[A-Za-z]*", text))


def _looks_like_designation(value: str) -> bool:
    text = _clean_value(value).lower()
    return any(
        word in text
        for word in (
            "prof",
            "assistant",
            "associate",
            "lecturer",
            "hod",
            "dean",
            "trainer",
        )
    )


def _looks_like_faculty(value: str) -> bool:
    text = _clean_value(value)
    lower = text.lower()
    return bool(
        re.search(r"\b(dr|prof|mr|mrs|ms)\.?\b", lower)
        or _looks_like_designation(lower)
        or (len(text.split()) >= 2 and not _contains_elective(text))
    )


def _looks_like_split_component(raw_line: str) -> bool:
    lower = _clean_value(raw_line).lower()
    return any(
        word in lower
        for word in ("lab", "practical", "tutorial", "blended", "track", "batch")
    )


def _looks_like_footnote(line: str) -> bool:
    lower = line.strip().lower()
    return lower.startswith(("note:", "notes:", "remark:", "remarks:", "*", "#"))


def _is_generic_component_name(value: Any) -> bool:
    normalized = _header_token(_clean_value(value))
    return normalized in {
        "lab",
        "practical",
        "laboratory",
        "tutorial",
        "theory",
        "blended",
        "component",
    }


def _is_header_like_item(item: Dict[str, Any]) -> bool:
    details = item.get("course_details", {})
    raw = _header_token(item.get("meta", {}).get("raw_text_line", ""))
    subject_code = _header_token(details.get("subject_code") or "")
    subject_name = _header_token(details.get("subject_name") or "")
    header_blob = " ".join([raw, subject_code, subject_name])
    return (
        "subjectcode" in header_blob
        and ("subjectname" in header_blob or "coursename" in header_blob)
        and any(
            token in header_blob
            for token in ("faculty", "designation", "credits", "ltpc")
        )
    )
