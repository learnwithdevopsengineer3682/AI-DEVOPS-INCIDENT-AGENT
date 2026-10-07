import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from psycopg_pool import ConnectionPool, PoolTimeout

DB_HOST = os.getenv("DB_HOST", "taskflow-db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "taskflow")
DB_USER = os.getenv("DB_USER", "taskflow")
DB_PASSWORD = os.getenv("DB_PASSWORD", "taskflow-demo-password")
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "3"))

DATABASE_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=0,
    max_size=DB_POOL_MAX,
    timeout=2,
    open=False,
)

held_connections = []
hold_lock = threading.Lock()


def bootstrap_database():
    try:
        with pool.connection(timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL
                    )
                """)
                cur.execute("SELECT COUNT(*) FROM tasks")
                if cur.fetchone()[0] == 0:
                    cur.execute(
                        "INSERT INTO tasks (title) VALUES (%s), (%s), (%s)",
                        (
                            "Deploy API",
                            "Check production logs",
                            "Verify database connectivity",
                        ),
                    )
                conn.commit()
    except Exception as exc:
        print(f"Startup database bootstrap failed: {exc}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=False)
    bootstrap_database()
    yield

    with hold_lock:
        for conn in held_connections:
            try:
                conn.close()
            except Exception:
                pass
        held_connections.clear()

    pool.close()


app = FastAPI(title="TaskFlow", lifespan=lifespan)


@app.get("/health")
def health():
    # This only proves the API process is alive.
    return {"status": "running"}


@app.get("/tasks")
def tasks():
    try:
        with pool.connection(timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, title FROM tasks ORDER BY id")
                rows = cur.fetchall()

        return {
            "status": "ok",
            "tasks": [{"id": row[0], "title": row[1]} for row in rows],
        }

    except PoolTimeout as exc:
        print(f"ERROR database pool timeout: {exc}", flush=True)
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "message": "Database connection pool exhausted",
            },
        )

    except Exception as exc:
        print(f"ERROR database connection failed: {exc}", flush=True)
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Unable to load tasks",
            },
        )


@app.get("/debug/pool")
def debug_pool():
    stats = pool.get_stats()
    return {
        "pool_min": stats.get("pool_min"),
        "pool_max": stats.get("pool_max"),
        "pool_size": stats.get("pool_size"),
        "pool_available": stats.get("pool_available"),
        "requests_waiting": stats.get("requests_waiting"),
        "requests_errors": stats.get("requests_errors"),
    }


@app.post("/admin/hold-pool")
def hold_pool(count: int = 3):
    opened = 0

    with hold_lock:
        for _ in range(count):
            try:
                conn = pool.getconn(timeout=2)
                held_connections.append(conn)
                opened += 1
            except Exception:
                break

    return {
        "requested": count,
        "held": opened,
        "pool": pool.get_stats(),
    }


@app.post("/admin/release-pool")
def release_pool():
    released = 0

    with hold_lock:
        while held_connections:
            conn = held_connections.pop()
            try:
                pool.putconn(conn)
                released += 1
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

    return {"released": released}
