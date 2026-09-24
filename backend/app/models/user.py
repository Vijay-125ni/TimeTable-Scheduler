from datetime import datetime


def user_helper(doc: dict) -> dict:
    """Convert a MongoDB user document to a plain dict with string id."""
    return {
        "id": str(doc["_id"]),
        "username": doc.get("username", ""),
        "email": doc.get("email", ""),
        "full_name": doc.get("full_name"),
        "role": doc.get("role", "faculty"),
        "tenant_db_name": doc.get("tenant_db_name"),
        "tenant_id": str(doc.get("tenant_id")) if doc.get("tenant_id") else None,
        "is_active": doc.get("is_active", True),
        "is_admin": doc.get("is_admin", False),
        "hashed_password": doc.get("hashed_password", ""),
        "created_at": doc.get("created_at", datetime.utcnow()),
        "updated_at": doc.get("updated_at"),
    }
