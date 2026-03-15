import os
import json
import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from dotenv import load_dotenv
import google.generativeai as genai
from sklearn.metrics import mean_absolute_error, mean_squared_error
from session_manager import require_auth, get_current_user
from auth_db_utils import add_query_history
from forecasting_models import run_forecast, get_model

# CRITICAL: Check authentication before rendering anything
require_auth("forecasting_page", required_role=None)

# ─── Configuration ─────────────────────────────────────────────────────────
load_dotenv()
GEMINI_FORECAST_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
client = genai.GenerativeModel(GEMINI_FORECAST_MODEL)



# No custom CSS → using Streamlit default theme

st.title("📈 Price Forecasting & Analysis")
st.markdown("Upload your monthly price data • Ask questions • Generate forecasts")

current_user = get_current_user()

# ─── Core Functions ────────────────────────────────────────────────────────

def safe_list(x, n=60):
    return x[:n] if len(x) > n else x

def df_head_for_llm(df: pd.DataFrame, n=8) -> list:
    return df.head(n).to_dict(orient="records")

def detect_date_col(df: pd.DataFrame) -> str | None:
    preferred = ["date", "ds", "timestamp", "time", "month", "yearmonth"]
    for c in preferred:
        if c in df.columns:
            return c
    best, best_score = None, 0
    for c in df.columns:
        s = pd.to_datetime(df[c], errors="coerce")
        score = s.notna().mean()
        if score > best_score and score > 0.6:
            best_score = score
            best = c
    return best

def detect_target_col(df: pd.DataFrame, date_col: str | None) -> str | None:
    numeric_candidates = []
    for c in df.columns:
        if c == date_col:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().mean() >= 0.75:
            numeric_candidates.append((c, s))
    if not numeric_candidates:
        return None

    target_kw = ["price", "value", "rate", "amount", "cost"]
    avoid_kw = ["fuel", "rain", "temp", "temperature", "humidity", "wind", "qim", "soiltemp", "windspeed"]

    best_col, best_score = None, -1e9
    for c, s in numeric_candidates:
        name = c.lower()
        var_score = np.log1p(float(np.nanstd(s.values) or 0))
        name_score = 3.5 if any(k in name for k in target_kw) else 0
        name_score -= 4.0 if any(k in name for k in avoid_kw) else 0
        score = name_score + var_score
        if score > best_score:
            best_score = score
            best_col = c
    return best_col

def profile_dataset(df: pd.DataFrame) -> dict:
    info = {}
    info["shape"] = df.shape
    info["columns"] = df.columns.tolist()
    info["date_col"] = detect_date_col(df)
    info["y_col"] = detect_target_col(df, info["date_col"])
    info["city_col"] = "city" if "city" in df.columns else None
    info["commodity_col"] = "commodity" if "commodity" in df.columns else None

    if info["date_col"]:
        d = pd.to_datetime(df[info["date_col"]], errors="coerce")
        info["date_min"] = str(d.min().date()) if pd.notna(d.min()) else None
        info["date_max"] = str(d.max().date()) if pd.notna(d.max()) else None

    info["cities"] = sorted(df[info["city_col"]].dropna().unique().astype(str).tolist()) if info.get("city_col") else []
    info["commodities"] = sorted(df[info["commodity_col"]].dropna().unique().astype(str).tolist()) if info.get("commodity_col") else []
    info["numeric_cols"] = df.select_dtypes(include="number").columns.tolist()

    return info

def init_chat():
    if "fc_chat" not in st.session_state:
        st.session_state.fc_chat = [
            {"role": "assistant", "content":
             "👋 Hi there!\n\n"
             "Upload your monthly price CSV and ask me anything:\n\n"
             "• What is the average price of POTATOES in Lahore?\n"
             "• Price of TOMATOES in June 2023?\n"
             "• Forecast ONION prices in Karachi for next 12 months\n\n"
             "I'm ready when you are! 🚀"}
        ]

def prepare_panel_series(df, date_col, y_col, city=None, commodity=None, freq="MS"):
    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col], errors="coerce")
    d[y_col] = pd.to_numeric(d[y_col], errors="coerce")
    d = d.dropna(subset=[date_col, y_col])

    if city and "city" in d.columns:
        d = d[d["city"].astype(str).str.strip() == str(city).strip()]
    if commodity and "commodity" in d.columns:
        d = d[d["commodity"].astype(str).str.strip() == str(commodity).strip()]

    d = d.groupby(date_col, as_index=True)[y_col].mean().sort_index()
    ts = d.asfreq(freq).interpolate(limit_direction="both")
    return ts

