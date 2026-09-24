import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.database.database import get_client


def main() -> None:
    client = get_client()
    db = client[settings.DB_NAME]
    collections = [name for name in db.list_collection_names() if not name.startswith("system.")]

    print(f"Deleting all data from database: {settings.DB_NAME}")
    if not collections:
        print("No collections found.")
        return

    total_deleted = 0
    for collection_name in sorted(collections):
        result = db[collection_name].delete_many({})
        total_deleted += result.deleted_count
        print(f"{collection_name}: deleted {result.deleted_count} documents")

    print(f"Done. Deleted {total_deleted} documents from {len(collections)} collections.")


if __name__ == "__main__":
    main()
