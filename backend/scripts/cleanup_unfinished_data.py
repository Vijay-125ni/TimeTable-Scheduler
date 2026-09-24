import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from bson import ObjectId

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.database.database import get_client


MAX_EXAMPLES = 8


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def object_id_strings(docs: Iterable[Dict[str, Any]]) -> set[str]:
    return {str(doc["_id"]) for doc in docs if doc.get("_id") is not None}


def describe(doc: Dict[str, Any]) -> str:
    label = doc.get("name") or doc.get("code") or doc.get("username") or doc.get("email") or "<no label>"
    return f"{doc.get('_id')} | {label}"


def add_reason(reasons: List[Tuple[str, str]], collection: str, doc: Dict[str, Any], reason: str) -> None:
    reasons.append((collection, str(doc["_id"]), reason))


def collect_unfinished(db, include_unassigned: bool) -> List[Tuple[str, str, str]]:
    reasons: List[Tuple[str, str, str]] = []

    departments = list(db["departments"].find({}, {"name": 1, "code": 1}))
    batches = list(db["batches"].find({}, {"name": 1, "start_time": 1, "end_time": 1, "period_duration": 1}))
    rooms = list(db["rooms"].find({}, {"name": 1, "capacity": 1, "department_id": 1}))
    faculty = list(db["faculty"].find({}, {"name": 1, "email": 1, "department_id": 1}))
    classes = list(db["classes"].find({}, {"name": 1, "department_id": 1, "batch_id": 1, "room_id": 1}))
    subjects = list(db["subjects"].find({}, {
        "name": 1,
        "code": 1,
        "hours_per_week": 1,
        "department_id": 1,
        "department_ids": 1,
        "batch_id": 1,
        "class_id": 1,
        "faculty_id": 1,
        "source_subject_id": 1,
    }))
    timetables = list(db["timetables"].find({}, {"name": 1, "schedule_data": 1, "solver_status": 1}))

    department_ids = object_id_strings(departments)
    batch_ids = object_id_strings(batches)
    room_ids = object_id_strings(rooms)
    faculty_ids = object_id_strings(faculty)
    class_ids = object_id_strings(classes)
    subject_ids = object_id_strings(subjects)

    for doc in departments:
        if is_blank(doc.get("name")) or is_blank(doc.get("code")):
            add_reason(reasons, "departments", doc, "missing department name/code")

    for doc in batches:
        if is_blank(doc.get("name")) or is_blank(doc.get("start_time")) or is_blank(doc.get("end_time")):
            add_reason(reasons, "batches", doc, "missing batch name/start/end time")
        elif doc.get("period_duration") in (None, 0):
            add_reason(reasons, "batches", doc, "missing period duration")

    for doc in rooms:
        if is_blank(doc.get("name")):
            add_reason(reasons, "rooms", doc, "missing room name")
        elif doc.get("department_id") and str(doc["department_id"]) not in department_ids:
            add_reason(reasons, "rooms", doc, "room references missing department")

    for doc in faculty:
        if is_blank(doc.get("name")) or is_blank(doc.get("email")):
            add_reason(reasons, "faculty", doc, "missing faculty name/email")
        elif doc.get("department_id") and str(doc["department_id"]) not in department_ids:
            add_reason(reasons, "faculty", doc, "faculty references missing department")

    for doc in classes:
        if is_blank(doc.get("name")):
            add_reason(reasons, "classes", doc, "missing class name")
        elif doc.get("department_id") and str(doc["department_id"]) not in department_ids:
            add_reason(reasons, "classes", doc, "class references missing department")
        elif doc.get("batch_id") and str(doc["batch_id"]) not in batch_ids:
            add_reason(reasons, "classes", doc, "class references missing batch")
        elif doc.get("room_id") and str(doc["room_id"]) not in room_ids:
            add_reason(reasons, "classes", doc, "class references missing room")
        elif include_unassigned and (is_blank(doc.get("department_id")) or is_blank(doc.get("batch_id"))):
            add_reason(reasons, "classes", doc, "class missing department/batch assignment")

    for doc in subjects:
        department_refs = [str(x) for x in (doc.get("department_ids") or [])]
        if doc.get("department_id"):
            department_refs.append(str(doc["department_id"]))

        if is_blank(doc.get("name")) or is_blank(doc.get("code")):
            add_reason(reasons, "subjects", doc, "missing subject name/code")
        elif doc.get("hours_per_week") in (None, 0):
            add_reason(reasons, "subjects", doc, "missing subject hours_per_week")
        elif any(ref not in department_ids for ref in department_refs):
            add_reason(reasons, "subjects", doc, "subject references missing department")
        elif doc.get("batch_id") and str(doc["batch_id"]) not in batch_ids:
            add_reason(reasons, "subjects", doc, "subject references missing batch")
        elif doc.get("class_id") and str(doc["class_id"]) not in class_ids:
            add_reason(reasons, "subjects", doc, "subject references missing class")
        elif doc.get("faculty_id") and str(doc["faculty_id"]) not in faculty_ids:
            add_reason(reasons, "subjects", doc, "subject references missing faculty")
        elif doc.get("source_subject_id") and str(doc["source_subject_id"]) not in subject_ids:
            add_reason(reasons, "subjects", doc, "subject clone references missing source subject")
        elif include_unassigned and (is_blank(doc.get("class_id")) or is_blank(doc.get("faculty_id"))):
            add_reason(reasons, "subjects", doc, "subject missing class/faculty assignment")

    failed_statuses = {"failed", "infeasible", "no_solution", "no solution", "error"}
    for doc in timetables:
        status = str(doc.get("solver_status") or "").strip().lower()
        schedule_data = doc.get("schedule_data")
        if is_blank(doc.get("name")):
            add_reason(reasons, "timetables", doc, "missing timetable name")
        elif not schedule_data:
            add_reason(reasons, "timetables", doc, "empty schedule_data")
        elif status in failed_statuses:
            add_reason(reasons, "timetables", doc, f"failed solver status: {doc.get('solver_status')}")

    return reasons


