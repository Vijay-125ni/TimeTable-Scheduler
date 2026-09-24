import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')
load_dotenv('backend/.env')
load_dotenv('../backend/.env')

mongo_url = os.getenv("MONGODB_URL")
db_name = os.getenv("DB_NAME")

print("=" * 60)
print("🔍 DATABASE CONNECTION & STATUS CHECK")
print("=" * 60)
print(f"Configured MONGODB_URL: {mongo_url}")
print(f"Configured DB_NAME: {db_name}")
print("-" * 60)

if not mongo_url:
    print("❌ ERROR: MONGODB_URL not found in environment. Check backend/.env.")
    sys.exit(1)

try:
    print("Connecting to MongoDB cluster...")
    # Attempt standard connection with a timeout
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    # Ping database
    client.admin.command('ping')
    print("✅ Successfully connected to MongoDB!")
except Exception as e:
    print(f"⚠️ Standard connection failed: {e}")
    try:
        print("\nRetrying with SSL verification disabled...")
        client = MongoClient(mongo_url, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        print("✅ Successfully connected to MongoDB (SSL verification disabled)!")
    except Exception as e2:
        print(f"❌ Connection failed: {e2}")
        print("\nFallback: Checking local MongoDB (mongodb://localhost:27017)...")
        try:
            client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
            client.admin.command('ping')
            print("✅ Successfully connected to LOCAL MongoDB!")
            db_name = db_name or "timetable_db"
        except Exception as e3:
            print(f"❌ Local MongoDB also failed: {e3}")
            print("\nCould not establish connection to any database.")
            sys.exit(1)

print("-" * 60)
print("📊 COLLECTION STATUS:")
print("-" * 60)

try:
    db = client[db_name]
    collections = db.list_collection_names()
    print(f"Available Collections in '{db_name}': {collections}")
    
    target_collections = ['users', 'batches', 'departments', 'rooms', 'classes', 'subjects', 'faculty', 'timetables']
    
    for coll_name in target_collections:
        count = db[coll_name].count_documents({})
        print(f"  🔹 {coll_name:<15} : {count} documents")
        
except Exception as e:
    print(f"❌ Error listing collections: {e}")

print("=" * 60)
