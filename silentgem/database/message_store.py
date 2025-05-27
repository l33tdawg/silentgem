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
from typing import List

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
    
    def _extract_key_terms(self, query: str) -> List[str]:
        """
        Extract key terms from a complex query
        
        Args:
            query: The search query
            
        Returns:
            List of key terms to search for
        """
        import re
        
        # Remove common question words and phrases
        stop_words = {
            'what', 'whats', 'what\'s', 'who', 'when', 'where', 'why', 'how', 
            'is', 'are', 'was', 'were', 'the', 'a', 'an', 'and', 'or', 'but',
            'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'about',
            'latest', 'recent', 'new', 'any', 'some', 'all', 'most', 'many',
            'developments', 'updates', 'news', 'information', 'details'
        }
        
        # Clean and split the query
        query = query.lower().strip()
        # Remove punctuation except hyphens and apostrophes
        query = re.sub(r'[^\w\s\'-]', ' ', query)
        words = query.split()
        
        # Filter out stop words and short words
        key_terms = []
        for word in words:
            word = word.strip()
            if len(word) > 2 and word not in stop_words:
                key_terms.append(word)
        
        # If no key terms found, return the original query
        if not key_terms:
            key_terms = [query]
            
        return key_terms

    def search_messages(self, query=None, chat_id=None, chat_ids=None, sender=None, time_period=None, time_range=None, limit=20, fuzzy=False):
        """
        Search messages in the database
        
        Args:
            query: Text to search for (can include OR operators for complex searches)
            chat_id: Filter by a single chat ID (source or target)
            chat_ids: Filter by a list of chat IDs (source or target)
            sender: Filter by sender name
            time_period: Time period to search in (e.g., "today", "yesterday", "week")
            time_range: Tuple of (start_time, end_time) as datetime objects
            limit: Maximum number of results to return
            fuzzy: Whether to use fuzzy matching for the query
            
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
                # Normalize the query - remove extra spaces and lowercase
                query = ' '.join(query.split()).lower()
                
                # Check if we have OR operators in the query
                if " OR " in query:
                    # Split by OR and create a compound query
                    terms = query.split(" OR ")
                    or_conditions = []
                    
                    for term in terms:
                        term = term.strip()
                        if term:
                            # Simplified search for OR terms
                            or_conditions.append("LOWER(content) LIKE ?")
                            params.append(f"%{term.lower()}%")
                    
                    if or_conditions:
                        sql += f" AND ({' OR '.join(or_conditions)})"
                else:
                    # For complex natural language queries, extract key terms
                    key_terms = self._extract_key_terms(query)
                    
                    if len(key_terms) > 1:
                        # Multiple key terms - search for any of them (simplified)
                        term_conditions = []
                        for term in key_terms:
                            term_conditions.append("LOWER(content) LIKE ?")
                            params.append(f"%{term.lower()}%")
                        
                        sql += f" AND ({' OR '.join(term_conditions)})"
                    else:
                        # Single term or simple query - simplified search
                        search_term = key_terms[0] if key_terms else query
                        sql += " AND LOWER(content) LIKE ?"
                        params.append(f"%{search_term.lower()}%")
            
            # Add chat filter
            if chat_ids and isinstance(chat_ids, list) and chat_ids:
                # Handle list of chat IDs
                placeholders = ', '.join(['?'] * len(chat_ids))
                sql += f" AND (source_chat_id IN ({placeholders}) OR target_chat_id IN ({placeholders}))"
                params.extend(chat_ids + chat_ids)  # Add chat_ids twice for both source and target
            elif chat_id:
                # Handle single chat ID
                sql += " AND (source_chat_id = ? OR target_chat_id = ?)"
                params.extend([chat_id, chat_id])
            
            # Add sender filter
            if sender:
                sql += " AND LOWER(sender_name) LIKE ?"
                params.append(f"%{sender.lower()}%")
            
            # Add time filter based on time_range or time_period
            if time_range and isinstance(time_range, tuple) and len(time_range) == 2:
                start_time, end_time = time_range
                if start_time:
                    start_timestamp = int(start_time.timestamp())
                    sql += " AND timestamp >= ?"
                    params.append(start_timestamp)
                if end_time:
                    end_timestamp = int(end_time.timestamp())
                    sql += " AND timestamp <= ?"
                    params.append(end_timestamp)
            elif time_period:
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
            
            # Add fuzzy matching if requested
            if fuzzy and query:
                # Add additional fuzzy conditions
                sql += " OR LOWER(content) LIKE ?"
                params.append(f"%{query.lower().replace(' ', '%')}%")
            
            # Log the constructed query for debugging
            logger.debug(f"Search query: {sql}")
            logger.debug(f"Search params: {params}")
            
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
    
    def get_message_context(self, message_id, source_chat_id=None, before_count=10, after_count=10, cross_chat_context=True):
        """
        Get context messages before and after a specific message
        
        Args:
            message_id: Internal database ID of the message
            source_chat_id: Chat ID to limit context to (optional)
            before_count: Number of messages to retrieve before this message
            after_count: Number of messages to retrieve after this message
            cross_chat_context: Whether to retrieve context across all chats (True) or just the source chat (False)
            
        Returns:
            dict: Dictionary with 'before' and 'after' lists of message dictionaries
        """
        try:
            cursor = self.conn.cursor()
            result = {'before': [], 'after': []}
            
            # Get the timestamp of the target message
            cursor.execute('''
            SELECT timestamp, source_chat_id FROM messages WHERE id = ?
            ''', (message_id,))
            
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Cannot get context: Message {message_id} not found")
                return result
                
            target_timestamp, msg_source_chat_id = row
            
            # If source_chat_id not specified, use the message's chat
            if not source_chat_id:
                source_chat_id = msg_source_chat_id
            
            # Get messages before this one
            if before_count > 0:
                if source_chat_id and not cross_chat_context:
                    # Get context only from the same chat
                    cursor.execute('''
                    SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                        sender_id, sender_name, timestamp, content, original_content,
                        source_language, target_language, is_media, media_type, is_forwarded
                    FROM messages
                    WHERE timestamp < ? 
                    AND (source_chat_id = ? OR target_chat_id = ?)
                    ORDER BY timestamp DESC LIMIT ?
                    ''', (target_timestamp, source_chat_id, source_chat_id, before_count))
                else:
                    # Get context from all chats
                    cursor.execute('''
                    SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                        sender_id, sender_name, timestamp, content, original_content,
                        source_language, target_language, is_media, media_type, is_forwarded
                    FROM messages
                    WHERE timestamp < ?
                    ORDER BY timestamp DESC LIMIT ?
                    ''', (target_timestamp, before_count))
                
                # Convert to list of dictionaries
                columns = [col[0] for col in cursor.description]
                before_messages = [dict(zip(columns, row)) for row in cursor.fetchall()]
                
                # Reverse to get chronological order
                result['before'] = list(reversed(before_messages))
            
            # Get messages after this one
            if after_count > 0:
                if source_chat_id and not cross_chat_context:
                    # Get context only from the same chat
                    cursor.execute('''
                    SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                        sender_id, sender_name, timestamp, content, original_content,
                        source_language, target_language, is_media, media_type, is_forwarded
                    FROM messages
                    WHERE timestamp > ? 
                    AND (source_chat_id = ? OR target_chat_id = ?)
                    ORDER BY timestamp ASC LIMIT ?
                    ''', (target_timestamp, source_chat_id, source_chat_id, after_count))
                else:
                    # Get context from all chats
                    cursor.execute('''
                    SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                        sender_id, sender_name, timestamp, content, original_content,
                        source_language, target_language, is_media, media_type, is_forwarded
                    FROM messages
                    WHERE timestamp > ?
                    ORDER BY timestamp ASC LIMIT ?
                    ''', (target_timestamp, after_count))
                
                # Convert to list of dictionaries
                columns = [col[0] for col in cursor.description]
                result['after'] = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.debug(f"Retrieved {len(result['before'])} messages before and {len(result['after'])} messages after message {message_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting message context: {e}")
            return {'before': [], 'after': []}
    
    def get_messages_in_timespan(self, chat_id=None, start_time=None, end_time=None, limit=50):
        """
        Get messages within a specific time range
        
        Args:
            chat_id: Chat ID to filter by (optional)
            start_time: Start timestamp (inclusive)
            end_time: End timestamp (inclusive)
            limit: Maximum number of messages to retrieve
            
        Returns:
            list: List of message dictionaries in the specified timespan
        """
        try:
            cursor = self.conn.cursor()
            params = []
            
            query = '''
            SELECT id, message_id, original_message_id, source_chat_id, target_chat_id,
                sender_id, sender_name, timestamp, content, original_content,
                source_language, target_language, is_media, media_type, is_forwarded
            FROM messages
            WHERE 1=1
            '''
            
            # Apply chat_id filter if provided
            if chat_id:
                query += " AND (source_chat_id = ? OR target_chat_id = ?)"
                params.extend([chat_id, chat_id])
            
            # Apply time range if provided
            if start_time is not None:
                query += " AND timestamp >= ?"
                params.append(start_time)
                
            if end_time is not None:
                query += " AND timestamp <= ?"
                params.append(end_time)
            
            # Order by timestamp and apply limit
            query += " ORDER BY timestamp ASC LIMIT ?"
            params.append(limit)
            
            # Execute query
            cursor.execute(query, params)
            
            # Convert to list of dictionaries
            columns = [col[0] for col in cursor.description]
            messages = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            logger.debug(f"Retrieved {len(messages)} messages in timespan")
            return messages
            
        except Exception as e:
            logger.error(f"Error getting messages in timespan: {e}")
            return []


# Create a singleton instance
_instance = None

def get_message_store():
    """Get the message store singleton instance"""
    global _instance
    if _instance is None:
        _instance = MessageStore()
    return _instance 