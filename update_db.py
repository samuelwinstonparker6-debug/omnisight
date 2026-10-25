import sqlite3
conn = sqlite3.connect('omnisight.db')
conn.execute("UPDATE scan_runs SET status='FAILED' WHERE status='RUNNING' OR status='PENDING' OR status='running'")
conn.commit()
conn.close()
print("Successfully reset stuck runs with correct capitalization.")
