#!/usr/bin/env python3
"""
Initial admin setup script for FYP Oracle AI Assistant.
Run this once to create the first admin user and initialize the authentication system.

Usage:
    python setup_admin.py
"""

import os
import sys
import getpass
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_db_utils import init_users_db, get_user_by_username, create_user, grant_database_access, USERS_DB_PATH
from auth_utils import hash_password, check_password_strength, validate_username, validate_email


def main():
    """Main setup function."""
    load_dotenv()

    print("=" * 70)
    print(" FYP ORACLE AI ASSISTANT - INITIAL ADMIN SETUP".center(70))
    print("=" * 70)
    print()

    db_path = os.getenv("USERS_DB_PATH", USERS_DB_PATH)

    # Step 1: Initialize database
    print("📊 Step 1: Initializing users database...")
    try:
        init_users_db(db_path)
        print(f"   ✅ Database initialized at: {db_path}")
    except Exception as e:
        print(f"   ❌ Error initializing database: {e}")
        return False

    print()

    # Step 2: Check if admin already exists
    print("🔍 Step 2: Checking for existing admin account...")
    admin = get_user_by_username("admin", db_path)
    if admin:
        print("   ⚠️  Admin account already exists!")
        reset_choice = input("   Would you like to reset the admin password? (yes/no): ").strip().lower()
        if reset_choice == 'yes':
            proceed = True
        else:
            print("   Setup cancelled.")
            return True
    else:
        proceed = True

    if not proceed:
        return True

    print()

    # Step 3: Get admin credentials
    print("📝 Step 3: Enter admin account details")
    print("-" * 70)

    while True:
        username = input("   Username [admin]: ").strip() or "admin"
        is_valid, error_msg = validate_username(username)
        if is_valid:
            # Check if username already exists
            existing = get_user_by_username(username, db_path)
            if existing and username != "admin":
                print(f"   ❌ Username '{username}' already exists. Choose a different one.")
                continue
            break
        else:
            print(f"   ❌ {error_msg}")

    while True:
        email = input("   Email address: ").strip() or "admin@example.com"
        is_valid, error_msg = validate_email(email)
        if is_valid:
            break
        else:
            print(f"   ❌ {error_msg}")

    full_name = input("   Full name: ").strip() or "Administrator"

    # Password with validation
    while True:
        password = getpass.getpass("   Password: ")
        if not password:
            print("   ❌ Password cannot be empty")
            continue

        is_strong, errors = check_password_strength(password)
        if not is_strong:
            print("   ❌ Password does not meet requirements:")
            for error in errors:
                print(f"      - {error}")
            continue

        password_confirm = getpass.getpass("   Confirm password: ")
        if password != password_confirm:
            print("   ❌ Passwords do not match. Try again.")
            continue

        break

    print()

    # Step 4: Create admin user
    print("👤 Step 4: Creating admin user...")
    try:
        password_hash = hash_password(password)

        user_id = create_user(
            username=username,
            password_hash=password_hash,
            email=email,
            full_name=full_name,
            role='admin',
            db_path=db_path
        )
        print(f"   ✅ Admin user created (ID: {user_id})")
    except Exception as e:
        print(f"   ❌ Error creating user: {e}")
        return False

    print()

    # Step 5: Grant database access
    print("🗄️  Step 5: Granting database access...")
    for db_name in ['FYP', 'HR']:
        try:
            grant_database_access(user_id, db_name, can_read=True, can_export=True, db_path=db_path)
            print(f"   ✅ Granted full access to {db_name} database")
        except Exception as e:
            print(f"   ❌ Error granting access to {db_name}: {e}")

    print()
    print("=" * 70)
    print(" ✅ SETUP COMPLETE".center(70))
    print("=" * 70)
    print()
    print("📋 Next steps:")
    print("   1. Start the application: streamlit run App.py")
    print(f"   2. Login with username: {username}")
    print("   3. Create additional users in the 'User Management' section")
    print()
    print("🔐 Security Tips:")
    print("   - Store your admin password securely")
    print("   - Delete or revoke any test accounts before production")
    print("   - Change the OpenAI API key in .env (currently visible in history)")
    print()

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
