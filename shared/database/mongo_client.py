# shared/database/mongo_client.py
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

_client = None

def get_db():
    global _client
    if _client is None:
        url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
        _client = MongoClient(url, serverSelectionTimeoutMS=3000)
    db_name = os.getenv("DB_NAME", "ration_agent")
    return _client[db_name]