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

# Simple cache for expanded query terms
_expansion_cache = {}
_expansion_cache_ttl = 600  # 10 minutes

class SearchEngine:
    """Search engine for finding messages in the database"""
    
    def __init__(self):
        """Initialize the search engine"""
        self.message_store = get_message_store()
        self.config = get_insights_config()
        self.llm_client = get_llm_client()
        
        # Performance settings
        self.fast_mode = True  # Skip expensive LLM expansions
        self.max_semantic_terms = 3  # Limit semantic expansion
        self.enable_context_collection = False  # Skip context collection for speed
    
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
        strategies = search_params.strategies or ["direct"]  # Default to direct only for speed
        
        # Call the optimized search method
        results, _ = await self._search(
            query=query,
            chat_ids=chat_ids,
            sender=search_params.sender,
            collect_context=self.enable_context_collection,
            llm_expand_query=not self.fast_mode,  # Skip LLM expansion in fast mode
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
        collect_context: bool = False,  # Default to False for speed
        llm_expand_query: bool = False,  # Default to False for speed
        max_results: int = 50,
        max_context_per_message: int = 5,  # Reduced for speed
        time_limit: Optional[Tuple[datetime, datetime]] = None,
        strategies: Optional[List[str]] = None,
        parsed_query: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Search for messages based on the provided query (optimized for speed)
        """
        start_time = time.time()
        message_store = get_message_store()
        
        if not query or not query.strip():
            logger.warning("Empty search query provided")
            return [], {"query": query, "expanded_queries": [], "strategies": [], "time": 0}

        # Use simplified strategies for speed
        if not strategies:
            strategies = ["direct"]  # Only direct search by default
        
        # Process OR terms separately for better performance
        has_or_terms = " OR " in query
        flat_or_terms = []
        
        if has_or_terms:
            flat_or_terms = [term.strip() for term in query.split(" OR ") if term.strip()]
            direct_search_query = flat_or_terms[0] if flat_or_terms else query
        else:
            direct_search_query = query
        
        results = []
        all_expanded_queries = []
        direct_matches = set()
        
        # Step 1: Direct search (always enabled for speed)
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
            
        # Search for OR terms if present
        if has_or_terms and len(flat_or_terms) > 1:
            for term in flat_or_terms[1:]:  # Skip first term as it's already searched
                logger.debug(f"Searching for OR term: {term}")
                or_results = message_store.search_messages(
                    query=term,
                    chat_ids=chat_ids,
                    sender=sender,
                    limit=max_results // len(flat_or_terms),
                    time_range=time_limit,
                )
                
                for msg in or_results:
                    if msg["message_id"] not in direct_matches:
                        msg["match_type"] = "or_term"
                        msg["matched_term"] = term
                        results.append(msg)

        # Step 2: Semantic search (only if enabled and no direct results)
        if "semantic" in strategies and not results and llm_expand_query:
            semantic_query_terms = await self._get_cached_expansion(query)
            
            if semantic_query_terms:
                logger.debug(f"Performing semantic search with {len(semantic_query_terms)} expanded terms")
                
                for expanded_query in semantic_query_terms[:self.max_semantic_terms]:
                    if len(expanded_query.strip()) < 3:
                        continue
                        
                    semantic_results = message_store.search_messages(
                        query=expanded_query,
                        chat_ids=chat_ids,
                        sender=sender,
                        limit=max_results // len(semantic_query_terms),
                        time_range=time_limit,
                    )
                    
                    for msg in semantic_results:
                        if msg["message_id"] not in direct_matches:
                            msg["match_type"] = "semantic"
                            msg["matched_term"] = expanded_query
                            results.append(msg)

        # Step 3: Fuzzy search (only as last resort)
        if "fuzzy" in strategies and not results:
            logger.debug(f"Performing fuzzy search as fallback for: {query}")
            
            fuzzy_results = message_store.search_messages(
                query=query,
                chat_ids=chat_ids,
                sender=sender,
                limit=max_results,
                time_range=time_limit,
                fuzzy=True
            )
            
            for msg in fuzzy_results:
                if msg["message_id"] not in direct_matches:
                    msg["match_type"] = "fuzzy"
                    msg["matched_term"] = query
                    results.append(msg)

        # Deduplicate and sort results
        seen_ids = set()
        unique_results = []
        
        # Simple sort by match type priority and timestamp
        def result_sort_key(msg):
            match_type_priority = {"direct": 0, "or_term": 1, "semantic": 2, "fuzzy": 3}
            priority = match_type_priority.get(msg.get("match_type", "semantic"), 4)
            timestamp = msg.get("timestamp", 0)
            return (priority, -timestamp)
        
        for msg in sorted(results, key=result_sort_key):
            if msg["message_id"] not in seen_ids:
                seen_ids.add(msg["message_id"])
                unique_results.append(msg)
        
        # Limit total results
        final_results = unique_results[:max_results]
        
        # Skip context collection for speed unless explicitly requested
        if collect_context:
            for msg in final_results:
                context_messages = await self._collect_minimal_context(msg, message_store, max_context_per_message)
                msg["context"] = context_messages

        # Build metadata
        execution_time = time.time() - start_time
        metadata = {
            "query": query,
            "expanded_queries": all_expanded_queries,
            "strategies": strategies,
            "time": round(execution_time, 3)
        }
        
        if parsed_query:
            metadata["parsed_query"] = parsed_query
        
        logger.info(f"Search for '{query}' found {len(final_results)} messages in {execution_time:.2f}s")
        return final_results, metadata

    async def _get_cached_expansion(self, query: str) -> List[str]:
        """Get cached query expansion or generate new one"""
        cache_key = query.lower().strip()
        
        # Check cache first
        if cache_key in _expansion_cache:
            cached_terms, timestamp = _expansion_cache[cache_key]
            if time.time() - timestamp < _expansion_cache_ttl:
                return cached_terms
            else:
                del _expansion_cache[cache_key]
        
        # Generate new expansion (simplified)
        expanded_terms = self._simple_query_expansion(query)
        
        # Cache the result
        _expansion_cache[cache_key] = (expanded_terms, time.time())
        
        return expanded_terms

    def _simple_query_expansion(self, query: str) -> List[str]:
        """Simple rule-based query expansion without LLM"""
        expanded = []
        query_lower = query.lower()
        
        # Simple synonym mapping for common terms
        synonyms = {
            "price": ["cost", "value", "pricing"],
            "buy": ["purchase", "acquire", "get"],
            "sell": ["sale", "selling", "sold"],
            "good": ["great", "excellent", "nice"],
            "bad": ["poor", "terrible", "awful"],
            "new": ["latest", "recent", "fresh"],
            "old": ["previous", "past", "former"],
            "big": ["large", "huge", "massive"],
            "small": ["tiny", "little", "mini"]
        }
        
        # Add synonyms for words in the query
        words = query_lower.split()
        for word in words:
            if word in synonyms:
                expanded.extend(synonyms[word])
        
        # Add partial matches
        if len(query) > 6:
            # Add query without last word
            words = query.split()
            if len(words) > 1:
                expanded.append(" ".join(words[:-1]))
        
        # Remove duplicates and limit
        expanded = list(set(expanded))[:self.max_semantic_terms]
        
        return expanded

    async def _collect_minimal_context(
        self, 
        message: Dict[str, Any], 
        message_store,
        max_context: int = 3  # Reduced for speed
    ) -> List[Dict[str, Any]]:
        """
        Collect minimal context around a message for speed
        """
        try:
            message_id = message.get("id")
            if not message_id:
                return []
            
            # Get minimal context (fewer messages)
            context = message_store.get_message_context(
                message_id=message_id,
                before_count=max_context // 2,
                after_count=max_context // 2,
                cross_chat_context=False  # Stay within same chat for speed
            )
            
            # Combine before and after context
            all_context = context.get("before", []) + context.get("after", [])
            
            # Limit and return
            return all_context[:max_context]
            
        except Exception as e:
            logger.warning(f"Error collecting context for message {message.get('id')}: {e}")
            return []

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
5. Recognize entity types like places, people, and topics

For each query, generate 3-5 alternative search phrases that would help find relevant messages.
Consider synonyms, related concepts, domain-specific language, and common abbreviations.
Extract the most important terms that should definitely be included in results.

IMPORTANT: 
- Focus on the SPECIFIC topic of the query, don't mix unrelated topics
- When a query asks "What's happening in X?", focus only on X and related terms
- Never include terms from completely unrelated topics
- For example, if the query is about blockchain, don't include terms about conflicts or weather events
- If the query is about Gaza conflicts, don't include terms about cryptocurrency or blockchain

For queries about places, locations, cities:
- Common spellings and variations of place names
- Alternative names for the same locations
- Regional terms, neighborhoods, and districts
- Categories like "town", "city", "location", "area", "region"

For queries about "places hit" or similar, include terms for:
- affected areas, damaged locations, impact zones, target sites
- cities, towns, villages affected
- regions and territories mentioned

Return your response as a JSON object with this structure:
{
  "expanded_terms": ["term1", "term2", "term3"],
  "key_concepts": ["concept1", "concept2"],
  "entity_type": "place|person|topic|event|other",
  "primary_topic": "main subject of the query"
}
"""

            user_prompt = f"Search query: {query}"
            
            response = await self.llm_client.complete(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=250,
                temperature=0.4,
                response_format={"type": "json_object"}
            )
            
            if not response:
                logger.warning("Empty response from LLM during query processing")
                return [query]
                
            try:
                # First try to parse the raw response
                try:
                    parsed_response = json.loads(response)
                    logger.debug(f"Successfully parsed JSON from search LLM")
                except json.JSONDecodeError:
                    # If that fails, try to extract JSON using regex
                    logger.info("Initial JSON parsing failed, trying to extract JSON with regex")
                    json_match = re.search(r'({[\s\S]*})', response)
                    if json_match:
                        json_str = json_match.group(1)
                        try:
                            parsed_response = json.loads(json_str)
                            logger.debug(f"Successfully extracted JSON with regex")
                        except json.JSONDecodeError:
                            # Better JSON cleanup strategy
                            logger.warning("Regex extraction failed, trying advanced JSON cleanup")
                            # Try to find and fix common JSON formatting issues
                            cleaned_json = json_str
                            # Fix unescaped quotes in strings
                            cleaned_json = re.sub(r'(?<!")(".*?)(?<!\\)"(.*?)(?<!\\)"(?!")', r'\1\"\2\"', cleaned_json)
                            # Fix trailing commas before closing brackets
                            cleaned_json = re.sub(r',\s*}', '}', cleaned_json)
                            # Fix missing quotes around property names
                            cleaned_json = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', cleaned_json)
                            
                            try:
                                parsed_response = json.loads(cleaned_json)
                                logger.debug(f"Successfully parsed JSON after cleanup")
                            except json.JSONDecodeError:
                                # Last resort: extract terms manually
                                logger.warning("Advanced cleanup failed, extracting terms manually")
                                parsed_response = self._extract_terms_manually(response, query)
                    else:
                        # No JSON-like content found
                        logger.warning(f"No JSON found in LLM response, using manual extraction")
                        parsed_response = self._extract_terms_manually(response, query)
                
                if not parsed_response or not isinstance(parsed_response, dict):
                    logger.warning("Invalid parsed response, using fallback")
                    return [query]
                
                expanded_terms = parsed_response.get("expanded_terms", [])
                key_concepts = parsed_response.get("key_concepts", [])
                entity_type = parsed_response.get("entity_type", "other")
                
                # Combine and ensure the original query is included
                all_terms = expanded_terms + key_concepts
                if query not in all_terms:
                    all_terms.append(query)
                    
                # For place/location queries, make sure we have place-specific terms
                if entity_type == "place" or "place" in query.lower() or "city" in query.lower() or "location" in query.lower():
                    place_terms = ["cities", "towns", "locations", "places", "areas", "regions", "territories"]
                    # Only add terms that aren't already included
                    for term in place_terms:
                        if not any(term in t.lower() for t in all_terms):
                            all_terms.append(term)
                
                # Remove duplicates (case-insensitive)
                seen = set()
                unique_terms = []
                for term in all_terms:
                    if term and isinstance(term, str):
                        term_lower = term.lower()
                        if term_lower not in seen:
                            seen.add(term_lower)
                            unique_terms.append(term)
                
                logger.debug(f"Expanded query '{query}' to {len(unique_terms)} terms: {unique_terms}")
                logger.info(f"Expanded query: {' OR '.join(unique_terms)}")
                return unique_terms
                
            except Exception as e:
                logger.error(f"Failed to process LLM response: {e}. Response: {response}")
                return [query]
                
        except Exception as e:
            logger.error(f"Error in query processing with LLM: {e}")
            return [query] if query else []
    
    def _extract_fallback_terms(self, query: str, response: str) -> List[str]:
        """
        Extract useful search terms from response when JSON parsing fails
        
        Args:
            query: The original query string
            response: The text response from the LLM
            
        Returns:
            List of extracted search terms
        """
        # Start with the original query
        terms = [query]
        
        # Extract anything that looks like it could be a search term
        # Look for lists like "1. term1", "- term2", etc.
        list_items = re.findall(r'(?:^|\n)\s*(?:[0-9]+\.|\-|\*)\s*([^\n]+)', response)
        if list_items:
            terms.extend(list_items)
        
        # Look for quoted strings which might contain search terms
        quoted = re.findall(r'"([^"]+)"', response)
        if quoted:
            terms.extend(quoted)
        
        # For place-related queries, add some standard place terms
        if "place" in query.lower() or "city" in query.lower() or "location" in query.lower():
            place_terms = ["cities", "towns", "locations", "places", "areas", "regions", "territories"]
            terms.extend(place_terms)
        
        # Remove duplicates and very short terms
        return list(set([term for term in terms if term and len(term) > 2]))
    
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
    
    def _extract_terms_manually(self, response: str, query: str) -> Dict[str, Any]:
        """
        Manually extract search terms when JSON parsing fails completely
        
        Args:
            response: The raw LLM response
            query: The original query
            
        Returns:
            dict: Extracted terms in expected format
        """
        try:
            # Start with the original query
            terms = [query]
            
            # Extract anything that looks like it could be a search term
            # Look for lists like "1. term1", "- term2", etc.
            list_items = re.findall(r'(?:^|\n)\s*(?:[0-9]+\.|\-|\*)\s*([^\n]+)', response)
            if list_items:
                terms.extend([item.strip() for item in list_items if item.strip()])
            
            # Look for quoted strings which might contain search terms
            quoted = re.findall(r'"([^"]+)"', response)
            if quoted:
                terms.extend([q.strip() for q in quoted if q.strip() and len(q.strip()) > 2])
            
            # Look for terms after common phrases
            phrase_patterns = [
                r'(?:terms?|keywords?|search for|look for|find):\s*([^\n]+)',
                r'(?:related|similar|expanded):\s*([^\n]+)',
                r'(?:also try|alternatives?):\s*([^\n]+)'
            ]
            
            for pattern in phrase_patterns:
                matches = re.findall(pattern, response, re.IGNORECASE)
                for match in matches:
                    # Split on common separators
                    split_terms = re.split(r'[,;|]', match)
                    terms.extend([t.strip() for t in split_terms if t.strip()])
            
            # For place-related queries, add some standard place terms
            if "place" in query.lower() or "city" in query.lower() or "location" in query.lower():
                place_terms = ["cities", "towns", "locations", "places", "areas", "regions", "territories"]
                terms.extend(place_terms)
            
            # Remove duplicates and very short terms
            unique_terms = []
            seen = set()
            for term in terms:
                if term and len(term) > 2:
                    term_clean = term.lower().strip()
                    if term_clean not in seen:
                        seen.add(term_clean)
                        unique_terms.append(term.strip())
            
            return {
                "expanded_terms": unique_terms[1:] if len(unique_terms) > 1 else [],  # Exclude original query
                "key_concepts": [],
                "entity_type": "other"
            }
            
        except Exception as e:
            logger.warning(f"Manual term extraction failed: {e}")
            return {
                "expanded_terms": [],
                "key_concepts": [],
                "entity_type": "other"
            }


# Singleton instance
_instance = None

def get_search_engine():
    """Get the search engine singleton instance"""
    global _instance
    if _instance is None:
        _instance = SearchEngine()
    return _instance 