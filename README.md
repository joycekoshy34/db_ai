# db_ai
Generate Schema via Groq LLM

What This Project Does?
-------------------------
This tool automatically designs and populates a MySQL database using AI with zero manual SQL writing. You describe the domain, and the system handles the rest.

The flow looks like this:
-------------------------------
Run one Python script
* Groq AI designs the schema (CREATE TABLE statements)
* Python executes the schema against MySQL
* Groq AI generates realistic INSERT data
* Python loads data with FK validation & error handling
* Auto-detects empty tables and re-prompts AI with real IDs
* Verified, populated database and this database is ready to query

Why I Built This?
-------------------
Most data engineers prepare schemas and seeding test data that is a slow, repetitive process. 
This project automates both steps using AI, showing how modern data engineers can use LLMs as core engineering tools, not just chatbots.

Tech Stack
----------------
Tool	                    |        Purpose
-------------------------------------------------
* Python 3.10+	            |  Core scripting language
* Groq API                	|  AI schema and data generation
* MySQL                     |  Target database
* PyMySQL	                  |  MySQL connector
* SQLAlchemy	              |  Database inspection
* python-dotenv	            | Environment variable management

Getting Started
=================

Prerequisites
-------------------
* Python 3.10 or higher
* MySQL running locally
* Free Groq API key. Get one at console.groq.com

Installation
---------------
git clone https://github.com/your-username/db_ai.git
cd db_ai

# python virtual environment
python -m venv venv

.\venv\Scripts\Activate.ps1        # Windows PowerShell
source venv/bin/activate           # Mac / Linux
pip install sqlalchemy pymysql anthropic python-dotenv

Configuration
-------------------------
Copy the example env file and fill in your credentials:

DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=logistics_db
GROQ_API_KEY=your_groq_api_key

Run
----------------
python ai_schema_builder.py

Expected Output
-------------------
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
  total                             65

3 table(s) empty — retrying...
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
  total                             86

Done in 16.7s


