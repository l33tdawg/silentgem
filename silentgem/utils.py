"""
Utility functions for SilentGem
"""

import os
import asyncio
from pathlib import Path
from loguru import logger
from pyrogram import Client, errors

from silentgem.config import API_ID, API_HASH, SESSION_NAME

async def get_chat_info(chat_id):
    """
    Get information about a chat using the userbot client
    
    Args:
        chat_id: The chat ID to get info for
        
    Returns:
        dict: Chat information or None if not found
    """
    client = Client(
        SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=str(Path("."))
    )
    
    try:
        await client.start()
        chat = await client.get_chat(chat_id)
        
        result = {
            "id": chat.id,
            "type": chat.type,
            "title": getattr(chat, "title", None) or getattr(chat, "first_name", "Unknown"),
            "username": getattr(chat, "username", None),
            "members_count": getattr(chat, "members_count", None),
        }
        
        return result
        
    except errors.RPCError as e:
        logger.error(f"Error getting chat info: {e}")
        return None
    
    finally:
        await client.stop()

def ensure_dir_exists(directory):
    """Ensure a directory exists, creating it if needed"""
    os.makedirs(directory, exist_ok=True)

def format_chat_id(chat_id):
    """Format a chat ID to be recognizable to Telegram"""
    # If it's a channel ID that starts with -100, leave it as is
    if str(chat_id).startswith("-100"):
        return str(chat_id)
    
    # If it's a private chat or basic group, ensure it's just the number
    try:
        # Remove any non-numeric characters except the leading minus sign
        chat_id_str = str(chat_id)
        if chat_id_str.startswith("-"):
            return "-" + "".join(c for c in chat_id_str[1:] if c.isdigit())
        else:
            return "".join(c for c in chat_id_str if c.isdigit())
    except Exception:
        return str(chat_id) 