import logging

from pymongo import MongoClient
from pymongo.database import Database

from ..core.config import settings

logger = logging.getLogger(__name__)

# Module-level client — created once at import time
_client: MongoClient = None
_connection_ready: bool = False


def get_client() -> MongoClient:
    """Get or create MongoDB client with fallback logic."""
    global _client, _connection_ready

    if _client is not None:
        return _client

    # Try MongoDB Atlas, unless local MongoDB is explicitly enabled in .env.
    try:
        conn_args = {
            "serverSelectionTimeoutMS": 10000,
            "connectTimeoutMS": 10000,
            "socketTimeoutMS": 10000,
            "retryWrites": True,
            "maxPoolSize": 10,
        }

        _client = MongoClient(settings.active_mongodb_url, **conn_args)
        _client.admin.command("ping")
        _connection_ready = True
        logger.info("[SUCCESS] Successfully connected to MongoDB!")
        return _client
    except Exception as e:
        logger.warning(f"[WARNING] Primary MongoDB connection failed: {str(e)[:200]}")
        try:
            # Try once more with SSL verification disabled
            logger.info("Retrying MongoDB with SSL verification disabled...")
            _client = MongoClient(
                settings.active_mongodb_url,
                tlsAllowInvalidCertificates=True,
                **conn_args,
            )
            _client.admin.command("ping")
            _connection_ready = True
            logger.info("[SUCCESS] Connected to MongoDB (SSL Safety Disabled)")
            return _client
        except Exception as e2:
            logger.error(f"[ERROR] Failed to reach primary MongoDB: {str(e2)[:200]}")

        # Fallback to local MongoDB
        try:
            _client = MongoClient(
                "mongodb://localhost:27017", serverSelectionTimeoutMS=3000
            )
            _client.admin.command("ping")
            _connection_ready = True
            logger.info("[SUCCESS] Connected to Local MongoDB")
            return _client
        except Exception as e3:
            logger.error(f"[ERROR] All MongoDB connections failed: {str(e3)[:200]}")
            _client = MongoClient("mongodb://localhost:27017")
            return _client


import pymongo


def _ensure_sparse_index(collection, field_name: str):
    try:
        index_name = f"{field_name}_1"
        try:
            info = collection.index_information()
            if index_name in info and not info[index_name].get("sparse"):
                collection.drop_index(index_name)
        except Exception:
            pass
        collection.create_index(field_name, unique=True, sparse=True)
    except Exception:
        pass


def init_indexes(db: Database):
    """Ensure essential indexes are created for performance and data integrity."""
    try:
        db["users"].create_index("username", unique=True)
        _ensure_sparse_index(db["users"], "email")
        _ensure_sparse_index(db["departments"], "code")
        _ensure_sparse_index(db["subjects"], "code")
        _ensure_sparse_index(db["faculty"], "email")
        db["ingestion_review_sessions"].create_index("session_id", unique=True)
        db["ingestion_history"].create_index("session_id", unique=True)
        db["audit_logs"].create_index([("upload_session_id", pymongo.ASCENDING)])
        db["ingestion_alias_rules"].create_index(
            [("original", pymongo.ASCENDING), ("entity_type", pymongo.ASCENDING)],
            unique=True,
        )
        logger.info("[SUCCESS] MongoDB indexes initialized")
    except Exception as e:
        logger.debug(f"Index initialization note: {e}")


def get_db() -> Database:
    """FastAPI dependency that yields the MongoDB database object."""
    client = get_client()
    db = client[settings.DB_NAME]
    try:
        yield db
    finally:
        pass  # PyMongo connections are pooled; no per-request close needed

def initialize_tenant_db(tenant_db_name: str):
    """Create a new tenant database with empty collections matching the app schema.
    
    MongoDB only materializes a database when data is written to it.
    We explicitly create_collection() for each expected collection so the
    database appears immediately and the tenant starts with the correct schema.
    """
    client = get_client()
    tenant_db = client[tenant_db_name]
    
    # All collections used by the timetable endpoints
    collections = [
        "batches",
        "departments",
        "rooms",
        "classes",
        "subjects",
        "faculty",
        "timetables",
    ]
    
    existing = set(tenant_db.list_collection_names())
    for col_name in collections:
        if col_name not in existing:
            tenant_db.create_collection(col_name)
    
    logger.info(f"[SUCCESS] Initialized tenant database: {tenant_db_name} with collections: {collections}")

def close_mongo_connection():
    """Close the MongoDB connection."""
    global _client, _connection_ready
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None
        _connection_ready = False
