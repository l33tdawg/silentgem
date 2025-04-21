"""
Message storage and retrieval for SilentGem Chat Insights
"""

import sqlite3
import json
import os
from pathlib import Path
from loguru import logger
import time
from datetime import datetime

# Ensure we use the same data directory as the main app
from silentgem.config import DATA_DIR, ensure_dir_exists

# Database file
DB_FILE = os.path.join(DATA_DIR, "messages.db")

class MessageStore:
    """Store and retrieve translated messages for chat insights"""
    
    def __init__(self):
        """Initialize the message store"""
        # Ensure the data directory exists
        ensure_dir_exists(DATA_DIR)
        
        # Initialize the database
        self.conn = None
        self.init_db()
        
    def init_db(self):
        """Initialize the database schema"""
        try:
            self.conn = sqlite3.connect(DB_FILE)
            cursor = self.conn.cursor()
            
            # Create messages table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                message_id INTEGER NOT NULL,
                original_message_id INTEGER NOT NULL,
                source_chat_id TEXT NOT NULL,
                target_chat_id TEXT NOT NULL,
                sender_id TEXT,
                sender_name TEXT,
                timestamp INTEGER NOT NULL,
                content TEXT,
                original_content TEXT,
                source_language TEXT,
                target_language TEXT,
                is_media BOOLEAN DEFAULT 0,
                media_type TEXT,
                is_forwarded BOOLEAN DEFAULT 0
            )
            ''')
            
            # Create indexes for faster querying
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_source_chat 
            ON messages(source_chat_id)
            ''')
            
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_target_chat 
            ON messages(target_chat_id)
            ''')
            
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON messages(timestamp)
            ''')
            
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_content 
            ON messages(content)
            ''')
            
            # Create message entities table for more detailed searching
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_entities (
                id INTEGER PRIMARY KEY,
                message_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_text TEXT NOT NULL,
                FOREIGN KEY (message_id) REFERENCES messages(id)
            )
            ''')
            
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_entity_text 
            ON message_entities(entity_text)
            ''')
            
            self.conn.commit()
            logger.info("Message database initialized")
            
        except Exception as e:
            logger.error(f"Error initializing message database: {e}")
            raise
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
    
    def store_message(self, message_id, original_message_id, source_chat_id, target_chat_id, 
                     sender_id, sender_name, content, original_content, source_language=None, 
                     target_language=None, is_media=False, media_type=None, is_forwarded=False):
        """
        Store a translated message in the database
        
        Args:
            message_id: ID of the translated message
            original_message_id: ID of the original message
            source_chat_id: Source chat ID
            target_chat_id: Target chat ID
            sender_id: Sender's user ID
            sender_name: Sender's name or username
            content: Translated content
            original_content: Original content
            source_language: Source language
            target_language: Target language
            is_media: Whether this is a media message
            media_type: Type of media (photo, video, etc.)
            is_forwarded: Whether the message was forwarded
            
        Returns:
            int: The ID of the stored message
        """
        try:
            cursor = self.conn.cursor()
            
            # Current timestamp
            timestamp = int(time.time())
            
            # Insert message
            cursor.execute('''
            INSERT INTO messages (
                message_id, original_message_id, source_chat_id, target_chat_id,
                sender_id, sender_name, timestamp, content, original_content,
                source_language, target_language, is_media, media_type, is_forwarded
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message_id, original_message_id, source_chat_id, target_chat_id,
                sender_id, sender_name, timestamp, content, original_content,
                source_language, target_language, 1 if is_media else 0, 
                media_type, 1 if is_forwarded else 0
            ))
            
            self.conn.commit()
            message_db_id = cursor.lastrowid
            
            # Extract entities for more detailed searching
            # This could be enhanced in the future with NLP/LLM
            # For now, we'll just extract basic entities like hashtags and mentions
            if content:
                words = content.split()
                for word in words:
                    if word.startswith('#'):
                        # Store hashtag
                        cursor.execute('''
                        INSERT INTO message_entities (message_id, entity_type, entity_text)
                        VALUES (?, ?, ?)
                        ''', (message_db_id, 'hashtag', word[1:]))
                    elif word.startswith('@'):
                        # Store mention
                        cursor.execute('''
                        INSERT INTO message_entities (message_id, entity_type, entity_text)
                        VALUES (?, ?, ?)
                        ''', (message_db_id, 'mention', word[1:]))
                
                self.conn.commit()
            
            logger.debug(f"Stored message {message_id} in database with ID {message_db_id}")
            return message_db_id
            
        except Exception as e:
            logger.error(f"Error storing message: {e}")
            return None
    
    def search_messages(self, query=None, chat_id=None, time_period=None, limit=20):
        """
        Search messages in the database
        
        Args:
            query: Text to search for
            chat_id: Filter by chat ID (source or target)
            time_period: Time period to search in (e.g., "today", "yesterday", "week")
            limit: Maximum number of results to return
            
        Returns:
            list: List of matching messages as dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            # Start with base query
            sql = '''
            SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                sender_id, sender_name, timestamp, content, original_content,
                source_language, target_language, is_media, media_type, is_forwarded
            FROM messages
            WHERE 1=1
            '''
            
            params = []
            
            # Add content search if query provided
            if query:
                sql += " AND (content LIKE ? OR original_content LIKE ?)"
                params.extend([f"%{query}%", f"%{query}%"])
                
                # Also check for entities (hashtags, mentions)
                sql += " OR id IN (SELECT message_id FROM message_entities WHERE entity_text LIKE ?)"
                params.append(f"%{query}%")
            
            # Add chat filter
            if chat_id:
                sql += " AND (source_chat_id = ? OR target_chat_id = ?)"
                params.extend([chat_id, chat_id])
            
            # Add time filter
            if time_period:
                current_time = int(time.time())
                if time_period == "today":
                    # Get timestamp for start of today
                    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    start_timestamp = int(today.timestamp())
                    sql += " AND timestamp >= ?"
                    params.append(start_timestamp)
                elif time_period == "yesterday":
                    # Get timestamp for start of yesterday and today
                    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    yesterday = today.timestamp() - 86400  # 24 hours in seconds
                    sql += " AND timestamp >= ? AND timestamp < ?"
                    params.extend([yesterday, today.timestamp()])
                elif time_period == "week":
                    # Get timestamp for 7 days ago
                    week_ago = current_time - (7 * 86400)
                    sql += " AND timestamp >= ?"
                    params.append(week_ago)
                elif time_period == "month":
                    # Get timestamp for 30 days ago
                    month_ago = current_time - (30 * 86400)
                    sql += " AND timestamp >= ?"
                    params.append(month_ago)
            
            # Add order and limit
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            # Execute query
            cursor.execute(sql, params)
            
            # Convert to list of dictionaries
            columns = [col[0] for col in cursor.description]
            messages = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.debug(f"Found {len(messages)} messages matching search criteria")
            return messages
            
        except Exception as e:
            logger.error(f"Error searching messages: {e}")
            return []
    
    def get_message_by_id(self, message_id, is_original=False):
        """
        Get a message by its ID
        
        Args:
            message_id: ID of the message
            is_original: Whether the ID is for the original message
            
        Returns:
            dict: Message data or None if not found
        """
        try:
            cursor = self.conn.cursor()
            
            if is_original:
                cursor.execute('''
                SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                    sender_id, sender_name, timestamp, content, original_content,
                    source_language, target_language, is_media, media_type, is_forwarded
                FROM messages
                WHERE original_message_id = ?
                ''', (message_id,))
            else:
                cursor.execute('''
                SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                    sender_id, sender_name, timestamp, content, original_content,
                    source_language, target_language, is_media, media_type, is_forwarded
                FROM messages
                WHERE message_id = ?
                ''', (message_id,))
            
            row = cursor.fetchone()
            
            if row:
                columns = [col[0] for col in cursor.description]
                return dict(zip(columns, row))
            return None
            
        except Exception as e:
            logger.error(f"Error getting message by ID: {e}")
            return None
    
    def get_recent_messages(self, chat_id=None, limit=10):
        """
        Get recent messages from the database
        
        Args:
            chat_id: Filter by chat ID (source or target)
            limit: Maximum number of results to return
            
        Returns:
            list: List of recent messages as dictionaries
        """
        try:
            cursor = self.conn.cursor()
            
            if chat_id:
                cursor.execute('''
                SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                    sender_id, sender_name, timestamp, content, original_content,
                    source_language, target_language, is_media, media_type, is_forwarded
                FROM messages
                WHERE source_chat_id = ? OR target_chat_id = ?
                ORDER BY timestamp DESC LIMIT ?
                ''', (chat_id, chat_id, limit))
            else:
                cursor.execute('''
                SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                    sender_id, sender_name, timestamp, content, original_content,
                    source_language, target_language, is_media, media_type, is_forwarded
                FROM messages
                ORDER BY timestamp DESC LIMIT ?
                ''', (limit,))
            
            # Convert to list of dictionaries
            columns = [col[0] for col in cursor.description]
            messages = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.debug(f"Retrieved {len(messages)} recent messages")
            return messages
            
        except Exception as e:
            logger.error(f"Error getting recent messages: {e}")
            return []
    
    def delete_old_messages(self, retention_days):
        """
        Delete messages older than the specified retention period
        
        Args:
            retention_days: Number of days to keep messages
            
        Returns:
            int: Number of deleted messages
        """
        if retention_days <= 0:
            logger.info("Message retention set to unlimited, skipping cleanup")
            return 0
            
        try:
            cursor = self.conn.cursor()
            
            # Calculate cutoff timestamp
            cutoff_time = int(time.time()) - (retention_days * 86400)
            
            # Delete old messages
            cursor.execute('DELETE FROM messages WHERE timestamp < ?', (cutoff_time,))
            deleted_count = cursor.rowcount
            
            # Commit the changes
            self.conn.commit()
            
            logger.info(f"Deleted {deleted_count} messages older than {retention_days} days")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting old messages: {e}")
            return 0
    
    def clear_all_messages(self):
        """
        Clear all stored messages
        
        Returns:
            bool: Success or failure
        """
        try:
            cursor = self.conn.cursor()
            
            # Delete all messages
            cursor.execute('DELETE FROM messages')
            cursor.execute('DELETE FROM message_entities')
            
            # Commit the changes
            self.conn.commit()
            
            logger.info("Cleared all stored messages")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing messages: {e}")
            return False


# Create a singleton instance
_instance = None

def get_message_store():
    """Get the message store singleton instance"""
    global _instance
    if _instance is None:
        _instance = MessageStore()
    return _instance 