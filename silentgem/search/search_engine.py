"""
Search engine for finding messages in the database
"""

from loguru import logger
from typing import List, Dict, Any, Optional, Tuple
import re
import time
from datetime import datetime, timedelta
import json

from silentgem.database.message_store import get_message_store
from silentgem.config.insights_config import get_insights_config
from silentgem.llm.llm_client import get_llm_client
from silentgem.query_params import QueryParams

class SearchEngine:
    """Search engine for finding messages in the database"""
    
    def __init__(self):
        """Initialize the search engine"""
        self.message_store = get_message_store()
        self.config = get_insights_config()
        self.llm_client = get_llm_client()
    
    async def search(self, search_params: QueryParams) -> List[Dict[str, Any]]:
        """
        Search for messages using QueryParams object
        
        Args:
            search_params: QueryParams object containing search parameters
            
        Returns:
            List of matching messages
        """
        # Extract parameters from QueryParams
        query = search_params.query
        chat_ids = [search_params.chat_id] if search_params.chat_id else None
        time_limit = search_params.get_time_range()
        strategies = search_params.strategies
        
        # Call the original search method with extracted parameters
        results, _ = await self._search(
            query=query,
            chat_ids=chat_ids,
            sender=search_params.sender,
            collect_context=True,
            llm_expand_query=True,
            max_results=search_params.limit,
            time_limit=time_limit,
            strategies=strategies,
            parsed_query={"processed_query": query, "time_period": search_params.time_period}
        )
        
        return results
    
    async def _search(
        self,
        query: str,
        chat_ids: Optional[List[int]] = None,
        sender: Optional[str] = None,
        collect_context: bool = True,
        llm_expand_query: bool = True,
        max_results: int = 50,
        max_context_per_message: int = 10,
        time_limit: Optional[Tuple[datetime, datetime]] = None,
        strategies: Optional[List[str]] = None,
        parsed_query: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Search for messages based on the provided query
        
        Args:
            query: Search query string
            chat_ids: Optional list of chat IDs to restrict search to
            sender: Optional sender name to restrict search to
            collect_context: Whether to collect context messages
            llm_expand_query: Whether to use LLM to expand query semantically
            max_results: Maximum number of search results to return
            max_context_per_message: Maximum number of context messages to collect per result
            time_limit: Optional tuple of (start_time, end_time) to restrict search to
            strategies: List of search strategies to use (default: ["direct", "semantic"])
            parsed_query: Optional pre-processed query information from QueryProcessor
            
        Returns:
            Tuple of (search results, query metadata)
        """
        start_time = time.time()
        message_store = get_message_store()
        
        if not query or not query.strip():
            logger.warning("Empty search query provided")
            return [], {"query": query, "expanded_queries": [], "strategies": [], "time": 0}
        
        # Use provided strategies or get from parsed query if available
        if not strategies and parsed_query and "search_strategies" in parsed_query:
            strategies = parsed_query.get("search_strategies")
        elif not strategies:
            strategies = ["direct", "semantic"]
        
        # Check if we already have expanded terms from query processor
        has_expanded_terms = False
        expanded_terms = []
        if parsed_query and "expanded_terms" in parsed_query:
            expanded_terms = parsed_query.get("expanded_terms", [])
            has_expanded_terms = bool(expanded_terms)
        
        # Process OR terms separately
        # Check if query contains OR operators
        has_or_terms = " OR " in query
        flat_or_terms = []
        
        if has_or_terms:
            # Split by " OR " to get all terms
            flat_or_terms = query.split(" OR ")
            flat_or_terms = [term.strip() for term in flat_or_terms if term.strip()]
            
            # First term will be used for direct search
            direct_search_query = flat_or_terms[0] if flat_or_terms else query
        else:
            direct_search_query = query
        
        results = []
        all_expanded_queries = []
        direct_matches = set()  # Track direct match message IDs to prioritize them
        
        # Step 1: Direct search if enabled
        if "direct" in strategies:
            logger.debug(f"Performing direct search for: {direct_search_query}")
            
            # Search for main query terms
            if direct_search_query:
                direct_results = message_store.search_messages(
                    query=direct_search_query,
                    chat_ids=chat_ids,
                    sender=sender,
                    limit=max_results,
                    time_range=time_limit,
                )
                
                for msg in direct_results:
                    msg["match_type"] = "direct"
                    msg["matched_term"] = direct_search_query
                    direct_matches.add(msg["message_id"])
                
                results.extend(direct_results)
                
            # Search for OR terms
            if has_or_terms:
                for term in flat_or_terms:
                    logger.debug(f"Searching for OR term: {term}")
                    or_results = message_store.search_messages(
                        query=term,
                        chat_ids=chat_ids,
                        sender=sender,
                        limit=max_results // 2,  # Limit results per OR term
                        time_range=time_limit,
                    )
                    
                    for msg in or_results:
                        if msg["message_id"] not in direct_matches:  # Avoid duplicates with direct matches
                            msg["match_type"] = "or_term"
                            msg["matched_term"] = term
                            results.append(msg)
        
        # Step 2: Semantic search if enabled
        if "semantic" in strategies:
            # Use expanded terms from QueryProcessor if available
            if has_expanded_terms:
                semantic_query_terms = expanded_terms
                all_expanded_queries = expanded_terms.copy()
                logger.debug(f"Using {len(semantic_query_terms)} expanded terms from query processor")
            # Otherwise use LLM to expand query if requested
            elif llm_expand_query and self.llm_client:
                try:
                    # Get semantically expanded queries
                    semantic_query_terms = await self._process_query_with_llm(query)
                    all_expanded_queries = semantic_query_terms.copy()
                    
                    # Remove the original query from expanded queries to avoid duplicate searches
                    if query in semantic_query_terms:
                        semantic_query_terms.remove(query)
                    
                    logger.debug(f"Using {len(semantic_query_terms)} expanded terms from LLM")
                except Exception as e:
                    logger.error(f"Error during semantic query expansion: {e}")
                    semantic_query_terms = []
            else:
                semantic_query_terms = []
            
            # Perform semantic search with expanded terms
            if semantic_query_terms:
                logger.debug(f"Performing semantic search with {len(semantic_query_terms)} expanded terms")
                
                for expanded_query in semantic_query_terms:
                    # Skip very short expanded queries
                    if len(expanded_query.strip()) < 3:
                        continue
                        
                    semantic_results = message_store.search_messages(
                        query=expanded_query,
                        chat_ids=chat_ids,
                        sender=sender,
                        limit=max_results // len(semantic_query_terms),  # Distribute limit among expanded queries
                        time_range=time_limit,
                    )
                    
                    for msg in semantic_results:
                        # Skip if this message was already found in direct search
                        if msg["message_id"] in direct_matches:
                            continue
                            
                        # Add semantic match info
                        msg["match_type"] = "semantic"
                        msg["matched_term"] = expanded_query
                        results.append(msg)
        
        # Step 3: Fuzzy search if enabled
        if "fuzzy" in strategies and not results:
            logger.debug(f"Performing fuzzy search as fallback for: {query}")
            
            # Simple fuzzy search implementation
            fuzzy_results = message_store.search_messages(
                query=query,
                chat_ids=chat_ids,
                sender=sender,
                limit=max_results,
                time_range=time_limit,
                fuzzy=True  # Enable fuzzy matching if supported by the database
            )
            
            for msg in fuzzy_results:
                if msg["message_id"] not in direct_matches:
                    msg["match_type"] = "fuzzy"
                    msg["matched_term"] = query
                    results.append(msg)
        
        # Deduplicate results based on message_id
        seen_ids = set()
        unique_results = []
        
        # Define sort key to prioritize direct matches, then OR terms, then semantic matches, then fuzzy
        def result_sort_key(msg):
            # First sort by match type (direct > or_term > semantic > fuzzy)
            match_type_priority = {
                "direct": 0,
                "or_term": 1,
                "semantic": 2,
                "fuzzy": 3
            }
            priority = match_type_priority.get(msg.get("match_type", "semantic"), 4)
            
            # Then sort by timestamp (newest first)
            timestamp = msg.get("timestamp", datetime.now())
            
            return (priority, -int(timestamp.timestamp() if isinstance(timestamp, datetime) else 0))
        
        # Sort and deduplicate
        for msg in sorted(results, key=result_sort_key):
            if msg["message_id"] not in seen_ids:
                seen_ids.add(msg["message_id"])
                unique_results.append(msg)
        
        # Limit total results
        final_results = unique_results[:max_results]
        
        # Collect context for each result
        if collect_context:
            for msg in final_results:
                context_messages = await self._collect_extended_context(
                    msg,
                    message_store,
                    max_context=max_context_per_message
                )
                msg["context"] = context_messages
        
        # Build metadata
        execution_time = time.time() - start_time
        metadata = {
            "query": query,
            "expanded_queries": all_expanded_queries,
            "strategies": strategies,
            "time": round(execution_time, 3)
        }
        
        # Add parsed query information to metadata if available
        if parsed_query:
            metadata["parsed_query"] = parsed_query
        
        logger.info(f"Search for '{query}' found {len(final_results)} messages in {execution_time:.2f}s")
        return final_results, metadata
    
    async def _process_query_with_llm(self, query: str) -> List[str]:
        """
        Process query with LLM to expand it semantically
        
        Args:
            query: Original search query
            
        Returns:
            List of expanded search terms
        """
        try:
            # Don't process very short queries or empty queries
            if not query or len(query.strip()) < 3:
                return [query] if query else []
                
            # Create a prompt for the LLM
            system_prompt = """You are a search query expansion assistant. Your task is to:
1. Understand the semantic meaning of the search query
2. Expand the query with relevant alternative search phrases
3. Identify important key terms in the query
4. Split complex queries into their core concepts

For each query, generate 3-5 alternative search phrases that would help find relevant messages.
Consider synonyms, related concepts, domain-specific language, and common abbreviations.
Extract the most important terms that should definitely be included in results.
Respond with a JSON object in this format:
{
  "expanded_terms": ["term1", "term2", "term3"],
  "key_concepts": ["concept1", "concept2"]
}
"""

            user_prompt = f"Search query: {query}"
            
            response = await self.llm_client.complete(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=250,  # Increased from 150 to allow for more detailed responses
                temperature=0.4,  # Reduced from 0.5 for more focused results
                response_format={"type": "json_object"}
            )
            
            if not response:
                logger.warning("Empty response from LLM during query processing")
                return [query]
                
            try:
                # First try to parse the raw response
                try:
                    parsed_response = json.loads(response)
                except json.JSONDecodeError:
                    # If that fails, try to extract JSON using regex
                    logger.warning("Initial JSON parsing failed, trying to extract JSON with regex")
                    json_match = re.search(r'({[\s\S]*})', response)
                    if json_match:
                        json_str = json_match.group(1)
                        try:
                            parsed_response = json.loads(json_str)
                        except json.JSONDecodeError:
                            # Last resort: strip any extra text that might be after the JSON
                            # Sometimes LLMs add explanations after the JSON
                            logger.warning("Regex extraction failed, trying to clean up the JSON")
                            lines = json_str.split('\n')
                            # Find where the closing brace is and keep only up to that point
                            for i, line in enumerate(lines):
                                if '}' in line:
                                    cleaned_json = '\n'.join(lines[:i+1])
                                    # Make sure we include the closing brace
                                    if not cleaned_json.strip().endswith('}'):
                                        cleaned_json = cleaned_json + '}'
                                    try:
                                        parsed_response = json.loads(cleaned_json)
                                        break
                                    except:
                                        pass
                            else:
                                # If we got here, we failed to parse the JSON
                                logger.error(f"Failed to parse LLM response after cleanup attempts: {response}")
                                return [query]
                    else:
                        # No JSON-like content found
                        logger.error(f"No JSON found in LLM response: {response}")
                        return [query]
                
                expanded_terms = parsed_response.get("expanded_terms", [])
                key_concepts = parsed_response.get("key_concepts", [])
                
                # Combine and ensure the original query is included
                all_terms = expanded_terms + key_concepts
                if query not in all_terms:
                    all_terms.append(query)
                    
                # Remove duplicates (case-insensitive)
                seen = set()
                unique_terms = []
                for term in all_terms:
                    term_lower = term.lower()
                    if term_lower not in seen:
                        seen.add(term_lower)
                        unique_terms.append(term)
                
                logger.debug(f"Expanded query '{query}' to {len(unique_terms)} terms: {unique_terms}")
                return unique_terms
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}. Response: {response}")
                return [query]
                
        except Exception as e:
            logger.error(f"Error in query processing with LLM: {e}")
            return [query] if query else []
    
    async def _collect_extended_context(
        self, 
        message: Dict[str, Any], 
        message_store,
        max_context: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Collect context messages for a given message
        
        Args:
            message: The message to collect context for
            message_store: The message store to query
            max_context: Maximum number of context messages to collect
            
        Returns:
            List of context messages
        """
        try:
            message_id = message.get("id")
            source_chat_id = message.get("source_chat_id")
            
            if not message_id:
                logger.warning("Cannot collect context: Message ID not found")
                return []
            
            # Use get_message_context directly without await since it's synchronous
            context = message_store.get_message_context(
                message_id=message_id,
                source_chat_id=source_chat_id,
                before_count=max_context // 2,
                after_count=max_context // 2,
                cross_chat_context=True
            )
            
            # Combine before and after messages
            context_messages = []
            if context:
                context_messages.extend(context.get('before', []))
                context_messages.extend(context.get('after', []))
            
            return context_messages
        except Exception as e:
            logger.error(f"Error collecting context: {e}")
            return []
    
    async def get_recent_activity(self, chat_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
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
            
            # If we have results, collect some context
            if results:
                # Get the most recent message
                most_recent = max(results, key=lambda x: x.get("timestamp", 0))
                
                # Get context for the most recent message - no await needed
                context = self.message_store.get_message_context(
                    message_id=most_recent.get("id"),
                    source_chat_id=most_recent.get("source_chat_id"),
                    before_count=25,  # Get more context for recent activity
                    after_count=0,    # No messages after the most recent
                    cross_chat_context=True
                )
                
                # Add context to the results
                if context.get("before"):
                    # Create a map of message IDs we already have
                    existing_ids = {msg.get("id") for msg in results if msg.get("id")}
                    
                    # Add context messages that aren't already in results
                    for ctx_msg in context.get("before"):
                        if ctx_msg.get("id") and ctx_msg.get("id") not in existing_ids:
                            ctx_msg["relative_time"] = self._get_relative_time(ctx_msg.get("timestamp", 0))
                            ctx_msg["is_context"] = True
                            results.append(ctx_msg)
                    
                    # Re-sort by timestamp
                    results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            
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
        elif diff < 2592000:  # ~30 days
            weeks = int(diff / 604800)
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
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