def prepare_exog(df, date_col, exog_cols, city=None, commodity=None, freq="MS", index=None):
    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col], errors="coerce")
    d = d.dropna(subset=[date_col])

    if city and "city" in d.columns:
        d = d[d["city"].astype(str).str.strip() == str(city).strip()]
    if commodity and "commodity" in d.columns:
        d = d[d["commodity"].astype(str).str.strip() == str(commodity).strip()]

    for c in exog_cols:
        d[c] = pd.to_numeric(d[c], errors="coerce")

    d = d.groupby(date_col, as_index=True)[exog_cols].mean().sort_index()
    ex = d.asfreq(freq).interpolate(limit_direction="both")

    if index is not None:
        ex = ex.reindex(index).interpolate(limit_direction="both")
    return ex

# ─── Upload & Profile ──────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Upload your monthly price CSV",
    type=["csv"],
    help="Expected columns: date, city, commodity, vegetable_price (or similar)"
)

if uploaded:
    try:
        df = pd.read_csv(uploaded)
        st.session_state.fc_df = df
        st.session_state.fc_profile = profile_dataset(df)
        st.session_state.fc_plan = None
        st.success("✅ File successfully loaded!", icon="🎉")
    except Exception as e:
        st.error(f"Error reading CSV: {str(e)}")

df = st.session_state.get("fc_df")
profile = st.session_state.get("fc_profile")

# ─── Dataset Overview ──────────────────────────────────────────────────────
if df is not None and profile is not None:
    st.subheader("Dataset Overview")

    cols = st.columns(4)

    cols[0].metric("Rows × Cols", f"{profile['shape'][0]:,} × {profile['shape'][1]}")
    cols[1].metric("Date Range", f"{profile.get('date_min', '—')} → {profile.get('date_max', '—')}")
    cols[2].metric("Commodities", len(profile.get("commodities", [])))
    cols[3].metric("Cities", len(profile.get("cities", [])))

    st.markdown("---")

    col_left, col_right = st.columns(2)
    with col_left:
        with st.expander("Commodities"):
            st.write(", ".join(profile.get("commodities", [])) or "None")
    with col_right:
        with st.expander("Cities/Areas"):
            st.write(", ".join(profile.get("cities", [])) or "None")

    st.subheader("Last 10 rows")
    st.dataframe(df.tail(10), use_container_width=True)

    st.divider()
# ─── Main Layout: Settings + Chat ──────────────────────────────────────────
left, right = st.columns([1.4, 1])

with right:
    st.subheader("⚙️ Forecast Controls")
    if df is None:
        st.info("Please upload your CSV file first")
    else:
        date_col = st.selectbox(
            "Date column",
            df.columns,
            index=df.columns.get_loc(profile["date_col"]) if profile["date_col"] in df.columns else 0
        )

        numeric_cols = [
            c for c in df.columns
            if pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.65
        ]
        y_col = st.selectbox(
            "Target Price column",
            numeric_cols,
            index=numeric_cols.index(profile["y_col"]) if profile["y_col"] in numeric_cols else 0
        )

        city_options = ["All"] + profile.get("cities", [])
        city_sel = st.selectbox("City/Area", city_options)
        city = None if city_sel == "All" else city_sel

        comm_options = ["All"] + profile.get("commodities", [])
        comm_sel = st.selectbox("Commodity", comm_options)
        commodity = None if comm_sel == "All" else comm_sel

        horizon = st.slider("Forecast horizon (months)", 1, 60, 12)
        test_pct = st.slider("Test set size (%)", 5, 40, 20)
        model_type = st.selectbox(
            "Model Type", 
            ["SARIMA", "ARIMA", "SARIMAX", "AUTO_ARIMA", "EXP_SMOOTHING", "PROPHET", "XGBOOST", "LIGHTGBM"]
        )

        exog_cols = []
        if model_type in ["SARIMAX", "PROPHET", "XGBOOST", "LIGHTGBM"]:
            candidates = ["qim", "fuel", "rainfall", "temperature", "humidity", "soiltemp", "windspeed"]
            exog_cols = st.multiselect(
                "Exogenous variables",
                [c for c in candidates if c in df.columns]
            )

        run_btn = st.button("🚀 Generate Forecast", type="primary")

