import sqlite3
from pathlib import Path


# Find the root Mairon project directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Mairon's private runtime data will live here
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "mairon.db"


def init_memory_db():
    DATA_DIR.mkdir(exist_ok=True)

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def save_memory(memory):
    init_memory_db()

    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO memories (memory) VALUES (?)",
            (memory,)
        )

    if cursor.rowcount == 0:
        return {
            "success": True,
            "message": "That memory already exists."
        }

    return {
        "success": True,
        "message": "Memory saved."
    }


def search_memories(query, limit=5):
    init_memory_db()

    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT id, memory, created_at
            FROM memories
            ORDER BY created_at DESC
            """
        ).fetchall()

    search_terms = [
        word.lower().strip(".,!?")
        for word in query.split()
        if len(word.strip(".,!?")) >= 3
    ]

    matches = []

    for memory_id, memory, created_at in rows:
        memory_lower = memory.lower()

        score = sum(
            term in memory_lower
            for term in search_terms
        )

        if score > 0:
            matches.append(
                {
                    "id": memory_id,
                    "memory": memory,
                    "created_at": created_at,
                    "score": score
                }
            )

    matches.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return matches[:limit]