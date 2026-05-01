# db\_ai

Generate a fully populated MySQL database from a plain-English domain description — no SQL writing required.

\---

## What it does

You describe the domain. The script handles everything else:

1. Sends your domain description to Groq and gets back `CREATE TABLE` statements
2. Executes the schema against a local MySQL instance
3. Asks Groq again and gets realistic `INSERT` data with proper FK references
4. Loads the data, catches any failures row-by-row
5. Checks for empty tables and re-prompts with existing IDs to fill gaps
6. Prints a final row-count summary

Total time: \~15–20 seconds for a 10-table schema.

\---

## Why?

Writing schemas and seeding test data by hand is slow and repetitive. This treats the LLM as an actual engineering tool, not a chatbot and cuts that work down to editing a single `DOMAIN` string.

\---

## Stack

|Tool|Role|
|-|-|
|Python 3.10+|Core scripting|
|Groq API|Schema + data generation|
|MySQL|Target database|
|PyMySQL|MySQL connector|
|python-dotenv|Credential management|

\---

## Setup

**Prerequisites**

* Python 3.10+
* MySQL running locally
* Groq API key found free at [console.groq.com](https://console.groq.com)

**Clone and install**

```bash
git clone https://github.com/your-username/db\_ai.git
cd db\_ai

python -m venv venv
source venv/bin/activate          # Mac/Linux
# .\\venv\\Scripts\\Activate.ps1    # Windows PowerShell

pip install pymysql groq python-dotenv
```

**Configure**

Create a `.env` file in the project root:

```env
DB\_HOST=localhost
DB\_PORT=3306
DB\_USER=root
DB\_PASSWORD=your\_mysql\_password
GROQ\_API\_KEY=your\_groq\_api\_key
```

\---

## Usage

```bash
python ai\_schema\_builder.py
```

To target a different domain, edit the `DOMAIN` string near the top of `builder.py`. The rest of the script is domain-agnostic.

If generated statements get cut off, increase `MAX\_TOKENS` (also at the top of the file).

\---

## Example output

```
DB: localhost / root
Groq key: gsk\_SkycesPFor...

Generating schema...
  10 tables defined
Creating tables in 'logistics\_db'...
  + countries
  + warehouses
  + suppliers
  + carriers
  + delivery\_routes
  + inventory
  + purchase\_orders
  + shipments
  + shipment\_items
  + shipment\_events
Generating inserts for 10 tables...
Loading data...
  65 inserted, 0 failed

Row counts in 'logistics\_db':
        carriers                          10
        countries                         10
        delivery\_routes                   10
        inventory                         10
        purchase\_orders                    5
  EMPTY shipment\_events                    0
  EMPTY shipment\_items                     0
  EMPTY shipments                          0
        suppliers                         10
        warehouses                        10
                                     -----
  total                                   65

3 table(s) empty — retrying...
Loading data...
  3 inserted, 0 failed

Row counts in 'logistics\_db':
        carriers                          10
        countries                         10
        delivery\_routes                   10
        inventory                         10
        purchase\_orders                    5
        shipment\_events                    8
        shipment\_items                     8
        shipments                          5
        suppliers                         10
        warehouses                        10
                                     -----
  total                                   86

Done in 16.7s
```

The retry pass (empty tables → re-prompt with real IDs) is automatic. You shouldn't need to run the script twice.

\---

## Notes

* Each run drops and recreates `logistics\_db`, so it's non-destructive to anything outside that database
* FK checks are disabled during load and re-enabled on commit, if a statement still fails, it's logged to `builder.log` and skipped
* `builder.log` is written alongside the script and contains every table name, row count, and failed statement for debugging

