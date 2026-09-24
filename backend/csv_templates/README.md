# CSV Templates for Bulk Data Import

Use these CSV templates to import large amounts of data into the timetable system.

Place data in the matching template and run the import script from the `backend` folder:

```bash
cd backend
source .venv/bin/activate
python3 scripts/import_csv.py --type departments
python3 scripts/import_csv.py --type classes
python3 scripts/import_csv.py --type rooms
python3 scripts/import_csv.py --type subjects
python3 scripts/import_csv.py --type faculty
python3 scripts/import_csv.py --type mappings
```

To import all supported templates in sequence:

```bash
python3 scripts/import_csv.py --type all
```

## Supported files

- `departments_template.csv`
- `batches_template.csv`
- `classes_template.csv`
- `rooms_template.csv`
- `subjects_template.csv`
- `faculty_template.csv`
- `mappings_template.csv`

## Notes

- `department_codes` in `subjects_template.csv` supports semicolon-separated values for multiple departments.
- Use `department_code` or `department_id` to relate classes, rooms, and faculty to departments.
- `classes_template.csv` can include `room_code` to assign a default room to a class.
- `mappings_template.csv` links `subject_code` with `class_name` and `faculty_email`; optional `room_code` sets the class default room used by room-aware scheduling.
