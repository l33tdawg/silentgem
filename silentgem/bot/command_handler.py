"""
Command handler for processing user queries in the Chat Insights bot
"""

import asyncio
import time
import re
from typing import Dict, List, Any, Optional, Callable, Tuple
from loguru import logger
from datetime import datetime
import functools

from silentgem.search.query_processor import get_query_processor
from silentgem.utils.response_formatter import format_search_results
from silentgem.database.message_store import get_message_store
from silentgem.config.insights_config import get_insights_config
from silentgem.search.search_engine import get_search_engine
from silentgem.bot.conversation_memory import get_conversation_memory
from silentgem.llm.query_processor import QueryProcessor, QueryInterpretationResult
from silentgem.query_params import QueryParams, ParamCompatibility
from silentgem.bot.guided_queries import get_guided_query_generator, GuidedQuerySuggestions

# Simple in-memory cache for query results
_query_cache = {}
_cache_max_size = 100
_cache_ttl = 300  # 5 minutes

def _cache_key(query: str, chat_id: Optional[str] = None) -> str:
    """Generate cache key for query"""
    return f"{query.lower().strip()}:{chat_id or 'all'}"

def _get_cached_result(cache_key: str) -> Optional[Tuple[List[Dict], float]]:
    """Get cached result if still valid"""
    if cache_key in _query_cache:
        result, timestamp = _query_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            return result, timestamp
        else:
            # Remove expired entry
            del _query_cache[cache_key]
    return None

