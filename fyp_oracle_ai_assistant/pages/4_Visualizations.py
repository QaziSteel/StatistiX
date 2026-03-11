import streamlit as st
import plotly.io as pio
import json
from session_manager import require_auth, get_current_user
from auth_db_utils import get_query_history

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

for item in history:
    with st.expander(f"🕒 {item['created_at']} - {item['question']}", expanded=True):
        st.caption(f"Database: {item['database_name']}")
        
        if item['viz_json']:
            try:
                fig_dict = json.loads(item['viz_json'])
                fig = pio.from_json(item['viz_json'])
                st.plotly_chart(fig, use_container_width=True)
                
                # Download buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    # Export to HTML
                    html_bytes = fig.to_html().encode('utf-8')
                    st.download_button(
                        label="🌐 HTML",
                        data=html_bytes,
                        file_name=f"viz_{item['history_id']}.html",
                        mime="text/html",
                        key=f"dl_html_{item['history_id']}"
                    )
                with col2:
                    # Static PNG image export
                    try:
                        img_bytes = fig.to_image(format="png")
                        st.download_button(
                            label="🖼️ PNG",
                            data=img_bytes,
                            file_name=f"viz_{item['history_id']}.png",
                            mime="image/png",
                            key=f"dl_png_{item['history_id']}"
                        )
                    except Exception as img_err:
                        st.error(f"Image export error: {img_err}")
                with col3:
                    st.code(item['sql_query'], language="sql")
            except Exception as e:
                st.error(f"Failed to render visualization: {e}")
        else:
            st.warning("No visualization available for this query.")
            st.code(item['sql_query'], language="sql")

        st.markdown("---")
