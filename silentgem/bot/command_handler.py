"""
Command handler for processing user queries in the Chat Insights bot
"""

import asyncio
import time
import re
from typing import Dict, List, Any, Optional, Callable, Tuple
from loguru import logger

from silentgem.search.query_processor import get_query_processor
from silentgem.utils.response_formatter import format_search_results
from silentgem.database.message_store import get_message_store
from silentgem.config.insights_config import get_insights_config
from silentgem.search.search_engine import get_search_engine
from silentgem.bot.conversation_memory import get_conversation_memory
from silentgem.llm.query_processor import QueryProcessor, QueryInterpretationResult
from silentgem.query_params import QueryParams, ParamCompatibility

class CommandHandler:
    """Handles commands and queries for the Chat Insights bot"""
    
    def __init__(self, bot=None, shutdown_event=None):
        """Initialize the command handler"""
        self.message_store = get_message_store()
        self.config = get_insights_config()
        self.query_processor = get_query_processor()
        self.bot = bot
        self.shutdown_event = shutdown_event or asyncio.Event()
        self.conversation_memory = get_conversation_memory()
    
    async def _send_typing_action(self, chat_id):
        """
        Send typing action to indicate the bot is processing
        
        This is a placeholder implementation that will be overridden
        by the telegram_bot module when setting the command handler.
        
        Args:
            chat_id: ID of the chat to send typing action to
        """
        # This method is intentionally left minimal as it will be replaced
        # by the telegram bot's implementation in set_command_handler
        logger.debug(f"Typing action requested for chat {chat_id}")
        # No actual implementation as this will be replaced
    
    async def handle_query(
        self, 
        query: str, 
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        callback: Optional[Callable[[str], None]] = None,
        verbosity: str = "standard",
        include_quotes: bool = True,
        include_timestamps: bool = True,
        include_sender_info: bool = True,
        include_channel_info: bool = True
    ) -> str:
        """
        Process a search query and return formatted results
        
        Args:
            query: The search query string
            chat_id: ID of the chat where the query was sent
            user_id: ID of the user who sent the query
            callback: Optional callback function to stream partial results
            verbosity: Verbosity level for response formatting (concise, standard, detailed)
            include_quotes: Whether to include quotes in the response
            include_timestamps: Whether to include timestamps in the response
            include_sender_info: Whether to include sender info in the response
            include_channel_info: Whether to include channel info in the response
            
        Returns:
            str: Formatted response to the query
        """
        try:
            # Store user message in conversation history
            if chat_id and user_id:
                conversation = self.conversation_memory.get_conversation(chat_id, user_id)
                self.conversation_memory.add_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    role="user",
                    content=query
                )
            
            # Send typing action if chat_id is provided
            if chat_id:
                # This will use the implementation provided by telegram_bot
                await self._send_typing_action(chat_id)
            
            # Send initial acknowledgment via callback if provided
            if callback:
                callback(f"⏳ Processing your request about '{query}'...")
                
            # Get conversation history for context if this is a follow-up question
            conversation_history = None
            conversation_context = {}
            if chat_id and user_id:
                conversation = self.conversation_memory.get_conversation(chat_id, user_id)
                conversation_history = self.conversation_memory.get_conversation_history(chat_id, user_id)
                conversation_context = conversation.context if hasattr(conversation, 'context') else {}
            
            # Determine if this is a follow-up question
            is_followup = False
            if conversation_history and len(conversation_history) >= 2:
                previous_messages = [msg for msg in conversation_history if msg.get('role') == 'user']
                if len(previous_messages) >= 2:
                    is_followup = self._is_related_query(query, previous_messages[-2].get('content', ''))
            
            # Process query with NLU to extract parameters
            # If this is a follow-up, include context from the previous query
            interpretation: QueryInterpretationResult = await self.query_processor.process_query(
                query=query,
                include_time=True,
                include_inferred_params=True,
                context=conversation_context if is_followup else None
            )
            
            # Reuse time period from previous query if this is a follow-up and doesn't specify a new time
            if is_followup and not interpretation.time_period and conversation_context.get('time_period'):
                interpretation.time_period = conversation_context.get('time_period')
                logger.info(f"Reusing time period from previous query: {interpretation.time_period}")
            
            # Include previous search results in follow-up if appropriate
            if is_followup and conversation_context.get('previous_message_ids'):
                previous_ids = conversation_context.get('previous_message_ids', [])
                logger.info(f"Found {len(previous_ids)} previous message IDs for context in follow-up")
                # We'll use this context in query processing later
            
            # Prepare search parameters
            search_params = QueryParams(
                query=interpretation.processed_query or query,
                limit=20,
                chat_id=chat_id if chat_id and not interpretation.cross_chats else None,
                time_period=interpretation.time_period
            )
            
            # Execute search
            start_time = time.time()
            messages = await get_search_engine().search(search_params)
            search_time = time.time() - start_time
            logger.info(f"Search completed in {search_time:.2f}s, found {len(messages)} results")
            
            # Organize messages by chat for better context
            chat_messages_map = {}
            if messages:
                for msg in messages:
                    chat_id = msg.get("target_chat_id") or msg.get("source_chat_id")
                    if chat_id:
                        if chat_id not in chat_messages_map:
                            chat_messages_map[chat_id] = []
                        chat_messages_map[chat_id].append(msg)
            
            # Format results with enhanced context, including conversation history
            response = await format_search_results(
                messages=messages,
                query=query,
                parsed_query={"processed_query": interpretation.processed_query, "time_period": interpretation.time_period},
                verbosity=verbosity,
                include_quotes=include_quotes,
                include_timestamps=include_timestamps,
                include_sender_info=include_sender_info,
                include_channel_info=include_channel_info,
                chat_messages_map=chat_messages_map,
                conversation_history=conversation_history
            )
            
            # Update conversation context with the latest query information
            if chat_id and user_id:
                message_ids = [msg.get("id") for msg in messages] if messages else []
                new_context = {
                    'last_query': query,
                    'processed_query': interpretation.processed_query or query,
                    'time_period': interpretation.time_period,
                    'previous_message_ids': message_ids,
                    'last_updated': int(time.time())
                }
                self.conversation_memory.update_context(chat_id, user_id, new_context)
            
            # Add assistant response to conversation history
            if chat_id and user_id:
                self.conversation_memory.add_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    role="assistant",
                    content=response
                )
            
            # Handle case where no results found
            if not messages:
                no_results_msg = "📭 No messages found matching your query: '{}'."
                
                # Suggest alternatives if this is a follow-up with no results
                if is_followup:
                    suggest_msg = (
                        "\n\nThis follow-up question didn't match any results. "
                        "Try rephrasing or asking a different question."
                    )
                    no_results_msg += suggest_msg
                
                if callback:
                    callback(no_results_msg.format(query))
                return no_results_msg.format(query)
            
            # Return the final formatted response
            if callback:
                callback(response)
            return response
            
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            error_msg = f"❌ Sorry, I encountered an error while processing your query: {str(e)}"
            if callback:
                callback(error_msg)
            return error_msg
    
    def _is_related_query(self, current_query: str, previous_query: str) -> bool:
        """
        Determine if the current query is related to the previous query
        
        Args:
            current_query: The current user query
            previous_query: The previous user query
            
        Returns:
            bool: True if this appears to be a follow-up question
        """
        # Common follow-up phrases
        follow_up_phrases = [
            "what about",
            "and what",
            "tell me more",
            "can you elaborate",
            "who",
            "when",
            "where",
            "why",
            "how",
            "also",
            "additionally"
        ]
        
        # Check for common follow-up phrases
        for phrase in follow_up_phrases:
            if current_query.lower().startswith(phrase):
                return True
        
        # Check for keyword overlap
        def extract_keywords(text: str) -> List[str]:
            # Remove stop words and punctuation, keep meaningful keywords
            text = re.sub(r'[^\w\s]', ' ', text.lower())
            words = text.split()
            stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'about'}
            return [w for w in words if len(w) > 2 and w not in stop_words]
        
        current_keywords = set(extract_keywords(current_query))
        previous_keywords = set(extract_keywords(previous_query))
        
        # If the current query is very short and there's keyword overlap, likely a follow-up
        if len(current_query.split()) <= 4 and len(current_keywords.intersection(previous_keywords)) > 0:
            return True
            
        # If there's significant keyword overlap, it's likely related
        overlap = len(current_keywords.intersection(previous_keywords))
        if overlap >= 2 or (overlap > 0 and len(current_keywords) <= 3):
            return True
            
        return False

# Singleton pattern for accessing command handler
_command_handler_instance = None

def get_command_handler(bot=None, shutdown_event=None) -> CommandHandler:
    """
    Get the singleton instance of CommandHandler
    
    Args:
        bot: Optional bot instance to use for sending messages
        shutdown_event: Optional event to signal shutdown
    
    Returns:
        CommandHandler: The singleton instance
    """
    global _command_handler_instance
    if _command_handler_instance is None:
        _command_handler_instance = CommandHandler(bot=bot, shutdown_event=shutdown_event)
    elif bot or shutdown_event:
        # Update existing instance with new bot or shutdown event if provided
        if bot:
            _command_handler_instance.bot = bot
        if shutdown_event:
            _command_handler_instance.shutdown_event = shutdown_event
    return _command_handler_instance 