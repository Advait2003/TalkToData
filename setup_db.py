import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please define it in your .env file.")
# Base URL targeting the default 'postgres' database
BASE_URL = DB_URL.rsplit('/', 1)[0] + "/postgres"

print(f"Connecting to Postgres at: {BASE_URL}")

try:
    # 1. Connect to default 'postgres' database
    conn = psycopg2.connect(BASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # 2. Check if 'chinook' database exists
    cur.execute("SELECT datname FROM pg_database WHERE datname = 'chinook';")
    exists = cur.fetchone()

    if not exists:
        print("Creating database 'chinook'...")
        cur.execute("CREATE DATABASE chinook;")
        print("Database 'chinook' created successfully!")
    else:
        print("Database 'chinook' already exists.")

    cur.close()
    conn.close()

    # 3. Connect directly to 'chinook' database
    print(f"Connecting to: {DB_URL}")
    conn = psycopg2.connect(DB_URL) 
    conn.autocommit = True
    cur = conn.cursor()

    # 4. Check if tables are already populated
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
    table_count = cur.fetchone()[0]

    if table_count == 0:
        print("Populating 'chinook' from chinook.sql (this may take a few seconds)...")
        with open("chinook.sql", "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Filter out DROP DATABASE, CREATE DATABASE, and \c chinook lines
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("DROP DATABASE") or stripped.startswith("CREATE DATABASE") or stripped.startswith(r"\c"):
                continue
            filtered_lines.append(line)
        
        sql_script = "".join(filtered_lines)
        cur.execute(sql_script)
        print("Tables and data imported successfully!")
    else:
        print(f"Found {table_count} existing tables in 'chinook'.")

    # 5. Verify customer count
    cur.execute("SELECT count(*) FROM customer;")
    count = cur.fetchone()[0]
    print(f"\n Verification Successful! Customer table has {count} rows.")

    cur.close()
    conn.close()

except Exception as e:
    print(f"\n Error: {e}")
