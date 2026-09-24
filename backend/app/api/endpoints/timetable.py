from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pymongo.database import Database

from ...core.config import settings
from ...core.security import get_admin_user, get_current_user, get_tenant_db
from ...models.timetable import (batch_helper, class_helper, department_helper,
                                 faculty_helper, room_helper, subject_helper,
                                 timetable_helper)
from ...schemas.timetable import (
    BatchCreate, BatchResponse, BatchUpdate,
    DepartmentCreate, DepartmentResponse, DepartmentUpdate,
    RoomCreate, RoomResponse, RoomUpdate,
    ClassCreate, ClassResponse, ClassUpdate,
    SubjectCreate, SubjectResponse, SubjectUpdate, SubjectMapRequest,
    FacultyCreate, FacultyResponse, FacultyUpdate,
    TimetableGenerateRequest, TimetableResponse
)
from ...services.ai_parser import AIConstraintParser
from ...services.document_analysis import analyze_academic_documents
from ...services.document_constraints import (
    build_constraint_text_from_documents, extract_document_text)
from ...services.scheduler import TimetableScheduler

router = APIRouter(redirect_slashes=False)

# ── helpers ──────────────────────────────────────────────────────────────────


def _oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid id: {id_str}")


def _build_ai_constraint_context(db: Database, periods_per_day: int) -> Dict[str, Any]:
    faculty_docs = list(db["faculty"].find({}, {"name": 1}))
    subject_docs = list(
        db["subjects"].find({}, {"name": 1, "code": 1, "requires_lab": 1})
    )
    class_docs = list(db["classes"].find({}, {"name": 1, "section": 1}))

    subject_names = []
    seen_subject_names = set()
    for subject in subject_docs:
        for value in (subject.get("name"), subject.get("code")):
            if value and value not in seen_subject_names:
                subject_names.append(value)
                seen_subject_names.add(value)
            if value and subject.get("requires_lab"):
                lab_alias = f"{value} Lab"
                if lab_alias not in seen_subject_names:
                    subject_names.append(lab_alias)
                    seen_subject_names.add(lab_alias)

    return {
        "faculty_names": [d["name"] for d in faculty_docs if d.get("name")],
        "subject_names": subject_names,
        "class_names": [
            f"{d.get('name', '')} {d.get('section', '')}".strip()
            for d in class_docs
            if d.get("name")
        ],
        "periods_per_day": periods_per_day,
    }


# ── Batches ───────────────────────────────────────────────────────────────────