with left:
    init_chat()

    for msg in st.session_state.fc_chat:
        avatar = "🧑‍💻" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    user_msg = st.chat_input("Ask about prices or request forecast...")
    if user_msg:
        st.session_state.fc_chat.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)

        # ─── LLM + Auto Price Query Logic ───────────────────────────────────
        dataset_context = ""
        if df is not None and profile is not None:
            dataset_context = f"""
DATASET CONTEXT:
- shape: {profile['shape']}
- date range: {profile.get('date_min')} → {profile.get('date_max')}
- date column: {profile.get('date_col')}
- price column: {profile.get('y_col')}
- sample head: {df_head_for_llm(df, 6)}
- cities: {safe_list(profile.get('cities', []), 40)}
- commodities: {safe_list(profile.get('commodities', []), 40)}
"""

        SYSTEM = """
You are a concise vegetable price assistant.
- For simple price questions (average, specific month/year) → give short, direct answer only.
- For forecast/future requests → output JSON plan in ```json block```.
- Be very brief. No unnecessary text.
"""

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "system", "content": dataset_context} if dataset_context else None,
            *[{"role": m["role"], "content": m["content"]} for m in st.session_state.fc_chat[-10:]]
        ]
        messages = [m for m in messages if m]

        with st.spinner("Thinking..."):
            try:
                # Convert messages to a single prompt for Gemini
                prompt_text = ""
                for msg in messages:
                    prompt_text += msg["content"] + "\n"
                
                resp = client.generate_content(
                    prompt_text,
                    generation_config=genai.types.GenerationConfig(temperature=0.35)
                )
                assistant_text = resp.text.strip()
            except Exception as e:
                assistant_text = f"⚠️ Error contacting model: {str(e)}"

        # ─── Handle Response ────────────────────────────────────────────────
        plan = None
        jm = re.search(r"```json\s*(\{.*?\})\s*```", assistant_text, re.DOTALL | re.IGNORECASE)
        if jm:
            try:
                plan = json.loads(jm.group(1))
            except:
                plan = None

        if plan and plan.get("intent") == "forecast":
            st.session_state.fc_plan = plan
            response = "✅ Forecast plan created!\n\nPress **Generate Forecast** button on the right →"
        else:
            response = assistant_text

            # Auto-detect simple price query
            if any(kw in user_msg.lower() for kw in ["average", "avg", "price in", "how much", "what is the price"]):
                try:
                    qdf = df.copy()
                    comm = next((c for c in profile.get("commodities", []) if c.lower() in user_msg.lower()), None)
                    city_q = next((c for c in profile.get("cities", []) if c.lower() in user_msg.lower()), None)

                    if comm and "commodity" in qdf.columns:
                        qdf = qdf[qdf["commodity"].str.contains(comm, case=False, na=False)]
                    if city_q and "city" in qdf.columns:
                        qdf = qdf[qdf["city"].str.contains(city_q, case=False, na=False)]

                    date_c = profile["date_col"]
                    price_c = profile["y_col"]
                    qdf[date_c] = pd.to_datetime(qdf[date_c], errors="coerce")
                    qdf = qdf.dropna(subset=[date_c, price_c])

                    if not qdf.empty:
                        value = qdf[price_c].mean()
                        count = len(qdf)
                        city_part = f" in {city_q}" if city_q else ""
                        response = f"**Answer:** Average price of **{comm}**{city_part}: **{value:.2f} PKR** (based on {count:,} records)"
                except:
                    pass

        st.session_state.fc_chat.append({"role": "assistant", "content": response})
        st.rerun()

