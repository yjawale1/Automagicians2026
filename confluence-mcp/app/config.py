import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
EMAIL = os.environ["CONFLUENCE_EMAIL"]
API_TOKEN = os.environ["CONFLUENCE_API_TOKEN"]
SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY") or None
