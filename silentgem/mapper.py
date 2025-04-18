"""
Chat mapping utilities for SilentGem
"""

import os
import json
from pathlib import Path
from loguru import logger

from silentgem.config import MAPPING_FILE, ensure_dir_exists

class ChatMapper:
    """Manage chat mappings between source and target chats"""
    
    def __init__(self):
        """Initialize the chat mapper"""
        self.mapping_file = MAPPING_FILE
        ensure_dir_exists(os.path.dirname(self.mapping_file))
        
        # Initialize state tracking file for message IDs
        self.state_file = str(Path(os.path.dirname(self.mapping_file)) / "message_state.json")
        
        # Load mappings and state
        self.mappings = self._load_mappings()
        self.message_state = self._load_message_state()
    
    def _load_mappings(self):
        """Load mappings from file"""
        if not os.path.exists(self.mapping_file):
            # Create empty mapping file
            with open(self.mapping_file, 'w') as f:
                json.dump({}, f, indent=2)
            return {}
        
        try:
            with open(self.mapping_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in {self.mapping_file}")
            return {}
        except Exception as e:
            logger.error(f"Error reading {self.mapping_file}: {e}")
            return {}
    
    def _save_mappings(self):
        """Save mappings to file"""
        try:
            with open(self.mapping_file, 'w') as f:
                json.dump(self.mappings, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving mappings to {self.mapping_file}: {e}")
            return False
    
    def _load_message_state(self):
        """Load message state from file"""
        if not os.path.exists(self.state_file):
            # Create empty state file
            with open(self.state_file, 'w') as f:
                json.dump({}, f, indent=2)
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in {self.state_file}")
            return {}
        except Exception as e:
            logger.error(f"Error reading {self.state_file}: {e}")
            return {}
    
    def _save_message_state(self):
        """Save message state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.message_state, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving message state to {self.state_file}: {e}")
            return False
    
    def get_all(self):
        """Get all mappings"""
        return self.mappings
    
    def get_message_state(self):
        """Get all message states"""
        return self.message_state
    
    def get_last_message_id(self, source_id):
        """Get the last processed message ID for a source chat"""
        source_id = str(source_id)
        return self.message_state.get(source_id, 0)
    
    def update_last_message_id(self, source_id, message_id):
        """Update the last processed message ID for a source chat"""
        source_id = str(source_id)
        message_id = int(message_id)
        
        # Update only if the new ID is higher
        current_id = self.message_state.get(source_id, 0)
        if message_id > current_id:
            self.message_state[source_id] = message_id
            self._save_message_state()
            logger.debug(f"Updated last message ID for {source_id} to {message_id}")
            return True
        return False
    
    def add(self, source_id, target_id):
        """Add a new mapping"""
        source_id = str(source_id)
        target_id = str(target_id)
        
        self.mappings[source_id] = target_id
        success = self._save_mappings()
        
        # Initialize message state if needed
        if source_id not in self.message_state:
            self.message_state[source_id] = 0
            self._save_message_state()
        
        return success
    
    def remove(self, source_id):
        """Remove a mapping"""
        source_id = str(source_id)
        
        if source_id in self.mappings:
            del self.mappings[source_id]
            
            # Also remove from message state
            if source_id in self.message_state:
                del self.message_state[source_id]
                self._save_message_state()
            
            return self._save_mappings()
        
        return False
    
    def get(self, source_id):
        """Get the target for a source"""
        source_id = str(source_id)
        return self.mappings.get(source_id) 