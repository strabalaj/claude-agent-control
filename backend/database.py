from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.models import Base
import os
from pathlib import Path

#DB configs
DB_DIR = Path(__file__).parent.parent / "data"
DB_DIR.mkdir(exist_ok=True) # create directory if needed 
DB_PATH = DB_DIR / "agents.db"
DATABSE_URL = f"sqlite:///{DB_PATH}"

#create engine
engine = create_engine(
    DATABSE_URL,
    connect_args={"check_same_thread" : False}
)

#create session factory
SessionLocal = sessionmaker(autocommit = False, autoflush = False, bind = engine)

#initiaize DB
def init_db():
    Base.metadata.create_all(bind=engine)
    print(f"DB initialized at: {DB_PATH}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()