import os
import json
from typing import Dict, Tuple
from dotenv import load_dotenv
import google.generativeai as genai
import sqlite3

from db_utils import run_sql  # ✅ needed for execute_with_autofix

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

if not GEMINI_API_KEY:
    raise ValueError("❌ Missing GEMINI_API_KEY in environment variables. Add it to .env")

genai.configure(api_key=GEMINI_API_KEY)
client = genai.GenerativeModel(GEMINI_MODEL)

SYSTEM_RULES = (
    "You are a senior SQLite SQL + Data Visualization engineer.\n"
    "- You receive: (1) a database schema, and (2) a user request.\n"
    "- Use ONLY exact table and column names that appear in the schema.\n"
    "- NEVER invent tables (e.g., SANDBOX_*, POP, USERS).\n"
    "- If the request cannot be answered using the schema, respond with:\n"
    "  {\"is_schema_query\": false, \"explanation\": \"<why>\"}\n"
    "- Otherwise, return ONE SQLite SELECT query (main query) with chart recommendation.\n"
    "- Only SELECT/WITH. No INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA.\n"
    "- SQLite syntax only. Use LIMIT n.\n"
    "- For text filtering use: col LIKE '%text%' COLLATE NOCASE.\n"
    "\n"
    "✅ IMPORTANT (decoded labels):\n"
    "- If a column has a decoded text version ending with '_LABEL' (e.g., GENDER_LABEL, ROOMS_LABEL),\n"
    "  PREFER using the *_LABEL column for grouping, filtering, and display.\n"
    "- If you aggregate by a coded column (e.g., gender=1/2/3), then ALSO include the corresponding\n"
    "  *_LABEL column in SELECT and GROUP BY if available.\n"
    "- Prefer returning human-readable outputs (labels) rather than numeric codes.\n"
    "\n"
    "📦 Output MUST be strict JSON with this format:\n"
    "{\n"
    "  \"is_schema_query\": true|false,\n"
    "  \"items\": [\n"
    "    {\n"
    "      \"sql\": \"<sqlite select query>\",\n"
    "      \"chart\": \"bar|line|scatter|pie|histogram|box|area|heatmap|treemap\",\n"
    "      \"title\": \"<short chart title>\",\n"
    "      \"explanation\": \"<1–2 sentence insight>\"\n"
    "    }\n"
    "  ]\n"
    "}\n"
)

def build_prompt(schema_text: str, user_question: str) -> str:
    return f"""SCHEMA:
{schema_text}

USER QUESTION:
{user_question}

Return strict JSON only (no extra commentary).
"""

import re

def extract_json(text: str) -> Dict:
    """Robustly extract JSON from model output, handling markdown blocks."""
    if not text:
        return {}
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try finding json block
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
            
    # Try finding any { ... }
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
            
    return {}

def generate_sql_json(schema_text: str, user_question: str) -> Dict:
    prompt = build_prompt(schema_text, user_question)
    
    full_prompt = f"{SYSTEM_RULES}\n\n{prompt}"

    try:
        response = client.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
            )
        )
        data = extract_json(response.text)
        if not data:
             raise json.JSONDecodeError("Failed to extract JSON", response.text, 0)
        return data

    except json.JSONDecodeError:
        return {"is_schema_query": False, "items": [], "explanation": "❌ Model returned invalid JSON."}
    except Exception as e:
        return {"is_schema_query": False, "items": [], "explanation": f"❌ Error while generating SQL: {str(e)}"}

def execute_with_autofix(
    sql: str,
    user_question: str,
    schema_text: str,
    max_retries: int = 5
) -> Tuple[list, list, str]:
    """
    Try running SQL; if SQLite error occurs, ask LLM to fix it.
    Forces the model to CHANGE STRUCTURE on each retry.
    Returns: (rows, colnames, final_sql)
    """
    attempt = 0
    current_sql = (sql or "").strip()

    while attempt < max_retries:
        try:
            rows, cols = run_sql(current_sql)
            return rows, cols, current_sql

        except sqlite3.Error as e:
            error_msg = str(e)

            repair_prompt = f"""
The following SQL failed on SQLite.

Error:
{error_msg}

Broken SQL:
{current_sql}

User Question:
{user_question}

SCHEMA:
{schema_text}

Task:
Rewrite into VALID SQLite SELECT/WITH.

IMPORTANT RULES:
- Use ONLY schema table/column names (no invented names).
- DO NOT use PRAGMA, ATTACH, INSERT, UPDATE, DELETE, DROP, ALTER.
- DO NOT repeat the same structure if it already failed.
- If UNION/JOIN across multiple tables fails, fall back to ONE best matching table.
- Keep it simple and clear.
- Add LIMIT only if needed.

✅ Decoded labels rule:
- Prefer *_LABEL columns (e.g., GENDER_LABEL, ROOMS_LABEL, WALLSTYPE_LABEL, etc.) when they exist.
- If grouping on a coded column, include the *_LABEL in SELECT/GROUP BY if available.

Return ONLY strict JSON:
{{
  "sql": "<fixed sql>",
  "note": "<what you changed and why>"
}}
"""
            response = client.generate_content(
                f"You are a SQLite SQL repair assistant. Respond ONLY in JSON.\n\n{repair_prompt}",
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                )
            )

            fix = extract_json(response.text)
            current_sql = (fix.get("sql") or current_sql).strip()

        attempt += 1

    raise RuntimeError(f"❌ Failed after {max_retries} attempts. Last SQL: {current_sql}") 