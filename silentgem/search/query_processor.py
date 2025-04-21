"""
Query processor for understanding natural language queries in Chat Insights
"""

import re
import time
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from loguru import logger

from silentgem.config.insights_config import get_insights_config
from silentgem.translator import create_translator
from silentgem.llm.llm_client import get_llm_client

class QueryProcessor:
    """
    Process natural language queries for the Chat Insights feature with
    enhanced semantic understanding and query expansion capabilities.
    """
    
    def __init__(self):
        """Initialize the query processor"""
        self.config = get_insights_config()
        self.translator = None
        self.llm_client = get_llm_client()
    
    async def process_query(self, query_text: str) -> Dict[str, Any]:
        """
        Process a natural language query and extract search parameters
        
        Args:
            query_text: The raw query text from the user
            
        Returns:
            dict: Extracted parameters for search
        """
        try:
            # Basic query preprocessing
            query_text = query_text.strip()
            
            # Initialize result
            result = {
                "original_query": query_text,
                "query_text": None,
                "time_period": None,
                "sender": None,
                "intent": "search",  # Default intent is to search
                "expanded_terms": [],
                "search_strategies": ["direct", "semantic"],  # Default strategies
            }
            
            # Extract time period information
            time_info = self._extract_time_period(query_text)
            if time_info["time_period"]:
                result["time_period"] = time_info["time_period"]
            
            # Extract sender information
            sender_match = re.search(r'\bfrom\s+(@?\w+|\".+?\")\b', query_text, re.IGNORECASE)
            if sender_match:
                sender = sender_match.group(1)
                # Remove quotes if present
                if sender.startswith('"') and sender.endswith('"'):
                    sender = sender[1:-1]
                result["sender"] = sender
                # Remove sender specification from query
                query_text = re.sub(r'\bfrom\s+(@?\w+|\".+?\")\b', '', query_text, flags=re.IGNORECASE)
            
            # Get query processing depth
            query_depth = self.config.get("query_processing_depth", "standard")
            
            # For basic processing, just use the original query with time extraction
            if query_depth == "basic":
                # Remove time-related phrases for cleaner query
                clean_query = self._clean_query(query_text)
                result["query_text"] = clean_query
                return result
            
            # For standard and detailed processing, use LLM
            if query_depth in ["standard", "detailed"]:
                # Check if we should use advanced LLM processing
                use_advanced_llm = self.config.get("use_advanced_query_processing", True) and self.llm_client
                
                if use_advanced_llm:
                    processed_query = await self._process_with_advanced_llm(query_text, query_depth)
                    if processed_query:
                        result.update(processed_query)
                        return result
                
                # Fall back to traditional LLM processing if advanced failed or is disabled
                # Initialize translator if needed
                if not self.translator:
                    self.translator = await create_translator()
                
                # Use the same LLM as translation by default
                use_translation_llm = self.config.get("use_translation_llm", True)
                
                if use_translation_llm and self.translator:
                    # Check if the translator has an async translate method
                    if hasattr(self.translator, 'translate') and callable(self.translator.translate):
                        # Process using translation LLM
                        processed_query = await self._process_with_llm(query_text, query_depth)
                        if processed_query:
                            result.update(processed_query)
                            return result
                    else:
                        logger.warning("Translator doesn't have a valid translate method")
            
            # Fallback to basic processing if LLM fails
            clean_query = self._clean_query(query_text)
            result["query_text"] = clean_query
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            # Return a minimal result on error
            return {
                "original_query": query_text,
                "query_text": query_text,
                "time_period": None,
                "sender": None,
                "intent": "search"
            }
    
    def _clean_query(self, query_text: str) -> str:
        """
        Clean and normalize a query by removing filler words and time phrases
        
        Args:
            query_text: Original query text
            
        Returns:
            Cleaned query string
        """
        # Remove time-related phrases
        time_patterns = [
            r'\b(today|in the last day|past 24 hours|last 24 hours|24 hours ago)\b',
            r'\b(yesterday|past day|last day|a day ago|1 day ago)\b', 
            r'\b(this week|past week|last 7 days|last seven days|within a week|recent days|recent)\b',
            r'\b(this month|past month|last 30 days|last thirty days|within a month|last few weeks)\b'
        ]
        
        for pattern in time_patterns:
            query_text = re.sub(pattern, "", query_text, flags=re.IGNORECASE)
        
        # Remove common filler phrases
        filler_patterns = [
            r'\b(who|what|when|where|find|search|look for|show me|tell me about)\b',
            r'\b(can you|please|could you|i need|i want|i would like)\b'
        ]
        
        for pattern in filler_patterns:
            query_text = re.sub(pattern, "", query_text, flags=re.IGNORECASE)
        
        # Clean up multiple spaces
        query_text = re.sub(r'\s+', ' ', query_text).strip()
        
        return query_text
    
    def _extract_time_period(self, query_text: str) -> Dict[str, Any]:
        """
        Extract time period information from query
        
        Args:
            query_text: The query text
            
        Returns:
            dict with time period information
        """
        result = {"time_period": None}
        
        # Time period extraction (enhanced patterns)
        time_patterns = [
            # Today patterns
            (r'\b(today|in the last day|past 24 hours|last 24 hours|24 hours ago)\b', 'today'),
            # Yesterday patterns
            (r'\b(yesterday|past day|last day|a day ago|1 day ago)\b', 'yesterday'),
            # Week patterns 
            (r'\b(this week|past week|last 7 days|last seven days|within a week)\b', 'week'),
            # Month patterns
            (r'\b(this month|past month|last 30 days|last thirty days|within a month|last few weeks)\b', 'month')
        ]
        
        # Apply time patterns with case insensitivity
        for pattern, period in time_patterns:
            if re.search(pattern, query_text, re.IGNORECASE):
                result["time_period"] = period
                break
        
        # Check for recent events queries
        if not result["time_period"]:
            recent_event_patterns = [
                r'\b(recent|latest|new|current|ongoing|happening now|breaking|updates|events)\b',
                r'\b(what.?s new|what.?s happening|what.?s going on)\b',
                r'\b(news|developments|situation|update me)\b'
            ]
            
            for pattern in recent_event_patterns:
                if re.search(pattern, query_text, re.IGNORECASE):
                    # Default to past week for recent events queries
                    result["time_period"] = "week"
                    break
        
        return result
    
    async def _process_with_advanced_llm(self, query_text: str, depth: str = "standard") -> Optional[Dict[str, Any]]:
        """
        Process query using the advanced LLM client for enhanced semantic understanding
        
        Args:
            query_text: The raw query text
            depth: The processing depth (standard or detailed)
            
        Returns:
            dict: Extracted parameters or None on failure
        """
        if not self.llm_client:
            return None
            
        try:
            max_tokens = 350 if depth == "detailed" else 250
            temp = 0.2 if depth == "detailed" else 0.3
            
            # Construct system prompt based on depth
            if depth == "standard":
                system_prompt = """You are an advanced query analyzer for a chat search system that helps users find messages and insights in conversation history. 
Your task is to analyze the search query and extract key information that will help the search engine find the most relevant results.

Focus on identifying:
1. The core search terms - what the user is actually searching for
2. Expanded terms - semantically related concepts that might appear in relevant messages
3. Search strategies that would be most effective

Respond with a JSON object containing:
- processed_query: The main search terms
- expanded_terms: 3-5 semantically related terms/phrases
- search_strategies: Array of strategies in priority order ["direct", "semantic", "fuzzy"]
- time_period: Time period mentioned (today, yesterday, week, month, null)
- sender: Person who sent the message mentioned (null if none)
- intent: The search intent (search, summarize, analyze)
"""
            else:  # detailed
                system_prompt = """You are an advanced query analyzer for a chat search system that helps users find messages and insights in conversation history.
Your task is to analyze the search query and extract key information that will help the search engine find the most relevant results.

Focus on identifying:
1. The core search terms - what the user is actually searching for
2. Expanded terms - semantically related concepts that might appear in relevant messages
3. Alternative phrasings - different ways people might express the same ideas
4. Related entities - people, organizations, products, concepts related to the search
5. Search strategies that would be most effective

Respond with a JSON object containing:
- processed_query: The main search terms
- expanded_terms: 5-8 semantically related terms/phrases
- alternative_phrasings: 2-3 different ways to express the same query
- related_entities: 2-4 entities related to the query
- search_strategies: Array of strategies in priority order ["direct", "semantic", "fuzzy"]
- time_period: Time period mentioned (today, yesterday, week, month, null)
- sender: Person who sent the message mentioned (null if none)
- intent: The search intent (search, summarize, analyze, compare)
"""
            
            # Process with LLM
            response = await self.llm_client.chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Query: {query_text}"}
            ], temperature=temp, max_tokens=max_tokens)
            
            if not response or not response.get("content"):
                logger.warning("Empty response from LLM during advanced query processing")
                return None
                
            try:
                # Extract JSON from response
                content = response.get("content", "")
                json_match = re.search(r'({[\s\S]*})', content)
                
                if json_match:
                    json_str = json_match.group(1)
                    result = json.loads(json_str)
                    logger.debug(f"Processed query with advanced LLM: {result}")
                    
                    # Build a final result dictionary
                    final_result = {
                        "query_text": result.get("processed_query", query_text),
                        "original_query_text": query_text,
                        "expanded_terms": result.get("expanded_terms", []),
                        "search_strategies": result.get("search_strategies", ["direct", "semantic"]),
                        "time_period": result.get("time_period"),
                        "sender": result.get("sender"),
                        "intent": result.get("intent", "search"),
                    }
                    
                    # Add additional fields if present (for detailed mode)
                    if "alternative_phrasings" in result:
                        final_result["alternative_phrasings"] = result["alternative_phrasings"]
                    
                    if "related_entities" in result:
                        final_result["related_entities"] = result["related_entities"]
                    
                    # Build a comprehensive search query if requested
                    use_expanded_query = self.config.get("use_expanded_query", True)
                    if use_expanded_query:
                        # Build the expanded query
                        expanded_query_parts = [final_result["query_text"]]
                        
                        # Add terms from expanded_terms
                        expanded_terms = final_result.get("expanded_terms", [])
                        if expanded_terms:
                            expanded_query_parts.extend(expanded_terms)
                            
                        # Add terms from alternative_phrasings
                        alt_phrasings = final_result.get("alternative_phrasings", [])
                        if alt_phrasings:
                            expanded_query_parts.extend(alt_phrasings)
                        
                        # Create OR query
                        if len(expanded_query_parts) > 1:
                            final_result["query_text"] = " OR ".join(expanded_query_parts)
                            logger.info(f"Expanded query: {final_result['query_text']}")
                    
                    return final_result
                
                logger.warning(f"Failed to extract JSON from LLM response: {content[:100]}...")
                return None
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from LLM response: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error in advanced query processing with LLM: {e}")
            return None
    
    async def _process_with_llm(self, query_text, depth="standard"):
        """
        Process query using the translation LLM (legacy method)
        
        Args:
            query_text: The raw query text
            depth: The processing depth (standard or detailed)
            
        Returns:
            dict: Extracted parameters or None on failure
        """
        try:
            # Construct prompt based on depth
            if depth == "standard":
                prompt = f"""
                You're an advanced query analyst for a chat search system that helps users find insights in conversation history across multiple Telegram chat groups.
                
                TASK: Analyze this user query and extract search parameters to find the most relevant messages and generate valuable insights:
                
                USER QUERY: "{query_text}"
                
                ANALYSIS REQUIREMENTS:
                1. Identify the main topics, entities, events, and concepts in the query
                2. Think deeply about related topics that would yield valuable insights even if not explicitly mentioned
                3. Consider different perspectives, viewpoints, or angles that might provide valuable context
                4. Think about what information would be most valuable to answer this query comprehensively
                
                OUTPUT FORMAT - Return ONLY a JSON object with these fields:
                - query_text: Primary search terms that directly match what user is looking for
                - search_alternatives: Array of 5-8 alternative search phrases or related topics that would provide valuable context
                - sub_topics: Array of 3-5 specific aspects or sub-topics of the main subject that should be included
                - time_period: Timeframe (today, yesterday, week, month, or null)
                - sender: Person who sent the message (null if not specified)
                - intent: The intent (search, summarize, analyze, compare, track_evolution)
                - knowledge_domains: Array of 2-3 relevant knowledge domains this query relates to (politics, technology, finance, etc.)
                
                ONLY RETURN THE JSON. Optimize each field to maximize search relevance and analytical value.
                """
            else:  # detailed
                prompt = f"""
                You're an advanced query analyst for a chat search system that helps users find deep insights in conversation history across multiple Telegram chat groups.
                
                TASK: Conduct a comprehensive analysis of this user query to extract parameters for finding the most relevant messages and generating sophisticated insights:
                
                USER QUERY: "{query_text}"
                
                COMPREHENSIVE ANALYSIS REQUIREMENTS:
                1. Identify all topics, entities, events, and concepts in the query (both explicit and implied)
                2. Think deeply about related topics that would yield valuable connections and insights
                3. Consider multiple perspectives, viewpoints, or angles that would provide comprehensive context
                4. Identify potential biases or assumptions in the query that should be balanced
                5. Consider temporal aspects - how this topic may have evolved over time
                6. Think about what information would be most valuable to the user beyond their literal request
                
                OUTPUT FORMAT - Return ONLY a JSON object with these fields:
                - query_text: Primary search terms that directly match what user is looking for
                - search_alternatives: Array of 5-10 alternative search phrases or related topics that would provide valuable context
                - sub_topics: Array of 3-5 specific aspects or sub-topics of the main subject that should be included
                - counter_perspectives: Array of 2-3 opposing or alternative viewpoints to consider
                - time_period: Timeframe (today, yesterday, week, month, or null)
                - sender: Person who sent the message (null if not specified)
                - intent: The intent (search, summarize, analyze, compare, track_evolution, identify_sentiment)
                - knowledge_domains: Array of 2-4 relevant knowledge domains this query relates to (politics, technology, finance, etc.)
                - sentiment: Array of relevant sentiment aspects to look for (if applicable)
                - entities: Array of key entities (people, organizations, places, products) central to this query
                - context_requirements: Array of specific contextual elements needed for proper analysis
                
                ONLY RETURN THE JSON. Optimize each field to maximize search relevance and analytical depth.
                """
            
            # Process with LLM
            llm_response = await self.translator.translate(prompt, source_language="english")
            
            # Extract JSON from response (handle potential formatting issues)
            import json
            import re
            
            # Try to find JSON-like content in the response
            json_match = re.search(r'({[\s\S]*})', llm_response)
            
            if json_match:
                json_str = json_match.group(1)
                try:
                    result = json.loads(json_str)
                    logger.debug(f"Processed query with legacy LLM: {result}")
                    
                    # Convert legacy format to new format
                    final_result = {
                        "original_query_text": query_text,
                        "time_period": result.get("time_period"),
                        "sender": result.get("sender"),
                        "intent": result.get("intent", "search"),
                    }
                    
                    # Build a comprehensive search query with all extracted insights
                    if "query_text" in result:
                        # Extract the original query for reference
                        processed_query = result.get("query_text", "")
                        final_result["query_text"] = processed_query
                        
                        # Build expanded terms list
                        expanded_terms = []
                        
                        # Add alternative search phrases if available
                        alternatives = result.get("search_alternatives", [])
                        if isinstance(alternatives, list) and alternatives:
                            expanded_terms.extend(alternatives)
                        
                        # Add sub-topics if available
                        sub_topics = result.get("sub_topics", [])
                        if isinstance(sub_topics, list) and sub_topics:
                            expanded_terms.extend(sub_topics)
                            
                        # Add counter perspectives if available
                        counter_perspectives = result.get("counter_perspectives", [])
                        if isinstance(counter_perspectives, list) and counter_perspectives:
                            expanded_terms.extend(counter_perspectives)
                        
                        # Add entities if available
                        entities = result.get("entities", [])
                        if isinstance(entities, list) and entities:
                            expanded_terms.extend(entities)
                        
                        # Filter and deduplicate terms
                        if expanded_terms:
                            expanded_terms = [term for term in expanded_terms if term and isinstance(term, str)]
                            expanded_terms = list(set(expanded_terms))  # Remove duplicates
                            final_result["expanded_terms"] = expanded_terms
                            
                            # Use the enhanced query for searching if configured
                            use_expanded_query = self.config.get("use_expanded_query", True)
                            if use_expanded_query and expanded_terms:
                                # Create OR query combining original and expanded terms
                                all_terms = [processed_query] + expanded_terms
                                final_result["query_text"] = " OR ".join(all_terms)
                                logger.info(f"Enhanced search query: {final_result['query_text']}")
                    
                    return final_result
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON from LLM response: {json_str}")
            
            logger.warning(f"LLM response didn't contain valid JSON: {llm_response[:100]}...")
            return None
            
        except Exception as e:
            logger.error(f"Error processing query with legacy LLM: {e}")
            return None


# Singleton instance
_instance = None

def get_query_processor():
    """Get the query processor singleton instance"""
    global _instance
    if _instance is None:
        _instance = QueryProcessor()
    return _instance 