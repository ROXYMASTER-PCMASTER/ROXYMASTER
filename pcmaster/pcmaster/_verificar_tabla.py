import sqlite3
conn = sqlite3.connect('data/roxymaster.db')
row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contextos_streamer'").fetchone()
print(row)
conn.close()