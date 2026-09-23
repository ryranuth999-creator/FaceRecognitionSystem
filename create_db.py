import sys
from pathlib import Path

# Add root folder to python path
sys.path.append(str(Path(__file__).resolve().parent))

from app.core.config import settings
from app.core.database import init_db

def main():
    backend = settings.DB_BACKEND
    db_name = settings.DB_NAME

    if backend == "mysql":
        import pymysql
        print(f"Connecting to MySQL server at {settings.DB_SERVER}:{settings.DB_PORT}...")
        try:
            conn = pymysql.connect(
                host=settings.DB_SERVER,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD
            )
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
                conn.commit()
                print(f"[OK] MySQL Database '{db_name}' verified/created.")
            finally:
                conn.close()
        except Exception as e:
            print(f"[ERROR] Failed to connect or create MySQL database: {e}")
            print("Please ensure your MySQL server is running and the credentials in .env are correct.")
            sys.exit(1)

    elif backend == "mssql":
        import pyodbc
        print(f"Connecting to SQL Server at {settings.DB_SERVER}:{settings.DB_PORT}...")
        try:
            conn_str = (
                f"DRIVER={{{settings.DB_DRIVER}}};"
                f"SERVER={settings.DB_SERVER},{settings.DB_PORT};"
                f"DATABASE=master;"
                f"UID={settings.DB_USER};"
                f"PWD={settings.DB_PASSWORD};"
                f"TrustServerCertificate=yes;"
            )
            conn = pyodbc.connect(conn_str, autocommit=True)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"SELECT db_id('{db_name}')")
                    db_id = cursor.fetchone()[0]
                    if db_id is None:
                        cursor.execute(f"CREATE DATABASE {db_name}")
                        print(f"[OK] SQL Server Database '{db_name}' created.")
                    else:
                        print(f"[OK] SQL Server Database '{db_name}' already exists.")
            finally:
                conn.close()
        except Exception as e:
            print(f"[ERROR] Failed to connect or create SQL Server database: {e}")
            print("Please ensure SQL Server is running, pyodbc is installed, and credentials in .env are correct.")
            sys.exit(1)

    elif backend == "sqlite":
        print(f"[INFO] Using SQLite database at '{settings.SQLITE_PATH}' (automatically created by SQLAlchemy).")

    # Run SQLAlchemy metadata creation
    print("Initializing database tables via SQLAlchemy...")
    try:
        init_db()
        print("[SUCCESS] Database tables initialized successfully!")
        
        # Seed default admin user
        from app.core.database import SessionLocal
        from app.models.user import User
        from app.core.security import hash_password
        
        db = SessionLocal()
        try:
            admin_user = db.query(User).filter(User.EmployeeID == "admin").first()
            if not admin_user:
                print("Seeding default admin user...")
                new_admin = User(
                    EmployeeID="admin",
                    FullName="System Administrator",
                    Role="admin",
                    Status="active",
                    HashedPassword=hash_password("admin")
                )
                db.add(new_admin)
                db.commit()
                print("[SUCCESS] Default admin user seeded successfully!")
                print(" -> Username: admin")
                print(" -> Password: admin")
            else:
                print("[INFO] Default admin user already exists.")
        finally:
            db.close()

    except Exception as e:
        print(f"[ERROR] Failed to initialize tables or seed admin: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
