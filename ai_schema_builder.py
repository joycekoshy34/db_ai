from groq import Groq
import pymysql
import logging
import os
import re
import time
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 3306)),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "charset":  "utf8mb4"
}

DB_NAME = "logistics_db"

logging.basicConfig(
    filename="builder.log",
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S"
)

try:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
except Exception as e:
    print(f"Groq init failed: {e}")
    exit(1)


# Edit this to point the generator at a different domain
DOMAIN = """
A logistics and supply chain system for a freight company:
- Multiple warehouses across different countries
- Suppliers and purchase orders
- Carriers (air, sea, road, rail) and delivery routes
- Inventory tracking per warehouse
- Shipments with real-time tracking events

Design requirements:
- Proper foreign key relationships
- ENUM for status fields
- Timestamps where relevant
- At least 8 tables
- Suitable for analytical queries (delays, supplier performance, revenue)
"""

# Bump max_tokens if the schema or inserts get cut off mid-statement
MAX_TOKENS = 2048


def ask_groq(prompt):
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=MAX_TOKENS,
        timeout=60
    )
    return resp.choices[0].message.content


def clean_sql(text):
    # Strip markdown fences the model sometimes wraps output in
    text = re.sub(r"```sql", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```", "", text)
    text = re.sub(r"--.*?$", "", text, flags=re.MULTILINE)

    # Curly quotes from the model break MySQL string literals
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')

    text = "\n".join(line for line in text.splitlines() if line.strip())
    return text.strip()


def generate_schema():
    print("Generating schema...")

    prompt = f"""You are a MySQL database architect.

Design a schema for a logistics company with these tables:
warehouses, suppliers, carriers, countries, delivery_routes,
inventory, purchase_orders, shipments, shipment_items, shipment_events

Domain context:
{DOMAIN}

Return only CREATE TABLE statements — no markdown, no comments, no explanations.
Use AUTO_INCREMENT PKs, include foreign keys, parent tables before child tables.
End every statement with a semicolon.
"""
    sql = clean_sql(ask_groq(prompt))
    print(f"  {sql.count('CREATE TABLE')} tables defined")
    logging.info("schema generated")
    return sql


def create_tables(schema_sql):
    print(f"Creating tables in '{DB_NAME}'...")

    try:
        conn = pymysql.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
        cur.execute(f"CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"USE {DB_NAME}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")

        created = []
        for stmt in (s.strip() for s in schema_sql.split(";") if s.strip()):
            if not re.match(r"(?i)^\s*CREATE\s+TABLE", stmt):
                continue
            try:
                cur.execute(stmt)
                m = re.search(r"(?i)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?", stmt)
                if m:
                    created.append(m.group(1))
                    print(f"  + {m.group(1)}")
            except pymysql.Error as e:
                print(f"  ! skipped: {e}")
                logging.warning(f"table skipped: {e}")

        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"created: {created}")
        return created

    except pymysql.Error as e:
        print(f"MySQL connection failed: {e}")
        print("Check DB_HOST / DB_USER / DB_PASSWORD in .env")
        exit(1)


def generate_inserts(schema_sql, tables):
    print(f"Generating inserts for {len(tables)} tables...")

    prompt = f"""You are a database engineer creating test data.

Schema:
{schema_sql}

Generate INSERT statements for these tables in this exact order:
{', '.join(tables)}

Return only INSERT SQL — no markdown, no explanations.
Use realistic logistics data (real city names, plausible company names).
5–10 rows per table. FK values must reference rows inserted earlier.
ENUM values must match the schema. One statement per row, semicolon at end.
"""
    sql = clean_sql(ask_groq(prompt))
    logging.info("inserts generated")
    return sql


def load_data(data_sql):
    print("Loading data...")

    try:
        conn = pymysql.connect(**DB_CONFIG, database=DB_NAME)
        cur = conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")

        # Split on semicolons that end a line rather than naive string split,
        # otherwise we'd break on semicolons inside quoted strings
        statements = []
        buf = ""
        for line in data_sql.splitlines():
            line = line.strip()
            if not line:
                continue
            buf += " " + line
            if line.endswith(";"):
                statements.append(buf.strip())
                buf = ""

        ok = bad = 0
        for i, stmt in enumerate(statements):
            if not re.match(r"(?i)^\s*INSERT\s+INTO", stmt):
                continue
            try:
                cur.execute(stmt)
                ok += 1
            except pymysql.Error as e:
                bad += 1
                logging.warning(f"insert #{i+1} failed: {e} | {stmt[:80]}")

        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        cur.close()
        conn.close()
        print(f"  {ok} inserted, {bad} failed")

    except pymysql.Error as e:
        print(f"Load failed: {e}")
        exit(1)


def fix_empty_tables(schema_sql, empty_tables):
    # Pull a sample of existing rows so the model can use real FK values
    conn = pymysql.connect(**DB_CONFIG, database=DB_NAME)
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    all_tables = [r[0] for r in cur.fetchall()]

    context = ""
    for t in all_tables:
        cur.execute(f"SELECT * FROM `{t}` LIMIT 5")
        rows = cur.fetchall()
        if not rows:
            continue
        cols = [d[0] for d in cur.description]
        context += f"\n{t}: {cols}\n"
        for row in rows:
            context += f"  {dict(zip(cols, row))}\n"

    cur.close()
    conn.close()

    prompt = f"""You are a database engineer fixing missing test data.

Schema:
{schema_sql}

Existing rows (use these FK values — do not invent new IDs):
{context}

Fill these empty tables: {', '.join(empty_tables)}
Return only INSERT statements, 5–8 rows per table, semicolon at end.
ENUM values must match the schema exactly.
"""
    sql = clean_sql(ask_groq(prompt))
    logging.info(f"fix data generated for: {empty_tables}")
    return sql


def verify(db_name):
    print(f"\nRow counts in '{db_name}':")

    conn = pymysql.connect(**DB_CONFIG, database=db_name)
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]

    total = 0
    empty = []
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM `{t}`")
        n = cur.fetchone()[0]
        total += n
        flag = "EMPTY" if n == 0 else "     "
        print(f"  {flag} {t:<30} {n:>5}")
        logging.info(f"{t}: {n}")
        if n == 0:
            empty.append(t)

    print(f"  {'':30} -----")
    print(f"  {'total':<30} {total:>5}")
    cur.close()
    conn.close()
    return empty


def main():
    t0 = time.time()

    print(f"DB: {os.getenv('DB_HOST')} / {os.getenv('DB_USER')}")
    print(f"Groq key: {os.getenv('GROQ_API_KEY', '')[:14]}...\n")

    schema  = generate_schema()
    tables  = create_tables(schema)
    inserts = generate_inserts(schema, tables)
    load_data(inserts)

    empty = verify(DB_NAME)
    if empty:
        print(f"\n{len(empty)} table(s) empty — retrying...")
        load_data(fix_empty_tables(schema, empty))
        verify(DB_NAME)

    print(f"\nDone in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
