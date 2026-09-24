import difflib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


class AIConstraintParser:
    """
    Parses natural language timetable constraints into structured JSON.
    Features:
    - AI (Groq/OpenAI) + rule-based hybrid parsing
    - Fuzzy name matching with auto-correction tracking
    - Rich diagnostics: corrections, warnings, unrecognized phrases
    - All 8 constraint types supported
    """

    SUPPORTED_TYPES = [
        "faculty_availability",
        "faculty_unavailability",
        "faculty_time_unavailability",
        "consecutive_periods",
        "subject_max_per_day",
        "preferred_time_slot",
        "avoid_time_slot",
        "class_gap",
        "specific_time_slot",
        "specific_time_slot_any",
    ]

    ALL_DAYS = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    WEEKDAY_ALIASES = {
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        "weekend": ["Saturday", "Sunday"],
        "mon": "Monday",
        "tue": "Tuesday",
        "wed": "Wednesday",
        "thu": "Thursday",
        "fri": "Friday",
        "sat": "Saturday",
        "sun": "Sunday",
    }

    NUMBER_WORDS = {
        "one": 1,
        "once": 1,
        "single": 1,
        "two": 2,
        "twice": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }

    def __init__(
        self,
        model=None,
        timeout_seconds=60,
        api_key=None,
        api_base="https://api.openai.com/v1",
        context=None,
    ):
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.context = context or {}
        self._corrections: List[Dict] = []
        self._warnings: List[str] = []
        self._unrecognized: List[str] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def parse_constraints(self, text: str) -> List[Dict[str, Any]]:
        return self.parse_constraints_with_diagnostics(text)["constraints"]

    def parse_constraints_with_diagnostics(self, text: str) -> Dict[str, Any]:
        self._corrections = []
        self._warnings = []
        self._unrecognized = []

        rule_c = self._rule_based(text)
        if not self.api_key or not self.model:
            constraints = rule_c
        else:
            try:
                raw = self._chat(
                    self._build_system_prompt(), self._build_user_prompt(text)
                )
                ai_c = self._extract_constraints(json.loads(raw))
                constraints = self._merge(
                    self._filter_ai_duplicates(self._normalize(ai_c), rule_c), rule_c
                )
            except Exception as e:
                print(f"AI Parse Error: {e}")
                constraints = rule_c

        return {
            "constraints": constraints,
            "corrections": self._corrections,
            "warnings": self._warnings,
            "unrecognized": self._unrecognized,
        }

    # ── Prompt building ────────────────────────────────────────────────────────

    @staticmethod
    def _build_user_prompt(text: str) -> str:
        return (
            "Convert this scheduling request into JSON constraints. "
            "Extract EVERY independent constraint. Treat separate sentences, lines, "
            "bullets, and clauses as separate constraints.\n\n"
            'Return ONLY this JSON shape: {"constraints": [ ... ]}\n\n'
            f"Scheduling request:\n{text}"
        )

    def _build_system_prompt(self) -> str:
        faculty_list = (
            ", ".join(self.context.get("faculty_names", [])) or "not provided"
        )
        subject_list = (
            ", ".join(self.context.get("subject_names", [])) or "not provided"
        )
        class_list = ", ".join(self.context.get("class_names", [])) or "not provided"
        return f"""You are a timetable scheduling assistant. Convert natural language scheduling requests into structured constraint objects. Return ONLY valid JSON.

## Context
- Faculty: {faculty_list}
- Subjects: {subject_list}
- Classes: {class_list}

## Constraint Types
1. faculty_availability  – {{"type": "faculty_availability", "faculty_name": "Dr. X", "available_days": ["Monday"]}}
2. faculty_unavailability – {{"type": "faculty_unavailability", "faculty_name": "Prof. Y", "unavailable_days": ["Friday"]}}
3. faculty_time_unavailability – {{"type": "faculty_time_unavailability", "faculty_name": "Dr. X", "start_time": "10:15", "end_time": "12:30"}}
4. consecutive_periods   – {{"type": "consecutive_periods", "subject_type": "lab"}}
5. subject_max_per_day   – {{"type": "subject_max_per_day", "subject_name": "Maths", "max_per_day": 1}}
6. preferred_time_slot   – {{"type": "preferred_time_slot", "target": "Physics", "target_type": "subject", "preference": "morning", "class_name": "CSE-A"}} (class_name is optional)
7. avoid_time_slot       – {{"type": "avoid_time_slot", "target": "CSE-A", "target_type": "class", "periods": [7, 8]}}
8. class_gap             – {{"type": "class_gap", "class_name": "CSE-A", "min_gap": 1}}
9. specific_time_slot    – {{"type": "specific_time_slot", "target": "Physics", "target_type": "subject", "day": "Monday", "period": 2, "class_name": "CSE-A"}} (class_name is optional)

## Rules
- Match names exactly to the context above.
- Day names → full English (Monday, Tuesday, ...).
- Extract EVERY constraint, not just the first.
- If a subject constraint (specific_time_slot, preferred_time_slot, avoid_time_slot) applies to a specific class, you MUST add "class_name" with the exact matched class from the Context.
- Return ONLY {{"constraints": [...]}}. No other text.

## Examples
Input: "Dr. Raj cannot teach on Fridays and Saturdays"
Output: {{"constraints": [{{"type": "faculty_unavailability", "faculty_name": "Dr. Raj", "unavailable_days": ["Friday", "Saturday"]}}]}}

Input: "For Class CSE-A, MLops must be on Monday periods 4 and 5"
Output: {{"constraints": [{{"type": "specific_time_slot", "target": "MLops", "target_type": "subject", "day": "Monday", "period": 4, "class_name": "CSE-A"}}, {{"type": "specific_time_slot", "target": "MLops", "target_type": "subject", "day": "Monday", "period": 5, "class_name": "CSE-A"}}]}}

Input: "Labs must be consecutive. Physics in the morning."
Output: {{"constraints": [{{"type": "consecutive_periods", "subject_type": "lab"}}, {{"type": "preferred_time_slot", "target": "Physics", "target_type": "subject", "preference": "morning"}}]}}
"""

    # ── AI chat ────────────────────────────────────────────────────────────────

    def _chat(self, system: str, user: str) -> str:
        client = OpenAI(
            api_key=self.api_key, base_url=self.api_base, timeout=self.timeout_seconds
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format=(
                {"type": "json_object"} if self._supports_json_mode() else None
            ),
        )
        return self._strip_md(response.choices[0].message.content or "")

    def _supports_json_mode(self) -> bool:
        supported = {"gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-4o-mini", "llama", "mixtral", "gemma", "qwen"}
        return any(s in (self.model or "").lower() for s in supported)

    @staticmethod
    def _strip_md(text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return text

    @staticmethod
    def _extract_constraints(parsed: Any) -> List[Dict[str, Any]]:
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            c = parsed.get("constraints")
            if isinstance(c, list):
                return c
            if isinstance(c, dict):
                return [c]
            if parsed.get("type"):
                return [parsed]
        raise ValueError("Expected JSON object with constraints array")

    # ── Name matching (exact + fuzzy) ──────────────────────────────────────────

    @staticmethod
    def _normalize_text(value: Any) -> str:
        value = str(value or "").strip()
        value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
        value = value.lower()
        value = re.sub(r"[^a-z0-9]+", " ", value).strip()
        honorifics = {
            "sir",
            "madam",
            "mam",
            "maam",
            "dr",
            "prof",
            "professor",
            "mr",
            "mrs",
            "ms",
        }
        return " ".join(t for t in value.split() if t not in honorifics)

    def _fuzzy_match(
        self, text: str, names: List[str], cutoff: float = 0.70
    ) -> Optional[Tuple[str, Optional[str]]]:
        """
        Returns (matched_name, misspelled_word_or_None).
        Tries exact substring match first, then token-level fuzzy.
        """
        norm_text = self._normalize_text(text)
        text_tokens = norm_text.split()

        normalized_names = [
            (name, normalized)
            for name in names
            if (normalized := self._normalize_text(name))
        ]
        normalized_names.sort(
            key=lambda item: (len(item[1].split()), len(item[1])), reverse=True
        )

        # 1. Exact full-name word-boundary match → no typo.
        for name, norm_name in normalized_names:
            if re.search(r"\b" + re.escape(norm_name) + r"\b", norm_text):
                return (name, None)

        # 2. Exact key-token match across all names before fuzzy correction.
        for name, norm_name in normalized_names:
            if not norm_name:
                continue
            name_tokens = [t for t in norm_name.split() if len(t) >= 2]
            if name_tokens and all(nt in text_tokens for nt in name_tokens):
                return (name, None)

        # 3. All key tokens present with near-exact typo correction.
        for name, norm_name in normalized_names:
            if not norm_name:
                continue
            name_tokens = [t for t in norm_name.split() if len(t) >= 2]
            if name_tokens:
                typo_found = None
                all_present = True
                for nt in name_tokens:
                    # Check near-exact (e.g. "shivaa" vs "shiva")
                    close = difflib.get_close_matches(nt, text_tokens, n=1, cutoff=0.78)
                    if close:
                        if close[0] != nt:
                            typo_found = close[
                                0
                            ]  # what the user typed (the misspelling)
                    else:
                        all_present = False
                        break
                if all_present:
                    return (
                        name,
                        typo_found,
                    )  # typo_found is the misspelling or None if all exact

        # 4. Lower-cutoff fuzzy for more distant typos
        for name, norm_name in normalized_names:
            name_tokens = [t for t in norm_name.split() if len(t) >= 2]
            if not name_tokens:
                continue
            matched, typo_pair = 0, None
            for nt in name_tokens:
                close = difflib.get_close_matches(nt, text_tokens, n=1, cutoff=cutoff)
                if close:
                    matched += 1
                    if close[0] != nt:
                        typo_pair = (close[0], nt)
            if matched >= max(1, (len(name_tokens) + 1) // 2):
                typo_word = typo_pair[0] if typo_pair else None
                return (name, typo_word)

        return None

    def _context_match(self, text: str, names: List[str]) -> Optional[str]:
        """Match a name from context with fuzzy fallback and correction tracking."""
        result = self._fuzzy_match(text, names)
        if result:
            matched_name, typo = result
            if typo:
                self._corrections.append(
                    {
                        "original": typo,
                        "corrected": matched_name,
                        "reason": f"Auto-corrected '{typo}' → '{matched_name}'",
                    }
                )
            return matched_name
        return None

    def _context_matches(self, text: str, names: List[str]) -> List[str]:
        """Return all exact context names present in a chunk, longest first."""
        norm_text = self._normalize_text(text)
        normalized_names = [
            (name, normalized)
            for name in names
            if (normalized := self._normalize_text(name))
        ]
        normalized_names.sort(
            key=lambda item: (len(item[1].split()), len(item[1])), reverse=True
        )

        matches: List[Tuple[int, str]] = []
        covered = set()
        for name, norm_name in normalized_names:
            match = re.search(r"\b" + re.escape(norm_name) + r"\b", norm_text)
            if not match:
                continue
            span = set(range(match.start(), match.end()))
            if covered & span:
                continue
            matches.append((match.start(), name))
            covered |= span
        return [name for _, name in sorted(matches, key=lambda item: item[0])]

    # ── Day parsing ────────────────────────────────────────────────────────────

    def _parse_day_names(self, value: Any) -> List[str]:
        """Parse day names from a string or list, supporting ranges, aliases, and abbreviations."""
        if not value:
            return []

        # Normalise to a single string first
        if isinstance(value, list):
            text = " , ".join(str(v) for v in value)
        else:
            text = str(value)

        lower = text.lower()

        # Expand weekdays/weekend aliases
        if "weekdays" in lower:
            return self.WEEKDAY_ALIASES["weekdays"]
        if "weekend" in lower:
            return self.WEEKDAY_ALIASES["weekend"]

        # Handle ranges like "Mon-Thu" or "Monday to Friday"
        range_match = re.search(r"(\w+)\s*(?:[-–]|to)\s*(\w+)", text, re.IGNORECASE)
        if range_match:
            s = self._single_day(range_match.group(1))
            e = self._single_day(range_match.group(2))
            if s and e:
                si, ei = self.ALL_DAYS.index(s), self.ALL_DAYS.index(e)
                return self.ALL_DAYS[si : ei + 1]

        # Tokenise by separators (commas, slashes, ampersands)
        # Do NOT split on "and" here — "Monday, Tuesday and Thursday" is fine as tokens
        normalized = re.sub(r"[/&;,]+", " ", text)
        # Replace " and " surrounded by spaces with a space only
        normalized = re.sub(r"\band\b", " ", normalized, flags=re.IGNORECASE)

        result = []
        for word in normalized.split():
            day = self._single_day(word)
            if day and day not in result:
                result.append(day)
        return sorted(result, key=lambda d: self.ALL_DAYS.index(d))

    def _single_day(self, text: str) -> Optional[str]:
        lower = text.strip().lower()
        alias = self.WEEKDAY_ALIASES.get(lower)
        if isinstance(alias, str):
            return alias
        for day in self.ALL_DAYS:
            if lower == day.lower() or lower.startswith(day[:3].lower()):
                return day
        return None

    def _parse_period_numbers(self, text: str) -> List[int]:
        """Extract period numbers from text, supporting various phrasings."""
        lower = text.lower()
        periods = []

        # "last N periods"
        m = re.search(r"last\s+(\d+)\s+period", lower)
        if m:
            total = self.context.get("periods_per_day", 7)
            n = int(m.group(1))
            periods.extend(range(total - n + 1, total + 1))

        if re.search(r"\bfirst\s+period\b", lower):
            periods.append(1)
        if re.search(r"\blast\s+period\b", lower):
            periods.append(self.context.get("periods_per_day", 7))

        # "period N" or "periods N and M" or just numbers after "period"
        # First find all numbers associated with period mentions
        period_section = re.sub(r"period[s]?\s*", "PERIOD ", lower)
        raw = re.findall(r"(?:PERIOD\s*)?(\d+)", period_section)
        # Only pick up numbers that appear after "period" or "avoid period N and M"
        for m2 in re.finditer(r"(?:period[s]?)\s*([\d\s,and&]+)", lower):
            nums = re.findall(r"\d+", m2.group(1))
            periods.extend(int(n) for n in nums if 1 <= int(n) <= 20)

        return sorted(set(p for p in periods if 1 <= p <= 20))

    def _parse_day_period_groups(self, text: str) -> List[Tuple[str, List[int]]]:
        """
        Parse compact timetable fragments such as:
        "Tuesday 4,5 Wednesday 4,5" or "Monday 7,8,9".
        """
        if not text:
            return []

        day_pattern = (
            r"\b("
            + "|".join(
                re.escape(day)
                for day in self.ALL_DAYS + list(self.WEEKDAY_ALIASES.keys())
            )
            + r")\b"
        )
        matches = list(re.finditer(day_pattern, text, flags=re.IGNORECASE))
        groups: List[Tuple[str, List[int]]] = []

        for idx, match in enumerate(matches):
            day = self._single_day(match.group(1))
            if not day:
                continue
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            segment = text[start:end]
            periods = self._parse_bare_period_numbers(segment)
            if periods:
                groups.append((day, periods))

        return groups

    def _lab_subject_for_line(
        self, chunk: str, subject: Optional[str], subject_names: List[str]
    ) -> Optional[str]:
        if not subject or "lab" not in self._normalize_text(chunk).split():
            return None
        if "lab" in self._normalize_text(subject).split():
            return subject

        subject_tokens = set(self._normalize_text(subject).split())
        chunk_tokens = set(self._normalize_text(chunk).split())
        lab_names = [
            name
            for name in subject_names
            if "lab" in self._normalize_text(name).split()
        ]
        for name in lab_names:
            name_tokens = set(self._normalize_text(name).split())
            non_lab_name_tokens = name_tokens - {"lab"}
            if subject_tokens & non_lab_name_tokens:
                return name
            if "fcv" in chunk_tokens and "cv" in non_lab_name_tokens:
                return name
        return None

    def _parse_count(self, text: str, default: int = 1) -> int:
        lower = text.lower()
        digit = re.search(r"\b(\d+)\b", lower)
        if digit:
            return int(digit.group(1))
        for word, value in self.NUMBER_WORDS.items():
            if re.search(r"\b" + re.escape(word) + r"\b", lower):
                return value
        return default

    def _target_class_name(
        self, active_class: Optional[str], cls: Optional[str], subject: Optional[str]
    ) -> Optional[str]:
        if subject and active_class:
            return active_class
        if subject and cls:
            return cls
        return None

    @staticmethod
    def _add_class_name(
        constraint: Dict[str, Any], class_name: Optional[str]
    ) -> Dict[str, Any]:
        if class_name:
            constraint["class_name"] = class_name
        return constraint

    @staticmethod
    def _contains_any(text: str, phrases: List[str]) -> bool:
        return any(phrase in text for phrase in phrases)

    def _parse_bare_period_numbers(self, text: str) -> List[int]:
        """Extract bare period numbers from compact timetable lines."""
        return sorted(set(self._parse_bare_period_numbers_with_duplicates(text)))

    def _parse_bare_period_numbers_with_duplicates(self, text: str) -> List[int]:
        """Extract bare period numbers while preserving repeated values."""
        periods = []
        for raw in re.findall(r"\b\d+\b", text):
            try:
                period = int(raw)
            except ValueError:
                continue
            if 1 <= period <= 20:
                periods.append(period)
        return periods

    def _repair_duplicate_lab_periods(
        self, periods: List[int], subject: Optional[str]
    ) -> List[int]:
        if (
            not periods
            or not subject
            or "lab" not in self._normalize_text(subject).split()
        ):
            return sorted(set(periods))
        if len(set(periods)) == len(periods):
            return sorted(periods)

        repaired = sorted(set(periods))
        max_period = int(self.context.get("periods_per_day", 20) or 20)
        expected_count = len(periods)
        next_period = repaired[-1] + 1 if repaired else 1
        while len(repaired) < expected_count and next_period <= max_period:
            if next_period not in repaired:
                repaired.append(next_period)
            next_period += 1

        return sorted(repaired)

    def _class_from_header(self, chunk: str, class_names: List[str]) -> Optional[str]:
        """Find the active class in headers like 'For AIML 2 A Class' or 'For B Class'."""
        lower = chunk.lower()
        if "class" not in lower and not re.search(r"\bfor\b", lower):
            return None

        direct = self._context_match(chunk, class_names)
        if direct:
            return direct

        header_match = re.search(
            r"\b(?:for\s+)?(.+?)\s+class\b", chunk, flags=re.IGNORECASE
        )
        if not header_match:
            return None

        header_norm = self._normalize_text(header_match.group(1))
        if not header_norm:
            return None

        header_tokens = header_norm.split()
        for class_name in class_names:
            class_norm = self._normalize_text(class_name)
            class_tokens = class_norm.split()
            if not class_tokens:
                continue
            if header_norm == class_norm or all(
                token in class_tokens for token in header_tokens
            ):
                return class_name
            if len(header_tokens) == 1 and header_tokens[0] == class_tokens[-1]:
                return class_name
            if len(header_tokens) == 1 and header_tokens[0] in class_tokens:
                return class_name
        return None

    def _format_time_24h(
        self, raw: Any, default_meridiem: Optional[str] = None
    ) -> Optional[str]:
        """
        Normalize user-entered times to HH:MM.
        If no am/pm is supplied, timetable afternoon hours like 1:15 are
        inferred as PM because college schedules rarely mean 1 AM.
        """
        if raw is None:
            return None

        text = str(raw).strip().lower().replace(".", ":")
        match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
        if not match:
            return None

        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3) or default_meridiem
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None

        if meridiem == "am":
            if hour == 12:
                hour = 0
        elif meridiem == "pm":
            if hour < 12:
                hour += 12
        elif 1 <= hour <= 5:
            hour += 12

        return f"{hour:02d}:{minute:02d}"

    def _normalize_time_range(
        self, start: Any, end: Any
    ) -> Tuple[Optional[str], Optional[str]]:
        start_text = str(start or "").strip().lower()
        end_text = str(end or "").strip().lower()
        end_meridiem_match = re.search(r"\b(am|pm)\b", end_text)
        default_meridiem = end_meridiem_match.group(1) if end_meridiem_match else None

        start_norm = self._format_time_24h(start_text, default_meridiem)
        end_norm = self._format_time_24h(end_text)
        if start_norm and end_norm and start_norm >= end_norm:
            # "1:15 to 2:45" should be afternoon, not overnight.
            adjusted_start = self._format_time_24h(start_text, "pm")
            adjusted_end = self._format_time_24h(end_text, "pm")
            if adjusted_start and adjusted_end and adjusted_start < adjusted_end:
                return adjusted_start, adjusted_end
        return start_norm, end_norm

    def _append_specific_slot_constraints(
        self,
        constraints: List[Dict[str, Any]],
        target: str,
        periods: List[int],
        days: List[str],
        class_name: Optional[str] = None,
        hard: bool = False,
    ) -> bool:
        if not target or not periods:
            return False

        produced = False
        for period in periods:
            c: Dict[str, Any] = {
                "type": "specific_time_slot",
                "target": target,
                "target_type": "subject",
                "period": period,
            }
            if days:
                c["day"] = days[0]
            if class_name:
                c["class_name"] = class_name
            if hard:
                c["hard"] = True
            constraints.append(c)
            produced = True
        return produced

    def _append_specific_any_slot_constraints(
        self,
        constraints: List[Dict[str, Any]],
        targets: List[str],
        periods: List[int],
        days: List[str],
        class_name: Optional[str] = None,
        hard: bool = False,
    ) -> bool:
        targets = [target for target in targets if target]
        if len(targets) < 2 or not periods:
            return False

        produced = False
        for period in periods:
            c: Dict[str, Any] = {
                "type": "specific_time_slot_any",
                "targets": targets,
                "target_type": "subject",
                "period": period,
            }
            if days:
                c["day"] = days[0]
            if class_name:
                c["class_name"] = class_name
            if hard:
                c["hard"] = True
            constraints.append(c)
            produced = True
        return produced

    # ── Text splitting (sentence-level only, NOT on "and") ──────────────────────

    def _split_text(self, text: str) -> List[str]:
        """Split on sentence boundaries only. Never split on 'and' — it's part of day lists."""
        # Fix dots in time formats (12.30 -> 12:30) before splitting
        if text:
            text = re.sub(r"(\d)\.(\d)", r"\1:\2", text)
        # Split on periods, semicolons, newlines, bullets
        chunks = re.split(r"[.;\n\r]+", text or "")
        result = []
        for chunk in chunks:
            chunk = chunk.strip(" -•\t*")
            if chunk:
                result.append(chunk)
        return result

    # ── Rule-based parser with diagnostics ────────────────────────────────────

    def _rule_based(self, text: str) -> List[Dict[str, Any]]:
        constraints: List[Dict[str, Any]] = []
        faculty_names = self.context.get("faculty_names", [])
        subject_names = self.context.get("subject_names", [])
        class_names = self.context.get("class_names", [])
        active_class: Optional[str] = None
        active_day: Optional[str] = None

        for chunk in self._split_text(text):
            produced = False
            produced_by_header = False
            produced_specific = False
            lower = chunk.lower()

            faculty = self._context_match(chunk, faculty_names)
            subjects = self._context_matches(chunk, subject_names)
            subject = (
                subjects[0] if subjects else self._context_match(chunk, subject_names)
            )

            # Only match a class if the chunk doesn't already match a subject
            # (prevents "Physics" from accidentally matching "CSE-A" via a partial word)
            cls = self._context_match(chunk, class_names) if not subject else None

            header_class = self._class_from_header(chunk, class_names)
            if header_class:
                active_class = header_class
                produced = True
                produced_by_header = True
            elif re.fullmatch(
                r"[A-Za-z0-9\s-]+class(?:\s+slots?)?",
                chunk.strip(),
                flags=re.IGNORECASE,
            ):
                produced = True
                produced_by_header = True

            chunk_days = self._parse_day_names(chunk)
            if (
                chunk_days
                and not subject
                and not faculty
                and not self._parse_period_numbers(chunk)
            ):
                active_day = chunk_days[0]
                produced = True
            elif chunk_days:
                active_day = chunk_days[0]

            UNAVAIL_PHRASES = [
                "not available",
                "unavailable",
                "cannot teach",
                "can't teach",
                "cant teach",
                "will not teach",
                "wont teach",
                "won't teach",
                "not come",
                "absent",
                "on leave",
                "not teaching",
                "cannot come",
                "can't come",
                "cant come",
                "avoid faculty",
                "no faculty",
                "not free",
            ]

            # ── 1. faculty_availability ─────────────────────────────────────
            AVAIL_PHRASES = [
                "only available",
                "available only",
                "available on",
                "available in",
                "can teach on",
                "can come on",
                "free on",
                "free in",
                "teaches on",
                "will teach on",
                "comes on",
            ]
            if (
                faculty
                and self._contains_any(lower, AVAIL_PHRASES)
                and not self._contains_any(lower, UNAVAIL_PHRASES)
            ):
                days = chunk_days
                if days:
                    constraints.append(
                        {
                            "type": "faculty_availability",
                            "faculty_name": faculty,
                            "available_days": days,
                        }
                    )
                    produced = True

            # ── 2. faculty_unavailability ───────────────────────────────────
            if faculty and any(p in lower for p in UNAVAIL_PHRASES):
                time_matches = list(
                    re.finditer(
                        r"(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\s*(?:to|-)\s*(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)",
                        lower,
                    )
                )
                if time_matches:
                    for tm in time_matches:
                        start_time, end_time = self._normalize_time_range(
                            tm.group(1), tm.group(2)
                        )
                        if start_time and end_time:
                            constraints.append(
                                {
                                    "type": "faculty_time_unavailability",
                                    "faculty_name": faculty,
                                    "start_time": start_time,
                                    "end_time": end_time,
                                }
                            )
                            produced = True
                else:
                    days = chunk_days
                    if days:
                        constraints.append(
                            {
                                "type": "faculty_unavailability",
                                "faculty_name": faculty,
                                "unavailable_days": days,
                            }
                        )
                        produced = True

            # ── 3. consecutive_periods ──────────────────────────────────────
            CONSEC_PHRASES = [
                "consecutive",
                "continuous",
                "back to back",
                "back-to-back",
                "together",
            ]
            if any(p in lower for p in CONSEC_PHRASES) or (
                "lab" in lower and "same day" in lower
            ):
                sub_type = "lab" if "lab" in lower else (subject or "lab")
                if isinstance(sub_type, str):
                    constraints.append(
                        {"type": "consecutive_periods", "subject_type": sub_type}
                    )
                    produced = True

            # ── 4. subject_max_per_day ──────────────────────────────────────
            MAX_PHRASES = [
                "not more than once",
                "only once",
                "once a day",
                "one time per day",
                "at most once",
                "maximum once",
                "not more than one",
                "no more than once",
                "once daily",
                "single period per day",
            ]
            if subject and any(p in lower for p in MAX_PHRASES):
                constraints.append(
                    {
                        "type": "subject_max_per_day",
                        "subject_name": subject,
                        "max_per_day": 1,
                    }
                )
                produced = True

            # "max N times per day"
            max_n = re.search(
                r"(?:max|maximum|at most|not more than|no more than|limit)\s+"
                r"(\d+|one|once|two|twice|three|four|five|six|seven|eight|nine|ten)\s+"
                r"(?:time|times|period|periods|class|classes|hour|hours)",
                lower,
            )
            if subject and max_n:
                constraints.append(
                    {
                        "type": "subject_max_per_day",
                        "subject_name": subject,
                        "max_per_day": self._parse_count(max_n.group(1)),
                    }
                )
                produced = True

            # ── 5. preferred_time_slot ──────────────────────────────────────
            PREF_MAP = {
                "morning": ["morning", "early morning", "before lunch", "first half"],
                "afternoon": ["afternoon", "after lunch", "post lunch", "second half"],
                "first_half": ["first half"],
                "second_half": ["second half"],
            }
            PREF_TRIGGERS = [
                "prefer",
                "preferred",
                "preference",
                "should be",
                "must be",
                "keep",
                "place",
                "schedule",
                "assign",
                "better in",
                "need in",
            ]
            for pref, kws in PREF_MAP.items():
                if any(kw in lower for kw in kws) and (
                    self._contains_any(lower, PREF_TRIGGERS)
                    or not self._parse_period_numbers(chunk)
                ):
                    if subject:
                        class_name = self._target_class_name(active_class, cls, subject)
                        constraints.append(
                            self._add_class_name(
                                {
                                    "type": "preferred_time_slot",
                                    "target": subject,
                                    "target_type": "subject",
                                    "preference": pref,
                                },
                                class_name,
                            )
                        )
                        produced = True
                    elif cls:
                        constraints.append(
                            {
                                "type": "preferred_time_slot",
                                "target": cls,
                                "target_type": "class",
                                "preference": pref,
                            }
                        )
                        produced = True
                    elif "lab" in lower:
                        constraints.append(
                            {
                                "type": "preferred_time_slot",
                                "target": "lab",
                                "target_type": "subject",
                                "preference": pref,
                            }
                        )
                        produced = True
                    break

            # ── 6. avoid_time_slot ──────────────────────────────────────────
            AVOID_PHRASES = [
                "avoid",
                "not in period",
                "should not",
                "don't schedule",
                "do not schedule",
                "no class at",
                "block period",
                "not at period",
                "not be in period",
                "not be on period",
                "shouldn't be",
                "dont schedule",
                "keep away from",
                "exclude period",
            ]
            periods = self._parse_period_numbers(chunk)
            if not periods and self._contains_any(lower, AVOID_PHRASES):
                periods = self._parse_bare_period_numbers(chunk)
            if periods and any(p in lower for p in AVOID_PHRASES):
                target = cls or subject
                t_type = "class" if cls else ("subject" if subject else None)
                if target and t_type:
                    class_name = self._target_class_name(active_class, cls, subject)
                    constraints.append(
                        self._add_class_name(
                            {
                                "type": "avoid_time_slot",
                                "target": target,
                                "target_type": t_type,
                                "periods": periods,
                            },
                            class_name if t_type == "subject" else None,
                        )
                    )
                    produced = True

            # ── 7. class_gap ────────────────────────────────────────────────
            GAP_KWS = [
                "gap",
                "free period",
                "break between",
                "free slot",
                "rest",
                "interval",
            ]
            gap_m = re.search(
                r"(\d+|one|single|two|three|four|five)\s*"
                r"(?:period|periods|slot|slots|free|hour|hours|gap|gaps)",
                lower,
            )
            gap_class = cls or active_class
            if gap_class and any(k in lower for k in GAP_KWS) and gap_m:
                constraints.append(
                    {
                        "type": "class_gap",
                        "class_name": gap_class,
                        "min_gap": self._parse_count(gap_m.group(1)),
                    }
                )
                produced = True

            # ── 8. specific_time_slot ───────────────────────────────────────
            SPECIFIC_KWS = [
                "schedule on",
                "place on",
                "fix on",
                "must be on",
                "assign to period",
                "keep on",
                "should be on",
                "exactly on",
                "fixed on",
                "locked on",
            ]
            if any(k in lower for k in SPECIFIC_KWS) and periods:
                days = chunk_days or ([active_day] if active_day else [])
                if len(subjects) >= 2:
                    added_specific = self._append_specific_any_slot_constraints(
                        constraints,
                        subjects,
                        periods,
                        days,
                        active_class,
                        hard=True,
                    )
                    produced = added_specific or produced
                    produced_specific = added_specific or produced_specific
                elif subject:
                    added_specific = self._append_specific_slot_constraints(
                        constraints,
                        subject,
                        periods,
                        days,
                        active_class,
                        hard=True,
                    )
                    produced = added_specific or produced
                    produced_specific = added_specific or produced_specific
                elif cls:
                    for period in periods:
                        c: Dict[str, Any] = {
                            "type": "specific_time_slot",
                            "target": cls,
                            "target_type": "class",
                            "period": period,
                        }
                        if days:
                            c["day"] = days[0]
                        constraints.append(c)
                        produced = True
                        produced_specific = True

            # Compact fixed-slot style:
            # "Mlops monday 4 and 5", "Wednesday 8,9 Mlops", "Friday FCV 3,8,9"
            if subject and not produced_specific:
                slot_subject = (
                    self._lab_subject_for_line(chunk, subject, subject_names) or subject
                )
                day_period_groups = self._parse_day_period_groups(chunk)
                if not day_period_groups and active_day:
                    day_period_groups = [(active_day, [])]

                compact_chunk = chunk
                if produced_by_header:
                    compact_chunk = re.sub(
                        r"\bfor\s+.+?\s+class\b", "", compact_chunk, flags=re.IGNORECASE
                    )

                if day_period_groups:
                    added_any_group = False
                    for group_day, group_periods in day_period_groups:
                        terse_periods = group_periods
                        if not terse_periods:
                            raw_periods = (
                                self._parse_bare_period_numbers_with_duplicates(
                                    compact_chunk
                                )
                            )
                            terse_periods = self._repair_duplicate_lab_periods(
                                raw_periods, subject
                            )
                        if not terse_periods:
                            continue
                        if len(subjects) >= 2:
                            added_specific = self._append_specific_any_slot_constraints(
                                constraints,
                                subjects,
                                terse_periods,
                                [group_day],
                                active_class,
                                hard=True,
                            )
                        else:
                            added_specific = self._append_specific_slot_constraints(
                                constraints,
                                slot_subject,
                                terse_periods,
                                [group_day],
                                active_class,
                                hard=True,
                            )
                        added_any_group = added_specific or added_any_group
                    produced = added_any_group or produced or produced_by_header
                else:
                    days = chunk_days or ([active_day] if active_day else [])
                    if periods:
                        terse_periods = periods
                    else:
                        raw_periods = self._parse_bare_period_numbers_with_duplicates(
                            compact_chunk
                        )
                        terse_periods = self._repair_duplicate_lab_periods(
                            raw_periods, subject
                        )
                    if days and terse_periods:
                        if len(subjects) >= 2:
                            added_specific = self._append_specific_any_slot_constraints(
                                constraints,
                                subjects,
                                terse_periods,
                                days,
                                active_class,
                                hard=True,
                            )
                        else:
                            added_specific = self._append_specific_slot_constraints(
                                constraints,
                                slot_subject,
                                terse_periods,
                                days,
                                active_class,
                                hard=True,
                            )
                        produced = added_specific or produced or produced_by_header

            # Track unrecognized
            if not produced and len(chunk.split()) > 2:
                self._unrecognized.append(chunk)

        return self._normalize(constraints)

    # ── Normalisation ──────────────────────────────────────────────────────────

    def _normalize(self, constraints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for c in constraints:
            if not isinstance(c, dict):
                continue
            t = str(c.get("type", "")).lower().replace(" ", "_")

            if t in {"faculty_availability", "availability"}:
                name = c.get("faculty_name") or c.get("faculty") or c.get("name")
                days = self._parse_day_names(
                    c.get("available_days") or c.get("days") or []
                )
                if name and days:
                    out.append(
                        {
                            "type": "faculty_availability",
                            "faculty_name": str(name),
                            "available_days": days,
                        }
                    )

            elif t in {
                "faculty_unavailability",
                "unavailability",
                "unavailable",
                "not_available",
            }:
                name = c.get("faculty_name") or c.get("faculty") or c.get("name")
                unavail = self._parse_day_names(
                    c.get("unavailable_days")
                    or c.get("not_available_days")
                    or c.get("days")
                    or []
                )
                avail = [d for d in self.ALL_DAYS if d not in unavail]
                if name and unavail:
                    # Store as faculty_availability with the complement days
                    out.append(
                        {
                            "type": "faculty_availability",
                            "faculty_name": str(name),
                            "available_days": avail,
                        }
                    )

            elif t in {
                "faculty_time_unavailability",
                "time_unavailability",
                "faculty_time",
            }:
                name = c.get("faculty_name") or c.get("faculty") or c.get("name")
                start = c.get("start_time") or c.get("start")
                end = c.get("end_time") or c.get("end")
                if name and start and end:
                    start_norm, end_norm = self._normalize_time_range(start, end)
                    if start_norm and end_norm:
                        out.append(
                            {
                                "type": "faculty_time_unavailability",
                                "faculty_name": str(name),
                                "start_time": start_norm,
                                "end_time": end_norm,
                            }
                        )

            elif t in {"consecutive_periods", "consecutive", "continuous"}:
                st = c.get("subject_type") or c.get("subject") or "lab"
                out.append(
                    {"type": "consecutive_periods", "subject_type": str(st).lower()}
                )

            elif t in {"subject_max_per_day", "max_per_day", "daily_limit"}:
                sn = c.get("subject_name") or c.get("subject") or ""
                mp = c.get("max_per_day") or c.get("max") or 1
                try:
                    mp = int(mp)
                except (TypeError, ValueError):
                    mp = 1
                if sn:
                    out.append(
                        {
                            "type": "subject_max_per_day",
                            "subject_name": str(sn),
                            "max_per_day": mp,
                        }
                    )

            elif t in {"preferred_time_slot", "preferred_slot", "time_preference"}:
                target = (
                    c.get("target")
                    or c.get("subject_name")
                    or c.get("class_name")
                    or ""
                )
                t_type = c.get("target_type") or (
                    "class" if c.get("class_name") else "subject"
                )
                pref = str(c.get("preference") or "morning").lower()
                if pref not in {"morning", "afternoon", "first_half", "second_half"}:
                    pref = "morning"
                if target:
                    nc: Dict[str, Any] = {
                        "type": "preferred_time_slot",
                        "target": str(target),
                        "target_type": str(t_type),
                        "preference": pref,
                    }
                    if c.get("soft") is not None:
                        nc["soft"] = bool(c["soft"])
                    if c.get("class_name"):
                        nc["class_name"] = str(c["class_name"])
                    out.append(nc)

            elif t in {"avoid_time_slot", "blocked_periods", "avoid_periods"}:
                target = (
                    c.get("target")
                    or c.get("class_name")
                    or c.get("subject_name")
                    or ""
                )
                t_type = c.get("target_type") or "class"
                periods = c.get("periods") or c.get("blocked_periods") or []
                if isinstance(periods, int):
                    periods = [periods]
                try:
                    periods = [int(p) for p in periods]
                except (TypeError, ValueError):
                    periods = []
                if target and periods:
                    nc3 = {
                        "type": "avoid_time_slot",
                        "target": str(target),
                        "target_type": str(t_type),
                        "periods": periods,
                    }
                    if c.get("class_name"):
                        nc3["class_name"] = str(c["class_name"])
                    out.append(nc3)

            elif t in {"class_gap", "gap", "free_period"}:
                cn = c.get("class_name") or c.get("class") or ""
                mg = c.get("min_gap") or c.get("gap") or 1
                try:
                    mg = int(mg)
                except (TypeError, ValueError):
                    mg = 1
                if cn:
                    out.append(
                        {"type": "class_gap", "class_name": str(cn), "min_gap": mg}
                    )

            elif t in {"specific_time_slot", "exact_time_slot", "specific_slot"}:
                target = (
                    c.get("target")
                    or c.get("subject_name")
                    or c.get("class_name")
                    or ""
                )
                t_type = c.get("target_type") or "subject"
                dv = c.get("day") or c.get("day_name")
                day = self._single_day(dv) if dv else None
                period = c.get("period") or c.get("period_number")
                try:
                    period = int(period) if period is not None else None
                except (TypeError, ValueError):
                    period = None
                if target and period is not None:
                    nc2: Dict[str, Any] = {
                        "type": "specific_time_slot",
                        "target": str(target),
                        "target_type": str(t_type),
                        "period": period,
                    }
                    if day:
                        nc2["day"] = day
                    if c.get("class_name"):
                        nc2["class_name"] = str(c["class_name"])
                    if c.get("hard") is not None:
                        nc2["hard"] = bool(c["hard"])
                    if c.get("strict") is not None:
                        nc2["strict"] = bool(c["strict"])
                    if c.get("soft") is not None:
                        nc2["soft"] = bool(c["soft"])
                    out.append(nc2)
            elif t in {
                "specific_time_slot_any",
                "exact_time_slot_any",
                "specific_slot_any",
            }:
                targets = c.get("targets") or c.get("target_names") or []
                if isinstance(targets, str):
                    targets = [
                        target.strip()
                        for target in re.split(r"\s*/\s*|,\s*", targets)
                        if target.strip()
                    ]
                t_type = c.get("target_type") or "subject"
                dv = c.get("day") or c.get("day_name")
                day = self._single_day(dv) if dv else None
                period = c.get("period") or c.get("period_number")
                try:
                    period = int(period) if period is not None else None
                except (TypeError, ValueError):
                    period = None
                targets = [str(target) for target in targets if target]
                if len(targets) >= 2 and period is not None:
                    nc_any: Dict[str, Any] = {
                        "type": "specific_time_slot_any",
                        "targets": targets,
                        "target_type": str(t_type),
                        "period": period,
                    }
                    if day:
                        nc_any["day"] = day
                    if c.get("class_name"):
                        nc_any["class_name"] = str(c["class_name"])
                    if c.get("hard") is not None:
                        nc_any["hard"] = bool(c["hard"])
                    if c.get("strict") is not None:
                        nc_any["strict"] = bool(c["strict"])
                    if c.get("soft") is not None:
                        nc_any["soft"] = bool(c["soft"])
                    out.append(nc_any)
            else:
                out.append(c)
        return out

    # ── Merge (deduplicate + combine overlapping) ──────────────────────────────

    @staticmethod
    def _merge(primary: List[Dict], supplemental: List[Dict]) -> List[Dict]:
        merged: List[Dict] = []
        by_id: Dict[str, Dict] = {}

        for c in primary + supplemental:
            ct = c.get("type")
            ident = None
            if ct == "faculty_availability":
                ident = f"fa::{c.get('faculty_name','').lower()}"
            elif ct == "avoid_time_slot":
                ident = f"av::{c.get('target_type','').lower()}::{c.get('target','').lower()}"

            if ident and ident in by_id:
                ex = by_id[ident]
                if ct == "faculty_availability":
                    ex["available_days"] = sorted(
                        set(ex.get("available_days", []))
                        | set(c.get("available_days", [])),
                        key=lambda d: (
                            AIConstraintParser.ALL_DAYS.index(d)
                            if d in AIConstraintParser.ALL_DAYS
                            else 99
                        ),
                    )
                elif ct == "avoid_time_slot":
                    ex["periods"] = sorted(
                        set(ex.get("periods", [])) | set(c.get("periods", []))
                    )
                continue

            key = json.dumps(c, sort_keys=True)
            if any(json.dumps(m, sort_keys=True) == key for m in merged):
                continue
            merged.append(c)
            if ident:
                by_id[ident] = c

        return merged

    @staticmethod
    def _filter_ai_duplicates(
        ai_constraints: List[Dict], rule_constraints: List[Dict]
    ) -> List[Dict]:
        """
        Rule parsing understands compact fixed-slot tables better than the LLM.
        Drop broad AI duplicates for day/period pairs already covered by a
        class-specific deterministic fixed slot, otherwise the scheduler reports
        false "not found" and "preference not met" warnings.
        """
        fixed_pairs = {
            (c.get("day"), c.get("period"))
            for c in rule_constraints
            if c.get("type") in {"specific_time_slot", "specific_time_slot_any"}
            and c.get("class_name")
            and c.get("day")
            and c.get("period") is not None
        }
        if not fixed_pairs:
            return ai_constraints

        filtered = []
        for c in ai_constraints:
            if (
                c.get("type")
                in {
                    "specific_time_slot",
                    "specific_time_slot_any",
                    "preferred_time_slot",
                }
                and (c.get("day"), c.get("period")) in fixed_pairs
            ):
                continue
            filtered.append(c)
        return filtered
