from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr


class DepartmentBase(BaseModel):
    name: str
    code: Optional[str] = ""


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None


class DepartmentResponse(DepartmentBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class BatchBase(BaseModel):
    name: str
    start_time: str
    end_time: str
    period_duration: int = 60
    break_times: List[Dict[str, str]] = []
    lunch_break: Dict[str, str] = {}


class BatchCreate(BatchBase):
    pass


class BatchUpdate(BaseModel):
    name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    period_duration: Optional[int] = None
    break_times: Optional[List[Dict[str, str]]] = None
    lunch_break: Optional[Dict[str, str]] = None


class BatchResponse(BatchBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ClassBase(BaseModel):
    name: str
    section: Optional[str] = None
    semester: Optional[int] = None
    student_count: Optional[int] = None
    department_id: Optional[str] = None
    batch_id: Optional[str] = None
    room_id: Optional[str] = None


class ClassCreate(ClassBase):
    pass


class ClassUpdate(BaseModel):
    name: Optional[str] = None
    section: Optional[str] = None
    semester: Optional[int] = None
    student_count: Optional[int] = None
    department_id: Optional[str] = None
    batch_id: Optional[str] = None
    room_id: Optional[str] = None


class ClassResponse(ClassBase):
    id: str
    created_at: datetime
    department: Optional[DepartmentResponse] = None
    batch: Optional[BatchResponse] = None

    class Config:
        from_attributes = True


class RoomBase(BaseModel):
    name: str
    code: Optional[str] = None
    capacity: Optional[int] = None
    room_type: str = "lecture"
    department_id: Optional[str] = None


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    capacity: Optional[int] = None
    room_type: Optional[str] = None
    department_id: Optional[str] = None


class RoomResponse(RoomBase):
    id: str
    created_at: datetime
    department: Optional[DepartmentResponse] = None

    class Config:
        from_attributes = True


class SubjectBase(BaseModel):
    name: str
    code: Optional[str] = ""
    hours_per_week: Optional[int] = None
    credits: int = 3
    requires_lab: bool = False
    department_id: Optional[str] = None
    department_ids: Optional[List[str]] = None
    batch_id: Optional[str] = None
    class_id: Optional[str] = None
    faculty_id: Optional[str] = None
    source_subject_id: Optional[str] = None


class SubjectCreate(SubjectBase):
    pass


class SubjectMapRequest(BaseModel):
    class_id: str
    faculty_id: str
    room_id: Optional[str] = None


class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    hours_per_week: Optional[int] = None
    credits: Optional[int] = None
    requires_lab: Optional[bool] = None
    required_lab: Optional[bool] = None
    department_id: Optional[str] = None
    department_ids: Optional[List[str]] = None
    batch_id: Optional[str] = None
    class_id: Optional[str] = None
    faculty_id: Optional[str] = None
    source_subject_id: Optional[str] = None


class SubjectResponse(SubjectBase):
    id: str
    created_at: datetime
    assigned_class: Optional[ClassResponse] = None

    class Config:
        from_attributes = True


class FacultyBase(BaseModel):
    name: str
    email: Optional[str] = ""
    department_id: Optional[str] = None
    max_hours_per_week: int = 20
    unavailable_slots: List[Dict[str, Any]] = []


class FacultyCreate(FacultyBase):
    pass


class FacultyUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    department_id: Optional[str] = None
    max_hours_per_week: Optional[int] = None
    unavailable_slots: Optional[List[Dict[str, Any]]] = None


class FacultyResponse(FacultyBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class TimetableGenerateRequest(BaseModel):
    name: str
    academic_year: str
    semester: int
    department_ids: Optional[List[str]] = None
    batch_ids: Optional[List[str]] = None
    class_ids: Optional[List[str]] = None
    faculty_ids: Optional[List[str]] = None
    working_days: List[str] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    periods_per_day: int = 7
    start_time: str = "09:00"
    end_time: Optional[str] = None
    period_duration_mins: int = 60
    break_after_period: Optional[int] = None
    break_duration_mins: int = 15
    lunch_after_period: Optional[int] = None
    lunch_duration_mins: int = 60
    break2_after_period: Optional[int] = None
    break2_duration_mins: int = 15
    break_times: Optional[List[Dict[str, str]]] = None
    constraints_text: Optional[str] = None


class TimetableResponse(BaseModel):
    id: str
    name: str
    academic_year: str
    semester: int
    schedule_data: Dict[str, Any]
    constraints_used: Dict[str, Any]
    solver_status: str
    solve_time_seconds: float
    created_at: datetime

    class Config:
        from_attributes = True
