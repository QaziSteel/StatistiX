import os
import json
import re
import pandas as pd
import streamlit as st
import plotly.express as px
from dotenv import load_dotenv
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
from io import BytesIO
import tempfile
from db_utils import run_sql  # add this import at top if not already
from db_utils import fetch_schema, schema_to_text, MAX_ROWS, SAFE_MODE
from db_utils import DB_CONFIGS, set_active_db, list_nonempty_tables
from llm_utils import generate_sql_json, execute_with_autofix, extract_json
from n8n_utils import log_event
from session_manager import require_auth, get_current_user, logout_user
from auth_db_utils import get_user_databases, add_query_history

# Load keys
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
client = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))

st.set_page_config(page_title="SQLite NL→SQL Assistant", layout="wide")

# CRITICAL: Check authentication before rendering anything
require_auth("home_page", required_role=None)

st.title("🧠 SQLite NL → SQL Assistant")


# ---------------------------
# Voice utils
# ---------------------------
def speak(text: str) -> BytesIO:
    """Convert assistant reply text into speech (mp3 in memory)."""
    try:
        speech = client.audio.speech.create(
            model=os.getenv("TTS_MODEL"),
            voice=os.getenv("TTS_VOICE"),
            input=text
        )
        buf = BytesIO(speech.read())
        buf.seek(0)
        return buf
    except Exception:
        return BytesIO()


def transcribe_to_english(audio_bytes: bytes) -> dict:
    """
    Transcribe mic audio with Whisper, auto-detect language,
    then translate to English if needed.
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        wav_path = f.name

    try:
        with open(wav_path, "rb") as af:
            tr = client.audio.transcriptions.create(
                model=os.getenv("WHISPER_MODEL"),
                file=af,
                response_format="verbose_json"
            )
        raw_text = tr.text.strip()
        detected = (getattr(tr, "language", None) or "unknown").lower()
    except Exception as e:
        return {"text_en": "", "lang": "error", "text_raw": f"STT failed: {e}"}

    # If already English, no need to translate
    text_en = raw_text
    if not detected.startswith("en"):
        try:
            trans = client.generate_content(
                f"Translate this into clear English, preserving table/column names.\n\n{raw_text}",
                generation_config=genai.types.GenerationConfig(temperature=0)
            )
            text_en = trans.text.strip()
        except Exception:
            text_en = raw_text + " (translation failed)"

    return {"text_en": text_en, "lang": detected, "text_raw": raw_text}




def get_db_sample_for_llm(max_tables: int = 5, rows_per_table: int = 5) -> str:
    """
    Build a compact text summary: table names, row counts, and head rows
    for a few tables, to help LLM understand what's in the DB.
    """
    summary_parts = []
    tables = list_nonempty_tables()[:max_tables]  # (NAME, count, COLS)

    for name, count, cols in tables:
        table_name = name
        try:
            sql = f'SELECT * FROM "{table_name}" LIMIT {rows_per_table}'
            rows, colnames = run_sql(sql)
            df_head = pd.DataFrame(rows, columns=colnames)
            sample = df_head.to_dict(orient="records")
        except Exception as e:
            sample = f"Error reading sample: {e}"
        summary_parts.append(
            f"TABLE {table_name} (rows ~ {count}):\n"
            f"Columns: {', '.join(cols)}\n"
            f"Sample rows: {sample}\n"
        )

    return "\n\n".join(summary_parts) if summary_parts else "No non-empty tables."

# ---------------------------
# SQL validation (robust)
# ---------------------------
def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def extract_tables_from_sql(sql: str) -> set[str]:
    """
    Extract table names after FROM/JOIN for validation.
    Lightweight but effective for LLM-generated queries.
    """
    if not sql:
        return set()

    s = _strip_sql_comments(sql)
    matches = re.findall(r"\b(from|join)\s+([`\"[\]\w\.]+)", s, flags=re.IGNORECASE)

    tables = set()
    for _, raw in matches:
        t = raw.strip().strip('`"[]')
        t = t.split(".")[-1].split(",")[0].strip()
        if t:
            tables.add(t.upper())
    return tables


def validate_sql_tables(sql: str, schema: dict) -> bool:
    """
    Validate: query must reference ONLY tables in schema.
    """
    tables = extract_tables_from_sql(sql)
    if not tables:
        return False
    return tables.issubset(set(schema.keys()))


def regenerate_sql_once(user_q: str, schema_text: str) -> str:
    """
    If model invents tables, regenerate ONE simpler SQL once.
    """
    prompt = f"""
