"""
learning_engine.py — Phase 14: Learning Engine

Stores and retrieves user-confirmed alias mappings.
When users repeatedly confirm that "ML" → "Machine Learning",
future uploads automatically apply this normalization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from loguru import logger
from pymongo.database import Database


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record_alias_decision(
    db: Database,
    original: str,
    resolved: str,
    entity_type: str,
    user: str,
    upload_session_id: str,
) -> None:
    """
    Record that a user confirmed an alias mapping.
    Increments the confirmation count if the mapping already exists.
    """
    original_norm = original.strip().lower()
    resolved_norm = resolved.strip().lower()

    if not original_norm or not resolved_norm or original_norm == resolved_norm:
        return

    existing = db["ingestion_alias_rules"].find_one(
        {
            "original": original_norm,
            "entity_type": entity_type,
        }
    )

    if existing:
        db["ingestion_alias_rules"].update_one(
            {"_id": existing["_id"]},
            {
                "$inc": {"confirmation_count": 1},
                "$set": {
                    "resolved": resolved_norm,
                    "last_confirmed_by": user,
                    "last_confirmed_at": _utcnow(),
                    "last_session_id": upload_session_id,
                },
            },
        )
        logger.debug(
            f"Alias confirmed: '{original}' → '{resolved}' (count={existing.get('confirmation_count', 0) + 1})"
        )
    else:
        db["ingestion_alias_rules"].insert_one(
            {
                "original": original_norm,
                "resolved": resolved_norm,
                "entity_type": entity_type,
                "confirmation_count": 1,
                "created_by": user,
                "created_at": _utcnow(),
                "last_confirmed_by": user,
                "last_confirmed_at": _utcnow(),
                "last_session_id": upload_session_id,
            }
        )
        logger.info(f"New alias learned: '{original}' → '{resolved}' for {entity_type}")


def get_learned_aliases(
    db: Database,
    entity_type: Optional[str] = None,
    min_confirmations: int = 1,
) -> Dict[str, str]:
    """
    Retrieve all confirmed alias mappings as a dict {original: resolved}.
    These are passed to the deduplicator for normalization.
    """
    query: Dict = {"confirmation_count": {"$gte": min_confirmations}}
    if entity_type:
        query["entity_type"] = entity_type

    rules = db["ingestion_alias_rules"].find(query)
    return {rule["original"]: rule["resolved"] for rule in rules}


def get_all_aliases(db: Database) -> List[Dict]:
    """Retrieve all alias rules for display in the admin UI."""
    rules = list(
        db["ingestion_alias_rules"].find({}, sort=[("confirmation_count", -1)])
    )
    for r in rules:
        r["_id"] = str(r["_id"])
    return rules


def delete_alias(db: Database, alias_id: str) -> bool:
    """Delete an alias rule by ID."""
    from bson import ObjectId

    try:
        result = db["ingestion_alias_rules"].delete_one({"_id": ObjectId(alias_id)})
        return result.deleted_count > 0
    except Exception:
        return False
