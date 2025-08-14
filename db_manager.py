import sqlite3
import json
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_file="trading_bot.db"):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """Creates the necessary tables if they don't exist."""
        # Stores the current state of open positions
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                asset TEXT PRIMARY KEY,
                direction TEXT,
                size REAL,
                entry_px REAL,
                status TEXT, -- 'OPEN' or 'CLOSED'
                last_update TEXT
            )
        ''')
        # Stores a running log of all significant events
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                event_type TEXT,
                details TEXT
            )
        ''')
        # Stores commands sent from the Discord bot to the trade bot
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS commands (
                command_name TEXT PRIMARY KEY,
                status TEXT,
                timestamp TEXT
            )
        ''')
        self.conn.commit()

    def set_command(self, command_name, status):
        """Sets or updates a command in the database."""
        self.cursor.execute('''
            INSERT INTO commands (command_name, status, timestamp) VALUES (?, ?, ?)
            ON CONFLICT(command_name) DO UPDATE SET status=excluded.status, timestamp=excluded.timestamp
        ''', (command_name, status, datetime.now().isoformat()))
        self.conn.commit()
        print(f"[DB] Set Command: {command_name} -> {status}")

    def get_command(self, command_name):
        """Gets a command's status from the database."""
        self.cursor.execute("SELECT status FROM commands WHERE command_name = ?", (command_name,))
        row = self.cursor.fetchone()
        return row[0] if row else None

    def log_event(self, event_type, details_dict):
        """Logs a new event to the events table."""
        timestamp = datetime.now().isoformat()
        details_json = json.dumps(details_dict)
        self.cursor.execute(
            "INSERT INTO events (timestamp, event_type, details) VALUES (?, ?, ?)",
            (timestamp, event_type, details_json)
        )
        self.conn.commit()
        print(f"[DB] Logged Event: {event_type}")

    def update_position(self, asset, direction, size, entry_px, status):
        """Updates or inserts a position's state."""
        timestamp = datetime.now().isoformat()
        self.cursor.execute('''
            INSERT INTO positions (asset, direction, size, entry_px, status, last_update)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset) DO UPDATE SET
                direction=excluded.direction,
                size=excluded.size,
                entry_px=excluded.entry_px,
                status=excluded.status,
                last_update=excluded.last_update
        ''', (asset, direction, size, entry_px, status, timestamp))
        self.conn.commit()
        print(f"[DB] Updated Position: {asset} is now {status}")

    def get_open_position(self, asset):
        """Retrieves a single open position."""
        self.cursor.execute("SELECT * FROM positions WHERE asset = ? AND status = 'OPEN'", (asset,))
        row = self.cursor.fetchone()
        if not row: return None
        return {"asset": row[0], "direction": row[1], "size": row[2], "entry_px": row[3], "status": row[4], "last_update": row[5]}

    def get_last_event(self):
        """Retrieves the most recent event from the log."""
        # The SELECT statement now correctly includes the 'timestamp' column
        self.cursor.execute("SELECT event_type, details, timestamp FROM events ORDER BY id DESC LIMIT 1")
        row = self.cursor.fetchone()
        if not row: return None
        # The returned dictionary now correctly includes the 'timestamp' key
        return {"event_type": row[0], "details": json.loads(row[1]), "timestamp": row[2]}
    
    def get_latest_events(self, limit=10):
        """Retrieves the most recent events from the log, up to a specified limit."""
        self.cursor.execute("SELECT timestamp, event_type, details FROM events ORDER BY id DESC LIMIT ?", (limit,))
        rows = self.cursor.fetchall()
        if not rows: return []
        
        events = []
        for row in rows:
            events.append({
                "timestamp": row[0],
                "event_type": row[1],
                "details": json.loads(row[2])
            })
        return events