SCHEMA:
{schema_text}

USER QUESTION:
{user_q}

Generate ONE simple SQLite SELECT/WITH query using ONLY tables/columns from SCHEMA.
Avoid UNION across multiple tables unless necessary.
Return JSON only:
{{"sql":"..."}}
"""
    resp = client.generate_content(
        f"You are a strict SQLite SQL generator. Use ONLY schema names. JSON only.\n\n{prompt}",
        generation_config=genai.types.GenerationConfig(temperature=0)
    )
    obj = extract_json(resp.text)
    return (obj.get("sql") or "").strip()


# ---------------------------
# Visualization (Refactored for dynamic controls)
# ---------------------------
def auto_plot_main(df: pd.DataFrame, user_question: str, 
                   override_chart_type=None, override_x=None, 
                   override_y=None, override_color=None, 
                   override_title=None, override_colorscale="Viridis",
                   show=True):
    """LLM-chosen chart with optional manual overrides for Title, Axes, and Color."""
    if df is None or df.empty:
        if show: st.warning("⚠️ Empty result; no chart.")
        return None, None, None, None, None

    cols_str = ", ".join(df.columns.tolist())
    preview = df.head(10).to_dict(orient="records")

    # Only ask LLM if we don't have overrides for the core structure
    if not override_chart_type:
        prompt = f"""
You are a visualization expert.
User question: {user_question}
Data columns: {cols_str}
First 10 rows: {preview}

