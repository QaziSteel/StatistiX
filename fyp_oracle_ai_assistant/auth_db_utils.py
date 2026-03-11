"""
Database utilities for users.db - handles authentication database operations.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv
from auth_utils import hash_password, verify_password

load_dotenv()

USERS_DB_PATH = os.getenv("USERS_DB_PATH", "users.db")


def init_users_db(db_path: str = None) -> None:
    """
    Initialize users.db with schema. Creates tables if they don't exist.

    Args:
        db_path: Path to users.db file
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    # Create parent directory if needed
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'user')),
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)

        # User permissions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                permission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                database_name TEXT NOT NULL CHECK(database_name IN ('FYP', 'HR')),
                can_read BOOLEAN DEFAULT 1,
                can_export BOOLEAN DEFAULT 0,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                UNIQUE(user_id, database_name)
            )
        """)

        # Device tokens table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_tokens (
                token_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                device_token TEXT UNIQUE NOT NULL,
                device_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Query history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                database_name TEXT NOT NULL,
                question TEXT,
                sql_query TEXT,
                viz_json TEXT, -- Serialized Plotly figure
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_permissions_user_id ON user_permissions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_device_tokens_user_id ON device_tokens(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_device_tokens_token ON device_tokens(device_token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_login_audit_user_id ON login_audit(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_login_audit_logged_at ON login_audit(logged_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_query_history_user_id ON query_history(user_id)")

        conn.commit()
    finally:
        conn.close()


def get_user_by_username(username: str, db_path: str = None) -> Optional[Dict]:
    """
    Get user record by username.

    Args:
        username: Username to lookup
        db_path: Path to users.db

    Returns:
        User dict or None if not found
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int, db_path: str = None) -> Optional[Dict]:
    """
    Get user record by ID.

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        User dict or None if not found
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(
    username: str,
    password_hash: str,
    email: str = None,
    full_name: str = None,
    role: str = "user",
    db_path: str = None
) -> int:
    """
    Create a new user.

    Args:
        username: Unique username
        password_hash: Hashed password
        email: Email address
        full_name: Full name
        role: 'admin' or 'user'
        db_path: Path to users.db

    Returns:
        New user ID

    Raises:
        sqlite3.IntegrityError: If username already exists
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, full_name, role)
            VALUES (?, ?, ?, ?, ?)
        """, (username, email, password_hash, full_name, role))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def authenticate_user(username: str, password: str, db_path: str = None) -> Tuple[bool, Optional[Dict]]:
    """
    Authenticate user with username and password.

    Args:
        username: Username
        password: Plain text password
        db_path: Path to users.db

    Returns:
        Tuple of (success: bool, user_dict or None)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    user = get_user_by_username(username, db_path)

    if not user:
        return False, None

    if not user.get('is_active'):
        return False, None

    if verify_password(password, user['password_hash']):
        return True, user

    return False, None


def get_user_databases(user_id: int, db_path: str = None) -> List[str]:
    """
    Get list of databases user has access to.

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        List of database names ('FYP', 'HR', etc.)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # If admin, return all databases
        user = get_user_by_id(user_id, db_path)
        if user and user['role'] == 'admin':
            return ['FYP', 'HR']

        # Otherwise get assigned databases
        cursor.execute("""
            SELECT database_name FROM user_permissions
            WHERE user_id = ? AND can_read = 1
            ORDER BY database_name
        """, (user_id,))

        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def user_has_database_access(user_id: int, database_name: str, db_path: str = None) -> bool:
    """
    Check if user has read access to a database.

    Args:
        user_id: User ID
        database_name: Database name ('FYP', 'HR')
        db_path: Path to users.db

    Returns:
        True if user has access
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    if not os.path.exists(db_path):
        return False

    # Admin has access to all
    user = get_user_by_id(user_id, db_path)
    if user and user['role'] == 'admin':
        return True

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT 1 FROM user_permissions
            WHERE user_id = ? AND database_name = ? AND can_read = 1
        """, (user_id, database_name))

        return cursor.fetchone() is not None
    finally:
        conn.close()


def grant_database_access(
    user_id: int,
    database_name: str,
    can_read: bool = True,
    can_export: bool = False,
    db_path: str = None
) -> bool:
    """
    Grant database access to a user.

    Args:
        user_id: User ID
        database_name: Database name
        can_read: Can read from database
        can_export: Can export data
        db_path: Path to users.db

    Returns:
        True if successful
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT OR REPLACE INTO user_permissions
            (user_id, database_name, can_read, can_export)
            VALUES (?, ?, ?, ?)
        """, (user_id, database_name, can_read, can_export))
        conn.commit()
        return True
    finally:
        conn.close()


def revoke_database_access(user_id: int, database_name: str, db_path: str = None) -> bool:
    """
    Revoke database access from a user.

    Args:
        user_id: User ID
        database_name: Database name
        db_path: Path to users.db

    Returns:
        True if successful
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            DELETE FROM user_permissions
            WHERE user_id = ? AND database_name = ?
        """, (user_id, database_name))
        conn.commit()
        return True
    finally:
        conn.close()


def create_device_token(
    user_id: int,
    device_token: str,
    device_name: str = None,
    ip_address: str = None,
    user_agent: str = None,
    expires_days: int = 30,
    db_path: str = None
) -> str:
    """
    Create a device token for persistent login.

    Args:
        user_id: User ID
        device_token: Secure random token
        device_name: Device identifier
        ip_address: IP address
        user_agent: Browser user agent
        expires_days: Token expiration in days
        db_path: Path to users.db

    Returns:
        The device token
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    expires_at = datetime.utcnow() + timedelta(days=expires_days)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO device_tokens
            (user_id, device_token, device_name, ip_address, user_agent, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, device_token, device_name, ip_address, user_agent, expires_at))
        conn.commit()
        return device_token
    finally:
        conn.close()


