"""
Search engine for finding messages in the database
"""

from loguru import logger
from typing import List, Dict, Any, Optional
import re
import time
from datetime import datetime

from silentgem.database.message_store import get_message_store
from silentgem.config.insights_config import get_insights_config

class SearchEngine:
    """Search engine for finding messages in the database"""
    
    def __init__(self):
        """Initialize the search engine"""
        self.message_store = get_message_store()
        self.config = get_insights_config()
    
    async def search(self, 
                    query_text: Optional[str] = None, 
                    chat_id: Optional[str] = None,
                    time_period: Optional[str] = None,
                    sender: Optional[str] = None,
                    limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for messages in the database
        
        Args:
            query_text: Text to search for
            chat_id: ID of the chat to search in
            time_period: Time period to search in (today, yesterday, week, month)
            sender: Sender name or ID to filter by
            limit: Maximum number of results to return
            
        Returns:
            list: List of matching messages
        """
        try:
            # Get messages from database
            results = self.message_store.search_messages(
                query=query_text,
                chat_id=chat_id,
                time_period=time_period,
                limit=limit
            )
            
            # Additional filtering for sender if specified
            if sender and results:
                filtered_results = []
                for msg in results:
                    # Case-insensitive partial match for sender name
                    if msg.get("sender_name") and sender.lower() in msg.get("sender_name", "").lower():
                        filtered_results.append(msg)
                    # Match for sender ID
                    elif msg.get("sender_id") and sender == msg.get("sender_id"):
                        filtered_results.append(msg)
                        
                results = filtered_results
            
            # Add relative time strings for easier display
            for msg in results:
                if "timestamp" in msg:
                    msg["relative_time"] = self._get_relative_time(msg["timestamp"])
            
            logger.debug(f"Found {len(results)} messages matching search criteria")
            return results
            
        except Exception as e:
            logger.error(f"Error searching messages: {e}")
            return []
    
    async def get_recent_activity(self, chat_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent activity in a chat
        
        Args:
            chat_id: ID of the chat to get activity for
            limit: Maximum number of messages to return
            
        Returns:
            list: List of recent messages
        """
        try:
            # Get recent messages
            results = self.message_store.get_recent_messages(
                chat_id=chat_id,
                limit=limit
            )
            
            # Add relative time strings for easier display
            for msg in results:
                if "timestamp" in msg:
                    msg["relative_time"] = self._get_relative_time(msg["timestamp"])
            
            logger.debug(f"Retrieved {len(results)} recent messages")
            return results
            
        except Exception as e:
            logger.error(f"Error getting recent activity: {e}")
            return []
    
    def _get_relative_time(self, timestamp: int) -> str:
        """
        Get a human-readable relative time string
        
        Args:
            timestamp: UNIX timestamp
            
        Returns:
            str: Relative time string (e.g., "2 hours ago")
        """
        now = time.time()
        diff = now - timestamp
        
        if diff < 60:
            return "just now"
        elif diff < 3600:
            minutes = int(diff / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff < 604800:
            days = int(diff / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        else:
            # Format as date
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")


# Singleton instance
_instance = None

def get_search_engine():
    """Get the search engine singleton instance"""
    global _instance
    if _instance is None:
        _instance = SearchEngine()
    return _instance 