import os
from pymongo import MongoClient
import ssl
from dotenv import load_dotenv
import logging
import sys

# Try to find .env in current dir or backend/
load_dotenv('.env')
load_dotenv('backend/.env')
load_dotenv('../backend/.env')

mongo_url = os.getenv("MONGODB_URL")
db_name = os.getenv("DB_NAME")

print(f"Cluster URL: {mongo_url.split('@')[-1]}")
print(f"Database: {db_name}")

try:
    print("\n[Attempt 1] Standard connection...")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    client.admin.command('ping')
    print("✅ Standard connection successful!")
except Exception as e:
    print(f"❌ Standard connection failed: {e}")
    
    try:
        print("\n[Attempt 2] Connection with disabled certificate verification...")
        client = MongoClient(mongo_url, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=10000)
        client.admin.command('ping')
        print("✅ Connection with disabled certificate verification successful!")
    except Exception as e2:
        print(f"❌ Verification-disabled connection also failed: {e2}")

        try:
             # Try forcing TLS 1.2
             print("\n[Attempt 3] Forcing TLS context...")
             import ssl
             context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
             context.check_hostname = False
             context.verify_mode = ssl.CERT_NONE
             client = MongoClient(mongo_url, ssl_context=context, serverSelectionTimeoutMS=10000)
             client.admin.command('ping')
             print("✅ Forcing TLS context successful!")
        except Exception as e3:
             print(f"❌ Forcing TLS context failed: {e3}")
