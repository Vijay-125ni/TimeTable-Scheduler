"""
mongo_writer.py — Phases 11 & 12 & 13: MongoDB Integration + Version History + Audit Logs

Provides atomic, idempotent writes with:
  - Full version history per entity
  - Audit log for every change
  - Rollback support
  - Referential integrity maintenance
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from loguru import logger
from pymongo.database import Database


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Collection name map ────────────────────────────────────────────────────────

ENTITY_COLLECTION: Dict[str, str] = {
    "departments": "departments",
    "faculty": "faculty",
    "subjects": "subjects",
    "rooms": "rooms",
    "classes": "classes",
    "batches": "batches",
}

# ── Version History ────────────────────────────────────────────────────────────


def record_version(
    db: Database,
    entity_type: str,
    entity_id: str,
    old_data: Optional[Dict],
    new_data: Dict,
    upload_session_id: str,
    user: str,
    action: str,
    session: Optional[Any] = None,
) -> None:
    """Store a version snapshot for rollback support."""
    db["ingestion_versions"].insert_one(
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "old_data": old_data,
            "new_data": new_data,
            "upload_session_id": upload_session_id,
            "user": user,
            "created_at": _utcnow(),
        }
    , session=session)


# ── Audit Log ─────────────────────────────────────────────────────────────────


def record_audit(
    db: Database,
    entity_type: str,
    entity_id: str,
    action: str,
    old_value: Optional[Any],
    new_value: Optional[Any],
    confidence_score: float,
    reason: str,
    user_decision: str,
    user: str,
    upload_session_id: str,
    session: Optional[Any] = None,
) -> None:
    """Record an immutable audit log entry."""
    db["ingestion_audit_logs"].insert_one(
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "old_value": old_value,
            "new_value": new_value,
            "confidence_score": confidence_score,
            "reason": reason,
            "user_decision": user_decision,
            "user": user,
            "upload_session_id": upload_session_id,
            "timestamp": _utcnow(),
        }
    , session=session)


# ── Entity Finders ─────────────────────────────────────────────────────────────


def _find_existing_entity(
    db: Database, entity_type: str, entity: Dict, session: Optional[Any] = None
) -> Optional[Dict]:
    """Find an existing DB record by natural key."""
    coll = ENTITY_COLLECTION.get(entity_type)
    if not coll:
        return None
    collection = db[coll]

    search_pairs = {
        "departments": [("code", entity.get("code")), ("name", entity.get("name"))],
        "faculty": [("email", entity.get("email"))],
        "subjects": [("code", entity.get("code"))],
        "rooms": [("code", entity.get("code")), ("name", entity.get("name"))],
        "classes": [("name", entity.get("name"))],
        "batches": [("name", entity.get("name"))],
    }

    for field, value in search_pairs.get(entity_type, []):
        if not value:
            continue
        doc = collection.find_one({field: value}, session=session)
        if doc:
            return doc

    return None


# ── Core writer ────────────────────────────────────────────────────────────────


def save_entity(
    db: Database,
    entity_type: str,
    entity: Dict,
    upload_session_id: str,
    user: str,
    action: str = "auto_merge",
    confidence_score: float = 100.0,
    reason: str = "",
    session: Optional[Any] = None,
) -> Tuple[str, bool]:
    """
    Insert or update a single entity in MongoDB.
    Records version history and audit log.

    Returns: (entity_id: str, was_inserted: bool)
    """
    coll_name = ENTITY_COLLECTION.get(entity_type)
    if not coll_name:
        raise ValueError(f"Unknown entity type: {entity_type}")

    collection = db[coll_name]
    now = _utcnow()

    # Clean entity dict
    clean = {
        k: v for k, v in entity.items() if v is not None and k not in ("id", "_id")
    }
    clean.pop("department_codes", None)  # normalize to department_ids later

    # Try to find existing
    existing = _find_existing_entity(db, entity_type, clean, session=session)

    if existing:
        existing_id = str(existing["_id"])
        update_doc = {**clean, "updated_at": now}

        # Don't overwrite existing values with None/empty
        for k, v in list(update_doc.items()):
            if v == "" or v is None:
                del update_doc[k]

        collection.update_one({"_id": existing["_id"]}, {"$set": update_doc}, session=session)

        # Record version
        record_version(
            db,
            entity_type,
            existing_id,
            dict(existing),
            update_doc,
            upload_session_id,
            user,
            "update",
            session=session,
        )

        # Audit log
        record_audit(
            db,
            entity_type,
            existing_id,
            "update",
            old_value=dict(existing),
            new_value=update_doc,
            confidence_score=confidence_score,
            reason=reason or f"Updated by ingestion session {upload_session_id}",
            user_decision=action,
            user=user,
            upload_session_id=upload_session_id,
            session=session,
        )

        logger.debug(f"Updated {entity_type}: {existing_id}")
        return existing_id, False

    else:
        insert_doc = {**clean, "created_at": now, "updated_at": now}
        result = collection.insert_one(insert_doc, session=session)
        entity_id = str(result.inserted_id)

        # Record version
        record_version(
            db,
            entity_type,
            entity_id,
            None,
            insert_doc,
            upload_session_id,
            user,
            "insert",
            session=session,
        )

        # Audit log
        record_audit(
            db,
            entity_type,
            entity_id,
            "insert",
            old_value=None,
            new_value=insert_doc,
            confidence_score=confidence_score,
            reason=reason or f"New record from ingestion session {upload_session_id}",
            user_decision=action,
            user=user,
            upload_session_id=upload_session_id,
            session=session,
        )

        logger.debug(f"Inserted {entity_type}: {entity_id}")
        return entity_id, True


# ── Upload Session History ─────────────────────────────────────────────────────


def create_upload_session(
    db: Database,
    session_id: str,
    user: str,
    file_names: List[str],
    ai_model: Optional[str] = None,
) -> str:
    """Create an upload session record in MongoDB."""
    doc = {
        "session_id": session_id,
        "user": user,
        "file_names": file_names,
        "ai_model": ai_model,
        "status": "processing",
        "started_at": _utcnow(),
        "completed_at": None,
        "stats": {
            "added": 0,
            "updated": 0,
            "merged": 0,
            "skipped": 0,
            "ignored": 0,
        },
        "entity_counts": {},
    }
    db["ingestion_sessions"].insert_one(doc)
    return session_id


def complete_upload_session(
    db: Database,
    session_id: str,
    stats: Dict,
    entity_counts: Dict,
    status: str = "completed",
) -> None:
    """Mark an upload session as completed and store final stats."""
    db["ingestion_sessions"].update_one(
        {"session_id": session_id},
        {
            "$set": {
                "status": status,
                "completed_at": _utcnow(),
                "stats": stats,
                "entity_counts": entity_counts,
            }
        },
    )


def get_upload_history(db: Database, limit: int = 50) -> List[Dict]:
    """Retrieve upload session history, newest first."""
    sessions = db["ingestion_sessions"].find({}, sort=[("started_at", -1)], limit=limit)
    result = []
    for s in sessions:
        s["_id"] = str(s["_id"])
        result.append(s)
    return result


def get_version_history(
    db: Database,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict]:
    """Retrieve version history for an entity or all entities."""
    query = {}
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id

    versions = db["ingestion_versions"].find(
        query, sort=[("created_at", -1)], limit=limit
    )
    result = []
    for v in versions:
        v["_id"] = str(v["_id"])
        result.append(v)
    return result


def rollback_session(db: Database, session_id: str, user: str) -> Dict:
    """
    Rollback all changes made in a specific upload session.
    Uses version history to restore previous state.
    """
    versions = list(
        db["ingestion_versions"].find(
            {"upload_session_id": session_id}, sort=[("created_at", -1)]
        )
    )

    rolled_back = 0
    errors = []

    for version in versions:
        entity_type = version["entity_type"]
        entity_id = version["entity_id"]
        old_data = version.get("old_data")
        action = version.get("action")
        coll_name = ENTITY_COLLECTION.get(entity_type)

        if not coll_name:
            continue

        try:
            oid = ObjectId(entity_id)
        except Exception:
            continue

        collection = db[coll_name]

        if action == "insert":
            # Undo insert → delete
            collection.delete_one({"_id": oid})
            rolled_back += 1
        elif action in ("update", "merge"):
            # Undo update → restore old data
            if old_data:
                old_clean = {k: v for k, v in old_data.items() if k != "_id"}
                collection.replace_one({"_id": oid}, old_clean, upsert=True)
                rolled_back += 1
        else:
            errors.append(f"Unknown action {action} for {entity_type}/{entity_id}")

    # Update session status
    db["ingestion_sessions"].update_one(
        {"session_id": session_id},
        {
            "$set": {
                "status": "rolled_back",
                "rolled_back_by": user,
                "rolled_back_at": _utcnow(),
            }
        },
    )

    # Audit log
    record_audit(
        db,
        "session",
        session_id,
        "rollback",
        old_value=None,
        new_value={"rolled_back_count": rolled_back},
        confidence_score=100.0,
        reason=f"Manual rollback by {user}",
        user_decision="rollback",
        user=user,
        upload_session_id=session_id,
    )

    return {"rolled_back": rolled_back, "errors": errors}


def get_audit_logs(
    db: Database,
    entity_type: Optional[str] = None,
    user: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict]:
    """Retrieve audit logs with optional filters."""
    query = {}
    if entity_type:
        query["entity_type"] = entity_type
    if user:
        query["user"] = user
    if session_id:
        query["upload_session_id"] = session_id

    logs = db["ingestion_audit_logs"].find(query, sort=[("timestamp", -1)], limit=limit)
    result = []
    for log in logs:
        log["_id"] = str(log["_id"])
        result.append(log)
    return result
