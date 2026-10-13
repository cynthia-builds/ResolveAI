"""SQLite setup and small data-access helpers for ResolveAI Sprint 1."""

from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "resolveai.db"


MOCK_ORDERS = [
    ("ORD-1001", 29.90, "PROCESSING", "2026-10-01", 0),
    ("ORD-1002", 48.00, "PROCESSING", "2026-10-02", 0),
    ("ORD-1003", 15.50, "PROCESSING", "2026-10-03", 0),
    ("ORD-1004", 120.00, "PROCESSING", "2026-10-04", 0),
    ("ORD-1005", 35.00, "SHIPPED", "2026-09-30", 1),
    ("ORD-1006", 64.90, "SHIPPED", "2026-10-01", 1),
    ("ORD-1007", 89.00, "SHIPPED", "2026-10-02", 1),
    ("ORD-1008", 22.40, "SHIPPED", "2026-10-03", 1),
    ("ORD-1009", 59.00, "IN_TRANSIT", "2026-09-28", 1),
    ("ORD-1010", 74.50, "IN_TRANSIT", "2026-09-29", 1),
    ("ORD-1011", 18.90, "IN_TRANSIT", "2026-09-30", 1),
    ("ORD-1012", 210.00, "IN_TRANSIT", "2026-10-01", 1),
    ("ORD-1013", 42.00, "DELIVERED", "2026-09-20", 1),
    ("ORD-1014", 99.90, "DELIVERED", "2026-09-21", 1),
    ("ORD-1015", 12.00, "DELIVERED", "2026-09-22", 1),
    ("ORD-1016", 55.50, "DELIVERED", "2026-09-23", 1),
    ("ORD-1017", 59.00, "LOST", "2026-09-22", 1),
    ("ORD-1018", 130.00, "LOST", "2026-09-23", 1),
    ("ORD-1019", 27.80, "LOST", "2026-09-24", 1),
    ("ORD-1020", 83.25, "LOST", "2026-09-25", 1),
    ("ORD-1021", 45.00, "CANCELLED", "2026-10-01", 0),
    ("ORD-1022", 68.00, "CANCELLED", "2026-10-02", 0),
    ("ORD-1023", 31.50, "CANCELLED", "2026-10-03", 0),
    ("ORD-1024", 145.00, "CANCELLED", "2026-09-30", 1)
]


def connect(db_path=DB_PATH):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path=DB_PATH):
    """Create tables and seed mock orders without duplicating existing data."""
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                amount REAL NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'PROCESSING', 'SHIPPED', 'IN_TRANSIT',
                    'DELIVERED', 'LOST', 'CANCELLED'
                )),
                estimated_delivery TEXT NOT NULL,
                has_shipped INTEGER NOT NULL CHECK(has_shipped IN (0, 1)),
                refunded INTEGER NOT NULL DEFAULT 0 CHECK(refunded IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(order_id) REFERENCES orders(order_id)
            );
            """
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO orders
                (order_id, amount, status, estimated_delivery, has_shipped)
            VALUES (?, ?, ?, ?, ?)
            """,
            MOCK_ORDERS,
        )


if __name__ == "__main__":
    initialize_database()
    with connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        print(f"Database ready with {count} mock orders: {DB_PATH}")
