import streamlit as st
import plotly.io as pio
import json
from session_manager import require_auth, get_current_user
from auth_db_utils import get_query_history, delete_query_history
import time

st.set_page_config(page_title="Saved Visualizations", layout="wide", page_icon="📊")

# CRITICAL: Check authentication
require_auth("visualizations_page", required_role=None)

current_user = get_current_user()

st.title("📊 Saved Visualizations")
st.markdown("View and download your previously generated charts.")

if not current_user:
    st.error("Please log in to view your history.")
    st.stop()

history = get_query_history(current_user['user_id'], limit=30)

if not history:
    st.info("No saved visualizations found. Go to the main app to generate some!")
    st.stop()

st.write(f"Total saved visualizations: **{len(history)}**")

for item in history:
    # Use a unique ID in the label to prevent Streamlit from merging expanders
    with st.expander(f"🕒 {item['created_at']} | ID: {item['history_id']} | {item['question']}", expanded=False):
        st.write(f"**Question:** {item['question']}")
        st.caption(f"Database: {item['database_name']} | Timestamp: {item['created_at']}")
        
        if item['viz_json']:
            try:
                fig = pio.from_json(item['viz_json'])
                # High-contrast styling for visibility (same as in App.py)
                fig.update_layout(
                    template="plotly_white",
                    font=dict(color="black"),
                    plot_bgcolor="white", paper_bgcolor="white"
                )
                fig.update_xaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
                fig.update_yaxes(tickfont=dict(color="black"), title_font=dict(color="black"))
                
                st.plotly_chart(fig, use_container_width=True, key=f"chart_hist_{item['history_id']}")
                
                # Download buttons
                col1, col2 = st.columns([1, 3])
                with col1:
                    html_bytes = fig.to_html().encode('utf-8')
                    st.download_button(
                        label="🌐 HTML",
                        data=html_bytes,
                        file_name=f"viz_{item['history_id']}.html",
                        mime="text/html",
                        key=f"dl_html_{item['history_id']}"
                    )
                with col2:
                    st.code(item['sql_query'], language="sql")
            except Exception as e:
                st.error(f"Failed to render visualization: {e}")
        else:
            st.warning("No visualization available for this query.")
            st.code(item['sql_query'], language="sql")

        col1, col2 = st.columns([4, 1])
        with col2:
            if st.button("🗑️ Delete", key=f"del_viz_{item['history_id']}"):
                if delete_query_history(item['history_id'], current_user['user_id']):
                    st.toast("Record deleted successfully!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Failed to delete record.")

        st.markdown("---")
