import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from ortools.sat.python import cp_model
from pymongo.database import Database

# Credit → contact hours/week mapping (industry standard for Indian universities)
CREDITS_TO_HOURS: Dict[int, int] = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6}

logger = logging.getLogger(__name__)


class _Obj:
    """Simple attribute-access wrapper around a MongoDB document dict."""

    def __init__(self, doc: dict):
        self._doc = doc
        # Expose string id
        self.id = str(doc["_id"])

    def __getattr__(self, name):
        if name.startswith("_") or name == "id":
            raise AttributeError(name)
        return self._doc.get(name)

    def __repr__(self):
        return f"<_Obj id={self.id} {self._doc}>"


class TimetableScheduler:
    def __init__(
        self,
        db: Database,
        working_days: List[str],
        periods_per_day: int,
        time_limit_seconds: int = 60,
        custom_constraints: List[Dict[str, Any]] = None,
    ):
        self.db = db
        self.working_days = working_days
        self.periods_per_day = periods_per_day
        self.time_limit_seconds = time_limit_seconds
        self.custom_constraints = custom_constraints or []
        self.num_days = len(working_days)

        # Caches
        self.departments = []
        self.batches = []
        self.classes = []
        self.subjects = []
        self.faculty = []
        self.rooms = []

        # OR-Tools
        self.model = cp_model.CpModel()
        self.variables = (
            {}
        )  # Map: "s{subject_id}_d{day_index}_p{period_index}" -> BoolVar

        # Smart correction state
        self._adjusted_hours: Dict[str, int] = {}  # subject_id -> corrected hours
        self._credit_extra_capacities: Dict[str, int] = (
            {}
        )  # subject_id -> extra slots for free-period fill
        self.auto_adjustments: List[str] = []  # human-readable auto-fix messages
        self.constraint_warnings: List[str] = (
            []
        )  # soft-fail warnings from custom constraints
        self.specific_constrained_slots = set()
        self.specific_preference_slots = set()

        # Optimization Caches
        self.vars_by_faculty = (
            {}
        )  # faculty_id -> day -> list of {'start', 'end', 'var', 'period'}
        self.vars_by_room = (
            {}
        )  # room_id -> day -> list of {'start', 'end', 'var', 'period'}
        self.vars_by_subject = {}  # subject_id -> list of BoolVar
        self.room_variables = (
            {}
        )  # Map: "s{subject_id}_d{day}_p{period}_r{room_id}" -> BoolVar
        self.empty_slot_vars = []
        self.subject_by_id = {}
        self.room_by_id = {}
        self._candidate_rooms_cache: Dict[str, List[_Obj]] = {}

    def _wrap(self, doc: dict) -> _Obj:
        return _Obj(doc)

    @staticmethod
    def _id_str(value: Any) -> str:
        return str(value) if value is not None else ""

    def _wrap_class(self, doc: dict) -> _Obj:
        """Wrap a class document and attach nested batch/department objects."""
        obj = _Obj(doc)
        # Attach batch
        batch_id = doc.get("batch_id")
        if batch_id:
            batch_doc = (
                self.db["batches"].find_one({"_id": ObjectId(batch_id)})
                if ObjectId.is_valid(batch_id)
                else None
            )
            obj._doc["_batch_obj"] = _Obj(batch_doc) if batch_doc else None
        else:
            obj._doc["_batch_obj"] = None
        return obj

    def load_data(
        self,
        department_ids: Optional[List[str]] = None,
        batch_ids: Optional[List[str]] = None,
        class_ids: Optional[List[str]] = None,
        faculty_ids: Optional[List[str]] = None,
    ):
        """Loads all necessary data from MongoDB."""
        logger.info("Step 1/5: Loading data from database...")

        # Departments
        dept_query = {}
        if department_ids:
            oids = [ObjectId(d) for d in department_ids if ObjectId.is_valid(d)]
            dept_query = {"_id": {"$in": oids}}
        self.departments = [
            self._wrap(d) for d in self.db["departments"].find(dept_query)
        ]
        dept_ids_str = [dep.id for dep in self.departments]

        # Batches
        batch_query = {}
        if batch_ids:
            oids = [ObjectId(b) for b in batch_ids if ObjectId.is_valid(b)]
            batch_query = {"_id": {"$in": oids}}
        self.batches = [self._wrap(d) for d in self.db["batches"].find(batch_query)]

        # Classes
        class_query = {}
        if class_ids:
            oids = [ObjectId(c) for c in class_ids if ObjectId.is_valid(c)]
            class_query = {"_id": {"$in": oids}}
        elif dept_ids_str:
            class_query = {"department_id": {"$in": dept_ids_str}}
        self.classes = [
            self._wrap_class(d) for d in self.db["classes"].find(class_query)
        ]
        loaded_class_ids = [c.id for c in self.classes]
        self.class_map = {self._id_str(c.id): c for c in self.classes}

        room_query = {}
        if dept_ids_str:
            room_query = {
                "$or": [
                    {"department_id": {"$in": dept_ids_str}},
                    {"department_id": None},
                    {"department_id": ""},
                    {"department_id": {"$exists": False}},
                ]
            }
        self.rooms = [self._wrap(d) for d in self.db["rooms"].find(room_query)]
        self.room_by_id = {self._id_str(r.id): r for r in self.rooms}

        # Subjects (linked to loaded classes)
        if loaded_class_ids:
            self.subjects = [
                self._wrap(d)
                for d in self.db["subjects"].find(
                    {"class_id": {"$in": loaded_class_ids}}
                )
            ]
        else:
            self.subjects = []
        self.subject_by_id = {self._id_str(s.id): s for s in self.subjects}

        # Faculty
        assigned_faculty_ids = {
            self._id_str(s.faculty_id) for s in self.subjects if s.faculty_id
        }
        if faculty_ids:
            all_ids = set(faculty_ids) | assigned_faculty_ids
            oids = [ObjectId(f) for f in all_ids if ObjectId.is_valid(f)]
            fac_query = {"_id": {"$in": oids}}
        elif dept_ids_str:
            fac_query = (
                {
                    "$or": [
                        {"department_id": {"$in": dept_ids_str}},
                        {
                            "_id": {
                                "$in": [
                                    ObjectId(f)
                                    for f in assigned_faculty_ids
                                    if ObjectId.is_valid(f)
                                ]
                            }
                        },
                    ]
                }
                if assigned_faculty_ids
                else {"department_id": {"$in": dept_ids_str}}
            )
        else:
            fac_query = {}
        self.faculty = [self._wrap(d) for d in self.db["faculty"].find(fac_query)]

        # Legacy assignment support is disabled.

        # Auto-adjust subject hours only for explicitly hard fixed-slot constraints.
        # PDF/given slots are preferences by default, so they should not inflate load.
        for sub in self.subjects:
            num_slots = 0
            for c in self.custom_constraints:
                if (
                    c.get("type") == "specific_time_slot"
                    and c.get("target_type", "subject") == "subject"
                    and self._is_hard_specific_constraint(c)
                ):
                    if self._matches_subject(c.get("target", ""), sub):
                        class_name = c.get("class_name")
                        if class_name:
                            class_obj = self.class_map.get(self._id_str(sub.class_id))
                            if class_obj and not self._matches_class(
                                class_name, class_obj
                            ):
                                continue
                        num_slots += 1

            if num_slots > 0:
                current_hours = self._effective_hours(sub)
                if num_slots > current_hours:
                    self._adjusted_hours[sub.id] = num_slots
                    self.auto_adjustments.append(
                        f"Subject '{sub.name}' (Class: {self.class_map.get(self._id_str(sub.class_id)).name if self.class_map.get(self._id_str(sub.class_id)) else 'Unknown'}) "
                        f"hours increased from {current_hours} to {num_slots} "
                        f"to accommodate specific_time_slot constraints."
                    )

        summary = {
            "departments": len(self.departments),
            "batches": len(self.batches),
            "classes": len(self.classes),
            "subjects": len(self.subjects),
            "faculty": len(self.faculty),
            "rooms": len(self.rooms),
        }
        logger.info(f"Data Loaded: {summary}")
        return summary

    def _room_label(self, room: Optional[_Obj]) -> Optional[str]:
        if not room:
            return None
        return room.name or room.code or room.id

    def _room_capacity(self, room: _Obj) -> Optional[int]:
        try:
            if room.capacity is None:
                return None
            return int(room.capacity)
        except (TypeError, ValueError):
            return None

    def _room_type(self, room: _Obj) -> str:
        return str(room.room_type or "lecture").strip().lower()

    def _room_change_reason(
        self, subject: _Obj, class_obj: _Obj, assigned_room: Optional[_Obj]
    ) -> Optional[str]:
        if not assigned_room or not class_obj or not class_obj.room_id:
            return None

        assigned_room_id = self._id_str(assigned_room.id)
        default_room_id = self._id_str(class_obj.room_id)
        if not assigned_room_id or assigned_room_id == default_room_id:
            return None

        if subject.requires_lab:
            return "lab_session"

        default_room = self.room_by_id.get(default_room_id)
        if default_room:
            default_capacity = self._room_capacity(default_room)
            try:
                student_count = int(class_obj.student_count or 0)
            except (TypeError, ValueError):
                student_count = 0

            if self._room_type(default_room) == "lab":
                return "home_room_is_lab"
            if (
                default_capacity is not None
                and student_count
                and default_capacity < student_count
            ):
                return "home_room_capacity"

        return "home_room_unavailable"

    def _candidate_rooms_for_subject(self, subject: _Obj) -> List[_Obj]:
        subject_id = self._id_str(subject.id)
        if subject_id in self._candidate_rooms_cache:
            return self._candidate_rooms_cache[subject_id]

        if not self.rooms:
            self._candidate_rooms_cache[subject_id] = []
            return []

        class_obj = self.class_map.get(self._id_str(subject.class_id))
        student_count = 0
        if class_obj:
            try:
                student_count = int(class_obj.student_count or 0)
            except (TypeError, ValueError):
                student_count = 0

        default_room_id = self._id_str(class_obj.room_id) if class_obj else ""
        default_room = self.room_by_id.get(default_room_id)

        viable = []
        for room in self.rooms:
            room_type = self._room_type(room)
            capacity = self._room_capacity(room)
            if capacity is not None and student_count and capacity < student_count:
                continue
            if subject.requires_lab:
                if room_type != "lab":
                    continue
            elif room_type == "lab":
                continue
            viable.append(room)

        if subject.requires_lab and not viable:
            viable = [
                room
                for room in self.rooms
                if self._room_capacity(room) is None
                or not student_count
                or self._room_capacity(room) >= student_count
            ]
            if viable:
                self._constraint_error(
                    f"Room warning: no lab room fits '{subject.name}', using any available room as fallback."
                )

        if default_room and default_room not in viable and not subject.requires_lab:
            capacity = self._room_capacity(default_room)
            if self._room_type(default_room) != "lab" and (
                capacity is None or not student_count or capacity >= student_count
            ):
                viable.insert(0, default_room)

        if not viable:
            self._constraint_error(
                f"Room warning: no suitable room found for '{subject.name}' in "
                f"{self._class_display_name(class_obj) if class_obj else 'unknown class'}."
            )
        self._candidate_rooms_cache[subject_id] = viable
        return viable

    def _parse_time(self, time_str: str) -> int:
        """Converts HH:MM string to minutes from midnight."""
        h, m = map(int, time_str.split(":"))
        return h * 60 + m

    def _format_time(self, minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def _format_display_time(self, minutes: int) -> str:
        hours_24 = (minutes // 60) % 24
        mins = minutes % 60
        suffix = "AM" if hours_24 < 12 else "PM"
        hours_12 = hours_24 % 12 or 12
        return f"{hours_12}:{mins:02d} {suffix}"

    def _format_time_range(self, start: int, end: int) -> str:
        return f"{self._format_display_time(start)} - {self._format_display_time(end)}"

    def _slot_blocks_day(
        self, slot: Dict[str, Any], day_idx: int, day_name: str
    ) -> bool:
        slot_day = slot.get("day") or slot.get("day_name")
        if slot_day and str(slot_day).lower() == day_name.lower():
            return True

        slot_day_index = slot.get("day_index")
        if slot_day_index is not None:
            try:
                return int(slot_day_index) == day_idx
            except (TypeError, ValueError):
                return False

        return not slot_day

    def _slot_blocks_period(
        self, slot: Dict[str, Any], period_idx: int, start: int, end: int
    ) -> bool:
        period_value = slot.get("period")
        if period_value is not None:
            try:
                return int(period_value) == period_idx + 1
            except (TypeError, ValueError):
                return False

        periods = slot.get("periods")
        if isinstance(periods, list):
            normalized_periods = set()
            for value in periods:
                try:
                    normalized_periods.add(int(value))
                except (TypeError, ValueError):
                    continue
            return period_idx + 1 in normalized_periods

        start_time = slot.get("start") or slot.get("start_time")
        end_time = slot.get("end") or slot.get("end_time")
        if start_time and end_time:
            slot_start = self._parse_time(start_time)
            slot_end = self._parse_time(end_time)
            return start < slot_end and slot_start < end

        return True

    def _is_faculty_unavailable(
        self,
        faculty: _Obj,
        day_idx: int,
        day_name: str,
        period_idx: int,
        start: int,
        end: int,
    ) -> bool:
        for slot in faculty.unavailable_slots or []:
            if not isinstance(slot, dict):
                continue
            if self._slot_blocks_day(
                slot, day_idx, day_name
            ) and self._slot_blocks_period(slot, period_idx, start, end):
                return True
        return False

    def _find_faculty_by_name(self, target_name: str) -> Optional[_Obj]:
        if not target_name:
            return None
        target_name = self._normalize_match_text(target_name)
        tokens = [token for token in target_name.split() if token]
        for fac in self.faculty:
            faculty_name = self._normalize_match_text(fac.name)
            if (
                target_name == faculty_name
                or target_name in faculty_name
                or faculty_name in target_name
            ):
                return fac
            if tokens and all(token in faculty_name for token in tokens):
                return fac
        return None

    @staticmethod
    def _normalize_match_text(value: Any) -> str:
        value = str(value or "").strip()
        value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
        value = value.lower()
        return re.sub(r"[^a-z0-9]+", " ", value).strip()

    @staticmethod
    def _is_hard_specific_constraint(constraint: Dict[str, Any]) -> bool:
        """Specific slots are hard by default unless explicitly marked soft."""
        if constraint.get("soft") is True:
            return False
        return True

    def _effective_hours(self, subject: _Obj) -> int:
        """Return hours/week for a subject: adjusted > explicit > credits mapping."""
        if subject.id in self._adjusted_hours:
            return self._adjusted_hours[subject.id]
        raw = subject.hours_per_week
        if raw is not None and int(raw) > 0:
            return int(raw)
        credits = int(subject.credits or 3)
        return CREDITS_TO_HOURS.get(credits, credits)

    def _credit_value(self, subject: _Obj) -> int:
        try:
            return max(1, int(subject.credits or 3))
        except (ValueError, TypeError):
            return 3

    def _credit_extra_capacity(self, subject: _Obj) -> int:
        """
        Optional extra periods used to occupy otherwise-free class slots.
        Higher-credit theory subjects can receive more extra periods, but no
        subject is allowed to expand without a cap.
        """
        subject_id = self._id_str(getattr(subject, "id", None))
        if subject_id in self._credit_extra_capacities:
            return self._credit_extra_capacities[subject_id]
        if subject.requires_lab:
            return 0
        return min(3, max(0, self._credit_value(subject) - 2))

    def _compute_credit_extra_capacities(self) -> Dict[str, int]:
        """
        Allocate each class's free period capacity to its highest-credit theory
        subjects. This keeps required credit hours intact while giving the
        solver enough capped capacity to occupy every usable class slot.
        """
        capacities: Dict[str, int] = {}
        for class_obj in self.classes:
            class_subjects = [
                sub
                for sub in self.subjects
                if self._id_str(sub.class_id) == self._id_str(class_obj.id)
            ]
            if not class_subjects:
                continue

            usable_slots = 0
            for day in range(self.num_days):
                for period in range(self.periods_per_day):
                    if any(
                        f"s{sub.id}_d{day}_p{period}" in self.variables
                        for sub in class_subjects
                    ):
                        usable_slots += 1

            required_slots = sum(self._effective_hours(sub) for sub in class_subjects)
            free_slots = max(0, usable_slots - required_slots)
            theory_subjects = [
                sub
                for sub in class_subjects
                if not sub.requires_lab and self.vars_by_subject.get(sub.id)
            ]
            if free_slots <= 0 or not theory_subjects:
                continue

            allocations = {self._id_str(sub.id): 0 for sub in theory_subjects}
            remaining = free_slots
            for sub in sorted(
                theory_subjects,
                key=lambda s: (-self._credit_value(s), s.name or "", s.code or ""),
            ):
                if remaining <= 0:
                    break
                sub_id = self._id_str(sub.id)
                target = self._effective_hours(sub)
                available = len(self.vars_by_subject.get(sub.id, []))
                max_extra = max(0, available - target)
                assigned = min(remaining, max_extra)
                if assigned <= 0:
                    continue
                allocations[sub_id] += assigned
                remaining -= assigned

            for sub_id, extra in allocations.items():
                if extra > 0:
                    capacities[sub_id] = extra

        return capacities

    def _matches_text(self, target: str, candidate: str) -> bool:
        target = self._normalize_match_text(target)
        candidate = self._normalize_match_text(candidate)
        if not target or not candidate:
            return False
        if target == candidate:
            return True
        target_tokens = target.split()
        candidate_tokens = candidate.split()

        # Distinguish labs from theory
        is_target_lab = "lab" in target_tokens
        is_candidate_lab = "lab" in candidate_tokens
        if is_target_lab != is_candidate_lab:
            return False

        return bool(target_tokens) and all(
            token in candidate_tokens for token in target_tokens
        )

    def _subject_target_variants(self, target: str) -> List[str]:
        """
        Spreadsheet imports often include class suffixes in subject labels, e.g.
        "NLP LAB-AIML A". Try the raw label and the subject part before the
        class suffix so it can still match a stored subject named/code "NLP".
        """
        raw = str(target or "").strip()
        if not raw:
            return []

        variants = [raw]
        for part in re.split(r"\s*/\s*", raw):
            part = part.strip()
            if part and part not in variants:
                variants.append(part)
            prefix = re.split(r"\s*-\s*", part, maxsplit=1)[0].strip()
            if prefix and prefix not in variants:
                variants.append(prefix)

        normalized_variants = {self._normalize_match_text(value) for value in variants}
        if any(
            "fcv" in value.split() and "lab" in value.split()
            for value in normalized_variants
        ):
            for alias in ("CV Lab", "Computer Vision Lab"):
                if alias not in variants:
                    variants.append(alias)

        return variants

    def _matches_subject_text(self, target: str, candidate: str, subject: _Obj) -> bool:
        target_norm = self._normalize_match_text(target)
        candidate_norm = self._normalize_match_text(candidate)
        if not target_norm or not candidate_norm:
            return False

        target_tokens = target_norm.split()
        candidate_tokens = candidate_norm.split()
        target_is_lab = "lab" in target_tokens
        candidate_is_lab = bool(subject.requires_lab) or "lab" in candidate_tokens

        if target_is_lab:
            if not candidate_is_lab:
                return False
            target_tokens = [token for token in target_tokens if token != "lab"]
            candidate_tokens = [token for token in candidate_tokens if token != "lab"]
            return bool(target_tokens) and all(
                token in candidate_tokens for token in target_tokens
            )

        if candidate_is_lab:
            return False

        return self._matches_text(target, candidate)

    def _class_display_name(self, class_obj: _Obj) -> str:
        return f"{class_obj.name or ''} {class_obj.section or ''}".strip()

    def _matches_class(self, target: str, class_obj: _Obj) -> bool:
        return (
            self._matches_text(target, class_obj.name)
            or self._matches_text(target, class_obj.section)
            or self._matches_text(target, self._class_display_name(class_obj))
        )

    def _matches_subject(self, target: str, subject: _Obj) -> bool:
        for variant in self._subject_target_variants(target):
            if self._matches_subject_text(
                variant, subject.name, subject
            ) or self._matches_subject_text(variant, subject.code, subject):
                return True
        return False

    def _matches_schedule_subject(self, target: str, slot: Dict[str, Any]) -> bool:
        subject_name = slot.get("subject")
        subject_code = slot.get("subject_code")
        if not subject_name and not subject_code:
            return False

        subject = _Obj(
            {
                "_id": slot.get("subject_id") or "schedule-slot",
                "name": subject_name,
                "code": subject_code,
                "requires_lab": bool(slot.get("is_lab")),
            }
        )
        return self._matches_subject(target, subject)

    def _subjects_for_class_target(self, target: str) -> List[_Obj]:
        class_ids = {
            self._id_str(cls.id)
            for cls in self.classes
            if self._matches_class(target, cls)
        }
        return [sub for sub in self.subjects if self._id_str(sub.class_id) in class_ids]

    def _subjects_for_target(
        self, target: str, target_type: str = "subject"
    ) -> List[_Obj]:
        if target_type == "class":
            return self._subjects_for_class_target(target)

        target_variants = self._subject_target_variants(target)
        if not target_variants:
            return []

        # Try exact match first, preserving lab/theory intent even when codes
        # are reused for both a theory and a lab subject.
        for variant in target_variants:
            target_norm = self._normalize_match_text(variant)
            if not target_norm:
                continue
            target_is_lab = "lab" in target_norm.split()
            exact_matches = [
                sub
                for sub in self.subjects
                if self._normalize_match_text(sub.name) == target_norm
                or self._normalize_match_text(sub.code) == target_norm
            ]
            if exact_matches and not target_is_lab:
                exact_matches = [sub for sub in exact_matches if not sub.requires_lab]
            if exact_matches:
                return exact_matches

        matches = [sub for sub in self.subjects if self._matches_subject(target, sub)]
        if matches:
            return matches

        # Some datasets store only the base theory subject even when the input
        # refers to a lab label such as "FCV Lab". Use the base subject as a
        # last resort so exact imported timetables can still be reproduced.
        target_tokens = self._normalize_match_text(target).split()
        if "lab" in target_tokens:
            base_target = " ".join(token for token in target_tokens if token != "lab")
            fallback_matches = [
                sub
                for sub in self.subjects
                if self._matches_text(base_target, sub.name)
                or self._matches_text(base_target, sub.code)
            ]
            if fallback_matches:
                message = (
                    f"specific_time_slot: target '{target}' matched base subject "
                    f"'{fallback_matches[0].name}' because no lab-specific subject was loaded"
                )
                if message not in self.auto_adjustments:
                    self.auto_adjustments.append(message)
                logger.info(message)
                return fallback_matches

        return []

    def _subjects_for_constraint_targets(
        self,
        targets: List[str],
        target_type: str = "subject",
        class_name: Optional[str] = None,
    ) -> List[_Obj]:
        matched_by_id: Dict[str, _Obj] = {}
        for target in targets:
            for sub in self._subjects_for_target(str(target), target_type):
                matched_by_id[self._id_str(sub.id)] = sub

        matched_subjects = list(matched_by_id.values())
        if class_name:
            matching_class_ids = {
                self._id_str(cls.id)
                for cls in self.classes
                if self._matches_class(class_name, cls)
            }
            matched_subjects = [
                sub
                for sub in matched_subjects
                if self._id_str(sub.class_id) in matching_class_ids
            ]
        return matched_subjects

    def _constraint_error(self, message: str):
        """Soft-fail: record warning and continue, never block scheduling."""
        self.constraint_warnings.append(message)
        logger.warning(message)

    def _calculate_class_period_intervals(
        self, class_obj: _Obj, max_periods: Optional[int] = None
    ) -> List[Tuple[int, int]]:
        """
        Returns a list of (start_minute, end_minute) for each period of the day for this class.
        Based on the class's Batch configuration.
        """
        batch = class_obj._doc.get("_batch_obj")
        if not batch:
            # Fallback if no batch assigned: Simple uniform 60min slots starting 09:00
            start = 9 * 60
            intervals = []
            for _ in range(max_periods or self.periods_per_day):
                intervals.append((start, start + 60))
                start += 60
            return intervals

        day_start = self._parse_time(batch.start_time)
        day_end = (
            self._parse_time(batch.end_time)
            if batch.end_time
            else day_start + (self.periods_per_day * (batch.period_duration or 60))
        )
        period_duration = batch.period_duration or 60
        break_slots = [
            slot
            for slot in self._get_class_break_slots(class_obj)
            if slot["start"] < day_end
            and slot["end"] > day_start
            and slot["end"] > slot["start"]
        ]

        intervals = []
        current_time = day_start

        while (
            max_periods is None or len(intervals) < max_periods
        ) and current_time + period_duration <= day_end:
            active_break = next(
                (
                    slot
                    for slot in break_slots
                    if slot["start"] <= current_time < slot["end"]
                ),
                None,
            )
            if active_break:
                current_time = active_break["end"]
                continue

            next_break = next(
                (slot for slot in break_slots if slot["start"] >= current_time), None
            )

            if next_break and current_time + period_duration > next_break["start"]:
                if current_time < next_break["start"]:
                    logger.warning(
                        "Skipping short teaching gap %s-%s before %s because it is less than the %s-minute period duration",
                        self._format_time(current_time),
                        self._format_time(next_break["start"]),
                        next_break.get("label", "break"),
                        period_duration,
                    )
                current_time = next_break["end"]
                continue

            p_start = current_time
            p_end = current_time + period_duration
            intervals.append((p_start, p_end))
            current_time = p_end

        return intervals

    def _get_class_period_intervals(self, class_obj: _Obj) -> List[Tuple[int, int]]:
        """
        Returns teaching period intervals capped by the scheduler's effective
        period count. The effective count is derived from batch timing before
        variables are created.
        """
        return self._calculate_class_period_intervals(class_obj, self.periods_per_day)

    def _sync_periods_per_day_to_batch_timings(self):
        calculated_counts = [
            len(self._calculate_class_period_intervals(class_obj, None))
            for class_obj in self.classes
            if class_obj._doc.get("_batch_obj")
        ]
        if calculated_counts:
            self.periods_per_day = max(calculated_counts)
            logger.info(
                f"Effective periods per day calculated from batch timings: {self.periods_per_day}"
            )

    def _get_class_break_slots(self, class_obj: _Obj) -> List[Dict[str, Any]]:
        batch = class_obj._doc.get("_batch_obj")
        if not batch:
            return []

        break_slots = []
        for idx, break_time in enumerate(batch.break_times or [], 1):
            start = break_time.get("start")
            end = break_time.get("end")
            if not start or not end:
                continue
            break_slots.append(
                {
                    "slot_type": "break",
                    "break_type": "break",
                    "label": f"Break {idx}",
                    "start": self._parse_time(start),
                    "end": self._parse_time(end),
                }
            )

        lunch_break = batch.lunch_break or {}
        if lunch_break.get("start") and lunch_break.get("end"):
            break_slots.append(
                {
                    "slot_type": "break",
                    "break_type": "lunch",
                    "label": "Lunch",
                    "start": self._parse_time(lunch_break["start"]),
                    "end": self._parse_time(lunch_break["end"]),
                }
            )

        return sorted(break_slots, key=lambda slot: (slot["start"], slot["end"]))

    def _get_class_timeline_slots(self, class_obj: _Obj) -> List[Dict[str, Any]]:
        timeline = []
        for period_idx, (start, end) in enumerate(
            self._get_class_period_intervals(class_obj)
        ):
            timeline.append(
                {
                    "slot_type": "period",
                    "period_index": period_idx,
                    "period": period_idx + 1,
                    "start": start,
                    "end": end,
                }
            )

        timeline.extend(self._get_class_break_slots(class_obj))
        return sorted(
            timeline,
            key=lambda slot: (
                slot["start"],
                0 if slot.get("slot_type") == "break" else 1,
                slot["end"],
            ),
        )

    def create_variables(self):
        """Creates boolean variables: X[subject, day, period]"""
        logger.info("Step 2/5: Creating decision variables...")

        class_timings = {
            self._id_str(c.id): self._get_class_period_intervals(c)
            for c in self.classes
        }
        faculty_map = {self._id_str(f.id): f for f in self.faculty}

        self.vars_by_faculty = {
            self._id_str(f.id): {d: [] for d in range(self.num_days)}
            for f in self.faculty
        }
        self.vars_by_room = {
            self._id_str(r.id): {d: [] for d in range(self.num_days)}
            for r in self.rooms
        }
        self.vars_by_class = {
            self._id_str(c.id): {d: [] for d in range(self.num_days)}
            for c in self.classes
        }
        self.vars_by_subject = {}

        for subject in self.subjects:
            subject_faculty_id = self._id_str(subject.faculty_id)
            subject_class_id = self._id_str(subject.class_id)
            if subject_class_id in self.class_map:
                cls = self.class_map[subject_class_id]
                c_intervals = class_timings.get(self._id_str(cls.id), [])
            else:
                c_intervals = []

            for day in range(self.num_days):
                for period in range(self.periods_per_day):
                    if period >= len(c_intervals):
                        continue
                    start, end = c_intervals[period]
                    faculty = faculty_map.get(subject_faculty_id)
                    if faculty and self._is_faculty_unavailable(
                        faculty, day, self.working_days[day], period, start, end
                    ):
                        continue

                    var_name = f"s{subject.id}_d{day}_p{period}"
                    var = self.model.NewBoolVar(var_name)
                    self.variables[var_name] = var

                    entry = {
                        "start": start,
                        "end": end,
                        "var": var,
                        "period": period,
                        "subject_id": subject.id,
                    }
                    if subject_faculty_id in self.vars_by_faculty:
                        self.vars_by_faculty[subject_faculty_id][day].append(entry)
                    if subject_class_id in self.vars_by_class:
                        self.vars_by_class[subject_class_id][day].append(entry)

                    self.vars_by_subject.setdefault(subject.id, []).append(var)

                    room_vars = []
                    for room in self._candidate_rooms_for_subject(subject):
                        room_id = self._id_str(room.id)
                        room_var_name = f"s{subject.id}_d{day}_p{period}_r{room.id}"
                        room_var = self.model.NewBoolVar(room_var_name)
                        self.room_variables[room_var_name] = room_var
                        room_vars.append(room_var)
                        self.model.Add(room_var <= var)
                        if room_id in self.vars_by_room:
                            self.vars_by_room[room_id][day].append(
                                {
                                    "start": start,
                                    "end": end,
                                    "var": room_var,
                                    "period": period,
                                    "subject_id": subject.id,
                                    "room_id": room_id,
                                }
                            )
                    if room_vars:
                        self.model.Add(sum(room_vars) == var)

        logger.info(
            f"Total decision variables created: {len(self.variables)} subject slots, "
            f"{len(self.room_variables)} room assignments"
        )

    def add_constraints(self):
        logger.info("Step 3/5: Adding constraints to the model...")

        specific_constrained_slots = set()
        specific_preference_slots = set()
        if self.custom_constraints:
            for c in self.custom_constraints:
                if (
                    c.get("type") in {"specific_time_slot", "specific_time_slot_any"}
                    and c.get("target_type", "subject") == "subject"
                ):
                    target = str(c.get("target", ""))
                    targets = c.get("targets") or [target]
                    period_num = c.get("period")
                    day_name = c.get("day")
                    if period_num is not None and day_name:
                        try:
                            p_idx = int(period_num) - 1
                        except (TypeError, ValueError):
                            continue
                        day_idx = next(
                            (
                                i
                                for i, d in enumerate(self.working_days)
                                if d.lower() == day_name.lower()
                            ),
                            None,
                        )
                        if day_idx is not None:
                            class_name = c.get("class_name")
                            matched_subjects = self._subjects_for_constraint_targets(
                                targets, "subject", class_name
                            )
                            for sub in matched_subjects:
                                slot = (sub.id, day_idx, p_idx)
                                specific_constrained_slots.add(slot)
                                if not self._is_hard_specific_constraint(c):
                                    specific_preference_slots.add(slot)
        self.specific_constrained_slots = specific_constrained_slots
        self.specific_preference_slots = specific_preference_slots

        self._credit_extra_capacities = self._compute_credit_extra_capacities()
        self.shortage_vars = []
        # 1. Subject Requirements: credits define target hours; theory subjects
        # may use bounded credit-based extra periods to fill free slots.
        for subject in self.subjects:
            all_sub_vars = self.vars_by_subject.get(subject.id, [])
            if all_sub_vars:
                scheduled = sum(all_sub_vars)
                target_hours = self._effective_hours(subject)
                shortage = self.model.NewIntVar(0, 100, f"shortage_s{subject.id}")
                self.shortage_vars.append(shortage)
                if subject.requires_lab:
                    self.model.Add(scheduled + shortage == target_hours)
                else:
                    extra_capacity = self._credit_extra_capacity(subject)
                    self.model.Add(scheduled + shortage >= target_hours)
                    self.model.Add(scheduled <= target_hours + extra_capacity)
        logger.debug("Added Subject Requirement constraints")

        # 1.5. Prevent Daily Monotony: Max 2 periods per day for theory subjects
        for subject in self.subjects:
            if not subject.requires_lab:
                for day in range(self.num_days):
                    day_vars = []
                    for period in range(self.periods_per_day):
                        key = f"s{subject.id}_d{day}_p{period}"
                        if key in self.variables:
                            day_vars.append(self.variables[key])
                    if day_vars:
                        # Allow higher limit if specific slots are requested for this subject on this day
                        day_name = self.working_days[day].lower()
                        specific_slots_count = 0
                        if self.custom_constraints:
                            for c in self.custom_constraints:
                                if (
                                    c.get("type")
                                    in {"specific_time_slot", "specific_time_slot_any"}
                                    and c.get("target_type", "subject") == "subject"
                                ):
                                    targets = c.get("targets") or [c.get("target", "")]
                                    if (
                                        any(
                                            self._matches_subject(target, subject)
                                            for target in targets
                                        )
                                        and c.get("day", "").lower() == day_name
                                    ):
                                        class_name = c.get("class_name")
                                        if not class_name:
                                            specific_slots_count += 1
                                        else:
                                            class_obj = self.class_map.get(
                                                self._id_str(subject.class_id)
                                            )
                                            if class_obj and self._matches_class(
                                                class_name, class_obj
                                            ):
                                                specific_slots_count += 1
                        limit = max(2, specific_slots_count)
                        self.model.Add(sum(day_vars) <= limit)

        # 2. Class occupancy: prefer exactly one subject in every usable class slot.
        for class_obj in self.classes:
            class_subjects = [
                s
                for s in self.subjects
                if self._id_str(s.class_id) == self._id_str(class_obj.id)
            ]
            for day in range(self.num_days):
                for period in range(self.periods_per_day):
                    slot_vars = []
                    for sub in class_subjects:
                        key = f"s{sub.id}_d{day}_p{period}"
                        if key in self.variables:
                            slot_vars.append(self.variables[key])
                    if slot_vars:
                        empty_slot = self.model.NewBoolVar(
                            f"empty_c{class_obj.id}_d{day}_p{period}"
                        )
                        self.model.Add(sum(slot_vars) + empty_slot == 1)
                        self.empty_slot_vars.append(empty_slot)
        logger.debug("Added Class Occupancy constraints")

        # 3. RESOURCE CONFLICTS (Optimized)
        def is_allowed_shared_slot(e1, e2, day, entity_name):
            if entity_name == "Class":
                return False

            sub1 = self.subject_by_id.get(self._id_str(e1.get("subject_id")))
            sub2 = self.subject_by_id.get(self._id_str(e2.get("subject_id")))
            if not sub1 or not sub2:
                return False

            if self._id_str(sub1.faculty_id) != self._id_str(sub2.faculty_id):
                return False

            if self._id_str(sub1.class_id) == self._id_str(sub2.class_id):
                return False

            s1_source = getattr(sub1, "source_subject_id", None) or self._id_str(sub1.id)
            s2_source = getattr(sub2, "source_subject_id", None) or self._id_str(sub2.id)

            is_combined = False
            if s1_source and s2_source and s1_source == s2_source:
                is_combined = True
            else:
                same_subject = self._normalize_match_text(
                    sub1.name
                ) == self._normalize_match_text(sub2.name) or (
                    sub1.code
                    and sub2.code
                    and self._normalize_match_text(sub1.code)
                    == self._normalize_match_text(sub2.code)
                )
                if same_subject:
                    is_combined = True

            if is_combined:
                return True

            if e1.get("period") != e2.get("period"):
                return False
            slot1 = (e1.get("subject_id"), day, e1.get("period"))
            slot2 = (e2.get("subject_id"), day, e2.get("period"))
            if (
                slot1 in self.specific_constrained_slots
                and slot2 in self.specific_constrained_slots
            ):
                same_subject = self._normalize_match_text(
                    sub1.name
                ) == self._normalize_match_text(sub2.name) or (
                    sub1.code
                    and sub2.code
                    and self._normalize_match_text(sub1.code)
                    == self._normalize_match_text(sub2.code)
                )
                return same_subject and not sub1.requires_lab and not sub2.requires_lab

            return False

        def add_overlap_constraints(allocations_map, entity_name):
            for entity_id, day_map in allocations_map.items():
                for day, entries in day_map.items():
                    if not entries:
                        continue

                    for i in range(len(entries)):
                        e1 = entries[i]
                        for j in range(i + 1, len(entries)):
                            e2 = entries[j]
                            if e1["start"] < e2["end"] and e2["start"] < e1["end"]:
                                if is_allowed_shared_slot(e1, e2, day, entity_name):
                                    continue
                                self.model.Add(e1["var"] + e2["var"] <= 1)

        add_overlap_constraints(self.vars_by_faculty, "Faculty")
        logger.debug("Added Resource Conflict (Faculty) constraints")

        add_overlap_constraints(self.vars_by_room, "Room")
        logger.debug("Added Resource Conflict (Rooms) constraints")

        add_overlap_constraints(self.vars_by_class, "Class")
        logger.debug("Added Resource Conflict (Class) constraints")

        # Keep a lab block in one lab room once the block is placed.
        for sub in self.subjects:
            if not sub.requires_lab:
                continue
            candidate_rooms = self._candidate_rooms_for_subject(sub)
            if len(candidate_rooms) <= 1:
                continue
            for day in range(self.num_days):
                room_period_vars = {}
                for period in range(self.periods_per_day):
                    for room in candidate_rooms:
                        key = f"s{sub.id}_d{day}_p{period}_r{room.id}"
                        if key in self.room_variables:
                            room_period_vars.setdefault(
                                self._id_str(room.id), []
                            ).append((period, self.room_variables[key]))

                room_ids = list(room_period_vars.keys())
                for i, room_id in enumerate(room_ids):
                    for other_room_id in room_ids[i + 1 :]:
                        for _, first_var in room_period_vars[room_id]:
                            for _, second_var in room_period_vars[other_room_id]:
                                self.model.Add(first_var + second_var <= 1)
        logger.debug("Added lab room consistency constraints")

        # 4. DEFAULT: Labs — all hours on ONE day, and consecutive within that day
        for sub in self.subjects:
            if not sub.requires_lab:
                continue

            # Soft PDF/given slots should guide lab placement, while the default
            # lab block rule still keeps labs together on one day.
            has_specific_slots = any(
                c.get("type") in {"specific_time_slot", "specific_time_slot_any"}
                and c.get("target_type", "subject") == "subject"
                and self._is_hard_specific_constraint(c)
                and any(
                    self._matches_subject(target, sub)
                    for target in (c.get("targets") or [c.get("target", "")])
                )
                for c in self.custom_constraints
            )
            if has_specific_slots:
                logger.info(
                    f"Bypassing default lab constraints for '{sub.name}' due to specific_time_slot constraints"
                )
                continue

            hours = self._effective_hours(sub)

            # is_lab_day[day] = 1 if this day is chosen for the lab session
            is_lab_day = [
                self.model.NewBoolVar(f"lab_day_s{sub.id}_d{day}")
                for day in range(self.num_days)
            ]
            # At most one lab day per week
            self.model.Add(sum(is_lab_day) <= 1)

            for day in range(self.num_days):
                period_vars = []
                for period in range(self.periods_per_day):
                    key = f"s{sub.id}_d{day}_p{period}"
                    period_vars.append(
                        self.variables[key] if key in self.variables else None
                    )

                valid_periods = [
                    (p, v) for p, v in enumerate(period_vars) if v is not None
                ]
                all_day_vars = [v for _, v in valid_periods]

                if not all_day_vars:
                    # No slots available this day → cannot be lab day
                    self.model.Add(is_lab_day[day] == 0)
                    continue

                total_daily = sum(all_day_vars)

                # If this IS the lab day → exactly `hours` slots must be scheduled
                self.model.Add(total_daily == hours * is_lab_day[day])

                # Consecutive-block enforcement:
                # Build presence vars per period index
                p_present = []
                for p in range(self.periods_per_day):
                    key = f"s{sub.id}_d{day}_p{p}"
                    if key in self.variables:
                        pv = self.model.NewBoolVar(f"pres_s{sub.id}_d{day}_p{p}")
                        self.model.Add(self.variables[key] == pv)
                        p_present.append(pv)
                    else:
                        p_present.append(None)

                # No gap between any two scheduled periods (contiguous block)
                for i in range(self.periods_per_day):
                    for k in range(i + 2, self.periods_per_day):
                        for j in range(i + 1, k):
                            vi = p_present[i]
                            vk = p_present[k]
                            vj = p_present[j]
                            if vi is None or vk is None or vj is None:
                                continue
                            # if i and k are both scheduled, j must also be scheduled
                            self.model.Add(vi + vk - vj <= 1)

        logger.debug("Added Default (Lab) consecutive + single-day constraints")

        # 5. CUSTOM CONSTRAINTS
        for constraint in self.custom_constraints:
            c_type = constraint.get("type")

            # ── faculty_availability ───────────────────────────────────────────
            if c_type == "faculty_availability":
                f_name = constraint.get("faculty_name", "")
                allowed_days = [
                    d.lower()
                    for d in constraint.get("available_days", [])
                    if isinstance(d, str)
                ]
                target_fac = self._find_faculty_by_name(f_name)
                if target_fac:
                    for day_idx, day_name in enumerate(self.working_days):
                        if day_name.lower() not in allowed_days:
                            entries = self.vars_by_faculty.get(
                                self._id_str(target_fac.id), {}
                            ).get(day_idx, [])
                            for e in entries:
                                self.model.Add(e["var"] == 0)
                    logger.debug(f"Applied faculty_availability for '{f_name}'")
                else:
                    self._constraint_error(
                        f"faculty_availability: faculty '{f_name}' not found in loaded data"
                    )

            # ── faculty_time_unavailability ────────────────────────────────────
            elif c_type == "faculty_time_unavailability":
                f_name = constraint.get("faculty_name", "")
                target_fac = self._find_faculty_by_name(f_name)
                start_time = constraint.get("start_time")
                end_time = constraint.get("end_time")
                if target_fac and start_time and end_time:
                    try:
                        s_min = self._parse_time(start_time)
                        e_min = self._parse_time(end_time)
                        for day_idx, day_name in enumerate(self.working_days):
                            entries = self.vars_by_faculty.get(
                                self._id_str(target_fac.id), {}
                            ).get(day_idx, [])
                            for e in entries:
                                if e["start"] < e_min and s_min < e["end"]:
                                    self.model.Add(e["var"] == 0)
                        logger.debug(
                            f"Applied faculty_time_unavailability for '{f_name}' ({start_time}-{end_time})"
                        )
                    except Exception as ex:
                        self._constraint_error(
                            f"faculty_time_unavailability: invalid time format {ex}"
                        )
                else:
                    self._constraint_error(
                        f"faculty_time_unavailability: target '{f_name}' not found or missing times"
                    )

            # ── subject_max_per_day ────────────────────────────────────────────
            elif c_type == "subject_max_per_day":
                sub_name = str(constraint.get("subject_name", ""))
                max_pd = int(constraint.get("max_per_day", 1))
                matched_subjects = [
                    sub for sub in self.subjects if self._matches_subject(sub_name, sub)
                ]
                for sub in matched_subjects:
                    for day in range(self.num_days):
                        day_vars = [
                            self.variables[f"s{sub.id}_d{day}_p{p}"]
                            for p in range(self.periods_per_day)
                            if f"s{sub.id}_d{day}_p{p}" in self.variables
                        ]
                        if day_vars:
                            self.model.Add(sum(day_vars) <= max_pd)
                if matched_subjects:
                    logger.debug(
                        f"Applied subject_max_per_day for '{sub_name}' (max={max_pd})"
                    )
                else:
                    self._constraint_error(
                        f"subject_max_per_day: subject '{sub_name}' not found in loaded data"
                    )

            # ── preferred_time_slot ────────────────────────────────────────────
            elif c_type == "preferred_time_slot":
                target = str(constraint.get("target", ""))
                target_type = str(constraint.get("target_type", "subject")).lower()
                pref = str(constraint.get("preference", "morning")).lower()
                if constraint.get("soft"):
                    logger.debug(
                        f"Skipped soft preferred_time_slot for '{target}' ({target_type}) -> {pref}"
                    )
                    continue
                half = self.periods_per_day // 2

                # Determine which periods to PREFER (soft: penalise non-preferred)
                # We implement this as a hard constraint to keep it simple & reliable
                if pref in {"morning", "first_half"}:
                    preferred_periods = set(range(0, half))
                else:  # afternoon / second_half
                    preferred_periods = set(range(half, self.periods_per_day))

                non_preferred = set(range(self.periods_per_day)) - preferred_periods

                matched_subjects = self._subjects_for_target(target, target_type)
                class_name = constraint.get("class_name")
                if class_name:
                    matching_class_ids = {
                        self._id_str(cls.id)
                        for cls in self.classes
                        if self._matches_class(class_name, cls)
                    }
                    matched_subjects = [
                        sub
                        for sub in matched_subjects
                        if self._id_str(sub.class_id) in matching_class_ids
                    ]

                for sub in matched_subjects:
                    for day in range(self.num_days):
                        for p in non_preferred:
                            key = f"s{sub.id}_d{day}_p{p}"
                            if key in self.variables:
                                self.model.Add(self.variables[key] == 0)
                if matched_subjects:
                    logger.debug(
                        f"Applied preferred_time_slot for '{target}' ({target_type}) -> {pref}"
                    )
                else:
                    self._constraint_error(
                        f"preferred_time_slot: target '{target}' ({target_type}) not found in loaded data"
                    )

            # ── avoid_time_slot ────────────────────────────────────────────────
            elif c_type == "avoid_time_slot":
                target = str(constraint.get("target", ""))
                target_type = str(constraint.get("target_type", "class")).lower()
                blocked_periods = [
                    int(p) - 1 for p in constraint.get("periods", [])
                ]  # convert 1-indexed → 0-indexed

                matched_subjects = self._subjects_for_target(target, target_type)
                class_name = constraint.get("class_name")
                if class_name:
                    matching_class_ids = {
                        self._id_str(cls.id)
                        for cls in self.classes
                        if self._matches_class(class_name, cls)
                    }
                    matched_subjects = [
                        sub
                        for sub in matched_subjects
                        if self._id_str(sub.class_id) in matching_class_ids
                    ]

                for sub in matched_subjects:
                    for day in range(self.num_days):
                        for p in blocked_periods:
                            if 0 <= p < self.periods_per_day:
                                key = f"s{sub.id}_d{day}_p{p}"
                                if key in self.variables:
                                    self.model.Add(self.variables[key] == 0)
                if matched_subjects:
                    logger.debug(
                        f"Applied avoid_time_slot for '{target}' ({target_type}, periods={blocked_periods})"
                    )
                else:
                    self._constraint_error(
                        f"avoid_time_slot: target '{target}' ({target_type}) not found in loaded data"
                    )

            # ── consecutive_periods ────────────────────────────────────────────
            elif c_type == "consecutive_periods":
                sub_type = str(constraint.get("subject_type", "lab")).strip().lower()
                matched_count = 0
                for sub in self.subjects:
                    matches = False
                    if sub_type == "lab" and sub.requires_lab:
                        matches = True
                    elif self._matches_subject(sub_type, sub):
                        matches = True

                    if matches:
                        matched_count += 1
                        for day in range(self.num_days):
                            p_present = []
                            for p in range(self.periods_per_day):
                                key = f"s{sub.id}_d{day}_p{p}"
                                if key in self.variables:
                                    pv = self.model.NewBoolVar(
                                        f"custom_pres_s{sub.id}_d{day}_p{p}"
                                    )
                                    self.model.Add(self.variables[key] == pv)
                                    p_present.append(pv)
                                else:
                                    p_present.append(None)

                            for i in range(self.periods_per_day):
                                for k in range(i + 2, self.periods_per_day):
                                    for j in range(i + 1, k):
                                        vi = p_present[i]
                                        vk = p_present[k]
                                        vj = p_present[j]
                                        if (
                                            vi is not None
                                            and vk is not None
                                            and vj is not None
                                        ):
                                            self.model.Add(vi + vk - vj <= 1)
                if matched_count:
                    logger.debug(f"Applied consecutive_periods for type '{sub_type}'")
                else:
                    self._constraint_error(
                        f"consecutive_periods: subject type '{sub_type}' not found in loaded data"
                    )

            # ── class_gap ──────────────────────────────────────────────────────
            elif c_type == "class_gap":
                cls_name = str(constraint.get("class_name", ""))
                min_gap = int(constraint.get("min_gap", 1))
                matched_classes = [
                    cls for cls in self.classes if self._matches_class(cls_name, cls)
                ]
                for cls in matched_classes:
                    cls_subjects = [
                        s
                        for s in self.subjects
                        if self._id_str(s.class_id) == self._id_str(cls.id)
                    ]
                    for day in range(self.num_days):
                        class_slot_vars = []
                        for p in range(self.periods_per_day):
                            slot_vars = [
                                self.variables[f"s{sub.id}_d{day}_p{p}"]
                                for sub in cls_subjects
                                if f"s{sub.id}_d{day}_p{p}" in self.variables
                            ]
                            class_slot_vars.append(slot_vars)

                        for p in range(self.periods_per_day):
                            for gap in range(1, min_gap + 1):
                                p_next = p + gap
                                if (
                                    p_next < self.periods_per_day
                                    and class_slot_vars[p]
                                    and class_slot_vars[p_next]
                                ):
                                    self.model.Add(
                                        sum(class_slot_vars[p])
                                        + sum(class_slot_vars[p_next])
                                        <= 1
                                    )
                if matched_classes:
                    logger.debug(
                        f"Applied class_gap for class '{cls_name}' (min_gap={min_gap})"
                    )
                else:
                    self._constraint_error(
                        f"class_gap: class '{cls_name}' not found in loaded data"
                    )

            # ── specific_time_slot ─────────────────────────────────────────────
            elif c_type == "specific_time_slot":
                target = str(constraint.get("target", ""))
                target_type = str(constraint.get("target_type", "subject")).lower()
                period_num = constraint.get("period")
                if period_num is not None:
                    try:
                        p_idx = int(period_num) - 1
                    except (TypeError, ValueError):
                        self._constraint_error(
                            f"specific_time_slot: invalid period '{period_num}' for target '{target}'"
                        )
                        continue
                    day_name = constraint.get("day")
                    matched_subjects = self._subjects_for_target(target, target_type)
                    class_name = constraint.get("class_name")
                    if class_name:
                        matching_class_ids = {
                            self._id_str(cls.id)
                            for cls in self.classes
                            if self._matches_class(class_name, cls)
                        }
                        matched_subjects = [
                            sub
                            for sub in matched_subjects
                            if self._id_str(sub.class_id) in matching_class_ids
                        ]

                    for sub in matched_subjects:
                        sub_vars = []
                        for day_idx in range(self.num_days):
                            if (
                                day_name
                                and self.working_days[day_idx].lower()
                                != day_name.lower()
                            ):
                                continue
                            if 0 <= p_idx < self.periods_per_day:
                                key = f"s{sub.id}_d{day_idx}_p{p_idx}"
                                if key in self.variables:
                                    sub_vars.append(self.variables[key])
                        if sub_vars and self._is_hard_specific_constraint(constraint):
                            self.model.Add(sum(sub_vars) >= 1)
                        elif not sub_vars:
                            self._constraint_error(
                                f"specific_time_slot preference unavailable: '{target}' has no feasible variable "
                                f"for period {period_num}"
                                + (f" on {day_name}" if day_name else "")
                            )
                    if matched_subjects:
                        mode = (
                            "hard"
                            if self._is_hard_specific_constraint(constraint)
                            else "preferred"
                        )
                        logger.debug(
                            f"Applied {mode} specific_time_slot for '{target}' ({target_type}, period={period_num}, day={day_name})"
                        )
                    else:
                        self._constraint_error(
                            f"specific_time_slot: target '{target}' ({target_type}) not found in loaded data"
                        )

            elif c_type == "specific_time_slot_any":
                targets = [
                    str(target) for target in constraint.get("targets", []) if target
                ]
                target_type = str(constraint.get("target_type", "subject")).lower()
                period_num = constraint.get("period")
                if period_num is not None:
                    try:
                        p_idx = int(period_num) - 1
                    except (TypeError, ValueError):
                        self._constraint_error(
                            f"specific_time_slot_any: invalid period '{period_num}' for targets '{targets}'"
                        )
                        continue

                    day_name = constraint.get("day")
                    class_name = constraint.get("class_name")
                    matched_subjects = self._subjects_for_constraint_targets(
                        targets, target_type, class_name
                    )
                    slot_vars = []
                    for sub in matched_subjects:
                        for day_idx in range(self.num_days):
                            if (
                                day_name
                                and self.working_days[day_idx].lower()
                                != day_name.lower()
                            ):
                                continue
                            if 0 <= p_idx < self.periods_per_day:
                                key = f"s{sub.id}_d{day_idx}_p{p_idx}"
                                if key in self.variables:
                                    slot_vars.append(self.variables[key])

                    if slot_vars and self._is_hard_specific_constraint(constraint):
                        self.model.Add(sum(slot_vars) >= 1)
                    elif not slot_vars:
                        self._constraint_error(
                            f"specific_time_slot_any unavailable: none of {targets} has a feasible variable "
                            f"for period {period_num}"
                            + (f" on {day_name}" if day_name else "")
                        )

                    if matched_subjects:
                        mode = (
                            "hard"
                            if self._is_hard_specific_constraint(constraint)
                            else "preferred"
                        )
                        logger.debug(
                            f"Applied {mode} specific_time_slot_any for {targets} ({target_type}, period={period_num}, day={day_name})"
                        )
                    else:
                        self._constraint_error(
                            f"specific_time_slot_any: targets {targets} ({target_type}) not found in loaded data"
                        )

            else:
                self._constraint_error(f"Unsupported AI constraint type: '{c_type}'")

    def _add_distribution_objective(self):
        """
        Soft objective:
        - avoid missing required credit-derived hours,
        - fill otherwise-free slots with bounded credit-weighted theory extras,
        - keep morning periods fairly shared across theory subjects,
        - spread theory load across the week.
        """
        theory_daily_load = []  # one IntVar per day
        for day in range(self.num_days):
            day_vars = []
            for sub in self.subjects:
                if not sub.requires_lab:  # only theory subjects
                    for period in range(self.periods_per_day):
                        key = f"s{sub.id}_d{day}_p{period}"
                        if key in self.variables:
                            day_vars.append(self.variables[key])
            if day_vars:
                load_var = self.model.NewIntVar(0, len(day_vars), f"load_day{day}")
                self.model.Add(load_var == sum(day_vars))
                theory_daily_load.append(load_var)

        penalty_terms = []
        half_day = max(1, self.periods_per_day // 2)
        for sub in self.subjects:
            credit = self._credit_value(sub)
            for day in range(self.num_days):
                for period in range(self.periods_per_day):
                    key = f"s{sub.id}_d{day}_p{period}"
                    if key in self.variables:
                        if sub.requires_lab:
                            # Prefer afternoon for labs: penalize early periods heavily
                            penalty_terms.append(
                                self.variables[key]
                                * (self.periods_per_day - period)
                                * 10
                            )
                        else:
                            # Filling extra/free slots is credit-weighted, while
                            # morning preference is period-based and equal for
                            # every theory subject.
                            credit_fill_reward = -100 * credit
                            equal_morning_penalty = period * 3
                            penalty_terms.append(
                                self.variables[key]
                                * (credit_fill_reward + equal_morning_penalty)
                            )

        # Treat user/PDF fixed slots as the first scheduling priority after
        # feasibility and required-hour coverage. Remaining slots are then
        # balanced by the normal distribution objective.
        for sub_id, day, period in getattr(self, "specific_preference_slots", set()):
            key = f"s{sub_id}_d{day}_p{period}"
            if key in self.variables:
                penalty_terms.append(self.variables[key] * -60000)

        for key, room_var in self.room_variables.items():
            match = re.match(r"^s(.+)_d(\d+)_p(\d+)_r(.+)$", key)
            if not match:
                continue
            sub_id = match.group(1)
            room_id = match.group(4)
            sub = self.subject_by_id.get(self._id_str(sub_id))
            if not sub:
                continue
            class_obj = self.class_map.get(self._id_str(sub.class_id))
            default_room_id = self._id_str(class_obj.room_id) if class_obj else ""
            room = self.room_by_id.get(self._id_str(room_id))
            room_type = self._room_type(room) if room else "lecture"
            if sub.requires_lab:
                penalty_terms.append(room_var * (0 if room_type == "lab" else 250000))
            elif default_room_id:
                penalty_terms.append(
                    room_var * (-50000 if room_id == default_room_id else 500000)
                )
            else:
                penalty_terms.append(room_var * 100)

        morning_fairness_terms = []
        for class_obj in self.classes:
            class_theory_subjects = [
                sub
                for sub in self.subjects
                if self._id_str(sub.class_id) == self._id_str(class_obj.id)
                and not sub.requires_lab
            ]
            morning_loads = []
            for sub in class_theory_subjects:
                morning_vars = []
                for day in range(self.num_days):
                    for period in range(half_day):
                        key = f"s{sub.id}_d{day}_p{period}"
                        if key in self.variables:
                            morning_vars.append(self.variables[key])
                if morning_vars:
                    max_possible = len(morning_vars)
                    morning_load = self.model.NewIntVar(
                        0, max_possible, f"morning_load_s{sub.id}"
                    )
                    self.model.Add(morning_load == sum(morning_vars))
                    morning_loads.append(morning_load)

            if len(morning_loads) >= 2:
                max_morning = self.model.NewIntVar(
                    0, self.num_days * half_day, f"max_morning_c{class_obj.id}"
                )
                min_morning = self.model.NewIntVar(
                    0, self.num_days * half_day, f"min_morning_c{class_obj.id}"
                )
                self.model.AddMaxEquality(max_morning, morning_loads)
                self.model.AddMinEquality(min_morning, morning_loads)
                morning_spread = self.model.NewIntVar(
                    0, self.num_days * half_day, f"morning_spread_c{class_obj.id}"
                )
                self.model.Add(morning_spread == max_morning - min_morning)
                morning_fairness_terms.append(morning_spread)

        morning_penalty = sum(penalty_terms) if penalty_terms else 0
        if hasattr(self, "shortage_vars") and self.shortage_vars:
            morning_penalty += sum(v * 100000 for v in self.shortage_vars)
        if hasattr(self, "empty_slot_vars") and self.empty_slot_vars:
            morning_penalty += sum(v * 50000 for v in self.empty_slot_vars)
        if morning_fairness_terms:
            morning_penalty += sum(v * 300 for v in morning_fairness_terms)

        if len(theory_daily_load) >= 2:
            max_load = self.model.NewIntVar(
                0, self.periods_per_day * len(self.subjects), "max_load"
            )
            min_load = self.model.NewIntVar(
                0, self.periods_per_day * len(self.subjects), "min_load"
            )
            self.model.AddMaxEquality(max_load, theory_daily_load)
            self.model.AddMinEquality(min_load, theory_daily_load)
            spread = self.model.NewIntVar(
                0, self.periods_per_day * len(self.subjects), "spread"
            )
            self.model.Add(spread == max_load - min_load)

            # Combine objectives: first avoid missing hours, then keep distribution
            # and morning fairness healthy, then use credit-weighted extras.
            self.model.Minimize(spread * 1000 + morning_penalty)
            logger.debug(
                "Added credit-fill, even distribution, and fair-morning objectives"
            )
        else:
            self.model.Minimize(morning_penalty)
            logger.debug("Added credit-fill and fair-morning objective")

    def solve(self) -> Dict[str, Any]:
        logger.info(
            f"Step 4/5: Solving model (Time Limit: {self.time_limit_seconds}s)..."
        )
        self._add_distribution_objective()
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        solver.parameters.num_search_workers = 8
        solver.parameters.log_search_progress = True

        start_time = time.time()
        status = solver.Solve(self.model)
        duration = time.time() - start_time
        logger.info(
            f"Step 5/5: Solver finished in {duration:.2f}s with status: {solver.StatusName(status)}"
        )
        logger.info(
            f"Solver Statistics: Conflicts: {solver.NumConflicts()}, Branches: {solver.NumBranches()}, WallTime: {solver.WallTime()}s"
        )

        status_map = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
            cp_model.UNKNOWN: "UNKNOWN",
        }

        result = {
            "status": status_map.get(status, "UNKNOWN"),
            "schedule": None,
            "solve_time": solver.WallTime(),
        }
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            result["schedule"] = self.extract_schedule(solver)
        return result

    def extract_schedule(self, solver: cp_model.CpSolver) -> Dict[str, Any]:
        schedule = {}
        for class_obj in self.classes:
            timeline_slots = self._get_class_timeline_slots(class_obj)
            batch = class_obj._doc.get("_batch_obj")
            dept_name = next(
                (d.name for d in self.departments if d.id == class_obj.department_id),
                "",
            )

            class_schedule = {
                "class_id": class_obj.id,
                "class_name": f"{class_obj.name} {class_obj.section or ''}",
                "department": dept_name,
                "batch_name": batch.name if batch else "Default",
                "default_room": self._room_label(
                    self.room_by_id.get(self._id_str(class_obj.room_id))
                ),
                "timetable": {},
            }

            class_subjects = [
                s
                for s in self.subjects
                if self._id_str(s.class_id) == self._id_str(class_obj.id)
            ]

            for day_idx, day_name in enumerate(self.working_days):
                day_schedule = []
                for timeline_slot in timeline_slots:
                    if timeline_slot.get("slot_type") == "break":
                        day_schedule.append(
                            {
                                "slot_type": "break",
                                "break_type": timeline_slot.get("break_type", "break"),
                                "label": timeline_slot.get("label", "Break"),
                                "period": None,
                                "time": self._format_time_range(
                                    timeline_slot["start"], timeline_slot["end"]
                                ),
                                "subject": None,
                            }
                        )
                        continue

                    p_idx = timeline_slot["period_index"]
                    slot_info = {
                        "slot_type": "period",
                        "period": p_idx + 1,
                        "time": self._format_time_range(
                            timeline_slot["start"], timeline_slot["end"]
                        ),
                        "subject": None,
                    }

                    for sub in class_subjects:
                        key = f"s{sub.id}_d{day_idx}_p{p_idx}"
                        if (
                            key in self.variables
                            and solver.Value(self.variables[key]) == 1
                        ):
                            faculty_name = "TBA"
                            if sub.faculty_id:
                                fac = next(
                                    (
                                        f
                                        for f in self.faculty
                                        if self._id_str(f.id)
                                        == self._id_str(sub.faculty_id)
                                    ),
                                    None,
                                )
                                if fac:
                                    faculty_name = fac.name

                            assigned_room = None
                            for room in self._candidate_rooms_for_subject(sub):
                                room_key = f"s{sub.id}_d{day_idx}_p{p_idx}_r{room.id}"
                                if (
                                    room_key in self.room_variables
                                    and solver.Value(self.room_variables[room_key]) == 1
                                ):
                                    assigned_room = room
                                    break

                            is_custom = (
                                sub.id,
                                day_idx,
                                p_idx,
                            ) in self.specific_constrained_slots
                            self._id_str(class_obj.room_id)
                            assigned_room_id = (
                                self._id_str(assigned_room.id)
                                if assigned_room
                                else None
                            )
                            room_change_reason = self._room_change_reason(
                                sub, class_obj, assigned_room
                            )
                            slot_info.update(
                                {
                                    "subject": sub.name,
                                    "subject_code": sub.code,
                                    "faculty": faculty_name,
                                    "room": self._room_label(assigned_room),
                                    "room_id": assigned_room_id,
                                    "room_moved": bool(room_change_reason),
                                    "room_change_reason": room_change_reason,
                                    "room_changed": bool(
                                        room_change_reason
                                        and room_change_reason != "lab_session"
                                    ),
                                    "is_lab": sub.requires_lab,
                                    "is_custom": is_custom,
                                    "credits": getattr(sub, "credits", 0),
                                }
                            )
                            break
                    day_schedule.append(slot_info)
                class_schedule["timetable"][day_name] = day_schedule

            schedule[f"class_{class_obj.id}"] = class_schedule
        return schedule

    def _validate_custom_constraints_against_schedule(
        self, schedule: Dict[str, Any]
    ) -> List[str]:
        errors = []
        for constraint in self.custom_constraints:
            c_type = constraint.get("type")

            if c_type == "faculty_availability":
                faculty_name = str(constraint.get("faculty_name", ""))
                allowed_days = {
                    str(day).lower()
                    for day in constraint.get("available_days", [])
                    if isinstance(day, str)
                }
                if not faculty_name or not allowed_days:
                    continue

                for class_schedule in schedule.values():
                    for day_name, slots in class_schedule.get("timetable", {}).items():
                        if day_name.lower() in allowed_days:
                            continue
                        for slot in slots:
                            slot_faculty = slot.get("faculty")
                            if slot.get("subject") and self._matches_text(
                                faculty_name, slot_faculty
                            ):
                                errors.append(
                                    f"faculty_availability violated: {slot_faculty} is scheduled for "
                                    f"{slot.get('subject')} in {class_schedule.get('class_name')} on {day_name}, "
                                    f"but allowed days are {', '.join(constraint.get('available_days', []))}."
                                )

            elif c_type == "faculty_unavailability":
                faculty_name = str(constraint.get("faculty_name", ""))
                unavailable_days = {
                    str(day).lower()
                    for day in constraint.get("unavailable_days", [])
                    if isinstance(day, str)
                }
                if not faculty_name or not unavailable_days:
                    continue

                for class_schedule in schedule.values():
                    for day_name, slots in class_schedule.get("timetable", {}).items():
                        if day_name.lower() not in unavailable_days:
                            continue
                        for slot in slots:
                            slot_faculty = slot.get("faculty")
                            if slot.get("subject") and self._matches_text(
                                faculty_name, slot_faculty
                            ):
                                errors.append(
                                    f"faculty_unavailability violated: {slot_faculty} is scheduled for "
                                    f"{slot.get('subject')} in {class_schedule.get('class_name')} on {day_name}."
                                )

            elif c_type == "specific_time_slot":
                target = str(constraint.get("target", ""))
                target_type = str(constraint.get("target_type", "subject")).lower()
                class_name = str(constraint.get("class_name", ""))
                day_filter = str(constraint.get("day", "")).lower()
                try:
                    period = int(constraint.get("period"))
                except (TypeError, ValueError):
                    continue

                matched_any_class = False
                satisfied = False
                for class_schedule in schedule.values():
                    schedule_class_name = str(class_schedule.get("class_name", ""))
                    if class_name and not self._matches_text(
                        class_name, schedule_class_name
                    ):
                        continue
                    matched_any_class = True

                    for day_name, slots in class_schedule.get("timetable", {}).items():
                        if day_filter and day_name.lower() != day_filter:
                            continue
                        for slot in slots:
                            if slot.get("period") != period:
                                continue
                            if target_type == "class":
                                satisfied = bool(slot.get("subject"))
                            else:
                                satisfied = self._matches_schedule_subject(target, slot)
                            if satisfied:
                                break
                        if satisfied:
                            break
                    if satisfied:
                        break

                if matched_any_class and not satisfied:
                    label = (
                        "hard constraint"
                        if self._is_hard_specific_constraint(constraint)
                        else "preference"
                    )
                    errors.append(
                        f"specific_time_slot {label} not met: {target} "
                        f"period {period}"
                        + (
                            f" on {constraint.get('day')}"
                            if constraint.get("day")
                            else ""
                        )
                        + (f" for {class_name}" if class_name else "")
                        + "."
                    )

            elif c_type == "specific_time_slot_any":
                targets = [
                    str(target) for target in constraint.get("targets", []) if target
                ]
                class_name = str(constraint.get("class_name", ""))
                day_filter = str(constraint.get("day", "")).lower()
                try:
                    period = int(constraint.get("period"))
                except (TypeError, ValueError):
                    continue

                matched_any_class = False
                satisfied = False
                for class_schedule in schedule.values():
                    schedule_class_name = str(class_schedule.get("class_name", ""))
                    if class_name and not self._matches_text(
                        class_name, schedule_class_name
                    ):
                        continue
                    matched_any_class = True

                    for day_name, slots in class_schedule.get("timetable", {}).items():
                        if day_filter and day_name.lower() != day_filter:
                            continue
                        for slot in slots:
                            if slot.get("period") != period:
                                continue
                            satisfied = any(
                                self._matches_schedule_subject(target, slot)
                                for target in targets
                            )
                            if satisfied:
                                break
                        if satisfied:
                            break
                    if satisfied:
                        break

                if matched_any_class and not satisfied:
                    label = (
                        "hard constraint"
                        if self._is_hard_specific_constraint(constraint)
                        else "preference"
                    )
                    errors.append(
                        f"specific_time_slot_any {label} not met: one of {', '.join(targets)} "
                        f"period {period}"
                        + (
                            f" on {constraint.get('day')}"
                            if constraint.get("day")
                            else ""
                        )
                        + (f" for {class_name}" if class_name else "")
                        + "."
                    )

        return errors

    def _auto_assign_faculty_to_unassigned_subjects(
        self,
    ) -> Tuple[List[Tuple[_Obj, str]], List[_Obj]]:
        """
        Greedy in-memory assignment of faculty to subjects that lack a `faculty_id`.
        Respects faculty `max_hours_per_week` and basic availability estimation.
        Returns: (auto_assigned list of (subject, faculty_name), failed_subjects list)
        """
        auto_assigned = []
        failed = []

        # Build faculty pools by department
        fac_by_dept = {}
        assigned_hours = {}
        for f in self.faculty:
            dep = getattr(f, "department_id", None)
            fac_by_dept.setdefault(dep, []).append(f)
            assigned_hours[self._id_str(f.id)] = 0

        # Count already assigned hours for faculties
        for s in self.subjects:
            if s.faculty_id:
                fid = self._id_str(s.faculty_id)
                assigned_hours[fid] = assigned_hours.get(
                    fid, 0
                ) + self._effective_hours(s)

        # Subjects that need faculty
        unassigned = [s for s in self.subjects if not s.faculty_id]
        # Sort by hours desc to assign heavy subjects first
        unassigned.sort(key=lambda x: -(x.hours_per_week or 0))

        for subj in unassigned:
            # Prefer faculty from same department of the subject's class
            class_obj = self.class_map.get(self._id_str(subj.class_id))
            preferred_dept = None
            if class_obj:
                preferred_dept = getattr(class_obj, "department_id", None)

            candidates = []
            if preferred_dept in fac_by_dept:
                candidates = fac_by_dept[preferred_dept][:]
            else:
                # fallback to any faculty
                candidates = [f for f in self.faculty]

            # Filter by capacity (max_hours)
            viable = []
            need = self._effective_hours(subj)
            for f in candidates:
                fid = self._id_str(f.id)
                max_h = getattr(f, "max_hours_per_week", None) or 0
                if assigned_hours.get(fid, 0) + need <= max_h:
                    # Basic availability check: count potential slots across class timelines
                    # Estimate available slots as total class slots minus faculty unavailability overlaps
                    total_potential = 0
                    # For subjects mapped to a class, calculate available period slots for that class
                    if subj.class_id and subj.class_id in self.class_map:
                        cls = self.class_map[self._id_str(subj.class_id)]
                        intervals = self._get_class_period_intervals(cls)
                        for day_idx, day_name in enumerate(self.working_days):
                            for p_idx, (start, end) in enumerate(intervals):
                                if not self._is_faculty_unavailable(
                                    f, day_idx, day_name, p_idx, start, end
                                ):
                                    total_potential += 1
                    else:
                        # conservatively allow
                        total_potential = need

                    if total_potential >= need:
                        viable.append((f, max_h - assigned_hours.get(fid, 0)))

            if not viable:
                failed.append(subj)
                continue

            # pick candidate with largest remaining capacity
            viable.sort(key=lambda x: -x[1])
            chosen = viable[0][0]
            # assign in-memory
            subj._doc["faculty_id"] = (
                ObjectId(chosen.id) if ObjectId.is_valid(chosen.id) else chosen.id
            )
            assigned_hours[self._id_str(chosen.id)] = (
                assigned_hours.get(self._id_str(chosen.id), 0) + need
            )
            auto_assigned.append((subj, chosen.name, self._id_str(chosen.id)))

        return auto_assigned, failed

    def generate_schedule(
        self,
        department_ids: Optional[List[str]] = None,
        batch_ids: Optional[List[str]] = None,
        class_ids: Optional[List[str]] = None,
        faculty_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        data_summary = self.load_data(department_ids, batch_ids, class_ids, faculty_ids)
        self._sync_periods_per_day_to_batch_timings()
        if not self.classes or not self.subjects:
            msg = (
                "No classes found."
                if not self.classes
                else "Found Classes, but NO Subjects are assigned to them.\nHint: Go to 'Mapping' and assign your Global Subjects to these Classes."
            )
            return {"status": "ERROR", "message": msg, "data_summary": data_summary}
        # VALIDATION: Ensure every subject has a Class mapped; try to auto-assign Faculty where missing.
        missing_mappings = []
        for sub in self.subjects:
            issues = []
            if not sub.class_id:
                issues.append("Missing Class")
            if not sub.faculty_id:
                issues.append("Missing Faculty")
            if issues:
                missing_mappings.append((sub, issues))

        # If some subjects are missing faculty, attempt an in-memory auto-assignment.
        if any("Missing Faculty" in issues for _, issues in missing_mappings):
            auto_assigned, failed = self._auto_assign_faculty_to_unassigned_subjects()
            if auto_assigned:
                logger.info(f"Auto-assigned faculty for {len(auto_assigned)} subjects")
                # Update data_summary with info
                data_summary["auto_assigned_subjects"] = [
                    f"{s.name} -> {f_name}" for s, f_name, _ in auto_assigned
                ]
                # Persist assignments to DB so mappings appear in UI
                for subj, _, fac_id in auto_assigned:
                    try:
                        sid = (
                            ObjectId(subj.id) if ObjectId.is_valid(subj.id) else subj.id
                        )
                        fid = ObjectId(fac_id) if ObjectId.is_valid(fac_id) else fac_id
                        self.db["subjects"].update_one(
                            {"_id": sid}, {"$set": {"faculty_id": fid}}
                        )
                    except Exception:
                        logger.exception(
                            f"Failed to persist auto-assignment for subject {subj.id}"
                        )

            if failed:
                # Build clear error list for subjects still lacking mapping
                missing_list = [f"{s.name} ({s.code}): Missing Faculty" for s in failed]
                msg = (
                    "Could not auto-assign faculty for the following subjects. Please assign faculty manually before generating a timetable:\n"
                    + "\n".join(missing_list)
                )
                logger.warning(msg)
                return {"status": "ERROR", "message": msg, "data_summary": data_summary}

        # VALIDATION 2: Smart Overflow Auto-Correction (think like staff)
        for class_obj in self.classes:
            class_subjects = [
                s
                for s in self.subjects
                if self._id_str(s.class_id) == self._id_str(class_obj.id)
            ]
            if not class_subjects:
                continue
            # Priority: labs first, then higher credits first
            class_subjects_sorted = sorted(
                class_subjects,
                key=lambda s: (-(1 if s.requires_lab else 0), -(int(s.credits or 3))),
            )
            total_eff = sum(self._effective_hours(s) for s in class_subjects_sorted)
            total_slots = self.num_days * len(
                self._get_class_period_intervals(class_obj)
            )

            if total_eff > total_slots:
                excess = total_eff - total_slots
                logger.warning(
                    f"Class '{class_obj.name}' overloaded by {excess} slots — auto-correcting..."
                )
                # Trim from lowest priority subjects first
                for sub in reversed(class_subjects_sorted):
                    if excess <= 0:
                        break
                    current = self._effective_hours(sub)
                    minimum = max(1, current // 2)  # never reduce below half
                    can_cut = current - minimum
                    if can_cut > 0:
                        cut = min(excess, can_cut)
                        new_h = current - cut
                        self._adjusted_hours[sub.id] = new_h
                        self.auto_adjustments.append(
                            f"'{class_obj.name}': '{sub.name}' hours reduced {current}→{new_h} "
                            f"to fit {total_slots} available slots."
                        )
                        excess -= cut
                if excess > 0:
                    self.auto_adjustments.append(
                        f"'{class_obj.name}': Still {excess} slot(s) over limit after auto-reduction. "
                        f"Some periods may be unscheduled."
                    )

        # VALIDATION 3: Faculty Workload — warn, don't block
        for fac in self.faculty:
            fac_subjects = [
                s
                for s in self.subjects
                if self._id_str(s.faculty_id) == self._id_str(fac.id)
            ]
            total_assigned = sum(self._effective_hours(s) for s in fac_subjects)
            max_h = int(fac.max_hours_per_week or 40)
            if total_assigned > max_h:
                self.auto_adjustments.append(
                    f"Faculty '{fac.name}': assigned {total_assigned} hrs exceeds max {max_h} hrs/week. "
                    f"Schedule may be tight."
                )

        self.create_variables()
        self.add_constraints()
        # Constraints are now soft-fail — never block scheduling
        result = self.solve()
        if result.get("schedule"):
            schedule_warnings = self._validate_custom_constraints_against_schedule(
                result["schedule"]
            )
            self.constraint_warnings.extend(schedule_warnings)
        result["data_summary"] = data_summary
        result["effective_periods_per_day"] = self.periods_per_day
        result["auto_adjustments"] = self.auto_adjustments
        result["constraint_warnings"] = self.constraint_warnings
        # Compute suggested alternates for any faculty absence constraints
        try:
            result["substitutes"] = self._compute_alternates_for_absent_faculty()
        except Exception:
            logger.exception("Failed to compute substitutes mapping")
        return result

    def _compute_alternates_for_absent_faculty(self) -> Dict[str, Any]:
        """Return suggested alternate faculty for faculty absence constraints.

        The returned structure maps faculty_name -> {
            "absent_days": [...],
            "subjects": { subject_name: { day_name: [candidate_names...] } }
        }
        This is a best-effort suggestion list (not persisted or enforced).
        """
        suggestions = {}

        # Helper: list faculty who could potentially cover a subject on a given day
        def candidates_for_subject_on_day(
            subject_obj, day_idx, day_name, excluded_faculty_id
        ):
            candidates = []
            for f in self.faculty:
                if self._id_str(f.id) == self._id_str(excluded_faculty_id):
                    continue
                # Check if faculty has at least one available slot for the class timeline
                cls = self.class_map.get(self._id_str(subject_obj.class_id))
                intervals = self._get_class_period_intervals(cls) if cls else []
                available = False
                for p_idx, (start, end) in enumerate(intervals):
                    if not self._is_faculty_unavailable(
                        f, day_idx, day_name, p_idx, start, end
                    ):
                        available = True
                        break
                if not available:
                    continue

                score = 0
                # Prefer faculty who already teach the same subject elsewhere
                for s in self.subjects:
                    if self._id_str(s.faculty_id) == self._id_str(
                        f.id
                    ) and self._matches_subject(subject_obj.name, s):
                        score += 30
                        break
                # Prefer same department
                if getattr(f, "department_id", None) and getattr(cls, "_doc", None):
                    if (
                        f.department_id
                        and cls._doc.get("department_id")
                        and f.department_id == cls._doc.get("department_id")
                    ):
                        score += 10

                candidates.append((score, f.name))

            # Sort by score desc, then name
            candidates.sort(key=lambda x: (-x[0], x[1]))
            return [name for _, name in candidates]

        for constraint in self.custom_constraints:
            c_type = constraint.get("type")
            if c_type != "faculty_availability":
                continue
            f_name = str(constraint.get("faculty_name") or "").strip()
            if not f_name:
                continue
            allowed_days = [
                d.lower()
                for d in constraint.get("available_days", [])
                if isinstance(d, str)
            ]
            absent_days = [
                d for d in self.working_days if d.lower() not in allowed_days
            ]
            if not absent_days:
                continue

            fac = self._find_faculty_by_name(f_name)
            if not fac:
                # store empty entry marking not found
                suggestions[f_name] = {
                    "absent_days": absent_days,
                    "error": "faculty not found",
                    "subjects": {},
                }
                continue

            subjects = [
                s
                for s in self.subjects
                if self._id_str(s.faculty_id) == self._id_str(fac.id)
            ]
            subj_map = {}
            for subj in subjects:
                subj_map[subj.name] = {}
                for day in absent_days:
                    day_idx = next(
                        (
                            i
                            for i, dn in enumerate(self.working_days)
                            if dn.lower() == day.lower()
                        ),
                        None,
                    )
                    if day_idx is None:
                        continue
                    candidates = candidates_for_subject_on_day(
                        subj, day_idx, day, fac.id
                    )
                    subj_map[subj.name][day] = candidates

            suggestions[fac.name] = {
                "absent_days": absent_days,
                "subjects": subj_map,
            }

        return suggestions
