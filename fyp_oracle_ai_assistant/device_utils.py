"""
Device utilities for local token storage and device fingerprinting.
Handles encrypted persistent login tokens.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict
from cryptography.fernet import Fernet
import hashlib


def get_token_file_path() -> Path:
    """
    Get the path to the local tokens file.

    Windows: C:\\Users\\{username}\\AppData\\Local\\Streamlit\\auth_tokens.json
    Linux/Mac: ~/.streamlit/auth_tokens.json

    Returns:
        Path to auth_tokens.json
    """
    if os.name == 'nt':  # Windows
        app_data = os.getenv('LOCALAPPDATA', os.path.expanduser('~'))
        token_dir = Path(app_data) / 'Streamlit'
    else:  # Linux/Mac
        token_dir = Path.home() / '.streamlit'

    token_dir.mkdir(parents=True, exist_ok=True)
    return token_dir / 'auth_tokens.json'


def get_encryption_key(username: str) -> bytes:
    """
    Derive encryption key from username and device fingerprint.
    Uses SHA256 to create a key for Fernet encryption.

    Args:
        username: Username to derive key from

    Returns:
        Fernet-compatible encryption key (base64 encoded bytes)
    """
    import platform
    device_info = f"{username}_{platform.system()}_{platform.node()}"
    key_hash = hashlib.sha256(device_info.encode()).digest()
    # Fernet key must be 32 bytes, base64 encoded
    import base64
    key = base64.urlsafe_b64encode(key_hash)
    return key


def encrypt_token(token: str, username: str) -> str:
    """
    Encrypt a device token using Fernet encryption.

    Args:
        token: Plain device token
        username: Username (for key derivation)

    Returns:
        Encrypted token string
    """
    try:
        key = get_encryption_key(username)
        f = Fernet(key)
        encrypted = f.encrypt(token.encode())
        return encrypted.decode()
    except Exception as e:
        print(f"Error encrypting token: {e}")
        return None


def decrypt_token(encrypted_token: str, username: str) -> Optional[str]:
    """
    Decrypt a stored encrypted token.

    Args:
        encrypted_token: Encrypted token string
        username: Username (for key derivation)

    Returns:
        Decrypted token or None if decryption fails
    """
    try:
        key = get_encryption_key(username)
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except Exception as e:
        print(f"Error decrypting token: {e}")
        return None


def load_tokens_file() -> Dict:
    """
    Load the tokens file from disk.

    Returns:
        Dict with 'devices' list or empty dict if file doesn't exist
    """
    token_file = get_token_file_path()

    if not token_file.exists():
        return {'devices': []}

    try:
        with open(token_file, 'r') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"Error loading tokens file: {e}")
        return {'devices': []}


def save_tokens_file(data: Dict) -> bool:
    """
    Save tokens to file.

    Args:
        data: Dict with 'devices' list

    Returns:
        True if successful
    """
    token_file = get_token_file_path()

    try:
        with open(token_file, 'w') as f:
            json.dump(data, f, indent=2)
        # Set restrictive permissions (Windows only has limited effect)
        if os.name == 'nt':
            os.chmod(token_file, 0o600)
        return True
    except Exception as e:
        print(f"Error saving tokens file: {e}")
        return False


def save_device_token_local(
    token: str,
    username: str,
    device_name: str = None,
    expires_days: int = 30
) -> bool:
    """
    Save a device token to local file (encrypted).

    Args:
        token: Device token to save
        username: Username
        device_name: Name of device
        expires_days: Expiration in days

    Returns:
        True if successful
    """
    try:
        # Encrypt the token
        encrypted_token = encrypt_token(token, username)
        if not encrypted_token:
            return False

        # Load existing tokens
        tokens_data = load_tokens_file()

        # Remove any existing token for this username
        tokens_data['devices'] = [
            d for d in tokens_data.get('devices', [])
            if d.get('username') != username
        ]

        # Add new token
        now = datetime.utcnow().isoformat() + 'Z'
        expires_at = (
            (datetime.utcnow().timestamp() + (expires_days * 86400))
            if expires_days else None
        )
        expires_at_str = (
            datetime.utcfromtimestamp(expires_at).isoformat() + 'Z'
            if expires_at else None
        )

        from auth_utils import get_device_fingerprint
        device_fingerprint = get_device_fingerprint()

        tokens_data['devices'].append({
            'username': username,
            'device_token': encrypted_token,
            'device_name': device_name or 'Unknown Device',
            'device_fingerprint': device_fingerprint,
            'saved_at': now,
            'expires_at': expires_at_str
        })

        # Save to file
        return save_tokens_file(tokens_data)

    except Exception as e:
        print(f"Error saving device token: {e}")
        return False


def load_device_token_local(username: str) -> Optional[str]:
    """
    Load and decrypt device token for a user.

    Args:
        username: Username

    Returns:
        Decrypted device token or None
    """
    try:
        tokens_data = load_tokens_file()

        for device in tokens_data.get('devices', []):
            if device.get('username') != username:
                continue

            # Check if token is expired
            expires_at_str = device.get('expires_at')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > expires_at:
                    # Token expired, skip
                    continue

            # Check device fingerprint matches
            from auth_utils import get_device_fingerprint
            device_fingerprint = get_device_fingerprint()
            saved_fingerprint = device.get('device_fingerprint')

            if saved_fingerprint != device_fingerprint:
                # Different device, skip
                continue

            # Decrypt and return
            encrypted_token = device.get('device_token')
            decrypted = decrypt_token(encrypted_token, username)
            return decrypted

        return None

    except Exception as e:
        print(f"Error loading device token: {e}")
        return None


def revoke_local_token(username: str) -> bool:
    """
    Remove device token for a user from local file.

    Args:
        username: Username

    Returns:
        True if successful
    """
    try:
        tokens_data = load_tokens_file()
        tokens_data['devices'] = [
            d for d in tokens_data.get('devices', [])
            if d.get('username') != username
        ]
        return save_tokens_file(tokens_data)
    except Exception as e:
        print(f"Error revoking local token: {e}")
        return False


def clear_all_local_tokens() -> bool:
    """
    Clear all tokens from local file (logout from all devices).

    Returns:
        True if successful
    """
    try:
        return save_tokens_file({'devices': []})
    except Exception as e:
        print(f"Error clearing all tokens: {e}")
        return False


def get_saved_devices() -> Dict[str, str]:
    """
    Get list of saved devices (username -> device_name mapping).

    Returns:
        Dict of username -> device_name
    """
    try:
        tokens_data = load_tokens_file()
        result = {}
        now = datetime.now(timezone.utc)

        for device in tokens_data.get('devices', []):
            username = device.get('username')
            device_name = device.get('device_name', 'Unknown')

            # Check if token not expired
            expires_at_str = device.get('expires_at')
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                    if now > expires_at:
                        continue
                except:
                    pass

            if username:
                result[username] = device_name

        return result
    except Exception as e:
        print(f"Error getting saved devices: {e}")
        return {}