Pick the BEST single chart type.
Choose only from: bar, line, scatter, pie, histogram, box, area, violin, heatmap, treemap.
Pick x and y columns if applicable.
Return ONLY JSON:
{{
  "chart_type": "bar|line|scatter|pie|histogram|box|area|violin|heatmap|treemap",
  "x": "<col_or_null>",
  "y": "<col_or_null>",
  "color": "<col_or_null>",
  "explanation": "short reason"
}}
"""
        try:
            resp = client.generate_content(
                f"You are a JSON-only visualization assistant.\n\n{prompt}",
                generation_config=genai.types.GenerationConfig(temperature=0)
            )
            chart = extract_json(resp.text)
        except Exception as e:
            st.warning(f"Chart suggestion failed: {e}")
            chart = {"chart_type": "bar", "x": None, "y": None, "color": None}
    else:
        chart = {"chart_type": override_chart_type, "x": override_x, "y": override_y, "color": override_color}

    chart_type = override_chart_type or chart.get("chart_type", "bar")
    x = override_x or chart.get("x")
    y = override_y or chart.get("y")
    color_col = override_color or chart.get("color")
    title_text = override_title or f"📊 {chart_type.title()} Visualization"

    # ---- sensible fallbacks ----
    if not x:
        obj_cols = df.select_dtypes(include=["object"]).columns
        x = obj_cols[0] if len(obj_cols) else df.columns[0]

    needs_y = chart_type in ("bar", "line", "scatter", "area", "violin", "box", "treemap", "pie")
    if needs_y and not y:
        num_cols = df.select_dtypes(include=["int64", "float64"]).columns
        if len(num_cols):
            y = num_cols[0]
        else:
            agg = df.groupby(x, dropna=False).size().reset_index(name="COUNT")
            df = agg
            y = "COUNT"

    if not color_col and not override_color:
        if y in df.columns and pd.api.types.is_numeric_dtype(df[y]):
            color_col = y

    # ---- plot ----
    try:
        if chart_type == "bar":
            fig = px.bar(df, x=x, y=y, color=color_col, color_continuous_scale=override_colorscale)
        elif chart_type == "line":
            fig = px.line(df, x=x, y=y, markers=True)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x, y=y, color=color_col, color_continuous_scale=override_colorscale)
        elif chart_type == "pie":
            fig = px.pie(df, names=x, values=y, hole=0.35)
        elif chart_type == "histogram":
            fig = px.histogram(df, x=x, color=color_col, color_continuous_scale=override_colorscale)
        elif chart_type == "area":
            fig = px.area(df, x=x, y=y)
        elif chart_type == "violin":
            fig = px.violin(df, x=x, y=y, box=True, points="all")
        elif chart_type == "box":
            fig = px.box(df, x=x, y=y)
        elif chart_type == "heatmap":
            corr = df.corr(numeric_only=True)
            fig = px.imshow(corr, text_auto=True, color_continuous_scale=override_colorscale)
        elif chart_type == "treemap":
            fig = px.treemap(df, path=[x], values=y, color=y, color_continuous_scale=override_colorscale)
        else:
            fig = px.bar(df, x=x, y=y)

        fig.update_layout(
            template="plotly_white",
            title=dict(text=title_text, font=dict(color="black", size=18)),
            font=dict(color="black", size=14),
            plot_bgcolor="white", paper_bgcolor="white",
            xaxis=dict(
                title_font=dict(color="black", size=14),
                tickfont=dict(color="black", size=12),
                linecolor="black",
                gridcolor="lightgrey"
            ),
            yaxis=dict(
                title_font=dict(color="black", size=14),
                tickfont=dict(color="black", size=12),
                linecolor="black",
                gridcolor="lightgrey"
            ),
            legend=dict(
                font=dict(color="black", size=12),
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="black",
                borderwidth=1
            )
        )
        fig.update_coloraxes(
            colorbar=dict(
                title=dict(font=dict(color="black", size=14)),
                tickfont=dict(color="black", size=12)
            )
        )
        if show:
            st.plotly_chart(fig, use_container_width=True)
        return fig, chart_type, x, y, color_col
    except Exception as e:
        st.error(f"Chart rendering failed: {e}")
        return None, None, None, None, None


# ---------------------------
# UI: Sidebar / tables
# ---------------------------
with st.sidebar.expander("🎙️ Voice Assistant (Beta)", expanded=False):
    st.caption("Speak in ANY language → I’ll transcribe → translate to English → fill the box.")

    audio_bytes = audio_recorder(
        text="Click to record / stop",
        recording_color="#ef4444",
        neutral_color="#3b82f6",
        icon_size="2x"
    )

    if audio_bytes:
        st.audio(audio_bytes, format="audio/wav")

        with st.spinner("Transcribing and translating…"):
            voice = transcribe_to_english(audio_bytes)

        if voice.get("lang") == "error":
            st.error(voice["text_raw"])
        else:
            st.write(f"Detected language: **{voice['lang']}**")
            st.text_area("Transcript (English)", value=voice["text_en"], height=100)

            if st.button("↪️ Use this as my question"):
                st.session_state.user_q = voice["text_en"]
                st.success("Copied to the input box above. Now click ✨ Generate & Run.")

            if st.button("🔊 Play assistant reply"):
                reply_text = "I captured your question. Press Generate and Run to query the database."
                audio_buf = speak(reply_text)
                if audio_buf.getbuffer().nbytes:
                    st.audio(audio_buf, format="audio/mp3")


with st.sidebar:
    # User info section
    current_user = get_current_user()
    if current_user:
        st.markdown("---")
        col_info, col_logout = st.columns([3, 1])
        with col_info:
            st.markdown(f"### 👤 Welcome")
            st.markdown(f"**{current_user['full_name']}**")
            st.caption(f"Role: {current_user['role'].upper()}")
        with col_logout:
            if st.button("Logout", key="logout_btn", use_container_width=True):
                logout_user()
                st.rerun()
        st.markdown("---")

    # Admin tools section
    if current_user and current_user['role'] == 'admin':
        st.markdown("### 👥 Admin Tools")
        if st.button("📋 User Management", use_container_width=True):
            st.switch_page("pages/3_User_Management.py")
        st.markdown("---")

    # Settings section
    st.header("Settings")
    if st.button("🔁 Refresh schema cache"):
        schema = fetch_schema(force=True)
        st.success(f"Schema refreshed: {len(schema)} tables cached.")
    st.checkbox("Safe mode (SELECT/WITH only)", value=SAFE_MODE, disabled=True)
    st.caption(f"Max rows fetched: {MAX_ROWS}")


# ✅ Select DB first, then fetch schema for that DB
# Use permission-aware database list (only assigned databases)
current_user = get_current_user()
user_databases = get_user_databases(current_user['user_id']) if current_user else []

if not user_databases:
    st.error("❌ You do not have access to any databases. Contact your administrator.")
    st.stop()

db_choice = st.selectbox(
    "🔄 Select Database",
    options=user_databases,
    help=f"Assigned databases for {current_user['username']}" if current_user else "Select database"
)
set_active_db(db_choice)

schema = fetch_schema(force=False)
schema_text = schema_to_text(schema, limit_tables=80, limit_cols=80)


st.subheader("📂 Database Tables")

if "show_tables" not in st.session_state:
    st.session_state.show_tables = False

col_tbl1, col_tbl2 = st.columns([1, 1])
with col_tbl1:
    if st.button("📄 Show Available Tables"):
        st.session_state.show_tables = not st.session_state.show_tables
with col_tbl2:
    db_details_btn = st.button("📑 Database details (LLM Summary)")

if st.session_state.show_tables:
    tables = list_nonempty_tables()
    if not tables:
        st.warning("No non-empty tables found.")
    else:
        for name, count, cols in tables:
            with st.expander(f"{name} ({count} rows)"):
                st.write(f"**Columns:** {', '.join(cols)}")
                
                # Pagination
                page_size = 100
                total_pages = (count // page_size) + (1 if count % page_size > 0 else 0)
                
                if total_pages > 1:
                    page = st.number_input(
                        f"Page (out of {total_pages})",
                        min_value=1,
                        max_value=total_pages,
                        value=1,
                        key=f"page_{db_choice}_{name}"
                    )
                else:
                    page = 1
                
                offset = (page - 1) * page_size
                
                # Fetch data for this page
                try:
                    paged_sql = f'SELECT * FROM "{name}" LIMIT {page_size} OFFSET {offset}'
                    paged_rows, paged_cols = run_sql(paged_sql)
                    paged_df = pd.DataFrame(paged_rows, columns=paged_cols)
                    st.dataframe(paged_df, use_container_width=True)
                    st.caption(f"Showing rows {offset + 1} to {min(offset + page_size, count)} of {count}")
                except Exception as e:
                    st.error(f"Failed to fetch table data: {e}")

if db_details_btn:
    with st.spinner("Analyzing database contents for summary..."):
        db_sample = get_db_sample_for_llm()

        # Let LLM summarize this for the user
        prompt = f"""
