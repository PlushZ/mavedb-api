import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# TODO Move these to a central config object.
DB_HOST = os.getenv('DB_HOST') or 'localhost'
DB_PORT = os.getenv('DB_PORT') or 5433
DB_DATABASE_NAME = os.getenv('DB_DATABASE_NAME') or 'mavedb'
DB_USERNAME = os.getenv('DB_USERNAME') or 'mave_admin'
DB_PASSWORD = os.getenv('DB_PASSWORD') or 'abc123'

# DB_URL = "sqlite:///./sql_app.db"
DB_URL = f'postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_DATABASE_NAME}'

engine = create_engine(
    # For PostgreSQL:
    DB_URL
    # For SQLite:
    # DB_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
