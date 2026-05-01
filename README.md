# db_ai

Generate a fully populated MySQL database from a plain-English domain description. No SQL writing required.

---

## What it does

You describe the DOMAIN. The script handles everything else:

1. Sends your domain description to Groq LLM API and gets back `CREATE TABLE` statements
2. Executes the schema against a local MySQL instance
3. Asks Groq again and gets realistic `INSERT` data with proper FK references
4. Loads the data, catches any failures row-by-row
5. Checks for empty tables and re-prompts with existing IDs to fill gaps
6. Prints a final row-count summary

Total time: ~15-20 seconds for a 10-table schema.

---

## Why

Writing schemas and seeding test data by hand is slow and repetitive. This treats the LLM as an actual engineering tool, not a chatbot, and cuts that work down to editing a single `DOMAIN` string.

---

## Stack

| Tool | Role |
|---|---|
| Python 3.10+ | Core scripting |
| Groq API | Schema + data generation  |
| MySQL | Target database |
| PyMySQL | MySQL connector |
| python-dotenv | Credential management |

---

## Setup

**Prerequisites**
- Python 3.10+
- MySQL running locally
- Groq API key, free at [console.groq.com](https://console.groq.com)

**Clone and install**

```bash
git clone https://github.com/your-username/db_ai.git
cd db_ai

python -m venv venv
source venv/bin/activate          # Mac/Linux
# .\venv\Scripts\Activate.ps1    # Windows PowerShell

pip install pymysql groq python-dotenv
```

**Configure**

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
GROQ_API_KEY=your_groq_api_key
```

---

## Usage

```bash
python ai_schema_builder.py
```

To target a different domain, edit the `DOMAIN` string near the top of `builder.py`. 
The rest of the script is domain-agnostic.
If generated statements get cut off, increase `MAX_TOKENS`.

---

## Example output

```
DB: localhost / root
Groq key: gsk_SkycesPFor...

Generating schema...
  10 tables defined
Creating tables in 'logistics_db'...
  + countries
  + warehouses
  + suppliers
  + carriers
  + delivery_routes
  + inventory
  + purchase_orders
  + shipments
  + shipment_items
  + shipment_events
Generating inserts for 10 tables...
Loading data...
  65 inserted, 0 failed

Row counts in 'logistics_db':
        carriers                          10
        countries                         10
        delivery_routes                   10
        inventory                         10
        purchase_orders                    5
  EMPTY shipment_events                    0
  EMPTY shipment_items                     0
  EMPTY shipments                          0
        suppliers                         10
        warehouses                        10
                                     -----
  total                                   65

3 table(s) empty - retrying...
Loading data...
  3 inserted, 0 failed

Row counts in 'logistics_db':
        carriers                          10
        countries                         10
        delivery_routes                   10
        inventory                         10
        purchase_orders                    5
        shipment_events                    8
        shipment_items                     8
        shipments                          5
        suppliers                         10
        warehouses                        10
                                     -----
  total                                   86

Done in 16.7s
```

The retry pass is automatic. You shouldn't need to run the script twice.

---

## Notes

- Each run drops and recreates `logistics_db`, so it's non-destructive to anything outside that database
- FK checks are disabled during load and re-enabled on commit. If a statement still fails, it's logged to `builder.log` and skipped
- `builder.log` is written alongside the script and has every table name, row count, and failed statement for debugging
