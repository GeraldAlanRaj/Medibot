import sqlite3
import os

DB_PATH = 'chat_memory.db'

def reset():
    if os.path.exists(DB_PATH):
        print(f"Removing existing database at {DB_PATH}...")
        os.remove(DB_PATH)
    
    # Importing init_db from current database.py
    from database import init_db # pyre-ignore[21]
    print("Re-initializing database with new schema...")
    init_db()
    print("Database reset successfully.")

if __name__ == "__main__":
    reset()
