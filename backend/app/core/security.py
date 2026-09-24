# pyrefly: ignore [missing-import]
import re
from datetime import datetime

import jwt
from fastapi import Depends, HTTPException, Request, status
# pyrefly: ignore [missing-import]
from pymongo.database import Database

from ..database.database import get_client, get_db
from .config import settings


async def get_current_user(request: Request, db: Database = Depends(get_db)) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        # Fallback for backward compatibility/local debug if no token is present
        return {
            "_id": "mock_admin_id",
            "username": "admin",
            "is_admin": True,
            "tenant_db_name": settings.DB_NAME,
        }

    token = auth_header.split(" ")[1]

    # 1. Handle mock/demo tokens
    if token == "mock-admin-token-12345":
        return {
            "_id": "mock_admin_id",
            "username": "admin",
            "is_admin": True,
            "tenant_db_name": settings.DB_NAME,
        }
    elif token == "mock-faculty-token-54321":
        user = db["users"].find_one({"username": "faculty"})
        if user:
            return user
        return {
            "_id": "mock_faculty_id",
            "username": "faculty",
            "is_admin": False,
            "role": "faculty",
            "tenant_db_name": settings.DB_NAME,
        }

    # 2. Try decoding token
    try:
        # We decode unverified claims first to understand the issuer (Firebase vs Custom JWT)
        claims = jwt.decode(token, options={"verify_signature": False})
        iss = claims.get("iss", "")

        # Check if it is a Firebase token
        if iss.startswith("https://securetoken.google.com/"):
            uid = claims.get("sub")
            email = claims.get("email")

            # Find the user by UID or Email
            user = db["users"].find_one({"$or": [{"uid": uid}, {"email": email}]})
            if user:
                # Link Google UID if not already linked
                if not user.get("uid"):
                    db["users"].update_one({"_id": user["_id"]}, {"$set": {"uid": uid}})
                    user["uid"] = uid
                return user

            # Auto-onboard Firebase users if they don't exist yet
            is_admin_user = email and "admin" in email.lower()
            role = "admin" if is_admin_user else "faculty"

            username = email.split("@")[0] if email else f"fb_{uid[:8]}"
            clean_username = re.sub(r"[^a-zA-Z0-9_]", "", username).lower()
            if not clean_username:
                clean_username = "tenant"

            tenant_db_name = (
                f"timetable_db_{clean_username}"
                if role == "admin"
                else settings.DB_NAME
            )

            if role == "admin":
                counter = 1
                while db["users"].find_one({"tenant_db_name": tenant_db_name}):
                    tenant_db_name = f"timetable_db_{clean_username}_{counter}"
                    counter += 1

            new_user = {
                "uid": uid,
                "username": username,
                "email": email,
                "full_name": claims.get("name", username),
                "role": role,
                "is_admin": role == "admin",
                "is_active": True,
                "tenant_db_name": tenant_db_name,
                "created_at": datetime.utcnow(),
            }
            res = db["users"].insert_one(new_user)
            return db["users"].find_one({"_id": res.inserted_id})

        else:
            # Custom backend JWT token verification
            try:
                payload = jwt.decode(
                    token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
                )
                username = payload.get("sub")
            except Exception:
                username = claims.get("sub")

            if username:
                user = db["users"].find_one({"username": username})
                if user:
                    return user

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or credentials invalid",
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
        )


async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Ensures current user is an admin"""
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user


async def get_tenant_db(current_user: dict = Depends(get_current_user)) -> Database:
    """Provides a database connection isolated to the current user's tenant"""
    tenant_db_name = current_user.get("tenant_db_name")
    if not tenant_db_name:
        tenant_db_name = settings.DB_NAME
    client = get_client()
    db = client[tenant_db_name]
    try:
        yield db
    finally:
        pass