def print_report(db, reasons: List[Tuple[str, str, str]]) -> None:
    print(f"Database: {settings.DB_NAME}")
    print("Candidate unfinished records:")

    if not reasons:
        print("  None found.")
        return

    by_collection: Dict[str, List[Tuple[str, str]]] = {}
    for collection, doc_id, reason in reasons:
        by_collection.setdefault(collection, []).append((doc_id, reason))

    for collection, entries in sorted(by_collection.items()):
        print(f"  {collection}: {len(entries)}")
        for doc_id, reason in entries[:MAX_EXAMPLES]:
            doc = db[collection].find_one({"_id": ObjectId(doc_id)})
            print(f"    - {describe(doc)} | {reason}")
        if len(entries) > MAX_EXAMPLES:
            print(f"    ... {len(entries) - MAX_EXAMPLES} more")


def delete_records(db, reasons: List[Tuple[str, str, str]]) -> None:
    by_collection: Dict[str, List[ObjectId]] = {}
    for collection, doc_id, _reason in reasons:
        by_collection.setdefault(collection, []).append(ObjectId(doc_id))

    for collection, ids in sorted(by_collection.items()):
        result = db[collection].delete_many({"_id": {"$in": ids}})
        print(f"Deleted {result.deleted_count} from {collection}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Find and optionally remove unfinished timetable scheduler data.")
    parser.add_argument("--apply", action="store_true", help="Delete the candidate records. Without this flag, only prints a dry-run report.")
    parser.add_argument(
        "--include-unassigned",
        action="store_true",
        help="Also include classes missing department/batch and subjects missing class/faculty assignments.",
    )
    args = parser.parse_args()

    db = get_client()[settings.DB_NAME]
    reasons = collect_unfinished(db, include_unassigned=args.include_unassigned)
    print_report(db, reasons)

    if args.apply:
        delete_records(db, reasons)
    else:
        print("\nDry run only. Re-run with --apply to delete these records.")


if __name__ == "__main__":
    main()
