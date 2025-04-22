"""
Conversation memory module for storing and retrieving chat history
to enable contextual follow-up questions in Chat Insights bot
"""

import json
import os
import time
from typing import Dict, List, Optional, Any
from loguru import logger
from dataclasses import dataclass, field, asdict

@dataclass
class Message:
    """Represents a message in a conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Conversation:
    """Represents a conversation between a user and the bot"""
    chat_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    last_activity: int = field(default_factory=int)

class ConversationMemory:
    """
    Manages conversations between users and the bot
    
    Features:
    - Stores conversation history per user/chat
    - Maintains context for follow-up questions
    - Implements time-based conversation expiry
    - Supports serialization/deserialization for persistence
    """
    
    def __init__(self, storage_dir: str = "data", max_history_length: int = 10, 
                conversation_expiry_hours: int = 24):
        """
        Initialize conversation memory
        
        Args:
            storage_dir: Directory to store conversation data
            max_history_length: Maximum number of messages to retain per conversation
            conversation_expiry_hours: Hours after which a conversation is considered expired
        """
        self.storage_dir = os.path.join(storage_dir, "conversations")
        os.makedirs(self.storage_dir, exist_ok=True)
        
        self.max_history_length = max_history_length
        self.conversation_expiry_seconds = conversation_expiry_hours * 3600
        self.conversations: Dict[str, Conversation] = {}
        self.max_conversations = 1000
        self._load_conversations()
    
    def _get_conversation_key(self, chat_id: str, user_id: str) -> str:
        """Generate a unique key for a conversation"""
        return f"{chat_id}:{user_id}"
    
    def _get_storage_path(self, conversation_key: str) -> str:
        """Get the file path for storing a conversation"""
        return os.path.join(self.storage_dir, f"{conversation_key}.json")
    
    def _load_conversations(self) -> None:
        """Load all saved conversations from disk"""
        try:
            for filename in os.listdir(self.storage_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.storage_dir, filename)
                    try:
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                            
                            # Check if conversation has expired
                            last_activity = data.get('last_activity', 0)
                            if time.time() - last_activity > self.conversation_expiry_seconds:
                                # Delete expired conversation file
                                os.remove(file_path)
                                continue
                                
                            # Create conversation object
                            conversation = Conversation(
                                chat_id=data.get('chat_id', ''),
                                user_id=data.get('user_id', ''),
                                last_activity=last_activity
                            )
                            
                            # Create message objects
                            for msg_data in data.get('messages', []):
                                message = Message(
                                    role=msg_data.get('role', ''),
                                    content=msg_data.get('content', ''),
                                    timestamp=msg_data.get('timestamp', 0),
                                    metadata=msg_data.get('metadata', {})
                                )
                                conversation.messages.append(message)
                            
                            # Store in memory
                            conversation_key = self._get_conversation_key(conversation.chat_id, conversation.user_id)
                            self.conversations[conversation_key] = conversation
                    except Exception as e:
                        logger.error(f"Error loading conversation from {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error loading conversations: {e}")
    
    def _save_conversation(self, conversation: Conversation) -> None:
        """Save a conversation to disk"""
        try:
            conversation_key = self._get_conversation_key(conversation.chat_id, conversation.user_id)
            file_path = self._get_storage_path(conversation_key)
            
            # Convert to dictionary
            data = {
                'chat_id': conversation.chat_id,
                'user_id': conversation.user_id,
                'last_activity': conversation.last_activity,
                'context': conversation.context,
                'messages': [asdict(msg) for msg in conversation.messages]
            }
            
            # Save to file
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
    
    def get_conversation(self, chat_id: str, user_id: str) -> Conversation:
        """
        Get or create a conversation for a chat and user
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            
        Returns:
            Conversation object
        """
        conversation_key = self._get_conversation_key(chat_id, user_id)
        
        # Create new conversation if it doesn't exist
        if conversation_key not in self.conversations:
            self.conversations[conversation_key] = Conversation(
                chat_id=chat_id,
                user_id=user_id
            )
            
            # Check if we've exceeded the maximum number of conversations
            if len(self.conversations) > self.max_conversations:
                self._cleanup_old_conversations()
            
        return self.conversations[conversation_key]
    
    def add_message(self, chat_id: str, user_id: str, role: str, content: str, 
                   metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a message to a conversation
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            role: Message role ("user" or "assistant")
            content: Message content
            metadata: Additional metadata about the message
        """
        if role not in ["user", "assistant"]:
            raise ValueError("Role must be 'user' or 'assistant'")
            
        conversation = self.get_conversation(chat_id, user_id)
        
        # Add the message
        message = Message(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        conversation.messages.append(message)
        
        # Trim to max history length
        if len(conversation.messages) > self.max_history_length:
            conversation.messages = conversation.messages[-self.max_history_length:]
        
        # Update timestamp
        conversation.last_activity = int(time.time())
        
        # Save to disk
        self._save_conversation(conversation)
    
    def update_context(self, chat_id: str, user_id: str, context_updates: Dict[str, Any]) -> None:
        """
        Update the context for a conversation
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            context_updates: Dictionary of context updates
        """
        conversation = self.get_conversation(chat_id, user_id)
        
        # Update context
        conversation.context.update(context_updates)
        
        # Update timestamp
        conversation.last_activity = int(time.time())
        
        # Save to disk
        self._save_conversation(conversation)
    
    def get_conversation_history(self, chat_id: str, user_id: str, 
                                max_messages: Optional[int] = None) -> List[Message]:
        """
        Get the message history for a conversation
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            max_messages: Maximum number of messages to return (from most recent)
            
        Returns:
            List of messages
        """
        conversation = self.get_conversation(chat_id, user_id)
        
        if max_messages is not None and max_messages > 0:
            return conversation.messages[-max_messages:]
        
        return conversation.messages
    
    def get_context(self, chat_id: str, user_id: str) -> Dict[str, Any]:
        """
        Get the context for a conversation
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            
        Returns:
            Context dictionary
        """
        conversation = self.get_conversation(chat_id, user_id)
        return conversation.context
    
    def clear_conversation(self, chat_id: str, user_id: str) -> None:
        """
        Clear a conversation's history and context
        
        Args:
            chat_id: Chat ID
            user_id: User ID
        """
        conversation_key = self._get_conversation_key(chat_id, user_id)
        
        # Remove from memory
        if conversation_key in self.conversations:
            del self.conversations[conversation_key]
            
        # Remove from disk
        file_path = self._get_storage_path(conversation_key)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    def clear_all_conversations(self) -> None:
        """Clear all conversations from memory and disk"""
        # Clear memory
        self.conversations = {}
        
        # Clear disk
        for filename in os.listdir(self.storage_dir):
            if filename.endswith('.json'):
                os.remove(os.path.join(self.storage_dir, filename))
                
    def get_format_for_llm(self, chat_id: str, user_id: str, max_history: int = 5) -> List[Dict[str, str]]:
        """
        Get conversation history in a format suitable for LLM context
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            max_history: Maximum number of messages to include
            
        Returns:
            List of message dictionaries in LLM-friendly format
        """
        messages = self.get_conversation_history(chat_id, user_id, max_history)
        
        # Format for LLM
        return [{"role": msg.role, "content": msg.content} for msg in messages]
    
    def _cleanup_old_conversations(self) -> None:
        """
        Clean up old conversations to free up memory
        
        This will remove conversations that haven't been active
        for the expiry time or remove the oldest conversations
        if we've exceeded the maximum limit.
        """
        now = int(time.time())
        active_conversations = {}
        expired_count = 0
        
        # Sort conversations by last activity time
        sorted_conversations = sorted(
            self.conversations.items(),
            key=lambda x: x[1].last_activity,
            reverse=True
        )
        
        # Keep only the most recent conversations up to the limit
        for i, (key, conversation) in enumerate(sorted_conversations):
            # Keep if under the limit and not expired
            if i < self.max_conversations and now - conversation.last_activity < self.conversation_expiry_seconds:
                active_conversations[key] = conversation
            else:
                expired_count += 1
        
        # Replace the conversations dictionary with the active ones
        self.conversations = active_conversations
        
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired conversations")


# Singleton instance
_memory_instance = None

def get_conversation_memory() -> ConversationMemory:
    """Get the singleton conversation memory instance"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ConversationMemory()
    return _memory_instance 