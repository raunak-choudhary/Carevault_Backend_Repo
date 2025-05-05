# config.py
import os
from dotenv import load_dotenv

load_dotenv()

API_V1_STR: str = os.getenv("API_V1_STR", "/api")
PROJECT_NAME: str = os.getenv("PROJECT_NAME", "CareVault-Server")

SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")

RAGFLOW_API_URL: str = os.getenv("RAGFLOW_API_URL")
RAGFLOW_API_KEY: str = os.getenv("RAGFLOW_API_KEY")
RAGFLOW_CHAT_ID: str = os.getenv("RAGFLOW_CHAT_ID")
