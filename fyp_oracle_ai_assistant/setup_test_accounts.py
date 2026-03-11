#!/usr/bin/env python3
"""
Auto-setup script for test accounts.
Creates admin and test_user_1 with pre-configured credentials.

Usage:
    python setup_test_accounts.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from auth_db_utils import init_users_db, create_user, grant_database_access, USERS_DB_PATH
from auth_utils import hash_password


def main():
    """Main setup function with pre-configured accounts."""
    load_dotenv()

    print("=" * 70)
    print(" FYP ORACLE AI - AUTO SETUP (TEST ACCOUNTS)".center(70))
    print("=" * 70)
    print()

    db_path = os.getenv("USERS_DB_PATH", USERS_DB_PATH)

    # Step 1: Initialize database
    print("Step 1: Initializing users database...")
    try:
        init_users_db(db_path)
        print(f"   OK: Database initialized at: {db_path}")
    except Exception as e:
        print(f"   ERROR: {e}")
        return False

    print()

    # Define test accounts
    accounts = [
        {
            'username': 'admin',
            'password': 'qazibhai',
            'email': 'admin@example.com',
            'full_name': 'Administrator',
            'role': 'admin',
            'databases': [
                {'name': 'FYP', 'can_read': True, 'can_export': True},
                {'name': 'HR', 'can_read': True, 'can_export': True}
            ]
        },
        {
            'username': 'test_user_1',
            'password': 'test_user_1p',
            'email': 'testuser1@example.com',
            'full_name': 'Test User 1',
            'role': 'user',
            'databases': [
                {'name': 'FYP', 'can_read': True, 'can_export': False}
            ]
        }
    ]

    # Step 2: Create accounts
    print("Step 2: Creating user accounts...")
    for account in accounts:
        try:
            password_hash = hash_password(account['password'])

            user_id = create_user(
                username=account['username'],
                password_hash=password_hash,
                email=account['email'],
                full_name=account['full_name'],
                role=account['role'],
                db_path=db_path
            )
            print(f"   OK: Created {account['role']} account: {account['username']} (ID: {user_id})")

            # Grant database access
            for db in account['databases']:
                grant_database_access(
                    user_id,
                    db['name'],
                    can_read=db['can_read'],
                    can_export=db['can_export'],
                    db_path=db_path
                )
                perms = []
                if db['can_read']:
                    perms.append('read')
                if db['can_export']:
                    perms.append('export')
                perm_str = ', '.join(perms) if perms else 'none'
                print(f"      - {db['name']}: {perm_str}")

        except Exception as e:
            print(f"   ERROR creating account '{account['username']}': {e}")
            return False

    print()
    print("=" * 70)
    print(" SETUP COMPLETE".center(70))
    print("=" * 70)
    print()

    print("Test Accounts Created:")
    print()
    print("   ADMIN ACCOUNT")
    print("      Username: admin")
    print("      Password: qazibhai")
    print("      Access: FYP, HR (all permissions)")
    print()
    print("   TEST USER ACCOUNT")
    print("      Username: test_user_1")
    print("      Password: test_user_1p")
    print("      Access: FYP only (read-only)")
    print()

    print("Next steps:")
    print("   1. Run: streamlit run App.py")
    print("   2. You'll be redirected to login page")
    print("   3. Use one of the accounts above to login")
    print()

    print("Testing Tips:")
    print("   - Login as admin --> see both FYP and HR in database dropdown")
    print("   - Login as test_user_1 --> see only FYP in database dropdown")
    print("   - Admin can access User Management page (sidebar)")
    print()

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