# ─── Forecast Execution ────────────────────────────────────────────────────
if df is not None and profile is not None and run_btn:
    with st.spinner("Running forecast model..."):
        try:
            use_plan = st.session_state.get("fc_plan")

            date_c = date_col
            price_c = y_col
            city_u = city
            comm_u = commodity
            h = horizon
            model = model_type
            m = 12  # monthly seasonality
            exog_u = exog_cols
            test_p = test_pct

            if use_plan:
                date_c = use_plan.get("date_col", date_c)
                price_c = use_plan.get("target_col", price_c)
                city_u = use_plan.get("city", city_u)
                comm_u = use_plan.get("commodity", comm_u)
                h = int(use_plan.get("horizon", h))
                model = use_plan.get("model", model).upper()
                m = int(use_plan.get("m", m))
                exog_u = use_plan.get("exog_cols", []) if use_plan.get("use_exog", False) else []

            ts = prepare_panel_series(df, date_c, price_c, city_u, comm_u)

            exog = None
            exog_fut = None
            if model == "SARIMAX" and exog_u:
                exog = prepare_exog(df, date_c, exog_u, city_u, comm_u, index=ts.index)
                last_row = exog.iloc[-1]
                exog_fut = pd.DataFrame(
                    [last_row.values] * h,
                    columns=exog.columns,
                    index=pd.date_range(ts.index[-1] + pd.offsets.MonthBegin(1), periods=h, freq="MS")
                )

            res, train, test, yhat_test, fc, metrics = run_forecast(
                ts, model, h, m, exog, exog_fut, test_p
            )

            title = f"{comm_u or 'Selected Commodity'} in {city_u or 'All Areas'}"
            
            # Historical trend chart generator
            fig_hist = px.line(ts, title=None)
            fig_hist.update_traces(line=dict(width=2.5))
            fig_hist.update_layout(
                height=400,
                xaxis_title="Date",
                yaxis_title="Price (PKR)"
            )
            
            # Forecast chart generator
            fig = go.Figure()

            fig.add_trace(go.Scatter(x=ts.index, y=ts, name="Historical Data", line=dict(width=2.5)))
            fig.add_trace(go.Scatter(x=train.index, y=train, name="Training"))
            fig.add_trace(go.Scatter(x=test.index, y=test, name="Actual Test"))
            fig.add_trace(go.Scatter(x=test.index, y=yhat_test, name="Predicted Test", line=dict(dash="dot")))

            fc_dates = pd.date_range(ts.index[-1] + pd.offsets.MonthBegin(1), periods=h, freq="MS")
            fig.add_trace(go.Scatter(x=fc_dates, y=fc["mean"], name="Forecast", line=dict(width=4)))
            fig.add_trace(go.Scatter(x=fc_dates, y=fc["mean_ci_upper"], name="Upper 95%"))
            fig.add_trace(go.Scatter(x=fc_dates, y=fc["mean_ci_lower"], name="Lower 95%",
                                    fill="tonexty"))

            fig.update_layout(
                xaxis_title="Date",
                yaxis_title="Price (PKR)",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=600
            )

            # Download CSV Data
            csv_data = fc.to_csv(index=True).encode('utf-8')

            # Save to Session State to prevent disappearing on Save click
            st.session_state.fc_results = {
                "title": title,
                "model": model,
                "fig_hist": fig_hist,
                "fig": fig,
                "metrics": metrics,
                "csv_data": csv_data,
                "h": h,
                "comm_u": comm_u,
                "city_u": city_u
            }

            # Clean plan
            st.session_state.fc_plan = None

        except Exception as e:
            st.error(f"Forecast execution failed: {str(e)}")
            st.session_state.fc_chat.append({"role": "assistant", "content": f"⚠️ Error during forecast: {str(e)}"})

# ─── Render Forecast Results ───────────────────────────────────────────────
if "fc_results" in st.session_state:
    res = st.session_state.fc_results
    
    st.subheader(f"Forecast Result: {res['title']} ({res['model']})")

    # Historical trend
    st.markdown("### Historical Price Trend")
    st.plotly_chart(res['fig_hist'], use_container_width=True)

    # Save Historical Plot Button
    if st.button("💾 Save Historical Trend to History", key="save_hist", use_container_width=True):
        if current_user and res['fig_hist']:
            add_query_history(
                user_id=current_user['user_id'],
                database_name="Forecasting",
                question=f"Historical trend for {res['comm_u'] or 'all'} in {res['city_u'] or 'all'}",
                sql_query=f"-- AI Data Preparation\n-- Filter: City='{res['city_u']}', Commodity='{res['comm_u']}'",
                viz_json=res['fig_hist'].to_json()
            )
            st.success("✅ Historical Trend saved to Visualizations history!")
        else:
            st.warning("Could not save history. Are you logged in?")

    # Forecast plot
    st.markdown("### Forecast with 95% Confidence Interval")
    st.plotly_chart(res['fig'], use_container_width=True)

    # Metrics
    st.markdown("### Model Performance")
    cols = st.columns(3)
    cols[0].metric("MAE (Test)", f"{res['metrics']['MAE']:.2f}")
    cols[1].metric("RMSE (Test)", f"{res['metrics']['RMSE']:.2f}")
    cols[2].metric("Training Points", f"{res['metrics']['n_train']:,}")

    # Download
    st.download_button(
        label="⬇️ Download Forecast CSV",
        data=res['csv_data'],
        file_name=f"forecast_{res['comm_u'] or 'all'}_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

    # Save Forecast Plot button
    if st.button("💾 Save Forecast to History", key="save_forecast", use_container_width=True):
        if current_user and res['fig']:
            add_query_history(
                user_id=current_user['user_id'],
                database_name="Forecasting",
                question=f"Forecast {res['h']} months for {res['comm_u'] or 'all'} in {res['city_u'] or 'all'}",
                sql_query=f"-- AI Forecast Model: {res['model']}\n-- Horizon: {res['h']} months",
                viz_json=res['fig'].to_json()
            )
            st.success("✅ Forecast chart saved to Visualizations history!")
        else:
            st.warning("Could not save history. Are you logged in?")

