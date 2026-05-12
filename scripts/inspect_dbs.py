import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATHS = [
    ROOT / "data" / "app.db",
    ROOT / "backend" / "data" / "app.db",
    ROOT / "backend" / "data" / "test_app.db",
]


def inspect(path: Path) -> dict:
    item = {"path": str(path), "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}
    if not path.exists():
        return item
    con = sqlite3.connect(path)
    try:
        tables = [row[0] for row in con.execute("select name from sqlite_master where type='table' order by name")]
        item["tables"] = tables
        if "api_keys" in tables:
            rows = con.execute(
                "select id, exchange, env, label, length(key_encrypted), length(secret_encrypted), created_at "
                "from api_keys order by id"
            ).fetchall()
            item["api_keys"] = [
                {
                    "id": row[0],
                    "exchange": row[1],
                    "env": row[2],
                    "label": row[3],
                    "key_len": row[4],
                    "secret_len": row[5],
                    "created_at": row[6],
                }
                for row in rows
            ]
    finally:
        con.close()
    return item


print(json.dumps([inspect(path) for path in PATHS], ensure_ascii=False, indent=2))
