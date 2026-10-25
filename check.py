import sqlite3
db=sqlite3.connect('omnisight.db')
print(db.execute('SELECT total_bugs FROM scan_runs WHERE id=\"e3c30088-89d4-4609-ae14-7f62193a246f\"').fetchone())