You are a data analyst. The user will ask questions about this SQLite database.

Here is a compact view of the available tables, columns, row counts,
and a few sample rows from each:

{db_sample}

Write a short, beginner-friendly summary of:
- What kind of data is stored
- What each table roughly represents
- Examples of interesting questions the user can ask

Answer in plain text, 3–6 bullet points, no JSON.
"""
        try:
            resp = client.generate_content(
                f"You summarize database schemas for non-technical users.\n\n{prompt}",
                generation_config=genai.types.GenerationConfig(temperature=0.3)
            )
            summary = resp.text.strip()
            st.markdown("### 🗂 Database Summary (LLM)")
            st.markdown(summary)
        except Exception as e:
            st.error(f"Failed to generate DB summary: {e}")



# ---------------------------
# Main query flow
# ---------------------------
st.subheader("💬 Ask your database in plain English")

# Initialize session state for query persistent storage
if "query_results" not in st.session_state:
    st.session_state.query_results = None

user_q = st.text_input(
    "Your question",
    key="user_q",
    placeholder="e.g., total households by district"
)

col_run1, col_run2 = st.columns([1, 1])
with col_run1:
    run_btn = st.button("✨ Generate & Run")
with col_run2:
    sql_only_btn = st.button("🧪 Generate SQL only")

if (run_btn or sql_only_btn) and not user_q.strip():
    st.warning("Please enter a question.")
    st.stop()


if run_btn or sql_only_btn:
    with st.spinner("Thinking..."):
        result = generate_sql_json(schema_text, user_q)

    st.subheader("🧾 Model decision")
    st.json(result)

    if not result.get("is_schema_query"):
        st.error(result.get("explanation") or "The question doesn't match the schema. Please rephrase.")
        log_event("reject", {"question": user_q, "reason": result.get("explanation", "")})
        st.stop()

    items = result.get("items", [])
    sql_main = (items[0].get("sql") if items else result.get("sql") or "").strip()

    if not sql_main:
        st.error("Model didn't return SQL. Try rephrasing.")
        st.stop()

    # Validate tables; if invalid, regenerate once
    if not validate_sql_tables(sql_main, schema):
        st.warning("⚠️ SQL referenced invalid tables. Regenerating a simpler query once...")
        sql_main = regenerate_sql_once(user_q, schema_text)

        if not sql_main or not validate_sql_tables(sql_main, schema):
            st.error("❌ Still invalid after regeneration. Please rephrase your question.")
            st.stop()

    st.subheader("🧠 Generated SQL (Main)")
    st.code(sql_main, language="sql")

    if sql_only_btn:
        st.info("SQL generated (not executed). Click '✨ Generate & Run' to execute.")
        st.stop()

    try:
        # Execute with autofix (LLM will rewrite structure if it fails)
        rows, cols, final_sql = execute_with_autofix(sql_main, user_q, schema_text, max_retries=5)

        # Update session state with results
        st.session_state.query_results = {
            "df": pd.DataFrame(rows, columns=cols),
            "sql": final_sql,
            "question": user_q,
            "db": db_choice,
            "history_saved": False
        }
        
        # Reset customization state for new result
        st.session_state.viz_config = {"title": f"📊 {user_q}", "colorscale": "Viridis"}

    except Exception as e:
        st.error(f"Execution failed: {e}")
        log_event("error", {"question": user_q, "error": str(e)})

# ─── Render Results (Persistent from Session State) ───
if st.session_state.query_results:
    res = st.session_state.query_results
    df_main = res["df"]
    final_sql = res["sql"]
    user_q = res["question"]
    db_choice = res["db"]

    st.success(f"✅ Query executed. Showing up to {len(df_main)} rows (cap: {MAX_ROWS}).")
    st.dataframe(df_main, use_container_width=True)

    st.markdown("### 📊 Visualization & Customization")
    
    with st.expander("🛠️ Customize Chart", expanded=False):
        cust_title = st.text_input("Chart Title", value=st.session_state.viz_config.get("title", f"📊 {user_q}"))
        
        # Determine defaults purely from data/question without showing
        _, def_type, def_x, def_y, def_c = auto_plot_main(df_main, user_q, show=False)

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            cust_type = st.selectbox("Chart Type", 
                                    ["bar", "line", "scatter", "pie", "histogram", "box", "area", "violin", "heatmap", "treemap"],
                                    index=["bar", "line", "scatter", "pie", "histogram", "box", "area", "violin", "heatmap", "treemap"].index(def_type) if def_type in ["bar", "line", "scatter", "pie", "histogram", "box", "area", "violin", "heatmap", "treemap"] else 0)
            cust_x = st.selectbox("X-Axis", df_main.columns, index=list(df_main.columns).index(def_x) if def_x in df_main.columns else 0)
        with col_c2:
            cust_y = st.selectbox("Y-Axis", df_main.columns, index=list(df_main.columns).index(def_y) if def_y in df_main.columns else 0)
            cust_color = st.selectbox("Color/Group By", ["None"] + list(df_main.columns), index=list(df_main.columns).index(def_c)+1 if def_c in df_main.columns else 0)
        
        cust_scale = st.selectbox("Color Scale", ["Viridis", "Plasma", "Inferno", "Magma", "Cividis", "Rocket", "Mako"], index=0)

    # Render Final Plot
    fig_obj, _, _, _, _ = auto_plot_main(
        df_main, user_q, 
        override_chart_type=cust_type,
        override_x=cust_x,
        override_y=cust_y,
        override_color=None if cust_color == "None" else cust_color,
        override_title=cust_title,
        override_colorscale=cust_scale,
        show=True
    )

    # Save to history & Log only once
    if st.button("💾 Save to History", use_container_width=True):
        if current_user and fig_obj:
            viz_json = fig_obj.to_json()
            add_query_history(
                user_id=current_user['user_id'],
                database_name=db_choice,
                question=user_q,
                sql_query=final_sql,
                viz_json=viz_json
            )
            st.success("✅ Chart and query saved to history!")
            log_event("success", {"question": user_q, "sql": final_sql, "rows": len(df_main)})
        else:
            st.warning("Could not save history. Are you logged in?")