@router.post("/batches", response_model=BatchResponse)
def create_batch(
    batch: BatchCreate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    doc = {**batch.dict(), "created_at": datetime.utcnow()}
    result = db["batches"].insert_one(doc)
    return batch_helper(db["batches"].find_one({"_id": result.inserted_id}))


@router.get("/batches", response_model=List[BatchResponse])
def list_batches(
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    return [batch_helper(d) for d in db["batches"].find()]


@router.delete("/batches/{id}")
def delete_batch(
    id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    result = db["batches"].delete_one({"_id": _oid(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


@router.put("/batches/{id}", response_model=BatchResponse)
def update_batch(
    id: str,
    batch: BatchUpdate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    update_data = {k: v for k, v in batch.dict(exclude_unset=True).items()}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = db["batches"].update_one({"_id": _oid(id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return batch_helper(db["batches"].find_one({"_id": _oid(id)}))


# ── Departments ───────────────────────────────────────────────────────────────


@router.post("/departments", response_model=DepartmentResponse)
def create_department(
    dept: DepartmentCreate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    doc = {**dept.dict(), "created_at": datetime.utcnow()}
    result = db["departments"].insert_one(doc)
    return department_helper(db["departments"].find_one({"_id": result.inserted_id}))


@router.get("/departments", response_model=List[DepartmentResponse])
def list_departments(
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    return [department_helper(d) for d in db["departments"].find()]


@router.delete("/departments/{id}")
def delete_department(
    id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    # Check if any classes or faculty reference this department
    if db["classes"].find_one({"department_id": id}) or db["faculty"].find_one(
        {"department_id": id}
    ):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete Department: It has associated Faculty or Classes. Please delete them first.",
        )
    result = db["departments"].delete_one({"_id": _oid(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


@router.put("/departments/{id}", response_model=DepartmentResponse)
def update_department(
    id: str,
    dept: DepartmentUpdate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    update_data = {k: v for k, v in dept.dict(exclude_unset=True).items()}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = db["departments"].update_one({"_id": _oid(id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return department_helper(db["departments"].find_one({"_id": _oid(id)}))


# ── Classes ───────────────────────────────────────────────────────────────────


def _enrich_class(doc: dict, db: Database) -> dict:
    dept = (
        db["departments"].find_one({"_id": _oid(doc["department_id"])})
        if doc.get("department_id")
        else None
    )
    batch = (
        db["batches"].find_one({"_id": _oid(doc["batch_id"])})
        if doc.get("batch_id")
        else None
    )
    return class_helper(
        doc,
        department=department_helper(dept) if dept else None,
        batch=batch_helper(batch) if batch else None,
    )


# ── Rooms ─────────────────────────────────────────────────────────────────────


def _normalize_room_payload(payload: dict) -> dict:
    if "room_type" in payload and payload["room_type"]:
        room_type = str(payload["room_type"]).strip().lower()
        if room_type not in {"lecture", "lab", "seminar"}:
            raise HTTPException(
                status_code=400, detail="room_type must be lecture, lab, or seminar"
            )
        payload["room_type"] = room_type
    if "capacity" in payload and payload["capacity"] is not None:
        capacity = int(payload["capacity"])
        if capacity < 0:
            raise HTTPException(status_code=400, detail="capacity must be 0 or more")
        payload["capacity"] = capacity
    return payload


def _enrich_room(doc: dict, db: Database) -> dict:
    dept = (
        db["departments"].find_one({"_id": _oid(doc["department_id"])})
        if doc.get("department_id")
        else None
    )
    return room_helper(doc, department=department_helper(dept) if dept else None)


@router.post("/rooms", response_model=RoomResponse)
def create_room(
    room: RoomCreate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    doc = _normalize_room_payload({**room.dict(), "created_at": datetime.utcnow()})
    result = db["rooms"].insert_one(doc)
    return _enrich_room(db["rooms"].find_one({"_id": result.inserted_id}), db)


@router.get("/rooms", response_model=List[RoomResponse])
def list_rooms(
    department_id: Optional[str] = None,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    query = {"department_id": department_id} if department_id else {}
    return [_enrich_room(d, db) for d in db["rooms"].find(query)]


@router.put("/rooms/{id}", response_model=RoomResponse)
def update_room(
    id: str,
    room: RoomUpdate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    update_data = _normalize_room_payload(
        {k: v for k, v in room.dict(exclude_unset=True).items()}
    )
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = db["rooms"].update_one({"_id": _oid(id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return _enrich_room(db["rooms"].find_one({"_id": _oid(id)}), db)


@router.delete("/rooms/{id}")
def delete_room(
    id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    if db["classes"].find_one({"room_id": id}):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete Room: It is assigned to one or more classes.",
        )
    result = db["rooms"].delete_one({"_id": _oid(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


@router.post("/classes", response_model=ClassResponse)
def create_class(
    cls: ClassCreate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    doc = {**cls.dict(), "created_at": datetime.utcnow()}
    result = db["classes"].insert_one(doc)
    return _enrich_class(db["classes"].find_one({"_id": result.inserted_id}), db)


@router.get("/classes", response_model=List[ClassResponse])
def list_classes(
    department_id: Optional[str] = None,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    query = {"department_id": department_id} if department_id else {}
    return [_enrich_class(d, db) for d in db["classes"].find(query)]


@router.delete("/classes/{id}")
def delete_class(
    id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    result = db["classes"].delete_one({"_id": _oid(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


@router.put("/classes/{id}", response_model=ClassResponse)
def update_class(
    id: str,
    cls: ClassUpdate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    update_data = {k: v for k, v in cls.dict(exclude_unset=True).items()}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = db["classes"].update_one({"_id": _oid(id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return _enrich_class(db["classes"].find_one({"_id": _oid(id)}), db)


# ── Subjects ──────────────────────────────────────────────────────────────────


def _enrich_subject(doc: dict, db: Database) -> dict:
    cls_doc = None
    if doc and doc.get("class_id"):
        try:
            cls_doc = db["classes"].find_one({"_id": _oid(doc["class_id"])})
        except Exception:
            pass
    return subject_helper(
        doc, assigned_class=_enrich_class(cls_doc, db) if cls_doc else None
    )


def _subject_source_id(doc: dict) -> str:
    return doc.get("source_subject_id") or str(doc["_id"])


def _subject_mapping_query(source_id: str, subject: dict, class_id: str) -> dict:
    return {
        "class_id": class_id,
        "$or": [
            {"source_subject_id": source_id},
            (
                {"_id": _oid(source_id)}
                if ObjectId.is_valid(source_id)
                else {"_id": source_id}
            ),
            {
                "code": subject.get("code", ""),
                "name": subject.get("name", ""),
                "requires_lab": subject.get("requires_lab", False),
                "source_subject_id": {"$exists": False},
            },
        ],
    }


@router.post("/subjects", response_model=SubjectResponse)
def create_subject(
    subj: SubjectCreate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    doc = {**subj.dict(), "created_at": datetime.utcnow()}
    if doc.get("department_ids") and not doc.get("department_id"):
        doc["department_id"] = doc["department_ids"][0]
    if doc.get("department_id") and not doc.get("department_ids"):
        doc["department_ids"] = [doc["department_id"]]
    result = db["subjects"].insert_one(doc)
    return _enrich_subject(db["subjects"].find_one({"_id": result.inserted_id}), db)


@router.get("/subjects", response_model=List[SubjectResponse])
def list_subjects(
    class_id: Optional[str] = None,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    query = {"class_id": class_id} if class_id else {}
    results = []
    for d in db["subjects"].find(query):
        try:
            results.append(_enrich_subject(d, db))
        except Exception as e:
            import logging

            logging.error(f"Error enriching subject {d.get('_id')}: {str(e)}")
            # Still include the subject even if enrichment fails
            results.append(subject_helper(d, assigned_class=None))
    return results


@router.put("/subjects/{id}", response_model=SubjectResponse)
def update_subject(
    id: str,
    subj: SubjectUpdate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    update_data = {k: v for k, v in subj.dict(exclude_unset=True).items()}
    if update_data.get("department_ids") and not update_data.get("department_id"):
        department_ids = update_data["department_ids"]
        update_data["department_id"] = department_ids[0] if department_ids else None
    if update_data.get("department_id") and not update_data.get("department_ids"):
        update_data["department_ids"] = [update_data["department_id"]]
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = db["subjects"].update_one({"_id": _oid(id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")

    # Propagate updates to cloned mappings referencing this subject
    propagate_fields = {
        k: v
        for k, v in update_data.items()
        if k
        not in [
            "class_id",
            "faculty_id",
            "source_subject_id",
            "created_at",
            "updated_at",
        ]
    }
    if propagate_fields:
        db["subjects"].update_many(
            {"source_subject_id": id}, {"$set": propagate_fields}
        )

    return _enrich_subject(db["subjects"].find_one({"_id": _oid(id)}), db)


@router.post("/subjects/{id}/map", response_model=SubjectResponse)
def map_subject_to_class(
    id: str,
    mapping: SubjectMapRequest,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    subject = db["subjects"].find_one({"_id": _oid(id)})
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    cls = db["classes"].find_one({"_id": _oid(mapping.class_id)})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")

    fac = db["faculty"].find_one({"_id": _oid(mapping.faculty_id)})
    if not fac:
        raise HTTPException(status_code=404, detail="Faculty not found")

    provided_fields = getattr(
        mapping, "model_fields_set", getattr(mapping, "__fields_set__", set())
    )
    if "room_id" in provided_fields:
        if mapping.room_id:
            room = db["rooms"].find_one({"_id": _oid(mapping.room_id)})
            if not room:
                raise HTTPException(status_code=404, detail="Room not found")
        db["classes"].update_one(
            {"_id": cls["_id"]},
            {"$set": {"room_id": mapping.room_id, "updated_at": datetime.utcnow()}},
        )

    source_id = _subject_source_id(subject)
    existing = db["subjects"].find_one(
        _subject_mapping_query(source_id, subject, mapping.class_id)
    )
    if existing:
        db["subjects"].update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "class_id": mapping.class_id,
                    "faculty_id": mapping.faculty_id,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return _enrich_subject(db["subjects"].find_one({"_id": existing["_id"]}), db)

    clone_fields = {
        "name": subject.get("name", ""),
        "code": subject.get("code", ""),
        "hours_per_week": subject.get("hours_per_week"),
        "credits": subject.get("credits", 3),
        "requires_lab": subject.get("requires_lab", False),
        "department_id": subject.get("department_id"),
        "department_ids": subject.get("department_ids")
        or ([subject.get("department_id")] if subject.get("department_id") else []),
        "batch_id": subject.get("batch_id"),
        "class_id": mapping.class_id,
        "faculty_id": mapping.faculty_id,
        "source_subject_id": source_id,
        "created_at": datetime.utcnow(),
    }
    result = db["subjects"].insert_one(clone_fields)
    return _enrich_subject(db["subjects"].find_one({"_id": result.inserted_id}), db)


@router.delete("/subjects/{id}")
def delete_subject(
    id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    # Delete all cloned mappings referencing this subject
    db["subjects"].delete_many({"source_subject_id": id})
    result = db["subjects"].delete_one({"_id": _oid(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


# ── Faculty ───────────────────────────────────────────────────────────────────


@router.post("/faculty", response_model=FacultyResponse)
def create_faculty(
    fac: FacultyCreate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    # Defensive validation: ensure types and shapes to avoid downstream constraint/parser errors
    payload = fac.dict()
    try:
        # max_hours_per_week must be an int >= 0
        max_h = int(payload.get("max_hours_per_week", 0))
        if max_h < 0:
            raise ValueError("max_hours_per_week must be non-negative")
        payload["max_hours_per_week"] = max_h

        # unavailable_slots must be a list of dicts (optional)
        us = payload.get("unavailable_slots", []) or []
        if not isinstance(us, list):
            raise ValueError("unavailable_slots must be a list")
        # shallow validation of each slot
        for s in us:
            if not isinstance(s, dict):
                raise ValueError("each unavailable slot must be an object")
            # optional keys: day, start, end
            # ensure start/end are strings if present
            for k in ("start", "end"):
                if k in s and s[k] is not None and not isinstance(s[k], str):
                    raise ValueError(
                        f"unavailable_slots.{k} must be a string in HH:MM form"
                    )

        payload["unavailable_slots"] = us
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid faculty data: {e}")

    doc = {**payload, "created_at": datetime.utcnow()}
    result = db["faculty"].insert_one(doc)
    return faculty_helper(db["faculty"].find_one({"_id": result.inserted_id}))


@router.get("/faculty", response_model=List[FacultyResponse])
def list_faculty(
    department_id: Optional[str] = None,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    query = {"department_id": department_id} if department_id else {}
    return [faculty_helper(d) for d in db["faculty"].find(query)]


@router.delete("/faculty/{id}")
def delete_faculty(
    id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    result = db["faculty"].delete_one({"_id": _oid(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


@router.put("/faculty/{id}", response_model=FacultyResponse)
def update_faculty(
    id: str,
    fac: FacultyUpdate,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    update_data = {k: v for k, v in fac.dict(exclude_unset=True).items()}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate updated fields similarly to create
    if "max_hours_per_week" in update_data:
        try:
            mh = (
                int(update_data["max_hours_per_week"])
                if update_data["max_hours_per_week"] is not None
                else None
            )
            if mh is not None and mh < 0:
                raise ValueError("max_hours_per_week must be non-negative")
            update_data["max_hours_per_week"] = mh
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid max_hours_per_week: {e}"
            )

    if "unavailable_slots" in update_data:
        us = update_data["unavailable_slots"] or []
        if not isinstance(us, list):
            raise HTTPException(
                status_code=400, detail="unavailable_slots must be a list"
            )
        for s in us:
            if not isinstance(s, dict):
                raise HTTPException(
                    status_code=400, detail="each unavailable slot must be an object"
                )
            for k in ("start", "end"):
                if k in s and s[k] is not None and not isinstance(s[k], str):
                    raise HTTPException(
                        status_code=400,
                        detail=f"unavailable_slots.{k} must be a string",
                    )

    result = db["faculty"].update_one({"_id": _oid(id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return faculty_helper(db["faculty"].find_one({"_id": _oid(id)}))


# ── Timetable Generation ──────────────────────────────────────────────────────


@router.post("/constraints/from-files")
async def generate_constraints_from_files(
    files: List[UploadFile] = File(...),
    periods_per_day: int = Form(9),
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    if not files:
        raise HTTPException(
            status_code=400, detail="Upload at least one timetable or constraint file."
        )
    if len(files) > settings.DOCUMENT_UPLOAD_MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Upload up to {settings.DOCUMENT_UPLOAD_MAX_FILES} files at a time.",
        )

    extracted_documents = []
    for file in files:
        content = await file.read()
        if len(content) > settings.DOCUMENT_UPLOAD_MAX_FILE_BYTES:
            limit_mb = settings.DOCUMENT_UPLOAD_MAX_FILE_BYTES // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"{file.filename or 'Uploaded file'} is larger than the {limit_mb} MB limit.",
            )

        extracted_documents.append(
            extract_document_text(
                file.filename or "uploaded-file",
                content,
                file.content_type,
                max_chars=settings.DOCUMENT_TEXT_MAX_CHARS,
                ocr_max_pages=settings.DOCUMENT_OCR_MAX_PAGES,
            )
        )

    context = _build_ai_constraint_context(db, periods_per_day)
    document_analysis = analyze_academic_documents(
        extracted_documents,
        model=settings.active_document_analysis_model,
        api_base=settings.active_document_analysis_api_base,
        api_key=settings.active_document_analysis_api_key,
        timeout_seconds=settings.DOCUMENT_ANALYSIS_TIMEOUT_SECONDS,
        max_chars=settings.DOCUMENT_ANALYSIS_MAX_CHARS,
    )
    constraints_text, detected_constraints, conversion_warnings = (
        build_constraint_text_from_documents(
            extracted_documents,
            context,
        )
    )

    if not constraints_text.strip():
        raise HTTPException(
            status_code=400,
            detail="No readable timetable text could be extracted from the uploaded file(s).",
        )

    # Keep document parsing local. The generated text is parsed with the deterministic
    # parser here; normal generation may still use the configured AI parser for user edits.
    parser = AIConstraintParser(context=context)
    parse_result = parser.parse_constraints_with_diagnostics(constraints_text)
    file_warnings = [
        warning for document in extracted_documents for warning in document.warnings
    ]

    return {
        "constraints_text": constraints_text,
        "custom_constraints": parse_result.get("constraints", []),
        "detected_constraints": detected_constraints,
        "extracted_timetable": document_analysis.get("extracted_timetable", []),
        "document_analysis": {
            "source": document_analysis.get("source"),
            "model": document_analysis.get("model"),
            "warnings": document_analysis.get("warnings", []),
        },
        "parse_diagnostics": {
            "corrections": parse_result.get("corrections", []),
            "warnings": parse_result.get("warnings", []),
            "unrecognized": parse_result.get("unrecognized", []),
        },
        "files": [
            {
                "filename": document.filename,
                "content_type": document.content_type,
                "extractor": document.extractor,
                "characters": len(document.text),
                "warnings": document.warnings,
            }
            for document in extracted_documents
        ],
        "warnings": conversion_warnings
        + file_warnings
        + document_analysis.get("warnings", []),
        "extracted_text_preview": "\n\n".join(
            document.text[:2000]
            for document in extracted_documents
            if document.text.strip()
        )[:6000],
    }


@router.post("/generate", response_model=TimetableResponse)
def generate_timetable(
    request: TimetableGenerateRequest,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    custom_constraints = []
    parse_diagnostics = {"corrections": [], "warnings": [], "unrecognized": []}
    if request.constraints_text:
        try:
            # ── Build context from live DB data so AI can match real names ──
            context = _build_ai_constraint_context(db, request.periods_per_day)

            parser = AIConstraintParser(
                model=settings.active_ai_model,
                timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
                api_key=settings.active_ai_api_key,
                api_base=settings.active_ai_api_base,
                context=context,
            )
            parse_result = parser.parse_constraints_with_diagnostics(
                request.constraints_text
            )
            custom_constraints = parse_result["constraints"]
            parse_diagnostics = {
                "corrections": parse_result.get("corrections", []),
                "warnings": parse_result.get("warnings", []),
                "unrecognized": parse_result.get("unrecognized", []),
            }
            if custom_constraints:
                print(
                    f"Parsed {len(custom_constraints)} constraints: {custom_constraints}"
                )
            else:
                print(
                    "Warning: no constraints parsed — proceeding without custom constraints"
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"AI constraint parsing failed: {e}"
            )

    scheduler = TimetableScheduler(
        db=db,
        working_days=request.working_days,
        periods_per_day=request.periods_per_day,
        time_limit_seconds=settings.SOLVER_TIME_LIMIT_SECONDS,
        custom_constraints=custom_constraints,
    )
    result = scheduler.generate_schedule(
        department_ids=request.department_ids,
        batch_ids=request.batch_ids,
        class_ids=request.class_ids,
        faculty_ids=request.faculty_ids,
    )
    if result["status"] == "ERROR":
        raise HTTPException(status_code=400, detail=result.get("message", "Failed"))
    if result["status"] in ["INFEASIBLE", "MODEL_INVALID"]:
        raise HTTPException(
            status_code=400,
            detail=f"Could not find valid timetable. Status: {result['status']}",
        )

    doc = {
        "name": request.name,
        "academic_year": request.academic_year,
        "semester": request.semester,
        "schedule_data": result["schedule"],
        "constraints_used": {
            "working_days": request.working_days,
            "periods_per_day": result.get(
                "effective_periods_per_day", request.periods_per_day
            ),
            "requested_periods_per_day": request.periods_per_day,
            "department_ids": request.department_ids,
            "start_time": request.start_time,
            "end_time": request.end_time,
            "period_duration_mins": request.period_duration_mins,
            "break_after_period": request.break_after_period,
            "break_duration_mins": request.break_duration_mins,
            "lunch_after_period": request.lunch_after_period,
            "lunch_duration_mins": request.lunch_duration_mins,
            "break2_after_period": request.break2_after_period,
            "break2_duration_mins": request.break2_duration_mins,
            "constraints_text": request.constraints_text,
            "custom_constraints": custom_constraints,
            "parse_diagnostics": parse_diagnostics,
            "auto_adjustments": result.get("auto_adjustments", []),
            "constraint_warnings": result.get("constraint_warnings", []),
            "substitutes": result.get("substitutes", {}),
        },
        "solver_status": result["status"],
        "solve_time_seconds": result["solve_time"],
        "created_at": datetime.utcnow(),
    }
    ins = db["timetables"].insert_one(doc)
    return timetable_helper(db["timetables"].find_one({"_id": ins.inserted_id}))


@router.get("/timetables", response_model=List[TimetableResponse])
def list_timetables(
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    return [timetable_helper(d) for d in db["timetables"].find().sort("created_at", -1)]


@router.get("/timetables/{id}", response_model=TimetableResponse)
def get_timetable(
    id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    doc = db["timetables"].find_one({"_id": _oid(id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return timetable_helper(doc)


@router.delete("/timetables/{id}")
def delete_timetable(
    id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    result = db["timetables"].delete_one({"_id": _oid(id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}
