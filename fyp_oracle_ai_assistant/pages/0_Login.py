"""
Login page - Authentication gateway for the application
"""

import streamlit as st
from dotenv import load_dotenv
from datetime import datetime
from auth_db_utils import authenticate_user, create_device_token, log_login_attempt
from session_manager import init_session_state, set_authenticated, check_authentication
from device_utils import load_device_token_local, save_device_token_local
from auth_utils import verify_password, check_password_strength
import os

load_dotenv()

st.set_page_config(page_title="FYP Oracle AI - Login", page_icon="🔐", layout="centered")

# Initialize session
init_session_state()

# Auto-login with device token on page startup
# Flag prevents re-checking in same session
if not st.session_state.get('_auto_login_checked'):
    st.session_state._auto_login_checked = True

    try:
        from device_utils import get_saved_devices, load_device_token_local
        from auth_db_utils import verify_device_token

        saved_devices = get_saved_devices()

        # Try first saved device
        if saved_devices:
            for device_username in saved_devices.keys():
                try:
                    device_token = load_device_token_local(device_username)

                    if device_token:
                        # Verify token (checks expiration & fingerprint match)
                        is_valid, user_data = verify_device_token(device_token)

                        if is_valid and user_data:
                            # Auto-login successful
                            log_login_attempt(
                                device_username,
                                success=True,
                                user_id=user_data.get('user_id'),
                                device_token=device_token,
                                failure_reason=None
                            )

                            set_authenticated(
                                user_data['user_id'],
                                user_data['username'],
                                user_data['full_name'] or user_data['username'],
                                user_data['email'] or '',
                                user_data['role'],
                                device_token=device_token
                            )

                            st.switch_page("App.py")
                except Exception:
                    continue
    except Exception:
        pass

# If already authenticated, redirect to main app
if st.session_state.get('authenticated'):
    st.switch_page("App.py")

st.title("🔐 FYP Oracle AI Assistant")
st.subheader("Sign In")

# Create two columns for layout
col1, col2 = st.columns([2, 1])

with col1:
    # Check if there are saved devices
    from device_utils import get_saved_devices
    saved_devices = get_saved_devices()

    # Create tabs for login methods
    tab1, tab2 = st.tabs(["💻 Login", "📱 Saved Devices"])

    with tab1:
        st.write("Enter your credentials to sign in")

        # Login form
        username = st.text_input(
            "Username",
            key="login_username",
            placeholder="Enter your username"
        )

        password = st.text_input(
            "Password",
            type="password",
            key="login_password",
            placeholder="Enter your password"
        )

        remember_device = st.checkbox(
            "✓ Remember this device (30 days)",
            value=True,
            help="Device-specific persistent login"
        )

        col_login, col_help = st.columns([2, 1])

        with col_login:
            if st.button("🔓 Sign In", use_container_width=True, type="primary"):
                if not username or not password:
                    st.error("❌ Please enter both username and password")
                else:
                    with st.spinner("Verifying credentials..."):
                        # Authenticate
                        success, user = authenticate_user(username, password)

                        if success:
                            # Generate device token for persistent login
                            device_token = None
                            if remember_device:
                                try:
                                    from auth_utils import generate_device_token
                                    import platform
                                    device_token = generate_device_token()
                                    device_name = f"{platform.node()}"
                                    create_device_token(
                                        user['user_id'],
                                        device_token,
                                        device_name=device_name
                                    )
                                    # Save locally
                                    save_device_token_local(
                                        device_token,
                                        username,
                                        device_name=device_name
                                    )
                                except Exception as e:
                                    st.warning(f"⚠️  Could not save device: {e}")

                            # Log successful login
                            log_login_attempt(
                                username,
                                success=True,
                                user_id=user['user_id'],
                                device_token=device_token,
                                failure_reason=None
                            )

                            # Set authenticated session
                            set_authenticated(
                                user['user_id'],
                                user['username'],
                                user['full_name'] or user['username'],
                                user['email'] or '',
                                user['role'],
                                device_token=device_token
                            )

                            st.success(f"✅ Welcome, {user['full_name'] or user['username']}!")
                            st.balloons()

                            # Redirect to main app
                            import time
                            time.sleep(1)
                            st.switch_page("App.py")

                        else:
                            # Log failed login
                            log_login_attempt(
                                username,
                                success=False,
                                failure_reason="Invalid credentials"
                            )
                            st.error("❌ Invalid username or password")

        with col_help:
            with st.expander("❓ Help"):
                st.write(
                    "Contact your admin for credentials"
                )

    with tab2:
        if saved_devices:
            st.write(f"Found {len(saved_devices)} saved device(s)")

            for device_username, device_name in saved_devices.items():
                col_dev_name, col_dev_login = st.columns([2, 1])

                with col_dev_name:
                    st.write(f"📱 **{device_name}**")
                    st.caption(f"Username: {device_username}")

                with col_dev_login:
                    if st.button(
                        "Sign In",
                        key=f"signin_device_{device_username}",
                        use_container_width=True
                    ):
                        with st.spinner("Signing in with saved device..."):
                            try:
                                # Load device token
                                device_token = load_device_token_local(device_username)

                                if device_token:
                                    # Verify token
                                    from auth_db_utils import verify_device_token
                                    is_valid, user_data = verify_device_token(device_token)

                                    if is_valid:
                                        # Log successful login
                                        log_login_attempt(
                                            device_username,
                                            success=True,
                                            user_id=user_data.get('user_id'),
                                            device_token=device_token,
                                            failure_reason=None
                                        )

                                        # Set authenticated session
                                        set_authenticated(
                                            user_data['user_id'],
                                            user_data['username'],
                                            user_data['full_name'] or user_data['username'],
                                            user_data['email'] or '',
                                            user_data['role'],
                                            device_token=device_token
                                        )

                                        st.success(f"✅ Welcome back, {user_data.get('full_name', device_username)}!")
                                        st.balloons()

                                        import time
                                        time.sleep(1)
                                        st.switch_page("App.py")
                                    else:
                                        # Token expired or invalid
                                        st.error("❌ Device token expired. Please sign in with username.")
                                        # Offer to clear the saved device
                                        if st.button("Clear saved device", key=f"clear_{device_username}"):
                                            from device_utils import revoke_local_token
                                            revoke_local_token(device_username)
                                            st.rerun()
                                else:
                                    st.error("❌ Could not load device token")

                            except Exception as e:
                                st.error(f"❌ Error: {e}")
        else:
            st.info("ℹ️  No saved devices found. Use the Login tab to sign in.")

# Sidebar info
with st.sidebar:
    st.markdown("---")
    st.markdown("### About")
    st.markdown(
        """
        **FYP Oracle AI Assistant**

        Advanced natural language querying with AI-powered forecasting
        """
    )

    st.markdown("---")
    st.markdown("### System Status")

    # Check if users.db exists
    users_db_path = os.getenv("USERS_DB_PATH", "users.db")
    if os.path.exists(users_db_path):
        from auth_db_utils import get_all_users
        try:
            users = get_all_users(users_db_path)
            st.caption(f"✅ {len(users)} users registered")
        except:
            st.caption("⚠️ Database issue")
    else:
        st.caption("⚠️ System not initialized")
        st.info(
            "Run `python setup_admin.py` to initialize the system with your admin account."
        )
