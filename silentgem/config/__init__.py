"""
Configuration package for SilentGem
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# Telegram settings
API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION_NAME = os.getenv("SESSION_NAME", "silentgem")

# LLM settings
LLM_ENGINE = os.getenv("LLM_ENGINE", "gemini").lower()  # Options: "gemini" or "ollama"

# Gemini settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Ollama settings
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Translation settings
TARGET_LANGUAGE = os.getenv("TARGET_LANGUAGE", "english")

# File paths
MAPPING_FILE = os.getenv("MAPPING_FILE", "data/mapping.json")
DATA_DIR = Path("data")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

def ensure_dir_exists(directory):
    """Ensure a directory exists, creating it if necessary."""
    Path(directory).mkdir(parents=True, exist_ok=True)
    return directory

def validate_config():
    """Validate that all required configuration is present."""
    if API_ID == 0:
        logger.error("TELEGRAM_API_ID not set in .env file")
        return False
    if not API_HASH:
        logger.error("TELEGRAM_API_HASH not set in .env file")
        return False
    
    # Validate LLM engine specific settings
    if LLM_ENGINE == "gemini":
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not set in .env file")
            return False
    elif LLM_ENGINE == "ollama":
        if not OLLAMA_URL:
            logger.error("OLLAMA_URL not set in .env file")
            return False
        if not OLLAMA_MODEL:
            logger.error("OLLAMA_MODEL not set in .env file")
            return False
    else:
        logger.error(f"Unknown LLM_ENGINE: {LLM_ENGINE}. Must be 'gemini' or 'ollama'")
        return False
        
    return True

def load_mapping():
    """Load the chat mapping from the JSON file."""
    try:
        if not os.path.exists(MAPPING_FILE):
            logger.error(f"Mapping file {MAPPING_FILE} not found")
            return {}
        
        with open(MAPPING_FILE, "r") as f:
            mapping = json.load(f)
        
        # Convert keys to strings (if they're integers)
        return {str(k): str(v) for k, v in mapping.items()}
    except Exception as e:
        logger.error(f"Error loading mapping file: {e}")
        return {} 