import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Ensure app package is importable when running from backend/ directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app.database.database import get_db


def load_csv_file(file_path: str) -> List[Dict[str, str]]:
    with open(file_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows: List[Dict[str, str]] = []
        for row in reader:
            cleaned_row = { (k or '').strip(): (v or '').strip() for k, v in row.items() }
            rows.append(cleaned_row)
        return rows


def safe_int(value: Optional[str], default: int = 0) -> int:
    try:
        return int(value) if value is not None and value != '' else default
    except ValueError:
        return default


def safe_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    val = str(value).strip().lower()
    return val in {'1', 'true', 'yes', 'y', 'on'}


def parse_json(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def split_list(value: Optional[str], sep: str = ';') -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(sep) if item.strip()]


def get_db_client():
    return next(get_db())


def bulk_insert(db, collection: str, documents: List[dict]):
    if not documents:
        print(f"No documents found for {collection}, skipping.")
        return
    print(f"Inserting {len(documents)} documents into {collection}...")
    result = db[collection].insert_many(documents)
    print(f"Inserted {len(result.inserted_ids)} documents into {collection}.")


def find_department_id(db, code_or_name: str) -> Optional[str]:
    if not code_or_name:
        return None
    department = db['departments'].find_one({'code': code_or_name})
    if department:
        return str(department['_id'])
    department = db['departments'].find_one({'name': code_or_name})
    return str(department['_id']) if department else None


def find_batch_id(db, name: str) -> Optional[str]:
    if not name:
        return None
    batch = db['batches'].find_one({'name': name})
    return str(batch['_id']) if batch else None


def find_room_id(db, code_or_name: str) -> Optional[str]:
    if not code_or_name:
        return None
    room = db['rooms'].find_one({'code': code_or_name})
    if room:
        return str(room['_id'])
    room = db['rooms'].find_one({'name': code_or_name})
    return str(room['_id']) if room else None


def find_class_id(db, name: str, section: Optional[str] = None) -> Optional[str]:
    if not name:
        return None
    query = {'name': name}
    if section:
        query['section'] = section
    class_doc = db['classes'].find_one(query)
    return str(class_doc['_id']) if class_doc else None


def find_subject_id(db, code: str) -> Optional[str]:
    if not code:
        return None
    subject = db['subjects'].find_one({'code': code})
    return str(subject['_id']) if subject else None


def find_faculty_id(db, email: str) -> Optional[str]:
    if not email:
        return None
    faculty = db['faculty'].find_one({'email': email})
    return str(faculty['_id']) if faculty else None


def import_departments(db, file_path: str):
    rows = load_csv_file(file_path)
    docs = []
    for row in rows:
        docs.append({
            'name': row.get('name') or '',
            'code': row.get('code') or '',
            'created_at': __import__('datetime').datetime.utcnow()
        })
    bulk_insert(db, 'departments', docs)


def import_batches(db, file_path: str):
    rows = load_csv_file(file_path)
    docs = []
    for row in rows:
        docs.append({
            'name': row.get('name') or '',
            'start_time': row.get('start_time') or '09:00',
            'end_time': row.get('end_time') or '17:00',
            'period_duration': safe_int(row.get('period_duration'), 60),
            'break_times': parse_json(row.get('break_times'), []),
            'lunch_break': parse_json(row.get('lunch_break'), {}),
            'created_at': __import__('datetime').datetime.utcnow()
        })
    bulk_insert(db, 'batches', docs)


def import_classes(db, file_path: str):
    rows = load_csv_file(file_path)
    docs = []
    for row in rows:
        department_id = find_department_id(db, row.get('department_code') or row.get('department_id'))
        batch_id = find_batch_id(db, row.get('batch_name') or row.get('batch_id'))
        room_id = find_room_id(db, row.get('room_code') or row.get('room_id') or row.get('room'))
        docs.append({
            'name': row.get('name') or '',
            'section': row.get('section') or '',
            'semester': safe_int(row.get('semester'), 1),
            'student_count': safe_int(row.get('student_count'), 0),
            'department_id': department_id,
            'batch_id': batch_id,
            'room_id': room_id,
            'created_at': __import__('datetime').datetime.utcnow()
        })
    bulk_insert(db, 'classes', docs)


def import_rooms(db, file_path: str):
    rows = load_csv_file(file_path)
    docs = []
    for row in rows:
        department_id = find_department_id(db, row.get('department_code') or row.get('department_id'))
        room_type = (row.get('room_type') or 'lecture').strip().lower()
        if room_type not in {'lecture', 'lab', 'seminar'}:
            room_type = 'lecture'
        docs.append({
            'name': row.get('name') or '',
            'code': row.get('code') or '',
            'room_type': room_type,
            'capacity': safe_int(row.get('capacity'), 0),
            'department_id': department_id,
            'created_at': __import__('datetime').datetime.utcnow()
        })
    bulk_insert(db, 'rooms', docs)


def import_subjects(db, file_path: str):
    rows = load_csv_file(file_path)
    docs = []
    for row in rows:
        department_codes = split_list(row.get('department_codes'))
        department_ids = [did for code in department_codes if (did := find_department_id(db, code))]
        if not department_ids and row.get('department_code'):
            first_id = find_department_id(db, row.get('department_code'))
            if first_id:
                department_ids = [first_id]
        batch_id = find_batch_id(db, row.get('batch_name'))
        docs.append({
            'name': row.get('name') or '',
            'code': row.get('code') or '',
            'hours_per_week': safe_int(row.get('hours_per_week'), 0),
            'requires_lab': safe_bool(row.get('requires_lab')),
            'department_ids': department_ids,
            'department_id': department_ids[0] if department_ids else None,
            'batch_id': batch_id,
            'class_id': None,
            'faculty_id': None,
            'created_at': __import__('datetime').datetime.utcnow()
        })
    bulk_insert(db, 'subjects', docs)


def import_faculty(db, file_path: str):
    rows = load_csv_file(file_path)
    docs = []
    for row in rows:
        department_id = find_department_id(db, row.get('department_code') or row.get('department_id'))
        docs.append({
            'name': row.get('name') or '',
            'email': row.get('email') or '',
            'department_id': department_id,
            'max_hours_per_week': safe_int(row.get('max_hours_per_week'), 20),
            'unavailable_slots': parse_json(row.get('unavailable_slots'), []),
            'created_at': __import__('datetime').datetime.utcnow()
        })
    bulk_insert(db, 'faculty', docs)




def apply_mappings(db, file_path: str):
    rows = load_csv_file(file_path)
    for row in rows:
        subject_code = row.get('subject_code') or ''
        class_name = row.get('class_name') or ''
        class_section = row.get('class_section') or ''
        faculty_email = row.get('faculty_email') or ''
        room_code = row.get('room_code') or row.get('room') or row.get('default_room') or ''
        subject_id = find_subject_id(db, subject_code)
        class_id = find_class_id(db, class_name, class_section)
        faculty_id = find_faculty_id(db, faculty_email)
        room_id = find_room_id(db, room_code)
        updates = {}
        if class_id:
            updates['class_id'] = class_id
        if faculty_id:
            updates['faculty_id'] = faculty_id
        if updates and subject_id:
            db['subjects'].update_one({'_id': __import__('bson').ObjectId(subject_id)}, {'$set': updates})
            print(f"Updated subject {subject_code}: {updates}")
            if class_id and room_id:
                db['classes'].update_one(
                    {'_id': __import__('bson').ObjectId(class_id)},
                    {'$set': {'room_id': room_id, 'updated_at': __import__('datetime').datetime.utcnow()}}
                )
                print(f"Updated class {class_name} {class_section}: room_id={room_id}")
        else:
            print(f"Skipping mapping row because subject or target ids were not found: {row}")


def import_all(db, template_dir: str):
    tasks = [
        ('departments', 'departments_template.csv', import_departments),
        ('batches', 'batches_template.csv', import_batches),
        ('rooms', 'rooms_template.csv', import_rooms),
        ('classes', 'classes_template.csv', import_classes),
        ('subjects', 'subjects_template.csv', import_subjects),
        ('faculty', 'faculty_template.csv', import_faculty),
        ('mappings', 'mappings_template.csv', apply_mappings),
    ]
    for name, filename, func in tasks:
        file_path = os.path.join(template_dir, filename)
        if os.path.exists(file_path):
            print(f"\n--- Importing {name} from {file_path} ---")
            func(db, file_path) if name != 'mappings' else func(db, file_path)
        else:
            print(f"Template missing: {file_path}, skipping {name}.")


def main():
    parser = argparse.ArgumentParser(description='Bulk import CSV data into the timetable MongoDB.')
    parser.add_argument('--type', choices=['departments', 'batches', 'classes', 'rooms', 'subjects', 'faculty', 'mappings', 'all'], default='all',
                        help='The import type to run.')
    parser.add_argument('--file', help='Path to a CSV file to import. If omitted, template files are used.')
    parser.add_argument('--template-dir', default=os.path.join(os.path.dirname(__file__), '..', 'csv_templates'),
                        help='Directory containing CSV template files.')
    args = parser.parse_args()

    db = get_db_client()
    if args.type == 'all':
        import_all(db, os.path.abspath(args.template_dir))
        return

    if args.file:
        file_path = args.file
    else:
        file_name = f"{args.type}_template.csv"
        file_path = os.path.join(os.path.abspath(args.template_dir), file_name)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    import_map = {
        'departments': import_departments,
        'batches': import_batches,
        'classes': import_classes,
        'rooms': import_rooms,
        'subjects': import_subjects,
        'faculty': import_faculty,
        'mappings': apply_mappings,
    }

    import_map[args.type](db, file_path)


if __name__ == '__main__':
    main()
