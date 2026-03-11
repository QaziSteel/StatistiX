# Oracle NL → SQL Assistant (Streamlit)

A fast, minimal starter for your FYP: ask questions in natural language, generate SQL against Oracle, run it, and visualize results in Streamlit. Optional logging to n8n.

## Quick Start

1) **Install dependencies**
```bash
pip install -r requirements.txt
```

2) **Install Oracle Instant Client (if cx_Oracle needs it)**
- https://www.oracle.com/database/technologies/instant-client.html
- Add the Instant Client folder to your PATH (Windows: Environment Variables).

3) **Create `.env` from example**
```
cp .env.example .env
```
Fill in your DB credentials and OpenAI key.

4) **Run the app**
```bash
streamlit run app.py
```

## Files
- `app.py` — Streamlit UI (chat style), charts, CSV export.
- `db_utils.py` — Oracle connect, schema fetch, safe SQL execution.
- `llm_utils.py` — Uses OpenAI to convert NL → SQL with schema awareness (returns JSON).
- `viz_utils.py` — Helpers for plotting in Streamlit.
- `n8n_utils.py` — Optional logging to n8n webhook.
- `requirements.txt` — Python deps.
- `.env.example` — Template for env vars.

## Notes
- **Safe mode ON**: Only `SELECT` / `WITH` queries are executed by default.
- Row fetch is capped by `MAX_ROWS` (change in `.env`). 
- Click **Refresh Schema** if you change DB objects.
- If your DB has many tables, set `SCHEMA_OWNER` to narrow scope (e.g., your app user).
