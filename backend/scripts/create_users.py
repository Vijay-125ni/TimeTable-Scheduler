from app.database.database import get_db
from app.core.security import get_password_hash
import sys
import datetime

def init_db():
    try:
        db = next(get_db())
        users_collection = db["users"]
        
        # Ensure admin user is created 
        admin = users_collection.find_one({"username": "admin"})
        if not admin:
            print("Creating admin user...")
            admin_user = {
                "username": "admin",
                "email": "admin@timetable.com",
                "full_name": "System Administrator",
                "hashed_password": get_password_hash("admin123"),
                "is_active": True,
                "role": "admin",
                "is_admin": True,
                "created_at": datetime.datetime.utcnow()
            }
            users_collection.insert_one(admin_user)
            print("✓ Admin user created!")
            
        # Ensure Shiva user is created
        shiva = users_collection.find_one({"username": "Shiva"})
        if not shiva:
            print("Creating second admin user Shiva...")
            shiva_user = {
                "username": "Shiva",
                "email": "shiva@timetable.com",
                "full_name": "Shiva Admin",
                "hashed_password": get_password_hash("Shiva123"),
                "is_active": True,
                "role": "admin",
                "is_admin": True,
                "created_at": datetime.datetime.utcnow()
            }
            users_collection.insert_one(shiva_user)
            print("✓ Shiva user created!")
        else:
            print("Shiva user already exists!")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_db()
