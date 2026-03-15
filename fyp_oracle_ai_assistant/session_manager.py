"""
Session management for Streamlit authentication.
Manages session state and provides auth guards for pages.
"""

import streamlit as st
from datetime import datetime
from typing import Optional, Dict
from auth_db_utils import (
    get_user_by_id,
    get_user_databases,
    update_last_login,
    verify_device_token,
)
from device_utils import load_device_token_local


def init_session_state() -> None:
    """
    Initialize session state variables for authentication.
    Called once per session.
    """
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.session_state.username = None
        st.session_state.full_name = None
        st.session_state.email = None
        st.session_state.role = None
        st.session_state.assigned_databases = []
        st.session_state.login_time = None
        st.session_state.device_token = None


def check_authentication() -> bool:
    """
    Check if user is currently authenticated.
    If not authenticated, tries to auto-login using device token.

    Returns:
        True if authenticated, False otherwise
    """
    init_session_state()

    # Already authenticated in this session
    if st.session_state.authenticated and st.session_state.user_id:
        return True

    # Try to load device token and auto-login
    # This is checked on page load before any auth-required content
    return _try_device_token_login()


def _try_device_token_login() -> bool:
    """
    Attempt to login using saved device token.

    Returns:
        True if device token login successful
    """
    # Try to find saved token in browser
    try:
        # We can't directly access browser storage from server-side Streamlit
        # Instead, we rely on the 0_Login.py page to set the device token
        # This function validates if token is still valid in database
        return False  # Will be handled by login page
    except Exception:
        return False


def set_authenticated(user_id: int, username: str, full_name: str, email: str, role: str, device_token: str = None) -> None:
    """
    Mark user as authenticated and set session variables.

    Args:
        user_id: User ID
        username: Username
        full_name: Full name
        email: Email
        role: Role ('admin' or 'user')
        device_token: Device token (if authenticated via token)
    """
    st.session_state.authenticated = True
    st.session_state.user_id = user_id
    st.session_state.username = username
    st.session_state.full_name = full_name
    st.session_state.email = email
    st.session_state.role = role
    st.session_state.login_time = datetime.utcnow()
    st.session_state.device_token = device_token
    st.session_state.assigned_databases = get_user_databases(user_id)

    # Update last login timestamp
    update_last_login(user_id)


def get_current_user() -> Optional[Dict]:
    """
    Get current logged-in user data.

    Returns:
        User dict or None if not authenticated
    """
    if not st.session_state.get('authenticated'):
        return None

    return {
        'user_id': st.session_state.user_id,
        'username': st.session_state.username,
        'full_name': st.session_state.full_name,
        'email': st.session_state.email,
        'role': st.session_state.role,
        'assigned_databases': st.session_state.assigned_databases,
        'login_time': st.session_state.login_time,
    }


def require_auth(page_name: str, required_role: Optional[str] = None) -> bool:
    """
    Guard function to require authentication on a page.
    If not authenticated, redirects to login page.

    Args:
        page_name: Name of page (for logging)
        required_role: Required role ('admin', 'user', or None for any)

    Returns:
        True if authorized, False otherwise (page should not render)

    Usage:
        At the top of your page:
        from session_manager import require_auth
        require_auth("page_name", required_role="admin")
    """
    init_session_state()

    # Check if authenticated
    if not st.session_state.get('authenticated'):
        st.warning("⚠️ Please log in to access this page.")
        st.switch_page("pages/0_Login.py")
        return False

    # Check role if specified
    if required_role and st.session_state.role != required_role:
        st.error(f"❌ This page requires {required_role} privileges.")
        st.switch_page("main_app.py")
        return False

    # Hide User Management tab for non-admins gracefully
    if st.session_state.role != 'admin':
        st.markdown(
            """
            <style>
                [data-testid="stSidebarNav"] a[href*="User_Management"] {
                    display: none !important;
                }
            </style>
            """,
            unsafe_allow_html=True
        )

    return True


def require_admin(page_name: str) -> bool:
    """
    Guard function to require admin role.

    Args:
        page_name: Name of page (for logging)

    Returns:
        True if authenticated as admin
    """
    return require_auth(page_name, required_role='admin')


def logout_user() -> None:
    """
    Log out current user.
    Clears session state and revokes local device token.
    """
    user_id = st.session_state.get('user_id')
    username = st.session_state.get('username')
    device_token = st.session_state.get('device_token')

    # Revoke device token in database if exists
    if device_token:
        try:
            from auth_db_utils import revoke_device_token
            revoke_device_token(device_token)
        except Exception:
            pass

    # Revoke local token
    if username:
        try:
            from device_utils import revoke_local_token
            revoke_local_token(username)
        except Exception:
            pass

    # Clear session state
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.username = None
    st.session_state.full_name = None
    st.session_state.email = None
    st.session_state.role = None
    st.session_state.assigned_databases = []
    st.session_state.login_time = None
    st.session_state.device_token = None

    # Redirect to login
    st.switch_page("pages/0_Login.py")
