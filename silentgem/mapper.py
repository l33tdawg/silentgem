"""
Chat mapping management for SilentGem
"""

import json
import os
from loguru import logger

from silentgem.config import MAPPING_FILE

class ChatMapper:
    """Manages the chat mapping configuration"""
    
    def __init__(self, mapping_file=MAPPING_FILE):
        """Initialize the mapper with the mapping file path"""
        self.mapping_file = mapping_file
        self.mapping = {}
        self.load()
    
    def load(self):
        """Load the mapping from file"""
        try:
            if not os.path.exists(self.mapping_file):
                logger.warning(f"Mapping file {self.mapping_file} not found")
                self.mapping = {}
                return
            
            with open(self.mapping_file, "r") as f:
                self.mapping = json.load(f)
            
            # Convert all keys and values to strings
            self.mapping = {str(k): str(v) for k, v in self.mapping.items()}
            logger.info(f"Loaded {len(self.mapping)} chat mappings")
            
        except Exception as e:
            logger.error(f"Error loading mapping file: {e}")
            self.mapping = {}
    
    def save(self):
        """Save the current mapping to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
            
            with open(self.mapping_file, "w") as f:
                json.dump(self.mapping, f, indent=2)
            
            logger.info(f"Saved {len(self.mapping)} chat mappings")
            
        except Exception as e:
            logger.error(f"Error saving mapping file: {e}")
    
    def add(self, source_chat_id, target_channel_id):
        """Add or update a chat mapping"""
        # Convert to strings
        source_chat_id = str(source_chat_id)
        target_channel_id = str(target_channel_id)
        
        self.mapping[source_chat_id] = target_channel_id
        logger.info(f"Added mapping: {source_chat_id} -> {target_channel_id}")
        self.save()
    
    def remove(self, source_chat_id):
        """Remove a chat mapping"""
        source_chat_id = str(source_chat_id)
        
        if source_chat_id in self.mapping:
            del self.mapping[source_chat_id]
            logger.info(f"Removed mapping for {source_chat_id}")
            self.save()
            return True
        else:
            logger.warning(f"No mapping found for {source_chat_id}")
            return False
    
    def get_all(self):
        """Return all chat mappings"""
        return self.mapping
    
    def get_target(self, source_chat_id):
        """Get the target channel for a source chat"""
        source_chat_id = str(source_chat_id)
        return self.mapping.get(source_chat_id) 