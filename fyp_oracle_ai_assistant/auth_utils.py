"""
Authentication utilities for password hashing, token generation, and validation.
"""

import os
import secrets
import hashlib
import platform
from typing import Tuple, List
import bcrypt


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt with salt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt-hashed password string
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against its bcrypt hash.

    Args:
        password: Plain text password to verify
        password_hash: Bcrypt hash from database

    Returns:
        True if password matches, False otherwise
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False


def generate_device_token(length: int = 32) -> str:
    """
    Generate a secure random device token.

    Args:
        length: Length of token in bytes

    Returns:
        Secure random hex token
    """
    return secrets.token_hex(length)


def get_device_fingerprint() -> str:
    """
    Get a unique device fingerprint based on hardware/OS info.
    Uses hostname, platform, and Python version for consistency.

    Returns:
        SHA256 hash of device identifying info
    """
    try:
        hostname = os.getenv('COMPUTERNAME', 'unknown')
    except:
        hostname = 'unknown'

    device_info = f"{hostname}_{platform.system()}_{platform.python_version()}"
    fingerprint = hashlib.sha256(device_info.encode()).hexdigest()
    return fingerprint


def check_password_strength(password: str) -> Tuple[bool, List[str]]:
    """
    Validate password strength according to policy.

    Requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 digit
    - At least 1 special character

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
    """
    errors = []

    if len(password) < 8:
        errors.append("Minimum 8 characters required")

    if not any(c.isupper() for c in password):
        errors.append("At least 1 uppercase letter required")

    if not any(c.isdigit() for c in password):
        errors.append("At least 1 digit required")

    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?~"
    if not any(c in special_chars for c in password):
        errors.append("At least 1 special character required")

    return len(errors) == 0, errors


def validate_username(username: str) -> Tuple[bool, str]:
    """
    Validate username format.

    Requirements:
    - Length 3-20 characters
    - Only alphanumeric and underscore
    - Cannot start with number

    Args:
        username: Username to validate

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    if not username:
        return False, "Username is required"

    if len(username) < 3:
        return False, "Username must be at least 3 characters"

    if len(username) > 20:
        return False, "Username must be at most 20 characters"

    if username[0].isdigit():
        return False, "Username cannot start with a number"

    if not all(c.isalnum() or c == '_' for c in username):
        return False, "Username can only contain letters, numbers, and underscores"

    return True, ""


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Basic email validation.

    Args:
        email: Email to validate

    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    if not email:
        return False, "Email is required"

    if len(email) > 254:
        return False, "Email too long"

    if '@' not in email or '.' not in email.split('@')[1]:
        return False, "Invalid email format"

    return True, ""


def validate_token_format(token: str) -> bool:
    """
    Validate device token format (should be hex string).

    Args:
        token: Token to validate

    Returns:
        True if token format is valid
    """
    if not token:
        return False

    try:
        int(token, 16)  # Try to parse as hex
        return len(token) == 64  # Should be 32 bytes = 64 hex chars
    except ValueError:
        return False
