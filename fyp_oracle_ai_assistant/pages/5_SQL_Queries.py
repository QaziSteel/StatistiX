import streamlit as st
from session_manager import require_auth, get_current_user
from auth_db_utils import get_query_history

st.set_page_config(page_title="SQL Query History", layout="wide", page_icon="📜")

# CRITICAL: Check authentication
require_auth("sql_queries_page", required_role=None)

current_user = get_current_user()

st.title("📜 SQL Query History")
st.markdown("Review your previous SQL queries and their natural language questions.")

if not current_user:
    st.error("Please log in to view your history.")
    st.stop()

history = get_query_history(current_user['user_id'], limit=50)

if not history:
    st.info("No query history found. Go to the main app to generate some!")
    st.stop()

st.write(f"Total saved queries: **{len(history)}**")

for item in history:
    with st.expander(f"🕒 {item['created_at']} | ID: {item['history_id']} | {item['question']}", expanded=False):
        st.caption(f"Database: {item['database_name']}")
        st.markdown("**NL Question:**")
        st.info(item['question'])
        
        st.markdown("**Generated SQL:**")
        st.code(item['sql_query'], language="sql")
        
        # Action buttons
        col1, col2 = st.columns(2)
        with col1:
             if st.button("📋 Copy SQL to Clipboard", key=f"copy_{item['history_id']}"):
                 # Streamlit doesn't have a direct "copy to clipboard" button that works without JS components
                 # but showing the code block is usually enough as it has a built-in copy button.
                 st.write("SQL highlighted above. You can use the copy button in the top right of the code block.")
        with col2:
             if st.button("🔄 Use this question again", key=f"reuse_{item['history_id']}"):
                 st.session_state.user_q = item['question']
                 st.success("Question copied to Home page! Navigate back to '🧠 App' to run it.")

        st.markdown("---")
