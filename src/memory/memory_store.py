import sqlite3
from pathlib import Path


# Find the root Mairon project directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Mairon's private runtime data
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


def list_memories():
    init_memory_db()

    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT id, memory, created_at
            FROM memories
            ORDER BY created_at DESC
            """
        ).fetchall()

    return [
        {
            "id": memory_id,
            "memory": memory,
            "created_at": created_at
        }
        for memory_id, memory, created_at in rows
    ]


def search_memories(query, limit=5):
    init_memory_db()

    memories = list_memories()

    search_terms = [
        word.lower().strip(".,!?")
        for word in query.split()
        if len(word.strip(".,!?")) >= 3
    ]

    matches = []

    for item in memories:
        memory_lower = item["memory"].lower()

        score = sum(
            term in memory_lower
            for term in search_terms
        )

        if score > 0:
            matches.append(
                {
                    **item,
                    "score": score
                }
            )

    matches.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return matches[:limit]


def delete_memory(query):
    matches = search_memories(query)

    if len(matches) == 0:
        return {
            "success": False,
            "message": "No matching memory was found."
        }

    if len(matches) > 1:
        return {
            "success": False,
            "message": "Multiple memories matched. Nothing was deleted.",
            "matches": matches
        }

    memory_to_delete = matches[0]

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_to_delete["id"],)
        )

    return {
        "success": True,
        "message": "Memory deleted.",
        "deleted_memory": memory_to_delete["memory"]
    }