def _cache_result(cache_key: str, result: List[Dict]):
    """Cache query result"""
    global _query_cache
    
    # Simple LRU: remove oldest if cache is full
    if len(_query_cache) >= _cache_max_size:
        oldest_key = min(_query_cache.keys(), key=lambda k: _query_cache[k][1])
        del _query_cache[oldest_key]
    
    _query_cache[cache_key] = (result, time.time())

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
        # Initialize conversation intelligence lazily to avoid circular imports
        self.conversation_intelligence = None
        
        # Performance settings
        self.enable_caching = True
        self.enable_parallel_processing = True
        self.fast_mode = False  # Enable full LLM processing for better responses
    
    def _get_conversation_intelligence(self):
        """Get conversation intelligence instance (lazy initialization)"""
        if self.conversation_intelligence is None:
            try:
                from silentgem.bot.conversation_intelligence import get_conversation_intelligence
                self.conversation_intelligence = get_conversation_intelligence()
            except Exception as e:
                logger.warning(f"Failed to initialize conversation intelligence: {e}")
                self.conversation_intelligence = None
        return self.conversation_intelligence

    async def _send_typing_action(self, chat_id):
        """Send typing action to indicate bot is processing"""
        try:
            if self.bot and hasattr(self.bot, 'send_chat_action'):
                await self.bot.send_chat_action(chat_id, "typing")
        except Exception as e:
            logger.debug(f"Could not send typing action: {e}")

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
        start_time = time.time()
        
        try:
            # Check cache first if enabled
            cache_key = _cache_key(query, chat_id) if self.enable_caching else None
            if cache_key:
                cached_result = _get_cached_result(cache_key)
                if cached_result:
                    messages, _ = cached_result
                    logger.info(f"Cache hit for query '{query}' - returning cached result")
                    
                    # Still format the response but skip search
                    response = await format_search_results(
                        messages=messages,
                        query=query,
                        verbosity=verbosity,
                        include_quotes=include_quotes,
                        include_timestamps=include_timestamps,
                        include_sender_info=include_sender_info,
                        include_channel_info=include_channel_info
                    )
                    
                    cache_time = time.time() - start_time
                    logger.info(f"Query '{query}' completed from cache in {cache_time:.2f}s")
                    return response

            # Send typing action if chat_id is provided (non-blocking)
            if chat_id:
                asyncio.create_task(self._send_typing_action(chat_id))

            # Send initial acknowledgment via callback if provided
            if callback:
                try:
                    callback(f"⏳ Searching for '{query}'...")
                except Exception as e:
                    logger.warning(f"Error sending callback: {e}")

            # Fast mode: Skip expensive conversation analysis for simple queries
            entities, topics = [], []
            conversation_history_dicts = []
            is_followup = False
            
            if not self.fast_mode:
                # Extract entities and topics from the query for enhanced context
                try:
                    conversation_intelligence = self._get_conversation_intelligence()
                    if conversation_intelligence:
                        entities, topics = await conversation_intelligence.extract_entities_and_topics(query)
                except Exception as e:
                    logger.warning(f"Error extracting entities and topics: {e}")

                # Store user message in conversation history with enhanced metadata
                if chat_id and user_id:
                    try:
                        conversation = self.conversation_memory.get_conversation(chat_id, user_id)
                        self.conversation_memory.add_message(
                            chat_id=chat_id,
                            user_id=user_id,
                            role="user",
                            content=query,
                            query_type="search",
                            topics_discussed=topics,
                            entities_mentioned=entities
                        )
                    except Exception as e:
                        logger.warning(f"Error storing user message: {e}")

                # Get conversation history for context if this is a follow-up question
                conversation_history = None
                conversation_context = {}
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

            # Process query with simplified interpretation for speed
            interpretation = None
            enhanced_query = query
            try:
                if self.fast_mode:
                    # Fast mode: minimal query processing
                    from silentgem.llm.query_processor import QueryInterpretationResult
                    interpretation = QueryInterpretationResult(
                        processed_query=query,
                        time_period=self._extract_simple_time_period(query),
                        cross_chats=True  # Default to searching across all chats
                    )
                else:
                    # Full processing with LLM
                    if is_followup and previous_query:
                        # Enhance the query with conversation context BEFORE searching
                        enhanced_query = await self._enhance_query_with_context(
                            query, 
                            previous_query,
                            conversation_history_dicts,
                            entities,
                            topics
                        )
                        logger.info(f"Enhanced follow-up query: '{query}' -> '{enhanced_query}'")
                    
                    # Call the processor with the potentially enhanced query
                    interpretation = await self.query_processor.process_query(enhanced_query)
            except Exception as e:
                logger.warning(f"Error processing query with NLU: {e}")
                # Create minimal interpretation
                from silentgem.llm.query_processor import QueryInterpretationResult
                interpretation = QueryInterpretationResult(
                    processed_query=query,
                    time_period=None,
                    cross_chats=True  # Default to searching across all chats
                )

            # Prepare search parameters - simplified for speed
            search_params = None
            try:
                from silentgem.query_params import QueryParams
                # Determine if we should search across all chats
                cross_chats = getattr(interpretation, "cross_chats", True)  # Default to True
                search_chat_id = None if cross_chats else chat_id
                
                search_params = QueryParams(
                    query=getattr(interpretation, "processed_query", None) or query,
                    limit=15 if self.fast_mode else 20,  # Fewer results for speed
                    chat_id=search_chat_id,
                    time_period=getattr(interpretation, "time_period", None)
                )
            except Exception as e:
                logger.warning(f"Error preparing search parameters: {e}")
                # Fallback to minimal search params - default to cross-chat search
                from silentgem.query_params import QueryParams
                search_params = QueryParams(
                    query=query,
                    limit=15 if self.fast_mode else 20,
                    chat_id=None  # Default to searching across all chats
                )

            # Execute search with performance monitoring
            messages = []
            try:
                search_start = time.time()
                messages = await get_search_engine().search(search_params)
                search_time = time.time() - search_start
                logger.info(f"Search completed in {search_time:.2f}s, found {len(messages)} results")
                
                # Cache the results if caching is enabled
                if cache_key and messages:
                    _cache_result(cache_key, messages)
                    
            except Exception as e:
                logger.error(f"Error during search: {e}")
                return f"❌ Search error: {str(e)}"

            # Handle no results case quickly
            if not messages:
                no_results_msg = f"No messages found matching '{query}'"
                if getattr(interpretation, "time_period", None):
                    no_results_msg += f" in the {interpretation.time_period}"
                return no_results_msg

            # Prepare safe messages for formatting
            safe_messages = []
            for msg in messages:
                safe_msg = {}
                for key, value in msg.items():
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        safe_msg[key] = value
                    else:
                        safe_msg[key] = str(value)
                safe_messages.append(safe_msg)

            # Build chat messages map for context
            chat_messages_map = {}
            for msg in safe_messages:
                chat_id_key = msg.get('source_chat_id') or msg.get('target_chat_id') or 'unknown'
                if chat_id_key not in chat_messages_map:
                    chat_messages_map[chat_id_key] = []
                chat_messages_map[chat_id_key].append(msg)

            # Format response - choose fast or intelligent mode
            try:
                # Prepare query metadata for the intelligence system
                query_metadata = {
                    "processed_query": getattr(interpretation, "processed_query", None),
                    "time_period": getattr(interpretation, "time_period", None),
                    "expanded_terms": getattr(interpretation, "expanded_terms", []),
                    "intent": getattr(interpretation, "intent", "search"),
                    "entities": entities,
                    "topics": topics
                }
                
                # Use conversation intelligence for sophisticated response generation only if not in fast mode
                if not self.fast_mode and user_id:
                    conversation_intelligence = self._get_conversation_intelligence()
                    if conversation_intelligence:
                        response = await conversation_intelligence.synthesize_intelligent_response(
                            query=query,
                            search_results=safe_messages,
                            chat_id=chat_id,
                            user_id=user_id,
                            query_metadata=query_metadata
                        )
                    else:
                        # Fallback to traditional formatting
                        response = await format_search_results(
                            messages=safe_messages,
                            query=query,
                            parsed_query=query_metadata,
                            verbosity=verbosity,
                            include_quotes=include_quotes,
                            include_timestamps=include_timestamps,
                            include_sender_info=include_sender_info,
                            include_channel_info=include_channel_info,
                            chat_messages_map=chat_messages_map,
                            conversation_history=conversation_history_dicts
                        )
                else:
                    # Fast mode: use simple formatting
                    response = await format_search_results(
                        messages=safe_messages,
                        query=query,
                        parsed_query=query_metadata,
                        verbosity=verbosity,
                        include_quotes=include_quotes,
                        include_timestamps=include_timestamps,
                        include_sender_info=include_sender_info,
                        include_channel_info=include_channel_info,
                        chat_messages_map=chat_messages_map,
                        conversation_history=conversation_history_dicts
                    )
                
            except Exception as e:
                logger.error(f"Error formatting response: {e}")
                # Simple fallback response
                response = f"Found {len(safe_messages)} messages matching '{query}'"
                if safe_messages:
                    response += f"\n\nSample result: {safe_messages[0].get('content', '')[:100]}..."

            # Store assistant response in conversation memory (if not in fast mode)
            if not self.fast_mode and chat_id and user_id:
                try:
                    self.conversation_memory.add_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        role="assistant",
                        content=response,
                        search_results_count=len(safe_messages),
                        query_type="search_response"
                    )
                except Exception as e:
                    logger.warning(f"Error storing assistant response: {e}")

            total_time = time.time() - start_time
            logger.info(f"Query '{query}' completed in {total_time:.2f}s (fast_mode: {self.fast_mode})")
            return response

        except Exception as e:
            logger.error(f"Error handling query '{query}': {e}")
            import traceback
            traceback.print_exc()
            return f"❌ Error processing query: {str(e)}"
    
    async def handle_query_with_suggestions(
        self,
        query: str,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        callback: Optional[Callable[[str], None]] = None,
        verbosity: str = "standard",
        include_quotes: bool = True,
        include_timestamps: bool = True,
        include_sender_info: bool = True,
        include_channel_info: bool = True,
        enable_guided_queries: bool = True
    ) -> Tuple[str, Optional[GuidedQuerySuggestions]]:
        """
        Process a search query and return formatted results WITH guided query suggestions
        
        This is the v1.5 enhanced version that includes contextual follow-up questions,
        expandable topics, and action buttons.
        
        Args:
            query: The search query string
            chat_id: ID of the chat where the query was sent
            user_id: ID of the user who sent the query
            callback: Optional callback function to stream partial results
            verbosity: Verbosity level for response formatting
            include_quotes: Whether to include quotes in the response
            include_timestamps: Whether to include timestamps
            include_sender_info: Whether to include sender info
            include_channel_info: Whether to include channel info
            enable_guided_queries: Whether to generate guided query suggestions
            
        Returns:
            Tuple[str, Optional[GuidedQuerySuggestions]]: Response text and guided suggestions
        """
        # First, get the standard response
        response = await self.handle_query(
            query=query,
            chat_id=chat_id,
            user_id=user_id,
            callback=callback,
            verbosity=verbosity,
            include_quotes=include_quotes,
            include_timestamps=include_timestamps,
            include_sender_info=include_sender_info,
            include_channel_info=include_channel_info
        )
        
        # If guided queries are disabled, return early
        if not enable_guided_queries:
            return response, None
        
        # Generate guided query suggestions
        try:
            # Re-execute the search to get results metadata
            # (We could optimize this by caching, but for now, let's keep it simple)
            cache_key = _cache_key(query, chat_id) if self.enable_caching else None
            cached_result = _get_cached_result(cache_key) if cache_key else None
            
            if cached_result:
                messages, _ = cached_result
            else:
                # Quick search to get metadata
                from silentgem.query_params import QueryParams
                search_params = QueryParams(
                    query=query,
                    limit=20,
                    chat_id=None  # Cross-chat search
                )
                messages = await get_search_engine().search(search_params)
            
            # Build search metadata
            search_metadata = self._build_search_metadata(messages, query)
            
            # Get conversation history
            conversation_history = []
            if chat_id and user_id:
                try:
                    raw_history = self.conversation_memory.get_conversation_history(chat_id, user_id)
                    for msg in raw_history:
                        if hasattr(msg, 'role') and hasattr(msg, 'content'):
                            conversation_history.append({
                                'role': msg.role,
                                'content': msg.content
                            })
                except Exception as e:
                    logger.warning(f"Error getting conversation history for guided queries: {e}")
            
            # Generate guided suggestions
            guided_generator = get_guided_query_generator()
            suggestions = await guided_generator.generate_suggestions(
                query=query,
                search_results=messages,
                search_metadata=search_metadata,
                conversation_history=conversation_history,
                response_text=response
            )
            
            logger.info(f"Generated {len(suggestions.follow_up_questions)} guided questions for query '{query}'")
            return response, suggestions
            
        except Exception as e:
            logger.error(f"Error generating guided queries: {e}")
            import traceback
            traceback.print_exc()
            # Return response without suggestions if generation fails
            return response, None
    
    def _build_search_metadata(self, messages: List[Dict], query: str) -> Dict[str, Any]:
        """Build metadata about search results for guided query generation"""
        
        # Extract channels
        channels = list(set(
            msg.get('source_chat_id') or msg.get('target_chat_id') or 'unknown'
            for msg in messages
        ))
        
        # Extract semantic topics from message content
        topics_found = self._extract_semantic_topics(messages, query)
        
        return {
            'total_messages': len(messages),
            'channels': channels,
            'topics_found': topics_found,
            'date_range': self._get_date_range(messages),
            'top_contributors': self._get_top_contributors(messages),
            'channel_titles': self._get_channel_titles(messages)
        }
    
    def _get_date_range(self, messages: List[Dict]) -> str:
        """Get the date range of messages"""
        if not messages:
            return "N/A"
        
        try:
            timestamps = [msg.get('timestamp') for msg in messages if msg.get('timestamp')]
            if timestamps:
                from datetime import datetime
                dates = [datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else ts for ts in timestamps]
                dates = [d for d in dates if d]  # Filter out None
                if dates:
                    min_date = min(dates)
                    max_date = max(dates)
                    return f"{min_date.strftime('%b %d')} - {max_date.strftime('%b %d, %Y')}"
        except Exception as e:
            logger.warning(f"Error calculating date range: {e}")
        
        return "N/A"
    
    def _get_top_contributors(self, messages: List[Dict], limit: int = 5) -> List[str]:
        """Get top contributors from messages"""
        if not messages:
            return []
        
        try:
            from collections import Counter
            senders = [msg.get('sender_name', 'Unknown') for msg in messages if msg.get('sender_name')]
            counter = Counter(senders)
            return [name for name, _ in counter.most_common(limit)]
        except Exception as e:
            logger.warning(f"Error getting top contributors: {e}")
            return []
    
    def _extract_semantic_topics(self, messages: List[Dict], query: str) -> Dict[str, Any]:
        """Extract meaningful topics from message content using keyword analysis"""
        if not messages:
            return {}
        
        import re
        from collections import Counter
        
        # Common business keywords that indicate topics
        topic_patterns = {
            # Project/Product names (capitalized words, acronyms)
            'projects': r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',
            # Events (words with "Event", "Meeting", "Launch", etc.)
            'events': r'\b\w+\s+(?:Event|Meeting|Launch|Conference|Summit|Presentation)\b',
            # Plans/Reports (Q1, Q2, Work Plan, Summary, Report, etc.)
            'plans': r'\b(?:Q[1-4]|[A-Z]+\s+)?(?:Work\s+Plan|Summary|Report|Proposal|Strategy|Business\s+Plan)\b',
            # People (@ mentions and full names)
            'people': r'@\w+|(?:[A-Z][a-z]+\s+[A-Z][a-z]+)',
            # Metrics/Numbers (percentages, rates, numbers with context)
            'metrics': r'\b\d+%|\b\d+\s+(?:customers|users|rate|percentage|conversion)\b'
        }
        
        topics_found = {}
        all_content = ' '.join([msg.get('content', '') or msg.get('text', '') for msg in messages[:20]])  # Limit to avoid too much processing
        
        # Extract capitalized phrases (likely to be names/titles)
        capitalized_phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', all_content)
        phrase_counter = Counter(capitalized_phrases)
        
        # Find significant phrases (mentioned more than once or longer than 2 words)
        for phrase, count in phrase_counter.most_common(10):
            if count >= 2 or len(phrase.split()) >= 2:
                # Get messages mentioning this phrase
                related_messages = [
                    msg for msg in messages 
                    if phrase.lower() in (msg.get('content', '') or msg.get('text', '')).lower()
                ]
                if related_messages:
                    topics_found[phrase] = {
                        'count': len(related_messages),
                        'messages': related_messages[:5],  # Limit to top 5
                        'type': 'named_entity'
                    }
        
        # Extract event names (anything with "Event", "Launch", "Meeting", etc.)
        events = re.findall(r'[\w\s]+\s+(?:Event|Launch|Meeting|Conference|Presentation)', all_content, re.IGNORECASE)
        for event in set(events):
            event_clean = event.strip()
            if len(event_clean) > 5:  # Filter out very short matches
                related_messages = [
                    msg for msg in messages 
                    if event_clean.lower() in (msg.get('content', '') or msg.get('text', '')).lower()
                ]
                if related_messages and event_clean not in topics_found:
                    topics_found[event_clean] = {
                        'count': len(related_messages),
                        'messages': related_messages[:5],
                        'type': 'event'
                    }
        
        # Extract plan/report names
        plans = re.findall(r'(?:Q[1-4]|[A-Z]+\s+)?(?:Work\s+Plan|Summary|Report|Proposal|Strategy|Business\s+Plan)', all_content, re.IGNORECASE)
        for plan in set(plans):
            plan_clean = plan.strip()
            related_messages = [
                msg for msg in messages 
                if plan_clean.lower() in (msg.get('content', '') or msg.get('text', '')).lower()
            ]
            if related_messages and plan_clean not in topics_found:
                topics_found[plan_clean] = {
                    'count': len(related_messages),
                    'messages': related_messages[:5],
                    'type': 'document'
                }
        
        # If no topics found, group by channel with actual titles
        if not topics_found:
            channels = {}
            for msg in messages:
                chat_id = msg.get('source_chat_id') or msg.get('target_chat_id')
                chat_title = msg.get('chat_title', f'Chat {chat_id}')
                
                if chat_title not in channels:
                    channels[chat_title] = []
                channels[chat_title].append(msg)
            
            for chat_title, channel_messages in channels.items():
                topics_found[chat_title] = {
                    'count': len(channel_messages),
                    'messages': channel_messages[:5],
                    'type': 'channel'
                }
        
        return topics_found
    
    def _get_channel_titles(self, messages: List[Dict]) -> Dict[str, str]:
        """Get mapping of channel IDs to channel titles"""
        channel_map = {}
        for msg in messages:
            chat_id = msg.get('source_chat_id') or msg.get('target_chat_id')
            chat_title = msg.get('chat_title')
            if chat_id and chat_title:
                channel_map[str(chat_id)] = chat_title
        return channel_map

    def _extract_simple_time_period(self, query: str) -> Optional[str]:
        """Fast extraction of time period from query without LLM"""
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["today", "this day"]):
            return "today"
        elif any(word in query_lower for word in ["yesterday", "last day"]):
            return "yesterday"
        elif any(word in query_lower for word in ["this week", "past week", "last week"]):
            return "week"
        elif any(word in query_lower for word in ["this month", "past month", "last month"]):
            return "month"
        
        return None

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
            "name the",
            "any new",
            "any recent",
            "latest",
            "update",
            "news"
        ]
        
        # Check for common follow-up phrases
        for phrase in follow_up_phrases:
            if current_query.lower().startswith(phrase):
                return True
            
        # Check for keyword overlap first - if there's significant overlap, likely related
        def extract_keywords(text: str) -> List[str]:
            # Remove stop words and punctuation, keep meaningful keywords
            text = re.sub(r'[^\w\s]', ' ', text.lower())
            words = text.split()
            stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'about', 'and', 'or', 'what', 'where', 'when', 'how', 'which', 'who', 'why', 'make', 'list', 'tell', 'me', 'show'}
            return [w for w in words if len(w) > 2 and w not in stop_words]
        
        current_keywords = set(extract_keywords(current_query))
        previous_keywords = set(extract_keywords(previous_query))
        
        # Check for shared company/entity names or specific terms
        overlap = current_keywords.intersection(previous_keywords)
        
        # If there's significant keyword overlap, it's likely related
        if len(overlap) >= 1:
            logger.info(f"Found keyword overlap: {overlap}")
            return True
        
        # Check for similar business/company context
        business_indicators = ["business", "company", "customers", "developments", "growth", "expansion", "market", "clients", "partners", "collaboration", "training", "program", "services"]
        
        current_has_business = any(indicator in current_query.lower() for indicator in business_indicators)
        previous_has_business = any(indicator in previous_query.lower() for indicator in business_indicators)
        
        # If both queries are business-related, they're likely related
        if current_has_business and previous_has_business:
            logger.info("Both queries are business-related, treating as follow-up")
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
            
            # If we can identify topics in both and they're completely different, consider it a new query
            if previous_topic and current_topic and previous_topic.lower() != current_topic.lower():
                # Check if they're related topics (e.g., both companies, both locations)
                if not self._are_related_topics(previous_topic, current_topic):
                    logger.info(f"Detected unrelated topic change from '{previous_topic}' to '{current_topic}'")
                    return False
            
            # Topics overlap or couldn't be determined clearly, treat as follow-up
            return True
        
        # If the current query is very short and there's any keyword overlap, likely a follow-up
        if len(current_query.split()) <= 4 and len(overlap) > 0:
            return True
        
        return False
    
    def _are_related_topics(self, topic1: str, topic2: str) -> bool:
        """
        Check if two topics are related (e.g., both companies, both locations)
        
        Args:
            topic1: First topic
            topic2: Second topic
            
        Returns:
            bool: True if topics are related
        """
        # Company/business name patterns
        business_suffixes = ["inc", "corp", "ltd", "llc", "co", "company", "technologies", "tech", "systems", "solutions"]
        
        def is_business_name(name: str) -> bool:
            name_lower = name.lower()
            return any(suffix in name_lower for suffix in business_suffixes) or len(name.split()) <= 2
        
        # If both look like business names, they're related
        if is_business_name(topic1) and is_business_name(topic2):
            return True
        
        # Location patterns
        common_locations = ["gaza", "israel", "palestine", "ukraine", "russia", "syria", "lebanon", "iran", "iraq", "china", "usa", "america"]
        
        def is_location(name: str) -> bool:
            return name.lower() in common_locations
        
        # If both are locations, they're related
        if is_location(topic1) and is_location(topic2):
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
    
    async def _enhance_query_with_context(
        self,
        current_query: str,
        previous_query: str,
        conversation_history: List[Dict[str, str]],
        entities: List[str],
        topics: List[str]
    ) -> str:
        """
        Enhance a follow-up query with conversation context using LLM
        
        Args:
            current_query: The current user query
            previous_query: The previous user query
            conversation_history: List of previous conversation messages
            entities: Extracted entities from current query
            topics: Extracted topics from current query
            
        Returns:
            str: Enhanced query that incorporates necessary context
        """
        try:
            # Get conversation intelligence
            conversation_intelligence = self._get_conversation_intelligence()
            if not conversation_intelligence or not conversation_intelligence.llm_client:
                # Fallback: simple context extraction
                return self._simple_query_enhancement(current_query, previous_query)
            
            # Build a prompt to enhance the query
            system_prompt = """You are a query enhancement assistant. Your job is to take a follow-up question and add necessary context from the previous conversation so it can be searched effectively.

**Important Rules**:
1. If the current query is complete and self-contained, return it unchanged
2. If the current query references context from previous messages, merge that context into the query
3. Keep the enhanced query natural and searchable
4. Don't add unnecessary details - only add what's needed for understanding
5. Return ONLY the enhanced query text, nothing else

**Examples**:

Previous: "What's the latest news about Gaza?"
Current: "What cities are being affected?"
Enhanced: "What cities in Gaza are being affected?"

Previous: "Tell me about Apple's new product"
Current: "When was it released?"
Enhanced: "When was Apple's new product released?"

Previous: "What happened in the Ukraine conflict?"
Current: "Who is involved?"
Enhanced: "Who is involved in the Ukraine conflict?"

Previous: "Search for crypto news"
Current: "What are the prices?"
Enhanced: "What are the crypto prices?"

Current: "Tell me about climate change" (complete query, no previous context needed)
Enhanced: "Tell me about climate change"
"""
            
            # Build context information
            context_parts = []
            
            # Add recent conversation exchanges (last 2-3 exchanges)
            if conversation_history and len(conversation_history) >= 2:
                recent = conversation_history[-4:]  # Last 2 exchanges (user + assistant)
                context_parts.append("## Recent Conversation:")
                for msg in recent:
                    role = msg.get("role", "").upper()
                    content = msg.get("content", "")
                    # Truncate long messages
                    if len(content) > 100:
                        content = content[:100] + "..."
                    context_parts.append(f"{role}: {content}")
            
            # Add entities and topics if available
            if entities or topics:
                context_parts.append("\n## Context Information:")
                if entities:
                    context_parts.append(f"Entities mentioned: {', '.join(entities)}")
                if topics:
                    context_parts.append(f"Topics discussed: {', '.join(topics)}")
            
            # Build user prompt
            user_prompt = f"""{chr(10).join(context_parts)}

## Current Query to Enhance:
{current_query}

## Enhanced Query:"""
            
            # Call LLM to enhance the query
            response = await conversation_intelligence.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            if response and response.get("content"):
                enhanced = response["content"].strip()
                # Remove any quotes or extra formatting
                enhanced = enhanced.strip('"\'')
                
                # Sanity check: enhanced query shouldn't be dramatically longer
                if len(enhanced) > len(current_query) * 3:
                    logger.warning("Enhanced query too long, using fallback")
                    return self._simple_query_enhancement(current_query, previous_query)
                
                # If enhancement is too similar or identical, return original
                if enhanced.lower() == current_query.lower():
                    return current_query
                
                return enhanced
            
            # Fallback if LLM fails
            return self._simple_query_enhancement(current_query, previous_query)
            
        except Exception as e:
            logger.warning(f"Error enhancing query with context: {e}")
            return self._simple_query_enhancement(current_query, previous_query)
    
    def _simple_query_enhancement(self, current_query: str, previous_query: str) -> str:
        """
        Simple rule-based query enhancement as fallback
        
        Args:
            current_query: Current user query
            previous_query: Previous user query
            
        Returns:
            str: Enhanced query
        """
        # Extract location/entity from previous query
        location = self._extract_location_context(previous_query)
        primary_topic = self._extract_primary_topic(previous_query)
        
        # Check if current query needs context
        needs_context_phrases = [
            "what cities", "which cities", "what places", "which places",
            "what about", "who", "when", "where", "how many",
            "what are", "which are", "who are", "list the", "name the"
        ]
        
        current_lower = current_query.lower()
        needs_context = any(phrase in current_lower for phrase in needs_context_phrases)
        
        if not needs_context:
            return current_query
        
        # Add location context if available and relevant
        if location and location.lower() not in current_lower:
            if any(word in current_lower for word in ["cities", "places", "locations", "areas"]):
                return f"{current_query} in {location}"
        
        # Add topic context if available and relevant
        if primary_topic and primary_topic.lower() not in current_lower:
            # For certain types of questions, add the topic
            if any(phrase in current_lower for phrase in ["who", "what", "when", "which", "how"]):
                return f"{current_query} about {primary_topic}"
        
        return current_query

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