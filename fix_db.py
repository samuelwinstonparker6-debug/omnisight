import sqlite3
import os

db_path = os.path.join("c:\\Users\\DELL\\Downloads\\Infotact Solutions\\omnisight", "omnisight.db")
conn = sqlite3.connect(db_path)
conn.execute("UPDATE scan_runs SET status='FAILED' WHERE status='RUNNING' OR status='PENDING'")
conn.commit()
conn.close()
print("Stuck runs fixed.")
