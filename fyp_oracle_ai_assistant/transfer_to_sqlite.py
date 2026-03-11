import oracledb
import sqlite3
import os

# Oracle connection details (from your .env)
ORACLE_USER_FYP = "fyp"
ORACLE_PWD_FYP = "fyp123"
ORACLE_USER_HR = "hr"
ORACLE_PWD_HR = "hr123"
ORACLE_DSN = "localhost:1521/XEPDB1"  # Try "XE" if listener fails

# Output SQLite files
SQLITE_FYP = "fyp.db"
SQLITE_HR = "hr.db"

def transfer_schema(oracle_user, oracle_pwd, schema_name, sqlite_file):
    print(f"Transferring schema {schema_name} to {sqlite_file}...")

    # Connect to Oracle (thin mode)
    try:
        oracle_conn = oracledb.connect(user=oracle_user, password=oracle_pwd, dsn=ORACLE_DSN)
    except oracledb.Error as e:
        print(f"Connection failed: {e}")
        print("Try changing DSN to 'XE' or fix listener.")
        return

    sqlite_conn = sqlite3.connect(sqlite_file)
    sqlite_cur = sqlite_conn.cursor()
    oracle_cur = oracle_conn.cursor()

    # Get tables for this schema
    oracle_cur.execute(f"""
        SELECT table_name FROM all_tables WHERE owner = UPPER('{schema_name}')
    """)
    tables = [row[0] for row in oracle_cur.fetchall()]

    for table_name in tables:
        print(f"  Exporting {schema_name}.{table_name}...")

        # Get columns
        oracle_cur.execute(f"SELECT * FROM {schema_name}.{table_name} WHERE ROWNUM <= 1")
        columns = [desc[0] for desc in oracle_cur.description]
        col_str = ", ".join([f'"{c}"' for c in columns])
        placeholders = ", ".join(["?"] * len(columns))

        # Fetch all rows
        oracle_cur.execute(f"SELECT * FROM {schema_name}.{table_name}")
        rows = oracle_cur.fetchall()

        if rows:
            # Create table in SQLite (use TEXT for simplicity; adjust if needed)
            col_defs = ", ".join([f'"{c}" TEXT' for c in columns])
            create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs})'
            sqlite_cur.execute(create_sql)

            # Insert data
            insert_sql = f'INSERT INTO "{table_name}" ({col_str}) VALUES ({placeholders})'
            sqlite_cur.executemany(insert_sql, rows)

    sqlite_conn.commit()
    sqlite_conn.close()
    oracle_conn.close()
    print(f"Done for {schema_name}!")

# Run transfers

transfer_schema(ORACLE_USER_FYP, ORACLE_PWD_FYP, "FYP", SQLITE_FYP)
transfer_schema(ORACLE_USER_HR, ORACLE_PWD_HR, "HR", SQLITE_HR)

print("Transfer complete! You now have fyp.db and hr.db")