import streamlit as st
from session_manager import init_session_state

st.set_page_config(page_title="SQL Generator", layout="wide", page_icon="🧠")

# Initialize session state so we know auth status
init_session_state()

# Define all pages
login_page = st.Page("pages/0_Login.py", title="Login", icon="🔑")
main_page = st.Page("main_app.py", title="SQL Generator", icon="🧠")
forecasting_page = st.Page("pages/2_Forecasting.py", title="Forecasting", icon="📈")
viz_page = st.Page("pages/4_Visualizations.py", title="Saved Visualizations", icon="📊")
sql_page = st.Page("pages/5_SQL_Queries.py", title="SQL Query History", icon="📜")
user_management_page = st.Page("pages/3_User_Management.py", title="User Management", icon="👥")

# Dynamically build the navigation menu
if not st.session_state.get("authenticated"):
    # When not logged in, show Login as first/default
    pages = {
        "Account": [login_page],
        "App": [main_page]
    }
else:
    # When logged in, main app components
    pages = {
        "App": [main_page, forecasting_page, viz_page, sql_page]
    }
    
    # Admin components
    if st.session_state.get("role") == "admin":
        pages["Admin"] = [user_management_page]
        
    # Keep login registered so sign out works smoothly
    pages["Account"] = [login_page]

# Mount navigation router
pg = st.navigation(pages)
pg.run()