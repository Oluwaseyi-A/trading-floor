import sqlite3
import json
from dotenv import load_dotenv

load_dotenv(override=True)

DB = "accounts.db"

# Row-key convention: f"{session_id}:{name.lower()}" — every per-trader row
# (accounts + logs) is namespaced by session so visitors can't see each other.

with sqlite3.connect(DB) as conn:
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS accounts (name TEXT PRIMARY KEY, account TEXT)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            datetime DATETIME,
            type TEXT,
            message TEXT
        )
    ''')
    cursor.execute('CREATE TABLE IF NOT EXISTS market (date TEXT PRIMARY KEY, data TEXT)')
    conn.commit()


def make_key(name: str, session_id: str) -> str:
    return f"{session_id}:{name.lower()}"


def write_account(key, account_dict):
    json_data = json.dumps(account_dict)
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO accounts (name, account)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET account=excluded.account
        ''', (key.lower(), json_data))
        conn.commit()


def read_account(key):
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT account FROM accounts WHERE name = ?', (key.lower(),))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None


def write_log(key: str, type: str, message: str):
    """Write a log entry, keyed by f'{session_id}:{trader_name}'."""
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO logs (name, datetime, type, message)
            VALUES (?, datetime('now'), ?, ?)
        ''', (key.lower(), type, message))
        conn.commit()


def read_log(key: str, last_n=10):
    """Read the most recent log entries for a key (session_id:trader_name)."""
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT datetime, type, message FROM logs
            WHERE name = ?
            ORDER BY datetime DESC
            LIMIT ?
        ''', (key.lower(), last_n))
        return reversed(cursor.fetchall())


def write_market(date: str, data: dict) -> None:
    data_json = json.dumps(data)
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO market (date, data)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET data=excluded.data
        ''', (date, data_json))
        conn.commit()


def read_market(date: str) -> dict | None:
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM market WHERE date = ?', (date,))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else None


def cleanup_session(session_id: str) -> None:
    """Delete every account row and log row belonging to this session."""
    prefix = f"{session_id.lower()}:"
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE name LIKE ?", (prefix + "%",))
        cursor.execute("DELETE FROM logs WHERE name LIKE ?", (prefix + "%",))
        conn.commit()


def list_session_ids() -> list[str]:
    """Return the distinct session_ids currently present in the accounts table."""
    with sqlite3.connect(DB) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT substr(name, 1, instr(name, ':') - 1) FROM accounts WHERE instr(name, ':') > 0")
        return [row[0] for row in cursor.fetchall() if row[0]]
