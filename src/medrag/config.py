"""Project settings. Reads the API key from the .env file"""

import os
from pathlib import Path

from dotenv import load_dotenv

# The project's main folder (two levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load the values from .env into the environment
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def get_api_key() -> str:
    """Return the OpenAI key, or explain clearly what's missing."""
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or key.startswith("your-"):
        raise RuntimeError("OPENAI_API_KEY is missing. Add your key to the .env file.")
    return key