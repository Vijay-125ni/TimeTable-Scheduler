# pyrefly: ignore [missing-import]
import re
from datetime import datetime, timedelta
from typing import List, Optional

import jwt
from bson import ObjectId
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
# pyrefly: ignore [missing-import]
from pymongo.database import Database
from slowapi import Limiter
from slowapi.util import get_remote_address

from ...core.config import settings
from ...core.security import get_admin_user, get_current_user
from ...database.database import get_db
from ...models.user import user_helper
from ...schemas.user import Token, UserResponse

router = APIRouter(redirect_slashes=False)
limiter = Limiter(key_func=get_remote_address)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


# Additional schemas for authentication request bodies
class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: Optional[str] = None
    full_name: Optional[str] = None
    uid: Optional[str] = None  # Firebase UID (if registered via Firebase)
    role: Optional[str] = "admin"


class LoginRequest(BaseModel):
    username: str
    password: str


class FacultyCreateRequest(BaseModel):
    username: str
    full_name: str
    email: EmailStr
    password: str


@router.post("/register", response_model=UserResponse)
def register_user(request: RegisterRequest, db: Database = Depends(get_db)):
    # 1. Check if user already exists (by email or username)
    existing_user = db["users"].find_one(
        {"$or": [{"username": request.username}, {"email": request.email}]}
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered",
        )

    # 2. Sanitize username for database name
    clean_username = re.sub(r"[^a-zA-Z0-9_]", "", request.username).lower()
    if not clean_username:
        clean_username = "tenant"

    # Generate unique tenant DB name
    if request.role == "admin":
        # Check if tenant db name already exists, if so append unique identifier
        tenant_db_name = f"timetable_db_{clean_username}"
        counter = 1
        while db["users"].find_one({"tenant_db_name": tenant_db_name}):
            tenant_db_name = f"timetable_db_{clean_username}_{counter}"
            counter += 1
    else:
        # Default to main DB for normal users if not created by admin
        tenant_db_name = settings.DB_NAME

    # 3. Create user record
    doc = {
        "username": request.username,
        "email": request.email,
        "full_name": request.full_name,
        "role": request.role,
        "is_admin": request.role == "admin",
        "is_active": True,
        "tenant_db_name": tenant_db_name,
        "created_at": datetime.utcnow(),
    }

    if request.password:
        doc["hashed_password"] = hash_password(request.password)
    if request.uid:
        doc["uid"] = request.uid

    result = db["users"].insert_one(doc)
    created_user = db["users"].find_one({"_id": result.inserted_id})
    return user_helper(created_user)


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login_user(
    http_request: Request,
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    request: Optional[LoginRequest] = None,
    db: Database = Depends(get_db),
):
    login_username = username
    login_password = password

    if request:
        if not login_username:
            login_username = request.username
        if not login_password:
            login_password = request.password

    if not login_username or not login_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required",
        )

    # Find user in the central users database
    user = db["users"].find_one(
        {"$or": [{"username": login_username}, {"email": login_username}]}
    )

    if (
        not user
        or "hashed_password" not in user
        or not verify_password(login_password, user["hashed_password"])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # Create token containing username, role, and tenant database name
    access_token = create_access_token(
        data={
            "sub": user["username"],
            "role": user.get("role", "faculty"),
            "tenant_db_name": user.get("tenant_db_name", settings.DB_NAME),
        }
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return user_helper(current_user)


# ── Faculty Account Management (Admins only) ─────────────────────────────────


@router.post("/faculty", response_model=UserResponse)
def create_faculty_account(
    request: FacultyCreateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_admin_user),
):
    # 1. Check if user already exists
    existing_user = db["users"].find_one(
        {"$or": [{"username": request.username}, {"email": request.email}]}
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered",
        )

    # 2. Create faculty account linked to admin's tenant database
    doc = {
        "username": request.username,
        "email": request.email,
        "full_name": request.full_name,
        "role": "faculty",
        "is_admin": False,
        "is_active": True,
        "hashed_password": hash_password(request.password),
        "tenant_db_name": current_user.get("tenant_db_name", settings.DB_NAME),
        "tenant_id": str(current_user.get("_id")),
        "created_at": datetime.utcnow(),
    }

    result = db["users"].insert_one(doc)
    created_user = db["users"].find_one({"_id": result.inserted_id})
    return user_helper(created_user)


@router.get("/faculty", response_model=List[UserResponse])
def list_faculty_accounts(
    db: Database = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    # Retrieve all faculty accounts that share the current user's tenant database
    tenant_db_name = current_user.get("tenant_db_name", settings.DB_NAME)

    # Non-admins can only see faculty accounts in their own tenant, admins see their tenant's faculty
    query = {"role": "faculty", "tenant_db_name": tenant_db_name}

    users = db["users"].find(query)
    return [user_helper(u) for u in users]


@router.delete("/faculty/{id}")
def delete_faculty_account(
    id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_admin_user),
):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid faculty ID format")

    # Admins can only delete faculty accounts belonging to their own tenant database
    tenant_db_name = current_user.get("tenant_db_name", settings.DB_NAME)

    faculty_user = db["users"].find_one(
        {"_id": oid, "role": "faculty", "tenant_db_name": tenant_db_name}
    )
    if not faculty_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faculty account not found or access denied",
        )

    db["users"].delete_one({"_id": oid})
    return {"message": "Faculty account access revoked successfully"}
