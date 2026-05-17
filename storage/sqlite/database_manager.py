import datetime
import sqlite3
import threading
from config_runtime import SQLITE_BUSY_TIMEOUT_MS, SQLITE_JOURNAL_MODE, SQLITE_SYNCHRONOUS
from utils.logger import logger

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=max(float(SQLITE_BUSY_TIMEOUT_MS) / 1000.0, 0.0),
        )
        self.cursor = self.conn.cursor()
        self._lock = threading.RLock()
        self._closed = False
        self._configure_connection()
        self._init_db()

    def _configure_connection(self):
        with self._lock:
            self.conn.execute(f"PRAGMA busy_timeout = {int(SQLITE_BUSY_TIMEOUT_MS)}")
            try:
                result = self.conn.execute(f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE}").fetchone()
                actual_mode = str(result[0]).upper() if result and result[0] is not None else ""
                if SQLITE_JOURNAL_MODE and actual_mode and actual_mode != SQLITE_JOURNAL_MODE:
                    logger.warning(
                        f"[DB] journal_mode 请求 {SQLITE_JOURNAL_MODE}，实际生效 {actual_mode}"
                    )
            except Exception as exc:
                logger.warning(f"[DB] 设置 journal_mode 失败: {exc}")
            try:
                self.conn.execute(f"PRAGMA synchronous = {SQLITE_SYNCHRONOUS}")
            except Exception as exc:
                logger.warning(f"[DB] 设置 synchronous 失败: {exc}")

    def _init_db(self):
        with self._lock:
            self.cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
            )

            self.cursor.execute(
                """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                question TEXT,
                answer TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_id INTEGER
            )
            """
            )

            self.cursor.execute("PRAGMA table_info(conversations)")
            columns = [info[1] for info in self.cursor.fetchall()]
            if "session_id" not in columns:
                logger.info("[DB] Migrating: Adding session_id to conversations table...")
                self.cursor.execute("ALTER TABLE conversations ADD COLUMN session_id INTEGER")
                self.cursor.execute("INSERT INTO sessions (title) VALUES (?)", ("默认对话",))
                default_session_id = self.cursor.lastrowid
                self.cursor.execute("UPDATE conversations SET session_id = ? WHERE session_id IS NULL", (default_session_id,))
                self.conn.commit()

            self.conn.commit()

    def get_runtime_pragmas(self):
        with self._lock:
            pragma_names = ("busy_timeout", "journal_mode", "synchronous")
            values = {}
            for name in pragma_names:
                try:
                    row = self.conn.execute(f"PRAGMA {name}").fetchone()
                    values[name] = row[0] if row else None
                except Exception as exc:
                    logger.warning(f"[DB] 读取 PRAGMA {name} 失败: {exc}")
                    values[name] = None
            return values

    # --- Session Management ---
    def create_session(self, title="新对话"):
        with self._lock:
            self.cursor.execute("INSERT INTO sessions (title) VALUES (?)", (title,))
            self.conn.commit()
            return self.cursor.lastrowid

    def get_all_sessions(self):
        with self._lock:
            self.cursor.execute("SELECT id, title, created_at FROM sessions ORDER BY updated_at DESC")
            return self.cursor.fetchall()

    def delete_session(self, session_id):
        with self._lock:
            self.cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self.cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
            self.conn.commit()

    def update_session_title(self, session_id, new_title):
        with self._lock:
            self.cursor.execute("UPDATE sessions SET title = ? WHERE id = ?", (new_title, session_id))
            self.conn.commit()

    def update_session_timestamp(self, session_id):
        with self._lock:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.cursor.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            self.conn.commit()

    # --- Conversation Management ---
    def add_conversation(self, user_id, question, answer, session_id=None):
        with self._lock:
            self.cursor.execute(
                "INSERT INTO conversations (user_id, question, answer, session_id) VALUES (?, ?, ?, ?)",
                (user_id, question, answer, session_id),
            )
            if session_id:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.cursor.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            self.conn.commit()

    def get_conversations_by_session(self, session_id, limit=50):
        with self._lock:
            self.cursor.execute(
                """
                SELECT question, answer FROM conversations
                WHERE session_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """,
                (session_id, limit),
            )
            return self.cursor.fetchall()

    def get_conversation_records_by_session(self, session_id, limit=50):
        with self._lock:
            self.cursor.execute(
                """
                SELECT id, question, answer, timestamp FROM (
                    SELECT id, question, answer, timestamp FROM conversations
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
            """,
                (session_id, limit),
            )
            return [
                {"id": row[0], "question": row[1], "answer": row[2], "timestamp": row[3]}
                for row in self.cursor.fetchall()
            ]

    def get_recent_conversations(self, user_id, limit=3, session_id=None):
        with self._lock:
            query = "SELECT question, answer FROM conversations WHERE user_id = ?"
            params = [user_id]

            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            self.cursor.execute(query, tuple(params))
            return self.cursor.fetchall()[::-1]

    def get_last_conversation(self, user_id, session_id=None):
        with self._lock:
            query = "SELECT question, answer FROM conversations WHERE user_id = ?"
            params = [user_id]
            if session_id:
                query += " AND session_id = ?"
                params.append(session_id)
            query += " ORDER BY id DESC LIMIT 1"

            self.cursor.execute(query, tuple(params))
            return self.cursor.fetchone()

    def get_conversation_count(self):
        with self._lock:
            self.cursor.execute("SELECT COUNT(*) FROM conversations")
            return self.cursor.fetchone()[0]

    def clear_conversations(self):
        with self._lock:
            self.cursor.execute("DELETE FROM conversations")
            self.cursor.execute("DELETE FROM sessions")
            self.conn.commit()

    def close(self):
        with self._lock:
            if self._closed:
                return
            cursor = self.cursor
            conn = self.conn
            self.cursor = None
            self.conn = None
            self._closed = True
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn is not None:
                conn.close()
