import sqlite3
import os
from dotenv import load_dotenv
from auth_db_utils import init_users_db, create_user, grant_database_access, USERS_DB_PATH
from auth_utils import hash_password

def restore_admin():
    load_dotenv()
    db_path = os.getenv("USERS_DB_PATH", USERS_DB_PATH)
    
    print(f"Initializing database at {db_path}...")
    init_users_db(db_path)
    
    username = "admin"
    password = "Admin@123"
    email = "admin@example.com"
    full_name = "Administrator"
    
    print(f"Creating admin user '{username}'...")
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
        print(f"✅ Admin user created (ID: {user_id})")
        
        print("Granting database access...")
        for db_name in ['FYP', 'HR']:
            grant_database_access(user_id, db_name, can_read=True, can_export=True, db_path=db_path)
            print(f"✅ Granted access to {db_name}")
            
        print("\n" + "="*40)
        print("RESTORATION COMPLETE")
        print("="*40)
        print(f"Username: {username}")
        print(f"Password: {password}")
        print("="*40)
        
    except sqlite3.IntegrityError:
        print(f"❌ User '{username}' already exists.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    restore_admin()
