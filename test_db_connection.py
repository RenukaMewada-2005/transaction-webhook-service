
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import os

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL is missing from .env")

engine = create_engine(database_url)

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("Database connection successful!")
        print("Test result:", result.scalar())
except Exception as error:
    print("Database connection failed.")
    print(type(error).__name__, str(error))
finally:
    engine.dispose()
