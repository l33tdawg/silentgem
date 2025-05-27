"""
Conversation memory module for storing and retrieving chat history
to enable contextual follow-up questions in Chat Insights bot
"""

import json
import os
import time
from typing import Dict, List, Optional, Any, Tuple
from loguru import logger
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta

@dataclass
class Message:
    """Represents a message in a conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Enhanced fields for richer context
    query_type: Optional[str] = None  # "search", "analysis", "follow_up", etc.
    search_results_count: Optional[int] = None
    topics_discussed: List[str] = field(default_factory=list)
    entities_mentioned: List[str] = field(default_factory=list)
    time_period_referenced: Optional[str] = None

@dataclass
class ConversationSummary:
    """Summary of conversation themes and context"""
    main_topics: List[str] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    conversation_theme: Optional[str] = None
    user_interests: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    
@dataclass
class Conversation:
    """Represents a conversation between a user and the bot"""
    chat_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    last_activity: int = field(default_factory=int)
    
    # Enhanced conversation tracking
    summary: ConversationSummary = field(default_factory=ConversationSummary)
    conversation_depth: int = 0  # How many exchanges have occurred
    current_topic_thread: Optional[str] = None  # Current discussion thread
    related_searches: List[str] = field(default_factory=list)  # Previous search queries
    insights_provided: List[str] = field(default_factory=list)  # Types of insights given

class ConversationMemory:
    """
    Enhanced conversation memory for rich contextual interactions
    
    Features:
    - Extended conversation history (up to 50 messages by default)
    - Rich context tracking with topics, entities, and themes
    - Conversation summarization for long-term memory
    - Intelligent context retrieval for LLM prompting
    - Topic thread tracking for coherent conversations
    """
    
    def __init__(self, storage_dir: str = "data", max_history_length: int = 50, 
                conversation_expiry_hours: int = 72, enable_summarization: bool = True):
        """
        Initialize enhanced conversation memory
        
        Args:
            storage_dir: Directory to store conversation data
            max_history_length: Maximum number of messages to retain per conversation (increased)
            conversation_expiry_hours: Hours after which a conversation is considered expired (increased)
            enable_summarization: Whether to enable automatic conversation summarization
        """
        self.storage_dir = os.path.join(storage_dir, "conversations")
        os.makedirs(self.storage_dir, exist_ok=True)
        
        self.max_history_length = max_history_length
        self.conversation_expiry_seconds = conversation_expiry_hours * 3600
        self.enable_summarization = enable_summarization
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
                                last_activity=last_activity,
                                conversation_depth=data.get('conversation_depth', 0),
                                current_topic_thread=data.get('current_topic_thread'),
                                related_searches=data.get('related_searches', []),
                                insights_provided=data.get('insights_provided', [])
                            )
                            
                            # Load conversation summary
                            summary_data = data.get('summary', {})
                            conversation.summary = ConversationSummary(
                                main_topics=summary_data.get('main_topics', []),
                                key_entities=summary_data.get('key_entities', []),
                                conversation_theme=summary_data.get('conversation_theme'),
                                user_interests=summary_data.get('user_interests', []),
                                last_updated=summary_data.get('last_updated', time.time())
                            )
                            
                            # Create message objects
                            for msg_data in data.get('messages', []):
                                message = Message(
                                    role=msg_data.get('role', ''),
                                    content=msg_data.get('content', ''),
                                    timestamp=msg_data.get('timestamp', 0),
                                    metadata=msg_data.get('metadata', {}),
                                    query_type=msg_data.get('query_type'),
                                    search_results_count=msg_data.get('search_results_count'),
                                    topics_discussed=msg_data.get('topics_discussed', []),
                                    entities_mentioned=msg_data.get('entities_mentioned', []),
                                    time_period_referenced=msg_data.get('time_period_referenced')
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
                'conversation_depth': conversation.conversation_depth,
                'current_topic_thread': conversation.current_topic_thread,
                'related_searches': conversation.related_searches,
                'insights_provided': conversation.insights_provided,
                'summary': asdict(conversation.summary),
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
                   metadata: Optional[Dict[str, Any]] = None,
                   query_type: Optional[str] = None,
                   search_results_count: Optional[int] = None,
                   topics_discussed: Optional[List[str]] = None,
                   entities_mentioned: Optional[List[str]] = None,
                   time_period_referenced: Optional[str] = None) -> None:
        """
        Add a message to a conversation with enhanced metadata
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            role: Message role ("user" or "assistant")
            content: Message content
            metadata: Additional metadata about the message
            query_type: Type of query (search, analysis, follow_up, etc.)
            search_results_count: Number of search results found
            topics_discussed: List of topics discussed in this message
            entities_mentioned: List of entities mentioned
            time_period_referenced: Time period referenced in the query
        """
        if role not in ["user", "assistant"]:
            raise ValueError("Role must be 'user' or 'assistant'")
            
        conversation = self.get_conversation(chat_id, user_id)
        
        # Add the message with enhanced metadata
        message = Message(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
            query_type=query_type,
            search_results_count=search_results_count,
            topics_discussed=topics_discussed or [],
            entities_mentioned=entities_mentioned or [],
            time_period_referenced=time_period_referenced
        )
        conversation.messages.append(message)
        
        # Update conversation depth
        if role == "user":
            conversation.conversation_depth += 1
        
        # Update conversation summary
        self._update_conversation_summary(conversation, message)
        
        # Trim to max history length
        if len(conversation.messages) > self.max_history_length:
            conversation.messages = conversation.messages[-self.max_history_length:]
        
        # Update timestamp
        conversation.last_activity = int(time.time())
        
        # Save to disk
        self._save_conversation(conversation)
    
    def _update_conversation_summary(self, conversation: Conversation, new_message: Message) -> None:
        """Update conversation summary with information from new message"""
        try:
            # Update topics
            if new_message.topics_discussed:
                for topic in new_message.topics_discussed:
                    if topic not in conversation.summary.main_topics:
                        conversation.summary.main_topics.append(topic)
            
            # Update entities
            if new_message.entities_mentioned:
                for entity in new_message.entities_mentioned:
                    if entity not in conversation.summary.key_entities:
                        conversation.summary.key_entities.append(entity)
            
            # Update related searches for user messages
            if new_message.role == "user" and new_message.query_type == "search":
                if new_message.content not in conversation.related_searches:
                    conversation.related_searches.append(new_message.content)
            
            # Track insights provided
            if new_message.role == "assistant" and new_message.query_type:
                if new_message.query_type not in conversation.insights_provided:
                    conversation.insights_provided.append(new_message.query_type)
            
            # Keep lists manageable
            conversation.summary.main_topics = conversation.summary.main_topics[-20:]
            conversation.summary.key_entities = conversation.summary.key_entities[-30:]
            conversation.related_searches = conversation.related_searches[-15:]
            conversation.insights_provided = conversation.insights_provided[-10:]
            
            conversation.summary.last_updated = time.time()
            
        except Exception as e:
            logger.warning(f"Error updating conversation summary: {e}")

    def update_context(self, chat_id: str, user_id: str, context_updates: Dict[str, Any]) -> None:
        """
        Update the context for a conversation
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            context_updates: Dictionary of context updates
        """
        conversation = self.get_conversation(chat_id, user_id)
        conversation.context.update(context_updates)
        
        # Update current topic thread if provided
        if 'current_topic' in context_updates:
            conversation.current_topic_thread = context_updates['current_topic']
        
        self._save_conversation(conversation)

    def get_conversation_history(self, chat_id: str, user_id: str, 
                                max_messages: Optional[int] = None) -> List[Message]:
        """
        Get conversation history for a user
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            max_messages: Maximum number of messages to return
            
        Returns:
            List of Message objects
        """
        conversation = self.get_conversation(chat_id, user_id)
        messages = conversation.messages
        
        if max_messages:
            messages = messages[-max_messages:]
            
        return messages

    def get_context(self, chat_id: str, user_id: str) -> Dict[str, Any]:
        """
        Get context for a conversation
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            
        Returns:
            Context dictionary
        """
        conversation = self.get_conversation(chat_id, user_id)
        return conversation.context

    def get_rich_context_for_llm(self, chat_id: str, user_id: str, 
                                max_history: int = 20) -> Dict[str, Any]:
        """
        Get rich context formatted for LLM consumption
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            max_history: Maximum number of recent messages to include
            
        Returns:
            Rich context dictionary with conversation history, summary, and metadata
        """
        conversation = self.get_conversation(chat_id, user_id)
        
        # Get recent messages
        recent_messages = conversation.messages[-max_history:] if conversation.messages else []
        
        # Format messages for LLM
        formatted_messages = []
        for msg in recent_messages:
            formatted_msg = {
                "role": msg.role,
                "content": msg.content,
                "timestamp": datetime.fromtimestamp(msg.timestamp).isoformat(),
                "query_type": msg.query_type,
                "topics": msg.topics_discussed,
                "entities": msg.entities_mentioned
            }
            if msg.search_results_count is not None:
                formatted_msg["results_found"] = msg.search_results_count
            formatted_messages.append(formatted_msg)
        
        return {
            "conversation_history": formatted_messages,
            "conversation_summary": {
                "depth": conversation.conversation_depth,
                "main_topics": conversation.summary.main_topics,
                "key_entities": conversation.summary.key_entities,
                "conversation_theme": conversation.summary.conversation_theme,
                "user_interests": conversation.summary.user_interests
            },
            "current_context": {
                "topic_thread": conversation.current_topic_thread,
                "related_searches": conversation.related_searches[-5:],  # Last 5 searches
                "insights_provided": conversation.insights_provided,
                "last_activity": conversation.last_activity
            },
            "conversation_metadata": {
                "total_exchanges": conversation.conversation_depth,
                "conversation_age_hours": (time.time() - conversation.last_activity) / 3600,
                "has_long_history": len(conversation.messages) > 10
            }
        }

    def clear_conversation(self, chat_id: str, user_id: str) -> None:
        """
        Clear a conversation
        
        Args:
            chat_id: Chat ID
            user_id: User ID
        """
        conversation_key = self._get_conversation_key(chat_id, user_id)
        
        if conversation_key in self.conversations:
            del self.conversations[conversation_key]
            
            # Remove from disk
            file_path = self._get_storage_path(conversation_key)
            if os.path.exists(file_path):
                os.remove(file_path)

    def clear_all_conversations(self) -> None:
        """Clear all conversations"""
        self.conversations.clear()
        
        # Remove all files
        for filename in os.listdir(self.storage_dir):
            if filename.endswith('.json'):
                os.remove(os.path.join(self.storage_dir, filename))

    def get_format_for_llm(self, chat_id: str, user_id: str, max_history: int = 10) -> List[Dict[str, str]]:
        """
        Get conversation history formatted for LLM input (legacy method for compatibility)
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            max_history: Maximum number of messages to include
            
        Returns:
            List of message dictionaries formatted for LLM
        """
        messages = self.get_conversation_history(chat_id, user_id, max_history)
        
        formatted = []
        for msg in messages:
            formatted.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return formatted

    def _cleanup_old_conversations(self) -> None:
        """Clean up old conversations to free memory"""
        try:
            # Sort conversations by last activity
            sorted_conversations = sorted(
                self.conversations.items(),
                key=lambda x: x[1].last_activity
            )
            
            # Remove oldest conversations until we're under the limit
            while len(self.conversations) > self.max_conversations * 0.8:  # Keep 80% of max
                oldest_key, oldest_conv = sorted_conversations.pop(0)
                
                # Remove from memory
                del self.conversations[oldest_key]
                
                # Remove from disk
                file_path = self._get_storage_path(oldest_key)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
                logger.debug(f"Cleaned up old conversation: {oldest_key}")
                
        except Exception as e:
            logger.error(f"Error during conversation cleanup: {e}")

# Singleton instance
_instance = None

def get_conversation_memory() -> ConversationMemory:
    """Get the conversation memory singleton instance"""
    global _instance
    if _instance is None:
        _instance = ConversationMemory()
    return _instance 