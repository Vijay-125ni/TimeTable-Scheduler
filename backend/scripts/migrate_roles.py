from app.database.database import get_client
from app.core.config import settings
import os

def update_user_roles():
    print("Updating user roles in database...")
    client = get_client()
    db = client[settings.DB_NAME]
    users_collection = db["users"]
    
    # Set role: admin for all is_admin: True
    res1 = users_collection.update_many(
        {"is_admin": True, "role": {"$exists": False}},
        {"$set": {"role": "admin"}}
    )
    print(f"Updated {res1.modified_count} admins to have role='admin'")
    
    # Set role: faculty for all is_admin: False
    res2 = users_collection.update_many(
        {"is_admin": False, "role": {"$exists": False}},
        {"$set": {"role": "faculty"}}
    )
    print(f"Updated {res2.modified_count} faculty to have role='faculty'")
    
    # Ensure all users have a role
    res3 = users_collection.update_many(
        {"role": {"$exists": False}},
        {"$set": {"role": "faculty"}}
    )
    print(f"Set default role='faculty' for {res3.modified_count} users")
    
    print("✓ User roles update complete!")

if __name__ == "__main__":
    update_user_roles()
