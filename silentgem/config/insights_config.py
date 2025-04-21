"""
Configuration for the Chat Insights feature
"""

import os
import json
from pathlib import Path
from loguru import logger

from silentgem.config import DATA_DIR, ensure_dir_exists

# Default configuration values
DEFAULT_CONFIG = {
    # Bot settings
    "bot_token": "",
    "bot_username": "",
    "bot_name": "SilentGem Insights",
    "auto_add_bot": True,
    
    # Storage settings
    "message_retention_days": 0,  # 0 = unlimited
    "storage_location": str(Path(DATA_DIR) / "messages.db"),
    "backup_frequency_days": 7,  # Days between backups
    
    # Query processing
    "use_translation_llm": True,  # Use the same LLM as translation
    "alternative_llm_engine": "",  # Only used if use_translation_llm is False
    "query_processing_depth": "standard",  # basic, standard, or detailed
    
    # Privacy settings
    "store_full_content": True,  # Store full message content
    "anonymize_senders": False,  # Anonymize sender information
    "encrypt_sensitive_data": False,  # Encrypt sensitive data
    "auto_purge_enabled": False,  # Automatically purge old messages
    
    # Response formatting
    "response_verbosity": "standard",  # concise, standard, or detailed
    "include_quotes": True,  # Include original message quotes
    "include_timestamps": True,  # Include timestamps
    "include_sender_info": True  # Include sender information
}

# Configuration file path
CONFIG_FILE = os.path.join(DATA_DIR, "insights_config.json")

class InsightsConfig:
    """Configuration manager for Chat Insights"""
    
    def __init__(self):
        """Initialize the configuration"""
        # Ensure the data directory exists
        ensure_dir_exists(DATA_DIR)
        
        # Load or create config
        self.config = self.load_config()
    
    def load_config(self):
        """Load configuration from file or create default"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                
                # Merge with default config to ensure all keys exist
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                
                logger.info("Loaded insights configuration")
                return config
            except Exception as e:
                logger.error(f"Error loading insights configuration: {e}")
                logger.info("Using default configuration")
                return DEFAULT_CONFIG.copy()
        else:
            logger.info("No insights configuration found, using default")
            return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
            logger.info("Saved insights configuration")
            return True
        except Exception as e:
            logger.error(f"Error saving insights configuration: {e}")
            return False
    
    def get(self, key, default=None):
        """Get a configuration value"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """Set a configuration value"""
        self.config[key] = value
        return self.save_config()
    
    def update(self, config_dict):
        """Update multiple configuration values"""
        self.config.update(config_dict)
        return self.save_config()
    
    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self.config = DEFAULT_CONFIG.copy()
        return self.save_config()
    
    def is_configured(self):
        """Check if the insights feature is configured"""
        return bool(self.config.get("bot_token", ""))


# Create a singleton instance
_instance = None

def get_insights_config():
    """Get the insights configuration singleton instance"""
    global _instance
    if _instance is None:
        _instance = InsightsConfig()
    return _instance 

def is_insights_configured():
    """Check if the insights feature is properly configured"""
    config = get_insights_config()
    return config.is_configured() 