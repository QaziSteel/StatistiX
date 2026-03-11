import pandas as pd
import streamlit as st
import plotly.express as px

def show_chart_builder(df: pd.DataFrame):
    st.subheader("📈 Build a quick chart")
    if df.empty:
        st.info("No data to plot.")
        return

    cols = list(df.columns)
    if not cols:
        st.info("No columns available.")
        return

    x = st.selectbox("X axis", cols, index=0)
    y_candidates = [c for c in cols if c != x]
    if not y_candidates:
        st.info("Need at least two columns to plot.")
        return
    y = st.selectbox("Y axis", y_candidates, index=0)
    chart_type = st.selectbox("Chart type", ["Bar", "Line", "Area", "Scatter"])

    if x and y:
        if chart_type == "Bar":
            fig = px.bar(df, x=x, y=y)
        elif chart_type == "Line":
            fig = px.line(df, x=x, y=y)
        elif chart_type == "Area":
            fig = px.area(df, x=x, y=y)
        else:
            fig = px.scatter(df, x=x, y=y)
        st.plotly_chart(fig, use_container_width=True)

def download_df(df: pd.DataFrame, label: str = "Download CSV"):
    if df.empty:
        return
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label=label, data=csv, file_name="result.csv", mime="text/csv")
