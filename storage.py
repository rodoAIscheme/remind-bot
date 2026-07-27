"""JSONドキュメントの永続化レイヤー。

DATABASE_URL があれば Postgres、無ければローカルの JSON ファイルに保存する。
Railway ではコンテナのファイルシステムが揮発性のため、Postgres が必須。
"""
import json
import os
import threading

DATABASE_URL = os.getenv("DATABASE_URL")

_LOCAL_DIR = os.path.join(os.path.dirname(__file__), "data")
_lock = threading.Lock()
_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool

        # Railway の DATABASE_URL は postgres:// 形式で来ることがある
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        _pool = ConnectionPool(url, min_size=1, max_size=3, kwargs={"autocommit": True})
        with _pool.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS documents ("
                "  key TEXT PRIMARY KEY,"
                "  value JSONB NOT NULL,"
                "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
    return _pool


def _local_path(key: str) -> str:
    return os.path.join(_LOCAL_DIR, f"{key}.json")


def load(key: str, default):
    """key に保存された JSON を返す。無ければ default。"""
    if not DATABASE_URL:
        path = _local_path(key)
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    with _get_pool().connection() as conn:
        row = conn.execute(
            "SELECT value FROM documents WHERE key = %s", (key,)
        ).fetchone()
    return default if row is None else row[0]


def save(key: str, value) -> None:
    """key に JSON を保存する（全体置き換え）。"""
    if not DATABASE_URL:
        os.makedirs(_LOCAL_DIR, exist_ok=True)
        with _lock, open(_local_path(key), "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        return

    with _get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO documents (key, value, updated_at)"
            " VALUES (%s, %s, now())"
            " ON CONFLICT (key) DO UPDATE"
            " SET value = EXCLUDED.value, updated_at = now()",
            (key, json.dumps(value, ensure_ascii=False)),
        )
