"""
Command handler for processing user queries in the Chat Insights bot
"""

import asyncio
import time
import re
from typing import Dict, List, Any, Optional, Callable, Tuple
from loguru import logger
from datetime import datetime

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
                try:
                    conversation = self.conversation_memory.get_conversation(chat_id, user_id)
                    self.conversation_memory.add_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        role="user",
                        content=query
                    )
                except Exception as e:
                    logger.warning(f"Error storing user message: {e}")
            
            # Send typing action if chat_id is provided
            if chat_id:
                try:
                    # This will use the implementation provided by telegram_bot
                    await self._send_typing_action(chat_id)
                except Exception as e:
                    logger.warning(f"Error sending typing action: {e}")
            
            # Send initial acknowledgment via callback if provided
            if callback:
                try:
                    callback(f"⏳ Processing your request about '{query}'...")
                except Exception as e:
                    logger.warning(f"Error sending callback: {e}")
                
            # Get conversation history for context if this is a follow-up question
            conversation_history = None
            conversation_context = {}
            conversation_history_dicts = [] # Use this list for formatting
            if chat_id and user_id:
                try:
                    conversation = self.conversation_memory.get_conversation(chat_id, user_id)
                    # Retrieve history as Message objects
                    raw_history = self.conversation_memory.get_conversation_history(chat_id, user_id)
                    conversation_context = conversation.context if hasattr(conversation, 'context') else {}
                    
                    # Convert Message objects to simple dicts for formatting
                    for msg in raw_history:
                        if hasattr(msg, 'role') and hasattr(msg, 'content'):
                            conversation_history_dicts.append({'role': msg.role, 'content': msg.content})
                        else:
                            logger.warning(f"Skipping invalid item in raw_history: {type(msg)}")
                            
                except Exception as e:
                    logger.warning(f"Error getting conversation history: {e}")
            
            # Determine if this is a follow-up question
            is_followup = False
            previous_query = ""
            try:
                # Use the converted dict list for checking
                if conversation_history_dicts and len(conversation_history_dicts) >= 2:
                    previous_messages = [msg for msg in conversation_history_dicts if msg.get('role') == 'user']
                    if len(previous_messages) >= 2:
                        previous_query = previous_messages[-2].get('content', '')
                        is_followup = self._is_related_query(query, previous_query)
                        
                        # Log the follow-up detection
                        if is_followup:
                            logger.info(f"Detected follow-up question. Current: '{query}', Previous: '{previous_query}'")
                        else:
                            logger.debug(f"Not a follow-up. Current: '{query}', Previous: '{previous_query}'")
            except Exception as e:
                logger.warning(f"Error determining if query is follow-up: {e}")
            
            # Process query with NLU to extract parameters - safely handle errors
            interpretation = None
            try:
                # If this is a follow-up, include context from the previous query
                # Special handling for place-related follow-up questions
                if is_followup:
                    # Check if this is a place-related query
                    place_indicators = ["cities", "places", "towns", "locations", "areas", "regions"]
                    is_place_query = any(indicator in query.lower() for indicator in place_indicators)
                    
                    if is_place_query:
                        # For place queries, try to enhance the query with context
                        enhanced_query = query
                        
                        # If previous query was about a specific location/event, add it to the query
                        location_context = self._extract_location_context(previous_query)
                        if location_context:
                            # Format: "Make a list of cities in [location_context]"
                            enhanced_query = f"{query} in {location_context}"
                            logger.info(f"Enhanced place query with context: '{enhanced_query}'")
                            query = enhanced_query
                
                # Call the processor with the potentially enhanced query
                interpretation = await self.query_processor.process_query(query)
            except Exception as e:
                logger.warning(f"Error processing query with NLU: {e}")
                # Create minimal interpretation
                from silentgem.llm.query_processor import QueryInterpretationResult
                interpretation = QueryInterpretationResult(
                    processed_query=query,
                    time_period=None,
                    cross_chats=False
                )
            
            # Reuse time period from previous query if this is a follow-up and doesn't specify a new time
            try:
                if is_followup and not interpretation.time_period and conversation_context.get('time_period'):
                    interpretation.time_period = conversation_context.get('time_period')
                    logger.info(f"Reusing time period from previous query: {interpretation.time_period}")
                    
                # For place-related follow-ups, ensure we maintain context about discussed places
                if is_followup and hasattr(interpretation, 'processed_query'):
                    # If this query is about places but doesn't mention specific places from previous query
                    place_indicators = ["cities", "places", "towns", "locations", "areas", "regions"]
                    is_place_query = any(indicator in query.lower() for indicator in place_indicators)
                    
                    if is_place_query:
                        previous_context = conversation_context.get('place_context', '')
                        if previous_context and previous_context not in interpretation.processed_query:
                            # Append the place context to the processed query
                            interpretation.processed_query = f"{interpretation.processed_query} {previous_context}"
                            logger.info(f"Added place context to processed query: {interpretation.processed_query}")
            except Exception as e:
                logger.warning(f"Error handling query context: {e}")
            
            # Include previous search results in follow-up if appropriate
            try:
                if is_followup and conversation_context.get('previous_message_ids'):
                    previous_ids = conversation_context.get('previous_message_ids', [])
                    logger.info(f"Found {len(previous_ids)} previous message IDs for context in follow-up")
            except Exception as e:
                logger.warning(f"Error handling previous message IDs: {e}")
            
            # Prepare search parameters - safely
            search_params = None
            try:
                from silentgem.query_params import QueryParams
                search_params = QueryParams(
                    query=getattr(interpretation, "processed_query", None) or query,
                    limit=20,
                    chat_id=chat_id if chat_id and not getattr(interpretation, "cross_chats", False) else None,
                    time_period=getattr(interpretation, "time_period", None)
                )
            except Exception as e:
                logger.warning(f"Error preparing search parameters: {e}")
                # Fallback to minimal search params
                from silentgem.query_params import QueryParams
                search_params = QueryParams(
                    query=query,
                    limit=20,
                    chat_id=chat_id
                )
            
            # Execute search - safely
            messages = []
            try:
                start_time = time.time()
                messages = await get_search_engine().search(search_params)
                search_time = time.time() - start_time
                logger.info(f"Search completed in {search_time:.2f}s, found {len(messages)} results")
            except Exception as e:
                logger.warning(f"Error executing search: {e}")
            
            # Convert any non-dict messages to dicts to prevent errors
            safe_messages = []
            try:
                for msg in messages:
                    msg_dict = None
                    if isinstance(msg, dict):
                        # Already a dictionary, use as is
                        msg_dict = msg
                    elif hasattr(msg, 'id') and hasattr(msg, 'text') and hasattr(msg, 'chat'):
                        # Looks like a Message object (or similar duck type), try converting
                        try:
                            msg_dict = {
                                'id': msg.id,
                                'text': msg.text or getattr(msg, 'content', ''),
                                'source_chat_id': str(getattr(msg.chat, 'id', 'unknown')),
                                'target_chat_id': str(getattr(msg.chat, 'id', 'unknown')),
                                'sender_name': getattr(getattr(msg, 'from_user', None), 'first_name', 'Unknown'),
                                'timestamp': int(getattr(msg, 'date', datetime.now()).timestamp()) if hasattr(msg, 'date') else int(time.time()),
                                # Add any other fields needed by the formatter
                                'content': msg.text or getattr(msg, 'content', ''),
                                'sender': getattr(getattr(msg, 'from_user', None), 'first_name', 'Unknown'),
                                'date': getattr(msg, 'date', datetime.now()).isoformat() if hasattr(msg, 'date') else datetime.now().isoformat(),
                                'chat_title': getattr(getattr(msg, 'chat', None), 'title', 'Unknown Chat')
                            }
                        except Exception as convert_err:
                            logger.warning(f"Failed to convert message-like object to dict: {convert_err}. Object: {type(msg)}")
                            msg_dict = None # Ensure it's None if conversion fails
                    else:
                        # Unexpected type, log it
                        logger.warning(f"Unexpected object type encountered in search results: {type(msg)}. Skipping.")
                        
                    # Only append if we successfully got or created a dictionary
                    if isinstance(msg_dict, dict):
                        safe_messages.append(msg_dict)
                        
            except Exception as e:
                logger.warning(f"Error during message conversion loop: {e}")
                # Worst case, clear the list to prevent downstream errors
                safe_messages = []
            
            # Organize messages by chat for better context - safely
            chat_messages_map = {}
            try:
                for msg in safe_messages:
                    chat_id_key = msg.get('target_chat_id') or msg.get('source_chat_id')
                    if chat_id_key:
                        if chat_id_key not in chat_messages_map:
                            chat_messages_map[chat_id_key] = []
                        chat_messages_map[chat_id_key].append(msg)
            except Exception as e:
                logger.warning(f"Error organizing messages by chat: {e}")
            
            # Format results with enhanced context - safely
            response = ""
            try:
                response = await format_search_results(
                    messages=safe_messages,
                    query=query,
                    parsed_query={"processed_query": getattr(interpretation, "processed_query", None), 
                                  "time_period": getattr(interpretation, "time_period", None)},
                    verbosity=verbosity,
                    include_quotes=include_quotes,
                    include_timestamps=include_timestamps,
                    include_sender_info=include_sender_info,
                    include_channel_info=include_channel_info,
                    chat_messages_map=chat_messages_map,
                    conversation_history=conversation_history_dicts # Pass the list of dicts
                )
            except Exception as e:
                logger.error(f"Error formatting search results: {e}")
                # Fallback to basic response
                if safe_messages:
                    response = f"Found {len(safe_messages)} messages matching '{query}'"
                    for i, msg in enumerate(safe_messages[:5]):
                        response += f"\n\n{i+1}. {msg.get('text', 'No text content')}"
                else:
                    response = f"No messages found matching '{query}'"
            
            # Update conversation context - safely
            try:
                if chat_id and user_id:
                    message_ids = []
                    for msg in safe_messages:
                        if msg.get('id'):
                            message_ids.append(msg.get('id'))
                    
                    # Check if this is a completely new topic
                    is_new_topic = not is_followup
                    
                    # Reset context for new topics
                    if is_new_topic:
                        # Create fresh context for new topic
                        new_context = {
                            'last_query': query,
                            'processed_query': getattr(interpretation, "processed_query", None) or query,
                            'time_period': getattr(interpretation, "time_period", None),
                            'previous_message_ids': message_ids,
                            'last_updated': int(time.time())
                        }
                        
                        # Extract new place context if present in this new topic
                        place_context = self._extract_location_context(query)
                        if place_context:
                            new_context['place_context'] = place_context
                            logger.info(f"New topic: saved place context in conversation memory: {place_context}")
                        else:
                            # Explicitly remove any old place context to avoid contamination
                            logger.info("New topic detected: clearing previous place context")
                    else:
                        # For follow-up questions, maintain relevant context
                        place_context = ''
                        
                        # Check if this was a place-related query
                        place_indicators = ["cities", "places", "towns", "locations", "areas", "regions"]
                        if any(indicator in query.lower() for indicator in place_indicators):
                            # If we're asking about places, preserve the context from previous query
                            place_context = conversation_context.get('place_context', '')
                        else:
                            # If this is a general query that might mention places, try to extract location
                            place_context = self._extract_location_context(query)
                        
                        new_context = {
                            'last_query': query,
                            'processed_query': getattr(interpretation, "processed_query", None) or query,
                            'time_period': getattr(interpretation, "time_period", None),
                            'previous_message_ids': message_ids,
                            'last_updated': int(time.time())
                        }
                        
                        # Add place context if available for follow-up questions
                        if place_context:
                            new_context['place_context'] = place_context
                            logger.info(f"Follow-up question: maintained place context in conversation memory: {place_context}")
                    
                    self.conversation_memory.update_context(chat_id, user_id, new_context)
            except Exception as e:
                logger.warning(f"Error updating conversation context: {e}")
            
            # Add assistant response to conversation history - safely
            try:
                if chat_id and user_id:
                    self.conversation_memory.add_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        role="assistant",
                        content=response
                    )
            except Exception as e:
                logger.warning(f"Error adding assistant response to conversation: {e}")
            
            # Handle case where no results found - safely
            if not safe_messages:
                try:
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
                except Exception as e:
                    logger.warning(f"Error handling no results case: {e}")
                    return f"No results found for '{query}'"
            
            # Return the final formatted response
            if callback:
                try:
                    callback(response)
                except Exception as e:
                    logger.warning(f"Error sending callback with response: {e}")
            return response
            
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            error_msg = f"❌ Sorry, I encountered an error while processing your query: {str(e)}"
            if callback:
                try:
                    callback(error_msg)
                except:
                    pass
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
        # If either query is empty, they can't be related
        if not current_query or not previous_query:
            return False
        
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
            "additionally",
            "make a list",
            "list",
            "show me",
            "which ones",
            "which",
            "name the"
        ]
        
        # Check for common follow-up phrases
        for phrase in follow_up_phrases:
            if current_query.lower().startswith(phrase):
                return True
            
        # Common query indicators for places, entities, or topics referenced in previous queries
        place_indicators = ["cities", "places", "towns", "locations", "areas", "regions"]
        
        # Check if the current query is asking about places referenced in previous conversations
        if any(indicator in current_query.lower() for indicator in place_indicators):
            # This is likely a follow-up about places mentioned earlier
            # BUT only if we're still talking about the same general topic
            
            # Extract topic entities from both queries
            previous_topic = self._extract_primary_topic(previous_query)
            current_topic = self._extract_primary_topic(current_query)
            
            # If we can identify topics in both and they're different, consider it a new query
            if previous_topic and current_topic and previous_topic.lower() != current_topic.lower():
                # Different identified topics mean this is NOT a follow-up
                logger.info(f"Detected topic change from '{previous_topic}' to '{current_topic}'")
                return False
            
            # Topics overlap or couldn't be determined clearly, treat as follow-up
            return True
        
        # Check for completely different topics that would indicate a new conversation
        previous_topics = self._extract_topics(previous_query)
        current_topics = self._extract_topics(current_query)
        
        # If the topics are completely different, it's likely a new query
        if previous_topics and current_topics and not any(t.lower() in [ct.lower() for ct in current_topics] for t in previous_topics):
            logger.info(f"Topics changed from {previous_topics} to {current_topics}")
            return False
        
        # Check for keyword overlap
        def extract_keywords(text: str) -> List[str]:
            # Remove stop words and punctuation, keep meaningful keywords
            text = re.sub(r'[^\w\s]', ' ', text.lower())
            words = text.split()
            stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'about', 'and', 'or', 'what', 'where', 'when', 'how', 'which', 'who', 'why', 'make', 'list', 'tell', 'me', 'show'}
            return [w for w in words if len(w) > 2 and w not in stop_words]
        
        current_keywords = set(extract_keywords(current_query))
        previous_keywords = set(extract_keywords(previous_query))
        
        # If the current query is very short and there's keyword overlap, likely a follow-up
        if len(current_query.split()) <= 4 and len(current_keywords.intersection(previous_keywords)) > 0:
            return True
        
        # If there's significant keyword overlap, it's likely related
        overlap = len(current_keywords.intersection(previous_keywords))
        if overlap >= 1 or (overlap > 0 and len(current_keywords) <= 3):
            return True
        
        return False

    def _extract_primary_topic(self, query: str) -> str:
        """
        Extract the primary topic (subject) from a query
        
        Args:
            query: The query to extract the topic from
            
        Returns:
            str: The primary topic or empty string
        """
        # Look for primary topics in the query (usually proper nouns)
        # First check for location names which are often primary topics
        location = self._extract_location_context(query)
        if location:
            return location
        
        # Look for capitalized terms that might be topics
        topic_match = re.search(r'([A-Z][a-zA-Z]+(?:(?:\s|-)[A-Z][a-zA-Z]+)*)', query)
        if topic_match:
            return topic_match.group(1)
        
        # Try to extract known topic words
        topic_words = ["blockchain", "crypto", "war", "conflict", "storm", "hurricane", 
                      "election", "politics", "technology", "attack", "bombing"]
        
        for word in topic_words:
            if word.lower() in query.lower():
                return word
        
        return ""
    
    def _extract_topics(self, query: str) -> List[str]:
        """
        Extract multiple potential topics from a query
        
        Args:
            query: The query to extract topics from
            
        Returns:
            List of identified topics
        """
        topics = []
        
        # Add the primary topic if one is found
        primary = self._extract_primary_topic(query)
        if primary:
            topics.append(primary)
        
        # Extract all capitalized terms as potential entities
        cap_terms = re.findall(r'([A-Z][a-zA-Z]+(?:(?:\s|-)[A-Z][a-zA-Z]+)*)', query)
        topics.extend([term for term in cap_terms if term not in topics])
        
        # Add known topic categories if they appear in the query
        categories = {
            "political": ["government", "election", "politics", "president", "minister"],
            "conflict": ["war", "bombing", "attack", "fighting", "troops", "military"],
            "tech": ["blockchain", "crypto", "cryptocurrency", "technology", "software", "digital"],
            "weather": ["storm", "hurricane", "typhoon", "weather", "climate"],
            "financial": ["market", "stock", "trading", "finance", "economy", "economic"]
        }
        
        # Check each category
        for category, terms in categories.items():
            if any(term in query.lower() for term in terms):
                topics.append(category)
        
        return topics

    def _extract_location_context(self, query: str) -> str:
        """
        Extract location context from a query
        
        Args:
            query: The query to extract location from
            
        Returns:
            str: Extracted location or empty string
        """
        # Check for common location patterns in the query
        # Common format: "What's happening in X?" or "Latest news from Y"
        location_patterns = [
            r'in ([A-Z][a-zA-Z]+)',  # "in Gaza", "in Ukraine" 
            r'from ([A-Z][a-zA-Z]+)',  # "from Israel"
            r'at ([A-Z][a-zA-Z]+)',  # "at Jerusalem"
            r'about ([A-Z][a-zA-Z]+)',  # "about Palestine" 
            r'on ([A-Z][a-zA-Z]+)',  # "on West Bank"
            r'([A-Z][a-zA-Z]+) (?:bombing|attack|conflict|war|situation)'  # "Gaza bombing", "Ukraine conflict"
        ]
        
        for pattern in location_patterns:
            matches = re.search(pattern, query)
            if matches:
                return matches.group(1)
        
        # Check for specifically mentioned regions that might not match the patterns above
        common_locations = ["Gaza", "Israel", "Palestine", "Ukraine", "Russia", "Syria", "Lebanon", "Iran", "Iraq"]
        for location in common_locations:
            if location in query:
                return location
            
        return ""

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