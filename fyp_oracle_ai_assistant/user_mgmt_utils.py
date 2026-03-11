"""
User management utilities for admin operations.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from auth_db_utils import (
    USERS_DB_PATH,
    get_user_by_id,
    get_all_users,
    update_user,
    delete_user,
    get_user_databases,
    grant_database_access,
)
from auth_utils import generate_device_token, hash_password, check_password_strength


def list_users_paginated(page: int = 1, per_page: int = 10, db_path: str = None) -> Tuple[List[Dict], int]:
    """
    Get paginated list of users.

    Args:
        page: Page number (1-indexed)
        per_page: Users per page
        db_path: Path to users.db

    Returns:
        Tuple of (users_list, total_count)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    if not os.path.exists(db_path):
        return [], 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get total count
        cursor.execute("SELECT COUNT(*) as count FROM users")
        total_count = cursor.fetchone()['count']

        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute("""
            SELECT * FROM users
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (per_page, offset))

        users = [dict(row) for row in cursor.fetchall()]
        return users, total_count

    finally:
        conn.close()


def search_users(query: str, db_path: str = None) -> List[Dict]:
    """
    Search users by username or email.

    Args:
        query: Search query
        db_path: Path to users.db

    Returns:
        List of matching users
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        search_pattern = f"%{query}%"
        cursor.execute("""
            SELECT * FROM users
            WHERE username LIKE ? OR email LIKE ? OR full_name LIKE ?
            ORDER BY created_at DESC
        """, (search_pattern, search_pattern, search_pattern))

        return [dict(row) for row in cursor.fetchall()]

    finally:
        conn.close()


def get_user_details(user_id: int, db_path: str = None) -> Optional[Dict]:
    """
    Get detailed user info including permissions.

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        User dict with permissions or None
    """
    user = get_user_by_id(user_id, db_path)
    if not user:
        return None

    # Add databases
    user['databases'] = get_user_databases(user_id, db_path)

    # Add permissions matrix
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT database_name, can_read, can_export
            FROM user_permissions
            WHERE user_id = ?
        """, (user_id,))

        permissions = {}
        for row in cursor.fetchall():
            permissions[row['database_name']] = {
                'can_read': bool(row['can_read']),
                'can_export': bool(row['can_export'])
            }

        user['permissions'] = permissions
        return user

    finally:
        conn.close()


def create_new_user(
    username: str,
    email: str,
    full_name: str,
    role: str = 'user',
    db_path: str = None
) -> Tuple[bool, int, str, str]:
    """
    Create a new user with auto-generated temporary password.

    Args:
        username: Username
        email: Email
        full_name: Full name
        role: 'admin' or 'user'
        db_path: Path to users.db

    Returns:
        Tuple of (success: bool, user_id: int, temp_password: str, error_message: str)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    try:
        from auth_utils import validate_username, validate_email

        # Validate username
        valid, msg = validate_username(username)
        if not valid:
            return False, None, None, msg

        # Validate email
        valid, msg = validate_email(email)
        if not valid:
            return False, None, None, msg

        # Generate temporary password
        temp_password = generate_device_token(8)  # 16-char random string
        password_hash = hash_password(temp_password)

        # Create user
        from auth_db_utils import create_user
        user_id = create_user(
            username=username,
            password_hash=password_hash,
            email=email,
            full_name=full_name,
            role=role,
            db_path=db_path
        )

        return True, user_id, temp_password, ""

    except sqlite3.IntegrityError:
        return False, None, None, "Username or email already exists"
    except Exception as e:
        return False, None, None, str(e)


def update_user_info(
    user_id: int,
    full_name: str = None,
    email: str = None,
    role: str = None,
    db_path: str = None
) -> Tuple[bool, str]:
    """
    Update user information.

    Args:
        user_id: User ID
        full_name: Full name
        email: Email
        role: Role
        db_path: Path to users.db

    Returns:
        Tuple of (success: bool, message: str)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    try:
        updates = {}
        if full_name is not None:
            updates['full_name'] = full_name
        if email is not None:
            updates['email'] = email
        if role is not None:
            updates['role'] = role

        if not updates:
            return True, "No updates"

        success = update_user(user_id, db_path, **updates)
        return success, "User updated" if success else "Failed to update"

    except Exception as e:
        return False, str(e)


def reset_user_password(user_id: int, db_path: str = None) -> Tuple[bool, str]:
    """
    Reset user password to new temporary password.

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        Tuple of (success: bool, temp_password: str)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    try:
        temp_password = generate_device_token(8)
        password_hash = hash_password(temp_password)

        success = update_user(user_id, db_path, password_hash=password_hash)
        return success, temp_password if success else ""

    except Exception as e:
        return False, str(e)


def deactivate_user_account(user_id: int, db_path: str = None) -> Tuple[bool, str]:
    """
    Deactivate a user account.

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        Tuple of (success: bool, message: str)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    try:
        from auth_db_utils import deactivate_user
        success = deactivate_user(user_id, db_path)
        return success, "User deactivated" if success else "Failed to deactivate"
    except Exception as e:
        return False, str(e)


def delete_user_account(user_id: int, db_path: str = None) -> Tuple[bool, str]:
    """
    Delete a user account.

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        Tuple of (success: bool, message: str)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    try:
        success = delete_user(user_id, db_path)
        return success, "User deleted" if success else "Failed to delete"
    except Exception as e:
        return False, str(e)


def update_user_permissions(
    user_id: int,
    permissions: Dict[str, Dict[str, bool]],
    db_path: str = None
) -> Tuple[bool, str]:
    """
    Update user database permissions.

    Args:
        user_id: User ID
        permissions: Dict like {'FYP': {'can_read': True, 'can_export': False}, ...}
        db_path: Path to users.db

    Returns:
        Tuple of (success: bool, message: str)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    try:
        for db_name, perms in permissions.items():
            can_read = perms.get('can_read', False)
            can_export = perms.get('can_export', False)

            # If no permissions, revoke
            if not can_read and not can_export:
                from auth_db_utils import revoke_database_access
                revoke_database_access(user_id, db_name, db_path)
            else:
                grant_database_access(user_id, db_name, can_read, can_export, db_path)

        return True, "Permissions updated"

    except Exception as e:
        return False, str(e)


def get_user_permissions_matrix(db_path: str = None) -> Dict[str, Dict[str, Dict[str, bool]]]:
    """
    Get matrix of all users and their database permissions.

    Args:
        db_path: Path to users.db

    Returns:
        Dict like {user_id: {db_name: {can_read, can_export}}}
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    if not os.path.exists(db_path):
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        matrix = {}

        cursor.execute("SELECT * FROM user_permissions")
        for row in cursor.fetchall():
            user_id = row['user_id']
            if user_id not in matrix:
                matrix[user_id] = {}

            matrix[user_id][row['database_name']] = {
                'can_read': bool(row['can_read']),
                'can_export': bool(row['can_export'])
            }

        return matrix

    finally:
        conn.close()


def get_user_devices(user_id: int, db_path: str = None) -> List[Dict]:
    """
    Get active device tokens for a user.

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        List of device dicts
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT token_id, device_name, ip_address, created_at, last_used, expires_at
            FROM device_tokens
            WHERE user_id = ? AND is_active = 1
            ORDER BY last_used DESC
        """, (user_id,))

        return [dict(row) for row in cursor.fetchall()]

    finally:
        conn.close()


def revoke_device(token_id: int, db_path: str = None) -> Tuple[bool, str]:
    """
    Revoke a device token.

    Args:
        token_id: Token ID
        db_path: Path to users.db

    Returns:
        Tuple of (success: bool, message: str)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE device_tokens SET is_active = 0
            WHERE token_id = ?
        """, (token_id,))
        conn.commit()
        return True, "Device revoked"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def get_login_audit_log(
    filters: Dict = None,
    limit: int = 100,
    db_path: str = None
) -> List[Dict]:
    """
    Get login audit log with optional filters.

    Args:
        filters: Dict with optional keys: username, status, user_id, date_from, date_to
        limit: Max records to return
        db_path: Path to users.db

    Returns:
        List of audit log records
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    if not os.path.exists(db_path):
        return []

    filters = filters or {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        query = "SELECT * FROM login_audit WHERE 1=1"
        params = []

        if filters.get('username'):
            query += " AND username LIKE ?"
            params.append(f"%{filters['username']}%")

        if filters.get('status'):
            query += " AND login_status = ?"
            params.append(filters['status'])

        if filters.get('user_id'):
            query += " AND user_id = ?"
            params.append(filters['user_id'])

        query += " ORDER BY logged_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    finally:
        conn.close()
