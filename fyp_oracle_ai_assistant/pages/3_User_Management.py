"""
User Management Page - Admin dashboard for user and permission management
"""

import streamlit as st
from datetime import datetime
from session_manager import require_admin, get_current_user
from user_mgmt_utils import (
    list_users_paginated,
    search_users,
    get_user_details,
    create_new_user,
    update_user_info,
    reset_user_password,
    deactivate_user_account,
    delete_user_account,
    update_user_permissions,
    get_user_permissions_matrix,
    get_user_devices,
    revoke_device,
    get_login_audit_log,
)

st.set_page_config(page_title="User Management", page_icon="👥", layout="wide")

# Check admin role
require_admin("user_management_page")

st.title("👥 User Management")
st.markdown("Manage users and their database access permissions")

# Tabs for different sections
tab1, tab2, tab3, tab4 = st.tabs(["👤 Users", "➕ Create New User", "🔐 Audit Log", "⚙️ System Status"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: User List
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.subheader("All Users")

    col_search, col_refresh = st.columns([4, 1])
    with col_search:
        search_query = st.text_input("🔍 Search users (username, email, name)")
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.rerun()

    if search_query:
        users = search_users(search_query)
        st.info(f"Found {len(users)} matching user(s)")
    else:
        page = st.number_input("Page", min_value=1, value=1, step=1)
        users, total_count = list_users_paginated(page=page, per_page=10)
        st.info(f"Showing page {page} ({len(users)} of {total_count} total users)")

    if not users:
        st.warning("No users found")
    else:
        # Display users in columns for better layout
        for user in users:
            with st.expander(f"👤 {user['username']} ({user['role'].upper()})", expanded=False):
                col1, col2, col3 = st.columns([2, 1, 1])

                with col1:
                    st.write(f"**Full Name:** {user['full_name'] or 'N/A'}")
                    st.write(f"**Email:** {user['email'] or 'N/A'}")
                    st.write(f"**Status:** {'✅ Active' if user['is_active'] else '❌ Inactive'}")
                    if user['last_login']:
                        st.write(f"**Last Login:** {user['last_login']}")

                with col2:
                    st.write("**Databases:**")
                    user_details = get_user_details(user['user_id'])
                    if user_details:
                        for db in user_details.get('databases', []):
                            st.write(f"- {db}")

                with col3:
                    st.write("**Actions:**")

                    # Edit button
                    if st.button(f"✏️ Edit", key=f"edit_{user['user_id']}"):
                        st.session_state[f"edit_user_{user['user_id']}"] = True

                # Edit user form
                if st.session_state.get(f"edit_user_{user['user_id']}"):
                    st.write("---")
                    st.write("### Edit User")

                    user_details = get_user_details(user['user_id'])

                    new_full_name = st.text_input(
                        "Full Name",
                        value=user['full_name'] or "",
                        key=f"fullname_{user['user_id']}"
                    )
                    new_email = st.text_input(
                        "Email",
                        value=user['email'] or "",
                        key=f"email_{user['user_id']}"
                    )
                    new_role = st.selectbox(
                        "Role",
                        ["user", "admin"],
                        index=0 if user['role'] == "user" else 1,
                        key=f"role_{user['user_id']}"
                    )

                    # Database permissions
                    st.write("**Database Permissions:**")
                    new_permissions = {}
                    for db_name in ['FYP', 'HR']:
                        current_perms = user_details['permissions'].get(db_name, {}) if user_details else {}
                        col_read, col_export = st.columns([1, 1])
                        with col_read:
                            can_read = st.checkbox(
                                f"{db_name} - Read",
                                value=current_perms.get('can_read', False),
                                key=f"read_{db_name}_{user['user_id']}"
                            )
                        with col_export:
                            can_export = st.checkbox(
                                f"{db_name} - Export",
                                value=current_perms.get('can_export', False),
                                key=f"export_{db_name}_{user['user_id']}"
                            )
                        new_permissions[db_name] = {'can_read': can_read, 'can_export': can_export}

                    # Action buttons
                    col_save, col_reset_pwd, col_deactivate = st.columns([1, 1, 1])

                    with col_save:
                        if st.button("💾 Save", key=f"save_{user['user_id']}"):
                            success, msg = update_user_info(
                                user['user_id'],
                                full_name=new_full_name,
                                email=new_email,
                                role=new_role
                            )
                            if success:
                                success, msg = update_user_permissions(user['user_id'], new_permissions)
                                if success:
                                    st.success("✅ User updated")
                                    st.session_state[f"edit_user_{user['user_id']}"] = False
                                    st.rerun()
                                else:
                                    st.error(f"❌ Permission update failed: {msg}")
                            else:
                                st.error(f"❌ Update failed: {msg}")

                    with col_reset_pwd:
                        if st.button("Reset Password", key=f"resetpwd_{user['user_id']}"):
                            success, temp_pwd = reset_user_password(user['user_id'])
                            if success:
                                st.success(f"Temporary password: `{temp_pwd}`")
                                st.info("Share this password with the user")
                            else:
                                st.error(f"Reset failed: {temp_pwd}")

                    with col_deactivate:
                        if st.button("Deactivate", key=f"deactivate_{user['user_id']}"):
                            success, msg = deactivate_user_account(user['user_id'])
                            if success:
                                st.success("User deactivated")
                                st.rerun()
                            else:
                                st.error(f"Deactivation failed: {msg}")

                    # Delete button - with confirmation warning
                    st.write("---")
                    st.write("**Danger Zone:**")
                    col_confirm, col_delete = st.columns([2, 1])

                    with col_confirm:
                        confirm_delete = st.checkbox(
                            f"Confirm delete user '{user['username']}'",
                            key=f"confirm_delete_{user['user_id']}"
                        )

                    with col_delete:
                        if st.button(
                            "Delete User",
                            key=f"delete_{user['user_id']}",
                            type="secondary",
                            disabled=not confirm_delete
                        ):
                            if confirm_delete:
                                with st.spinner(f"Deleting user {user['username']}..."):
                                    success, msg = delete_user_account(user['user_id'])
                                    if success:
                                        st.success(f"User '{user['username']}' has been deleted")
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to delete user: {msg}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: Create New User
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.subheader("Create New User")

    new_username = st.text_input(
        "Username",
        placeholder="john_doe",
        help="Alphanumeric and underscore only, 3-20 characters"
    )
    new_email = st.text_input(
        "Email",
        placeholder="user@example.com"
    )
    new_full_name = st.text_input(
        "Full Name",
        placeholder="John Doe"
    )
    new_role = st.selectbox(
        "Role",
        ["user", "admin"]
    )

    # Password section
    st.markdown("**Set Password:**")
    password_mode = st.radio(
        "Choose password method:",
        ["Auto-generate temporary", "Set manually"],
        horizontal=True
    )

    new_password = None
    if password_mode == "Set manually":
        new_password = st.text_input(
            "Password",
            type="password",
            placeholder="Enter password (min 8 chars)",
            help="Must be at least 8 characters with uppercase, number, and special char"
        )
        password_confirm = st.text_input(
            "Confirm Password",
            type="password",
            placeholder="Re-enter password"
        )
    else:
        st.info("A temporary password will be auto-generated and shown after user creation")

    st.write("**Assign Databases:**")
    col_fyp, col_hr = st.columns([1, 1])
    with col_fyp:
        fyp_read = st.checkbox("FYP - Read")
        fyp_export = st.checkbox("FYP - Export")
    with col_hr:
        hr_read = st.checkbox("HR - Read")
        hr_export = st.checkbox("HR - Export")

    if st.button("Create User", type="primary", use_container_width=True):
        # Validate inputs
        if not new_username or not new_email:
            st.error("Username and email are required")
        elif password_mode == "Set manually":
            if not new_password:
                st.error("Password is required when manually setting")
            elif new_password != password_confirm:
                st.error("Passwords do not match")
            else:
                # Validate password strength
                from auth_utils import check_password_strength
                is_strong, errors = check_password_strength(new_password)
                if not is_strong:
                    st.error("Password does not meet requirements:")
                    for error in errors:
                        st.write(f"- {error}")
                else:
                    # Create user with manual password
                    with st.spinner("Creating user..."):
                        try:
                            from auth_utils import hash_password
                            password_hash = hash_password(new_password)

                            from auth_db_utils import create_user, USERS_DB_PATH
                            user_id = create_user(
                                username=new_username,
                                password_hash=password_hash,
                                email=new_email,
                                full_name=new_full_name,
                                role=new_role,
                                db_path=USERS_DB_PATH
                            )

                            # Assign databases
                            permissions = {
                                'FYP': {'can_read': fyp_read, 'can_export': fyp_export},
                                'HR': {'can_read': hr_read, 'can_export': hr_export}
                            }
                            perm_success, perm_msg = update_user_permissions(user_id, permissions)

                            st.success(f"User created successfully!")
                            st.info(f"Username: {new_username} | Password: (as you set)")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to create user: {str(e)}")
        else:
            # Auto-generate password
            with st.spinner("Creating user..."):
                success, user_id, temp_password, error = create_new_user(
                    new_username,
                    new_email,
                    new_full_name,
                    role=new_role
                )

                if success:
                    # Assign databases
                    permissions = {
                        'FYP': {'can_read': fyp_read, 'can_export': fyp_export},
                        'HR': {'can_read': hr_read, 'can_export': hr_export}
                    }
                    perm_success, perm_msg = update_user_permissions(user_id, permissions)

                    st.success(f"User created successfully!")
                    st.info(f"Temporary Password: `{temp_password}`")
                    st.warning("Share this password with the user")
                    st.rerun()
                else:
                    st.error(f"Failed to create user: {error}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Audit Log
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader("Login Audit Log")

    col_filter1, col_filter2, col_filter3 = st.columns(3)
    with col_filter1:
        filter_username = st.text_input("Filter by username", "")
    with col_filter2:
        filter_status = st.selectbox(
            "Filter by status",
            ["All", "success", "failed", "token_expired"]
        )
    with col_filter3:
        limit_records = st.number_input("Show last N records", min_value=10, max_value=500, value=100, step=10)

    filters = {}
    if filter_username:
        filters['username'] = filter_username
    if filter_status != "All":
        filters['status'] = filter_status

    audit_log = get_login_audit_log(filters=filters, limit=limit_records)

    if not audit_log:
        st.info("No audit log entries found")
    else:
        st.write(f"Showing {len(audit_log)} entries (most recent first)")

        for entry in audit_log:
            status_emoji = "✅" if entry['login_status'] == 'success' else "❌"
            status_color = "green" if entry['login_status'] == 'success' else "red"

            with st.expander(f"{status_emoji} {entry['username']} - {entry['login_status']} ({entry['logged_at']})"):
                col_left, col_right = st.columns([2, 2])
                with col_left:
                    st.write(f"**Username:** {entry['username']}")
                    st.write(f"**Status:** {entry['login_status']}")
                with col_right:
                    st.write(f"**IP Address:** {entry['ip_address'] or 'N/A'}")
                    st.write(f"**Time:** {entry['logged_at']}")
                if entry['failure_reason']:
                    st.write(f"**Reason:** {entry['failure_reason']}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: System Status
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.subheader("System Status")

    try:
        from auth_db_utils import get_all_users
        all_users = get_all_users()

        col_status1, col_status2, col_status3 = st.columns(3)

        with col_status1:
            active_users = sum(1 for u in all_users if u['is_active'])
            st.metric("Active Users", active_users)

        with col_status2:
            admin_count = sum(1 for u in all_users if u['role'] == 'admin')
            st.metric("Admin Users", admin_count)

        with col_status3:
            regular_users = sum(1 for u in all_users if u['role'] == 'user')
            st.metric("Regular Users", regular_users)

        st.markdown("---")
        st.write("**Database Status:**")

        import os
        users_db_path = os.getenv("USERS_DB_PATH", "users.db")
        if os.path.exists(users_db_path):
            db_size = os.path.getsize(users_db_path)
            st.write(f"✅ users.db exists ({db_size} bytes)")
        else:
            st.warning("⚠️ users.db not found")

    except Exception as e:
        st.error(f"❌ Error loading system status: {e}")

    st.markdown("---")
    st.write("**Current Admin:**")
    current_user = get_current_user()
    if current_user:
        st.write(f"Username: {current_user['username']}")
        st.write(f"Full Name: {current_user['full_name']}")