def verify_device_token(device_token: str, db_path: str = None) -> Tuple[bool, Optional[Dict]]:
    """
    Verify a device token and return associated user data.

    Args:
        device_token: Device token to verify
        db_path: Path to users.db

    Returns:
        Tuple of (is_valid: bool, user_dict or None)
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    if not os.path.exists(db_path):
        return False, None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        now = datetime.utcnow()

        cursor.execute("""
            SELECT dt.*, u.* FROM device_tokens dt
            JOIN users u ON dt.user_id = u.user_id
            WHERE dt.device_token = ? AND dt.is_active = 1
            AND (dt.expires_at IS NULL OR dt.expires_at > ?)
        """, (device_token, now))

        row = cursor.fetchone()

        if row:
            # Update last_used timestamp
            cursor.execute("""
                UPDATE device_tokens SET last_used = ?
                WHERE device_token = ?
            """, (now, device_token))
            conn.commit()

            return True, dict(row)

        return False, None
    finally:
        conn.close()


def revoke_device_token(device_token: str, db_path: str = None) -> bool:
    """
    Revoke a device token.

    Args:
        device_token: Token to revoke
        db_path: Path to users.db

    Returns:
        True if successful
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE device_tokens SET is_active = 0
            WHERE device_token = ?
        """, (device_token,))
        conn.commit()
        return True
    finally:
        conn.close()


def log_login_attempt(
    username: str,
    success: bool,
    user_id: int = None,
    ip_address: str = None,
    device_token: str = None,
    failure_reason: str = None,
    db_path: str = None
) -> None:
    """
    Log a login attempt to audit trail.

    Args:
        username: Username attempted
        success: Was login successful
        user_id: User ID (if found)
        ip_address: IP address of attempt
        device_token: Device token used (if any)
        failure_reason: Reason for failure
        db_path: Path to users.db
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    if not os.path.exists(db_path):
        return

    status = 'success' if success else ('failed' if not success else 'token_expired')

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO login_audit
            (user_id, username, ip_address, device_token, login_status, failure_reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, ip_address, device_token, status, failure_reason))
        conn.commit()
    finally:
        conn.close()


def get_all_users(db_path: str = None) -> List[Dict]:
    """
    Get all users (admin function).

    Args:
        db_path: Path to users.db

    Returns:
        List of user dicts
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_user(user_id: int, db_path: str = None, **kwargs) -> bool:
    """
    Update user fields.

    Args:
        user_id: User ID
        db_path: Path to users.db
        **kwargs: Fields to update (full_name, email, role, is_active, password_hash)

    Returns:
        True if successful
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    allowed_fields = {'full_name', 'email', 'role', 'is_active', 'password_hash'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return True

    updates['updated_at'] = datetime.utcnow()

    set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [user_id]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", values)
        conn.commit()
        return True
    finally:
        conn.close()


def deactivate_user(user_id: int, db_path: str = None) -> bool:
    """
    Deactivate a user account.

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        True if successful
    """
    return update_user(user_id, db_path, is_active=False)


def delete_user(user_id: int, db_path: str = None) -> bool:
    """
    Delete a user (cascades to permissions and tokens).

    Args:
        user_id: User ID
        db_path: Path to users.db

    Returns:
        True if successful
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def add_query_history(
    user_id: int,
    database_name: str,
    question: str,
    sql_query: str,
    viz_json: str = None,
    db_path: str = None
) -> int:
    """
    Save a successful query and its visualization to history.

    Args:
        user_id: User ID
        database_name: Database name
        question: Natural language question
        sql_query: The final executed SQL
        viz_json: Serialized Plotly figure (JSON string)
        db_path: Path to users.db

    Returns:
        New history record ID
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO query_history (user_id, database_name, question, sql_query, viz_json)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, database_name, question, sql_query, viz_json))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_query_history(user_id: int, limit: int = 50, db_path: str = None) -> List[Dict]:
    """
    Get query history for a specific user.

    Args:
        user_id: User ID
        limit: Max records to return
        db_path: Path to users.db

    Returns:
        List of history records as dicts
    """
    if db_path is None:
        db_path = USERS_DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM query_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_last_login(user_id: int, db_path: str = None) -> None:
    """
    Update user's last login timestamp.

    Args:
        user_id: User ID
        db_path: Path to users.db
    """
    update_user(user_id, db_path, last_login=datetime.utcnow())
