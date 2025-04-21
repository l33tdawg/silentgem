"""
Utilities package for SilentGem
"""

import os
from pathlib import Path
import asyncio
from loguru import logger

def ensure_dir_exists(directory):
    """Ensure a directory exists, creating it if necessary."""
    Path(directory).mkdir(parents=True, exist_ok=True)
    return directory

async def get_chat_info(chat_id):
    """Get information about a chat"""
    try:
        # Dynamically import to avoid circular imports
        from silentgem.client import get_client
        
        # Get client
        client = get_client()
        
        # Get chat
        chat = await client.get_chat(chat_id)
        
        # Extract relevant information
        chat_info = {
            "id": chat.id,
            "title": getattr(chat, "title", None) or getattr(chat, "first_name", f"Unknown Chat ({chat_id})"),
            "type": str(chat.type.name) if hasattr(chat, "type") else "unknown",
            "username": getattr(chat, "username", None)
        }
        
        return chat_info
    except Exception as e:
        logger.error(f"Error getting chat info for {chat_id}: {e}")
        return None 