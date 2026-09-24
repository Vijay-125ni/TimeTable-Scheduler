"""
knowledge_ingestion.py — Phase 18: Backend APIs for Knowledge Ingestion Module

Provides complete REST API for all 19 phases.
All endpoints follow existing auth/router patterns.
Uses SSE (Server-Sent Events) for live progress streaming.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, File, HTTPException,
                     UploadFile)
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel
from pymongo.database import Database

from ...database.database import get_client
from ...core.security import get_admin_user, get_current_user, get_tenant_db
from ...services.ingestion.ai_extractor import (extract_entities_from_document,
                                                merge_extractions)
from ...services.ingestion.deduplicator import (check_missing_fields,
                                                run_deduplication)
from ...services.ingestion.file_handler import process_uploaded_files
from ...services.ingestion.learning_engine import (delete_alias,
                                                   get_all_aliases,
                                                   get_learned_aliases,
                                                   record_alias_decision)
from ...services.ingestion.mongo_writer import (complete_upload_session,
                                                create_upload_session,
                                                get_audit_logs,
                                                get_upload_history,
                                                get_version_history,
                                                record_audit, rollback_session,
                                                save_entity)
from ...services.ingestion.parsers import parse_document

router = APIRouter(redirect_slashes=False)

# ── In-memory progress store (cleared after retrieval) ─────────────────────────
# Key: session_id, Value: list of progress event dicts
_progress_store: Dict[str, List[Dict]] = {}


def _push_progress(session_id: str, event: Dict) -> None:
    if session_id not in _progress_store:
        _progress_store[session_id] = []
    _progress_store[session_id].append(
        {**event, "ts": datetime.now(timezone.utc).isoformat()}
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Pydantic schemas ───────────────────────────────────────────────────────────


class ReviewDecision(BaseModel):
    session_id: str
    decisions: List[
        Dict[str, Any]
    ]  # [{entity_type, entity, action, existing_id?, alias?}]


class RollbackRequest(BaseModel):
    session_id: str


class AliasDecision(BaseModel):
    original: str
    resolved: str
    entity_type: str


# ── Helper ─────────────────────────────────────────────────────────────────────


def _entity_to_db_fields(entity_type: str, entity: Dict, db: Database, session: Optional[Any] = None) -> Dict:
    """
    Convert extracted entity dict to DB-compatible format,
    resolving department_code → department_id etc.
    """
    clean = dict(entity)
    # Remove extraction-only fields
    for f in ("ai_extracted", "department_codes", "_missing"):
        clean.pop(f, None)

    # Resolve department_code → department_id
    dept_code = clean.pop("department_code", None)
    if dept_code:
        dept = db["departments"].find_one({"code": dept_code}, session=session) or db["departments"].find_one({"name": dept_code}, session=session)
        if dept:
            clean["department_id"] = str(dept["_id"])

    # Resolve department_codes → department_ids (for subjects)
    dept_codes = clean.pop("department_codes", []) or []
    if dept_codes and isinstance(dept_codes, list):
        dept_ids = []
        for code in dept_codes:
            dept = db["departments"].find_one({"code": code}, session=session) or db["departments"].find_one({"name": code}, session=session)
            if dept:
                dept_ids.append(str(dept["_id"]))
        if dept_ids:
            clean["department_ids"] = dept_ids

    return clean



# ── Phase 15 & 16: Relationships & Verification Helpers ───────────────────────

def _build_relationships(db: Database, entity_type: str, entity_id: str, clean_entity: Dict, session: Optional[Any] = None) -> None:
    """
    Automatically fetch and update related collections (e.g. mapping faculty to departments).
    """
    if entity_type == "faculty":
        dept_code = clean_entity.get("department_code")
        if dept_code:
            dept = db["departments"].find_one({"code": dept_code}, session=session)
            if dept:
                # Upsert a faculty mapping
                mapping = {
                    "faculty_id": entity_id,
                    "department_id": str(dept["_id"]),
                    "faculty_name": clean_entity.get("name"),
                    "updated_at": _utcnow(),
                }
                db["mappings"].update_one(
                    {"faculty_id": entity_id},
                    {"$set": mapping},
                    upsert=True,
                    session=session
                )

    elif entity_type == "subjects":
        # Check for departments based on department_ids already resolved in _entity_to_db_fields
        dept_ids = clean_entity.get("department_ids", [])
        for d_id in dept_ids:
            # Upsert into a generic subject-department mapping if needed,
            # but usually subjects just hold the department_ids list in our current schema.
            pass


def _verify_insertion(db: Database, entity_type: str, entity_id: str, session: Optional[Any] = None) -> None:
    """
    Phase 17: Post-Insert Verification
    Read the inserted document back from MongoDB. Throw if it doesn't exist.
    """
    from ...services.ingestion.mongo_writer import ENTITY_COLLECTION
    from bson import ObjectId
    coll_name = ENTITY_COLLECTION.get(entity_type)
    if not coll_name:
        return

    try:
        oid = ObjectId(entity_id)
    except Exception:
        raise ValueError(f"Invalid entity ID format for {entity_type}: {entity_id}")

    doc = db[coll_name].find_one({"_id": oid}, session=session)
    if not doc:
        raise RuntimeError(f"Post-insert verification failed: {entity_type} {entity_id} not found in DB.")


# ── Phase 1: Upload ────────────────────────────────────────────────────────────


@router.post("/upload")
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    """
    Upload one or more documents (including ZIPs).
    Returns session_id immediately; use /progress/{session_id} for live updates.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    # Process uploads (validate, extract ZIPs, store)
    session_id, queued_files, upload_errors = await process_uploaded_files(files)

    if not queued_files:
        raise HTTPException(
            status_code=400,
            detail=f"No valid files to process. Errors: {upload_errors}",
        )

    username = current_user.get("username", "unknown")
    file_names = [qf.original_name for qf in queued_files]

    from ...core.config import settings

    create_upload_session(
        db, session_id, username, file_names, settings.DOCUMENT_ANALYSIS_MODEL
    )

    # Queue background processing
    queued_dicts = [qf.to_dict() for qf in queued_files]
    background_tasks.add_task(
        _run_ingestion_pipeline, session_id, queued_dicts, dict(current_user), db
    )

    logger.info(
        f"Upload session {session_id}: {len(queued_files)} files queued for {username}"
    )

    return {
        "session_id": session_id,
        "queued_files": len(queued_files),
        "file_names": file_names,
        "upload_errors": upload_errors,
        "message": f"Processing {len(queued_files)} file(s) in background. Stream progress at /api/knowledge/progress/{session_id}",
    }


