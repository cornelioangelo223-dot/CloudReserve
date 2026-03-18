import sqlite3

conn = sqlite3.connect('cloudreserve.db')
c = conn.cursor()

# Staff table
c.execute('''CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
)''')

# Reservation table
c.execute('''CREATE TABLE IF NOT EXISTS reservation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guest_name TEXT NOT NULL,
    contact TEXT,
    email TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    group_size INTEGER NOT NULL,
    status TEXT NOT NULL,
    staff_id INTEGER,
    FOREIGN KEY(staff_id) REFERENCES staff(id)
)''')

# Queue table
c.execute('''CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id INTEGER,
    status TEXT NOT NULL,
    FOREIGN KEY(reservation_id) REFERENCES reservation(id)
)''')

conn.commit()
try:
    c.execute("INSERT INTO staff (username, password) VALUES (?, ?)", ("admin", "admin123"))
    conn.commit()
except sqlite3.IntegrityError:
    pass  # Account already exists
conn.close()
