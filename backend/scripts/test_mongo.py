import os
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

mongo_url = os.getenv("MONGODB_URL")
use_local_mongodb = os.getenv("USE_LOCAL_MONGODB", "false").lower() == "true"
local_mongo_url = os.getenv("LOCAL_MONGODB_URL", "mongodb://localhost:27017")
db_name = os.getenv("DB_NAME", "timetable_db")

if use_local_mongodb:
    mongo_url = local_mongo_url

if not mongo_url:
    raise SystemExit("MONGODB_URL is not set. Add it to backend/.env first.")

def mask_mongo_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if "@" not in parts.netloc:
            return url
        host = parts.netloc.rsplit("@", 1)[1]
        return urlunsplit((parts.scheme, f"***:***@{host}", parts.path, parts.query, parts.fragment))
    except Exception:
        return "<configured MongoDB URL>"

print(f"Testing MongoDB connection: {mask_mongo_url(mongo_url)}")
print(f"Database: {db_name}")

try:
    # Try standard connection
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print("Standard connection successful!")
except Exception as e:
    print(f"Standard connection failed: {e}")
    
    print("\nTrying with SSL certificate verification disabled...")
    try:
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000, tlsAllowInvalidCertificates=True)
        client.admin.command('ping')
        print("Connection successful with tlsAllowInvalidCertificates=True!")
    except Exception as e2:
        print(f"Connection with disabled SSL verification also failed: {e2}")

    print("\nChecking DNS resolution...")
    import socket
    try:
        host = urlsplit(mongo_url).hostname or mongo_url.split('@')[-1].split('/')[0].split('?')[0]
        print(f"Resolving {host}...")
        ip = socket.gethostbyname(host)
        print(f"IP: {ip}")
    except Exception as e3:
        print(f"DNS resolution failed: {e3}")