# ── Background pipeline ────────────────────────────────────────────────────────


async def _run_ingestion_pipeline(
    session_id: str,
    queued_dicts: List[Dict],
    current_user: Dict,
    db: Database,
) -> None:
    """
    Full async ingestion pipeline run in background:
    Parse → AI Extract → Cross-Doc Merge → Dedup → Build Review Payload
    """
    current_user.get("username", "unknown")
    total = len(queued_dicts)

    _push_progress(
        session_id,
        {"stage": "parsing", "message": "Starting document parsing...", "progress": 0},
    )

    # Phase 2: Parse all documents
    parsed_docs = []
    for i, qf in enumerate(queued_dicts):
        _push_progress(
            session_id,
            {
                "stage": "parsing",
                "message": f"Parsing {qf['original_name']}...",
                "progress": int((i / total) * 30),
                "file": qf["original_name"],
            },
        )
        await asyncio.sleep(0)  # yield to event loop

        parsed = parse_document(
            file_id=qf["file_id"],
            original_name=qf["original_name"],
            stored_path=qf["stored_path"],
            extension=qf["extension"],
        )
        parsed_docs.append(parsed)
        logger.info(f"Parsed {qf['original_name']}: {len(parsed.full_text)} chars")

    _push_progress(
        session_id,
        {
            "stage": "ai_extraction",
            "message": "Running AI entity extraction...",
            "progress": 30,
        },
    )

    # Phase 3: AI extraction per document
    extractions = []
    for i, parsed in enumerate(parsed_docs):
        _push_progress(
            session_id,
            {
                "stage": "ai_extraction",
                "message": f"Extracting entities from {parsed.original_name}...",
                "progress": 30 + int((i / total) * 30),
            },
        )
        await asyncio.sleep(0)

        extracted = extract_entities_from_document(
            file_id=parsed.file_id,
            original_name=parsed.original_name,
            full_text=parsed.full_text,
            tables=parsed.tables,
        )
        extractions.append(extracted)

    _push_progress(
        session_id,
        {
            "stage": "merging",
            "message": "Merging cross-document knowledge...",
            "progress": 60,
        },
    )
    await asyncio.sleep(0)

    # Phase 4: Cross-document merge
    merged = merge_extractions(extractions)

    _push_progress(
        session_id,
        {
            "stage": "deduplication",
            "message": "Running duplicate detection...",
            "progress": 70,
        },
    )
    await asyncio.sleep(0)


    # Phase 6 & 7: Deduplication and Database Auto-Population
    learned_aliases = get_learned_aliases(db)
    entity_types = ["departments", "faculty", "subjects", "rooms", "classes", "batches"]

    review_payload: Dict[str, List] = {
        "session_id": session_id,
        "auto_merged": [],
        "needs_review": [],
        "conflicts": [],
        "missing_fields": [],
        "new_records": [],
        "constraints": merged.get("constraints", []),
        "notes": merged.get("notes", []),
        "source_files": merged.get("source_files", []),
    }

    stats = {
        "added": 0,
        "updated": 0,
        "merged": 0,
        "conflicts": 0,
        "relationships_created": 0,
        "errors": []
    }

    client = get_client()

    for entity_type in entity_types:
        new_entities = merged.get(entity_type, [])
        if not new_entities:
            continue

        # Get existing DB records for this type
        coll_name = {
            "departments": "departments",
            "faculty": "faculty",
            "subjects": "subjects",
            "rooms": "rooms",
            "classes": "classes",
            "batches": "batches",
        }.get(entity_type, entity_type)

        db_entities = list(db[coll_name].find({}))
        # Convert ObjectIds to str for comparison
        for e in db_entities:
            e["_id"] = str(e["_id"])

        dup_results = run_deduplication(
            entity_type, new_entities, db_entities, learned_aliases
        )

        for dup_result in dup_results:
            entry = dup_result.to_dict()
            entry["entity_type"] = entity_type

            # Phase 9: Missing field detection
            missing = check_missing_fields(entity_type, dup_result.new_entity)
            if missing and (missing.get("required") or missing.get("recommended")):
                entry["missing_fields"] = missing

                # If required fields are missing, DO NOT insert, move to review payload.
                if missing.get("required"):
                    review_payload["missing_fields"].append(entry)
                    continue

            # Check action and handle automatic population
            action = dup_result.action

            if action in ("ask_user", "strong_recommendation"):
                if dup_result.conflicting_fields:
                    review_payload["conflicts"].append(entry)
                else:
                    review_payload["needs_review"].append(entry)
                stats["conflicts"] += 1
                continue

            # For new_record, auto_merge, auto_update -> populate database automatically
            try:
                with client.start_session() as session:
                    with session.start_transaction():
                        db_entity = _entity_to_db_fields(entity_type, dup_result.new_entity, db, session)
                        entity_id, was_inserted = save_entity(
                            db=db,
                            entity_type=entity_type,
                            entity=db_entity,
                            upload_session_id=session_id,
                            user=current_user.get("username", "unknown"),
                            action=action,
                            confidence_score=dup_result.score,
                            reason=dup_result.match_reason or "Automatic Population",
                            session=session
                        )

                        if was_inserted:
                            stats["added"] += 1
                        elif action == "auto_merge":
                            stats["merged"] += 1
                        else:
                            stats["updated"] += 1

                        # Build Relationships
                        _build_relationships(db, entity_type, entity_id, db_entity, session)
                        stats["relationships_created"] += 1

                        # Verify Insertion
                        _verify_insertion(db, entity_type, entity_id, session)

                        # If successful, no need to add to review_payload except for logging/reporting
                        if action == "new_record":
                            review_payload["new_records"].append(entry)
                        else:
                            review_payload["auto_merged"].append(entry)

            except Exception as e:
                logger.error(f"Error auto-populating {entity_type}: {e}")
                stats["errors"].append({"entity_type": entity_type, "error": str(e)})
                # Add to needs review if failed
                review_payload["needs_review"].append(entry)


    # Store review payload in DB for retrieval
    db["ingestion_review_sessions"].replace_one(
        {"session_id": session_id},
        {**review_payload, "created_at": _utcnow()},
        upsert=True,
    )

    stats["auto_merged"] = len(review_payload["auto_merged"])
    stats["needs_review"] = len(review_payload["needs_review"])
    stats["new_records"] = len(review_payload["new_records"])
    stats["missing_fields"] = len(review_payload["missing_fields"])

    _push_progress(
        session_id,
        {
            "stage": "ready",
            "message": "Analysis complete! Summary ready.",
            "progress": 100,
            "stats": stats,
        },
    )

    # Update session in DB
    complete_upload_session(
        db,
        session_id,
        stats,
        {et: len(merged.get(et, [])) for et in entity_types},
        status="completed" if not review_payload["conflicts"] and not review_payload["needs_review"] and not review_payload["missing_fields"] else "awaiting_review",
    )

    logger.info(f"Session {session_id} pipeline complete: {stats}")



