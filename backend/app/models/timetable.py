from datetime import datetime


def department_helper(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "code": doc.get("code", ""),
        "created_at": doc.get("created_at", datetime.utcnow()),
    }


def batch_helper(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "start_time": doc.get("start_time", ""),
        "end_time": doc.get("end_time", ""),
        "period_duration": doc.get("period_duration", 60),
        "break_times": doc.get("break_times", []),
        "lunch_break": doc.get("lunch_break", {}),
        "created_at": doc.get("created_at", datetime.utcnow()),
    }


def class_helper(doc: dict, department: dict = None, batch: dict = None) -> dict:
    result = {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "section": doc.get("section"),
        "semester": doc.get("semester"),
        "student_count": doc.get("student_count"),
        "department_id": doc.get("department_id"),
        "batch_id": doc.get("batch_id"),
        "room_id": doc.get("room_id"),
        "created_at": doc.get("created_at", datetime.utcnow()),
        "department": department,
        "batch": batch,
    }
    return result


def room_helper(doc: dict, department: dict = None) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "code": doc.get("code"),
        "capacity": doc.get("capacity"),
        "room_type": doc.get("room_type", "lecture"),
        "department_id": doc.get("department_id"),
        "created_at": doc.get("created_at", datetime.utcnow()),
        "department": department,
    }


def subject_helper(doc: dict, assigned_class: dict = None) -> dict:
    department_ids = doc.get("department_ids")
    if department_ids is None and doc.get("department_id"):
        department_ids = [doc.get("department_id")]

    faculty_id = doc.get("faculty_id")
    if faculty_id:
        faculty_id = str(faculty_id)

    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "code": doc.get("code", ""),
        "hours_per_week": doc.get("hours_per_week"),  # None means derive from credits
        "credits": doc.get("credits", 3),
        "requires_lab": doc.get("requires_lab", False),
        "department_id": doc.get("department_id"),
        "department_ids": department_ids or [],
        "batch_id": doc.get("batch_id"),
        "class_id": doc.get("class_id"),
        "faculty_id": faculty_id,
        "source_subject_id": doc.get("source_subject_id"),
        "created_at": doc.get("created_at", datetime.utcnow()),
        "assigned_class": assigned_class,
    }


def faculty_helper(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "department_id": doc.get("department_id"),
        "max_hours_per_week": doc.get("max_hours_per_week", 20),
        "unavailable_slots": doc.get("unavailable_slots", []),
        "created_at": doc.get("created_at", datetime.utcnow()),
    }


def timetable_helper(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "academic_year": doc.get("academic_year", ""),
        "semester": doc.get("semester", 0),
        "schedule_data": doc.get("schedule_data") or {},
        "constraints_used": doc.get("constraints_used") or {},
        "solver_status": doc.get("solver_status", ""),
        "solve_time_seconds": doc.get("solve_time_seconds", 0.0),
        "created_at": doc.get("created_at", datetime.utcnow()),
    }
