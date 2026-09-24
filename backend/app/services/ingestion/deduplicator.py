"""
deduplicator.py — Phases 6 & 7: Duplicate Detection + Similarity Scoring

Compares extracted entities against MongoDB and within the current batch.
Uses:
  - Exact matching
  - Normalized matching (casefold, remove whitespace/punctuation)
  - RapidFuzz fuzzy string matching
  - Sentence embedding cosine similarity (when available)
  - Abbreviation expansion from the Learning Engine

Confidence thresholds (configurable):
  100–99  → Auto-Merge
  98–95   → Strong Recommendation
  94–85   → Ask User
  <85     → New Record
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

from loguru import logger

# ── Threshold constants ────────────────────────────────────────────────────────
THRESHOLD_AUTO_MERGE = 98
THRESHOLD_STRONG = 95
THRESHOLD_UPDATE = 90
THRESHOLD_ASK = 90
# < THRESHOLD_ASK → treat as new record

# ── Known common abbreviations ─────────────────────────────────────────────────
BUILTIN_ABBREVIATIONS: Dict[str, str] = {
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "ds": "data structures",
    "os": "operating systems",
    "dbms": "database management systems",
    "cn": "computer networks",
    "se": "software engineering",
    "cs": "computer science",
    "ece": "electronics and communication engineering",
    "mech": "mechanical engineering",
    "civil": "civil engineering",
    "it": "information technology",
    "cse": "computer science and engineering",
    "eee": "electrical and electronics engineering",
    "lab": "laboratory",
    "dept": "department",
    "prof": "professor",
    "dr": "doctor",
    "mr": "mister",
    "ms": "miss",
}


# ── Text normalization ─────────────────────────────────────────────────────────


def _normalize(text: str, learned_aliases: Optional[Dict[str, str]] = None) -> str:
    """
    Normalize a string for comparison:
    1. Lowercase + strip accents
    2. Remove punctuation/whitespace
    3. Expand known abbreviations
    4. Apply learned aliases from the learning engine
    """
    if not text:
        return ""
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    # Remove titles
    text = re.sub(r"\b(dr|prof|mr|ms|mrs|sri|shri)\.?\b", "", text)
    # Remove punctuation and extra spaces
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Expand abbreviations
    all_abbrevs = {**BUILTIN_ABBREVIATIONS}
    if learned_aliases:
        all_abbrevs.update({k.lower(): v.lower() for k, v in learned_aliases.items()})

    words = text.split()
    expanded = [all_abbrevs.get(w, w) for w in words]
    return " ".join(expanded)


def _fuzzy_score(s1: str, s2: str) -> float:
    """RapidFuzz token sort ratio (handles word order differences)."""
    try:
        from rapidfuzz import fuzz

        return fuzz.token_sort_ratio(s1, s2)  # returns 0–100
    except ImportError:
        # Pure Python fallback
        return _levenshtein_score(s1, s2) * 100


def _levenshtein_score(s1: str, s2: str) -> float:
    """Simple Levenshtein similarity 0–1."""
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    matrix = list(range(len2 + 1))
    for i in range(1, len1 + 1):
        prev = matrix[:]
        matrix[0] = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            matrix[j] = min(matrix[j] + 1, matrix[j - 1] + 1, prev[j - 1] + cost)
    dist = matrix[len2]
    return 1.0 - (dist / max(len1, len2))


# ── Embedding similarity ───────────────────────────────────────────────────────

_embedder = None  # lazy-loaded


def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("SentenceTransformer loaded (all-MiniLM-L6-v2)")
    except Exception as exc:
        logger.warning(f"Sentence embeddings unavailable: {exc}")
        _embedder = False  # mark as unavailable
    return _embedder


def _embedding_similarity(s1: str, s2: str) -> Optional[float]:
    """Cosine similarity between sentence embeddings. Returns 0–100 or None."""
    embedder = _get_embedder()
    if not embedder:
        return None
    try:
        import numpy as np

        vecs = embedder.encode([s1, s2], normalize_embeddings=True)
        cosine = float(np.dot(vecs[0], vecs[1]))
        return max(0.0, cosine) * 100
    except Exception as exc:
        logger.debug(f"Embedding similarity failed: {exc}")
        return None


# ── Primary key extraction ─────────────────────────────────────────────────────


def _get_match_keys(entity_type: str, entity: Dict) -> List[str]:
    """Return the list of field values used for matching this entity type."""
    mapping = {
        "departments": ["name", "code"],
        "faculty": ["name", "email"],
        "subjects": ["name", "code"],
        "rooms": ["name", "code"],
        "classes": ["name"],
        "batches": ["name"],
    }
    fields = mapping.get(entity_type, ["name"])
    return [str(entity.get(f, "")).strip() for f in fields if entity.get(f)]


# ── Similarity computation ─────────────────────────────────────────────────────


def compute_similarity(
    new_val: str,
    existing_val: str,
    learned_aliases: Optional[Dict[str, str]] = None,
) -> float:
    """
    Compute similarity score (0–100) between two string values.
    Uses: exact → normalized → fuzzy → embedding.
    """
    if not new_val or not existing_val:
        return 0.0

    # Exact match
    if new_val.strip().lower() == existing_val.strip().lower():
        return 100.0

    # Normalized match
    norm_new = _normalize(new_val, learned_aliases)
    norm_existing = _normalize(existing_val, learned_aliases)
    if norm_new == norm_existing:
        return 100.0
    if not norm_new or not norm_existing:
        return 0.0

    # Substring containment (abbreviation match)
    if norm_new in norm_existing or norm_existing in norm_new:
        shorter = min(len(norm_new), len(norm_existing))
        longer = max(len(norm_new), len(norm_existing))
        score = (shorter / longer) * 90
        # Attempt embedding to confirm
        embed_score = _embedding_similarity(norm_new, norm_existing)
        if embed_score is not None:
            return max(score, embed_score)
        return score

    # Fuzzy score
    fuzzy = _fuzzy_score(norm_new, norm_existing)

    # Embedding score (if available)
    embed_score = _embedding_similarity(norm_new, norm_existing)
    if embed_score is not None:
        return max(fuzzy, embed_score)

    return fuzzy


# ── Main duplicate detection ───────────────────────────────────────────────────


class DuplicateResult:
    """Result of a single duplicate check."""

    def __init__(
        self,
        entity_type: str,
        new_entity: Dict,
        existing_entity: Optional[Dict],
        score: float,
        match_reason: str,
        action: str,  # "auto_merge" | "strong_recommendation" | "ask_user" | "new_record"
        conflicting_fields: Optional[List[Dict]] = None,
    ):
        self.entity_type = entity_type
        self.new_entity = new_entity
        self.existing_entity = existing_entity
        self.score = score
        self.match_reason = match_reason
        self.action = action
        self.conflicting_fields = conflicting_fields or []

    def to_dict(self) -> Dict:
        return {
            "entity_type": self.entity_type,
            "new_entity": self.new_entity,
            "existing_entity": self.existing_entity,
            "score": round(self.score, 2),
            "match_reason": self.match_reason,
            "action": self.action,
            "conflicting_fields": self.conflicting_fields,
        }


def _classify_action(score: float, has_key_match: bool = False) -> str:
    if score >= THRESHOLD_AUTO_MERGE:
        return "auto_merge"
    elif score >= THRESHOLD_UPDATE and has_key_match:
        return "auto_update"
    elif score >= THRESHOLD_ASK:
        return "ask_user"
    else:
        return "new_record"



def find_duplicate(
    entity_type: str,
    new_entity: Dict,
    existing_entities: List[Dict],
    learned_aliases: Optional[Dict[str, str]] = None,
) -> DuplicateResult:
    """
    Find the best matching existing entity for a new entity.
    Returns a DuplicateResult with similarity score and recommended action.
    """
    new_keys = _get_match_keys(entity_type, new_entity)
    if not new_keys:
        return DuplicateResult(
            entity_type, new_entity, None, 0.0, "No key fields", "new_record"
        )

    best_score = 0.0
    best_match = None
    best_reason = ""
    has_key_match = False

    for existing in existing_entities:
        ex_keys = _get_match_keys(entity_type, existing)
        if not ex_keys:
            continue

        # Check for strict key identifier match (e.g. Email or Code) for auto_update
        strict_keys = []
        if entity_type == "faculty":
            strict_keys = [str(new_entity.get("email", "")).strip().lower()] if new_entity.get("email") else []
            ex_strict_keys = [str(existing.get("email", "")).strip().lower()] if existing.get("email") else []
        elif entity_type in ["departments", "subjects", "rooms"]:
            strict_keys = [str(new_entity.get("code", "")).strip().lower()] if new_entity.get("code") else []
            ex_strict_keys = [str(existing.get("code", "")).strip().lower()] if existing.get("code") else []

        strict_match = False
        if strict_keys and ex_strict_keys:
            for sk in strict_keys:
                if sk and sk in ex_strict_keys:
                    strict_match = True
                    break

        # Compare all key combinations, take max
        for nk in new_keys:
            for ek in ex_keys:
                s = compute_similarity(nk, ek, learned_aliases)
                if s > best_score:
                    best_score = s
                    best_match = existing
                    best_reason = f"'{nk}' ≈ '{ek}' ({s:.1f}%)"
                    has_key_match = strict_match

    action = _classify_action(best_score, has_key_match)

    # Detect field-level conflicts if there's a match
    conflicts: List[Dict] = []
    if best_match and best_score >= THRESHOLD_ASK:
        conflicts = _detect_field_conflicts(entity_type, new_entity, best_match)

    return DuplicateResult(
        entity_type=entity_type,
        new_entity=new_entity,
        existing_entity=best_match,
        score=best_score,
        match_reason=best_reason,
        action=action,
        conflicting_fields=conflicts,
    )

def _detect_field_conflicts(
    entity_type: str, new_entity: Dict, existing: Dict
) -> List[Dict]:
    """
    Phase 8 (partial): Detect fields that differ between new and existing entity.
    Returns list of conflict dicts for display in the Review Dashboard.
    """
    # Fields that can conflict (never conflict on IDs or timestamps)
    conflict_fields = {
        "departments": ["name", "code"],
        "faculty": ["name", "email", "department_code", "max_hours_per_week"],
        "subjects": ["name", "code", "credits", "hours_per_week", "requires_lab"],
        "rooms": ["name", "code", "room_type", "capacity"],
        "classes": ["name", "section", "semester", "student_count"],
        "batches": ["name", "start_time", "end_time"],
    }
    fields = conflict_fields.get(entity_type, [])
    conflicts = []

    for field in fields:
        new_val = new_entity.get(field)
        existing_val = existing.get(field)

        if new_val is None or existing_val is None:
            continue
        if str(new_val).strip().lower() == str(existing_val).strip().lower():
            continue

        conflicts.append(
            {
                "field": field,
                "existing_value": existing_val,
                "new_value": new_val,
                "severity": "high" if field in ("code", "email") else "medium",
            }
        )

    return conflicts


def check_missing_fields(entity_type: str, entity: Dict) -> Dict[str, List[str]]:
    """
    Phase 9: Detect missing important fields for an entity.
    Returns a dict with 'required' and 'recommended' missing fields.
    """
    required_fields = {
        "departments": ["name", "code"],
        "faculty": ["name", "department_code"],
        "subjects": ["name", "code"],
        "rooms": ["name"],
        "classes": ["name"],
        "batches": ["name"],
    }
    recommended_fields = {
        "departments": [],
        "faculty": ["designation", "max_hours_per_week"],
        "subjects": ["credits", "hours_per_week"],
        "rooms": ["room_type", "capacity"],
        "classes": ["semester", "department_code"],
        "batches": ["start_time", "end_time"],
    }

    # Add mapping to match provided prompt:
    # Faculty Required: facultyName (handled as name here, it maps to name in db), department
    # Note: 'facultyName' and 'department' maps to 'name' and 'department_code' in our schema

    missing = {"required": [], "recommended": []}
    for field in required_fields.get(entity_type, []):
        if not entity.get(field):
            missing["required"].append(field)
    for field in recommended_fields.get(entity_type, []):
        if not entity.get(field) and entity.get(field) != 0:
            missing["recommended"].append(field)

    return missing


def run_deduplication(
    entity_type: str,
    new_entities: List[Dict],
    db_entities: List[Dict],
    learned_aliases: Optional[Dict[str, str]] = None,
) -> List[DuplicateResult]:
    """
    Run duplicate detection for a batch of new entities against the database.
    Also checks within the new batch itself for cross-upload duplicates.
    """
    all_existing = list(db_entities)  # start with DB records
    results: List[DuplicateResult] = []

    for entity in new_entities:
        result = find_duplicate(entity_type, entity, all_existing, learned_aliases)
        results.append(result)

        # If it's a new record, add it to the "seen" pool to detect intra-batch dupes
        if result.action == "new_record":
            all_existing.append(entity)

    return results