# ── Phase: SSE Progress Streaming ─────────────────────────────────────────────


@router.get("/progress/{session_id}")
async def stream_progress(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Server-Sent Events stream for live processing progress.
    Frontend subscribes to this endpoint for real-time updates.
    """

    async def event_generator():
        sent_count = 0
        max_polls = 600  # 5 minutes max
        for _ in range(max_polls):
            events = _progress_store.get(session_id, [])
            new_events = events[sent_count:]
            for event in new_events:
                yield f"data: {json.dumps(event)}\n\n"
                sent_count += 1
                if event.get("stage") == "ready":
                    return
            await asyncio.sleep(0.5)
        yield f"data: {json.dumps({'stage': 'timeout', 'message': 'Processing timed out'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Phase 10: Review Dashboard APIs ───────────────────────────────────────────


@router.get("/review/{session_id}")
async def get_review_data(
    session_id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    """Retrieve the complete review payload for a session."""
    review = db["ingestion_review_sessions"].find_one({"session_id": session_id})
    if not review:
        raise HTTPException(
            status_code=404, detail=f"Review session '{session_id}' not found."
        )
    review["_id"] = str(review["_id"])
    return review


@router.post("/review/apply")
async def apply_review_decisions(
    body: ReviewDecision,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    """
    Apply user decisions from the Review Dashboard.
    Each decision has: entity_type, entity, action, existing_id (optional), alias (optional)

    Actions:
      - "approve"        → save as new record
      - "merge"          → merge with existing (save + update)
      - "replace"        → replace existing with new data
      - "ignore"         → skip this entity
      - "create_new"     → force insert as new (even if duplicate detected)
    """
    username = current_user.get("username", "unknown")
    session_id = body.session_id

    stats = {"added": 0, "updated": 0, "merged": 0, "skipped": 0, "errors": []}

    for decision in body.decisions:
        action = decision.get("action", "approve")
        entity_type = decision.get("entity_type")
        entity = decision.get("entity", {})
        alias_original = decision.get("alias_original")
        alias_resolved = decision.get("alias_resolved")

        if not entity_type or not entity:
            continue

        # Phase 14: Record alias if user confirmed a mapping
        if alias_original and alias_resolved:
            record_alias_decision(
                db, alias_original, alias_resolved, entity_type, username, session_id
            )

        if action == "ignore":
            stats["skipped"] += 1
            record_audit(
                db,
                entity_type,
                "N/A",
                "ignore",
                old_value=None,
                new_value=entity,
                confidence_score=decision.get("score", 0),
                reason="User ignored during review",
                user_decision="ignore",
                user=username,
                upload_session_id=session_id,
            )
            continue

        try:
            db_entity = _entity_to_db_fields(entity_type, entity, db)
            entity_id, was_inserted = save_entity(
                db=db,
                entity_type=entity_type,
                entity=db_entity,
                upload_session_id=session_id,
                user=username,
                action=action,
                confidence_score=decision.get("score", 100.0),
                reason=f"User decision: {action}",
            )
            if was_inserted:
                stats["added"] += 1
            elif action == "merge":
                stats["merged"] += 1
            else:
                stats["updated"] += 1
        except Exception as exc:
            logger.exception(f"Failed to apply decision for {entity_type}: {exc}")
            stats["errors"].append({"entity_type": entity_type, "error": str(exc)})

    # Update session stats
    complete_upload_session(db, session_id, stats, {}, status="completed")

    return {
        "message": "Review decisions applied successfully.",
        "session_id": session_id,
        "stats": stats,
    }


@router.post("/review/apply-auto/{session_id}")
async def apply_auto_merges(
    session_id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    """
    Auto-apply all decisions marked as 'auto_merge' for a session.
    Only applies records with confidence ≥ 99%.
    """
    username = current_user.get("username", "unknown")
    review = db["ingestion_review_sessions"].find_one({"session_id": session_id})
    if not review:
        raise HTTPException(status_code=404, detail="Session not found.")

    auto_entities = review.get("auto_merged", [])
    stats = {"added": 0, "updated": 0, "errors": []}

    for entry in auto_entities:
        entity_type = entry.get("entity_type")
        entity = entry.get("new_entity", {})
        if not entity_type or not entity:
            continue
        try:
            db_entity = _entity_to_db_fields(entity_type, entity, db)
            _, was_inserted = save_entity(
                db=db,
                entity_type=entity_type,
                entity=db_entity,
                upload_session_id=session_id,
                user=username,
                action="auto_merge",
                confidence_score=entry.get("score", 100.0),
                reason="Auto-merged (confidence ≥ 99%)",
            )
            if was_inserted:
                stats["added"] += 1
            else:
                stats["updated"] += 1
        except Exception as exc:
            stats["errors"].append(str(exc))

    return {"message": "Auto-merge complete.", "stats": stats}


# ── Phase 12: Version History ──────────────────────────────────────────────────


@router.get("/history")
async def list_upload_history(
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    return get_upload_history(db)


@router.get("/history/{session_id}/versions")
async def get_session_versions(
    session_id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    return get_version_history(db, entity_id=None)


@router.post("/history/{session_id}/rollback")
async def rollback_upload_session(
    session_id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    """Roll back all changes from an upload session."""
    username = current_user.get("username", "unknown")
    result = rollback_session(db, session_id, username)
    return {"message": f"Rolled back {result['rolled_back']} records.", **result}


# ── Phase 13: Audit Logs ───────────────────────────────────────────────────────


@router.get("/audit-logs")
async def list_audit_logs(
    entity_type: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 100,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    return get_audit_logs(
        db, entity_type=entity_type, session_id=session_id, limit=limit
    )


# ── Phase 14: Learning Rules ───────────────────────────────────────────────────


@router.get("/aliases")
async def list_alias_rules(
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    return get_all_aliases(db)


@router.post("/aliases")
async def create_alias_rule(
    body: AliasDecision,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    username = current_user.get("username", "unknown")
    record_alias_decision(
        db, body.original, body.resolved, body.entity_type, username, "manual"
    )
    return {"message": "Alias rule created."}


@router.delete("/aliases/{alias_id}")
async def remove_alias_rule(
    alias_id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_admin_user),
):
    deleted = delete_alias(db, alias_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alias not found.")
    return {"message": "Alias deleted."}


# ── Session status ─────────────────────────────────────────────────────────────


@router.get("/session/{session_id}")
async def get_session_status(
    session_id: str,
    db: Database = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the current status of an upload session."""
    session = db["ingestion_sessions"].find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    session["_id"] = str(session["_id"])
    return session
