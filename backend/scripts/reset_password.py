from app.database.database import get_db
from app.core.security import get_password_hash
from datetime import datetime
import sys

def reset_password():
    try:
        db = next(get_db())
        admin = db["users"].find_one({"username": "admin"})
        if not admin:
            print("Admin user not found! Creating one...")
            admin_user = {
                "username": "admin",
                "email": "admin@timetable.com",
                "full_name": "System Administrator",
                "hashed_password": get_password_hash("admin123"),
                "is_active": True,
                "is_admin": True,
                "created_at": datetime.utcnow()
            }
            db["users"].insert_one(admin_user)
        else:
            print("Updating admin password...")
            db["users"].update_one(
                {"username": "admin"},
                {"$set": {"hashed_password": get_password_hash("admin123"), "updated_at": datetime.utcnow()}}
            )
        
        print("✓ Admin password reset to: admin123")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    reset_password()
