import os
import json
from db_utils import fetch_schema, schema_to_text, set_active_db, DB_CONFIGS
from llm_utils import generate_sql_json

def test_debug():
    print("--- Debugging Schema Fetch ---")
    for alias in DB_CONFIGS.keys():
        print(f"\nSwitching to DB: {alias}")
        try:
            set_active_db(alias)
            schema = fetch_schema(force=True)
            print(f"Tables found: {list(schema.keys())}")
            schema_text = schema_to_text(schema)
            print(f"Schema text length: {len(schema_text)}")
            
            if not schema_text:
                print("⚠️ Schema text is EMPTY!")
            
            print("\n--- Testing LLM call ---")
            res = generate_sql_json(schema_text, "list all tables")
            print("Response:", json.dumps(res, indent=2))
            
            if res.get("explanation"):
                print(f"Explanation: {res['explanation']}")
            else:
                print("✅ SQL generated successfully!")
        except Exception as e:
            print(f"❌ Error during test: {e}")

if __name__ == "__main__":
    test_debug()
