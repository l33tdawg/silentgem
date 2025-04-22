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
        if not query_text or not query_text.strip():
            return {"original_query": "", "query_text": ""}
        
        # Normalize query
        query_text = query_text.strip()
        
        # Store original query
        result = {"original_query": query_text}
        
        # Get processing depth
        depth = self.config.get("query_processing_depth", "standard")
        
        # For depth of none, just use the text as is
        if depth == "none":
            result["query_text"] = query_text
            return result
            
        # Try to initialize the translator if needed
        if not self.translator:
            self.translator = await create_translator()
        
        # Start with basic parsing
        basic_parsed = self._parse_query(query_text)
        
        # Apply the basic parsing results
        result.update(basic_parsed)
            
        # Use advanced LLM processing if available
        if depth != "basic" and self.llm_client:
            try:
                # First try with advanced LLM method
                advanced_result = await self._process_with_advanced_llm(query_text, depth)
                if advanced_result:
                    # Keep the original query
                    advanced_result["original_query"] = query_text
                    
                    # If basic parsing detected specific intents, preserve them
                    if basic_parsed.get("intent") == "track_evolution" and basic_parsed.get("query_text"):
                        advanced_result["intent"] = "track_evolution"
                        
                    # Merge any missing fields from basic parsing
                    for key, value in basic_parsed.items():
                        if key not in advanced_result or not advanced_result[key]:
                            advanced_result[key] = value
                    
                    return advanced_result
            except Exception as e:
                logger.error(f"Error in advanced LLM query processing: {e}")
         
        # Fallback: if legacy translator is available, try with it
        if depth != "basic" and self.translator:
            try:
                legacy_result = await self._process_with_llm(query_text, depth)
                if legacy_result:
                    # Keep the original query
                    legacy_result["original_query"] = query_text
                    
                    # Merge any missing fields from basic parsing
                    for key, value in basic_parsed.items():
                        if key not in legacy_result or not legacy_result[key]:
                            legacy_result[key] = value
                            
                    return legacy_result
            except Exception as e:
                logger.error(f"Error in legacy LLM query processing: {e}")
        
        # If no NLU results, just use basic parsing results
        if "query_text" not in result or not result["query_text"]:
            result["query_text"] = query_text
            
        return result
    
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
        Process query using advanced LLM analysis to extract search parameters
        
        Args:
            query_text: The raw query text
            depth: The processing depth (standard or detailed)
            
        Returns:
            dict: Extracted parameters or None on failure
        """
        try:
            # Get LLM client
            llm_client = self.llm_client
            if not llm_client:
                logger.warning("LLM client not available for advanced query processing")
                return None
            
            # Determine temperature and max tokens based on depth
            if depth == "detailed":
                temp = 0.2
                max_tokens = 800
            else:
                temp = 0.1
                max_tokens = 500
            
            # Construct system prompt based on depth
            if depth == "standard":
                system_prompt = """You are an advanced query analyzer for a conversational chat search system that helps users find messages and understand discussions across multiple channels.

Your task is to analyze the user's request and extract the key information needed to find relevant content, while also understanding the conversational intent behind the query.

The user may be asking about:
- Specific topics, events, or facts mentioned in conversations
- What someone said about a particular subject
- Recent developments on a topic
- The status of a project or situation
- Comparisons between different viewpoints
- Summaries of discussions

Respond with a JSON object containing:
- processed_query: The main search terms most likely to appear in relevant messages
- expanded_terms: 5-8 semantically related terms that might appear in relevant messages
- search_strategies: Array of strategies in priority order ["direct", "semantic", "fuzzy"]
- time_period: Time period mentioned (today, yesterday, week, month, null)
- sender: Person who sent the message mentioned (null if none)
- intent: The search intent (search, summarize, analyze, compare, track_evolution)

IMPORTANT: Focus on identifying terms that would actually appear in messages about this topic, not just conceptually related terms.
"""
            else:  # detailed
                system_prompt = """You are an advanced query analyzer for a conversational chat search system that helps users find messages and understand discussions across multiple channels.

Your task is to analyze the search query and extract key information that will help find the most relevant messages, while understanding the deeper conversational intent behind the query.

The user may be asking about:
- Specific topics, events, or facts mentioned in conversations
- What someone said about a particular subject
- Recent developments on a topic
- The status of a project or situation
- Comparisons between different viewpoints
- Summaries of discussions
- Insights across multiple conversations

Focus on identifying:
1. The core search terms - what would actually appear in messages about this topic
2. Expanded terms - semantically related concepts that might appear in relevant messages
3. Alternative phrasings - different ways people might express the same ideas
4. Related entities - people, organizations, products, concepts related to the search
5. Search strategies that would be most effective
6. The conversational intent behind the query - what the user really wants to know

Respond with a JSON object containing:
- processed_query: The main search terms
- expanded_terms: 5-8 semantically related terms/phrases
- alternative_phrasings: 2-3 different ways to express the same query
- related_entities: 2-4 entities related to the query
- search_strategies: Array of strategies in priority order ["direct", "semantic", "fuzzy"]
- time_period: Time period mentioned (today, yesterday, week, month, null)
- sender: Person who sent the message mentioned (null if none)
- intent: The search intent (search, summarize, analyze, compare, track_evolution, identify_sentiment)
"""
            
            # Process with LLM
            response = await llm_client.chat_completion([
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
                        "query_text": query_text,  # Default to original query
                        "original_query_text": query_text,
                        "expanded_terms": [],
                        "search_strategies": ["direct", "semantic"],
                        "time_period": None,
                        "sender": None,
                        "intent": "search",
                    }
                    
                    # Get processed query and ensure it's a string
                    processed_query = result.get("processed_query", query_text)
                    if processed_query is not None:
                        if isinstance(processed_query, list):
                            processed_query = " ".join([str(item) for item in processed_query if item is not None])
                        elif not isinstance(processed_query, str):
                            processed_query = str(processed_query)
                        final_result["query_text"] = processed_query
                    
                    # Add expanded terms if present
                    if "expanded_terms" in result:
                        expanded_terms = result["expanded_terms"]
                        if expanded_terms and isinstance(expanded_terms, list):
                            final_result["expanded_terms"] = [str(term) for term in expanded_terms if term is not None]
                    
                    # Add other fields if present
                    if "search_strategies" in result:
                        final_result["search_strategies"] = result["search_strategies"]
                    if "time_period" in result:
                        final_result["time_period"] = result["time_period"]
                    if "sender" in result:
                        final_result["sender"] = result["sender"]
                    if "intent" in result:
                        final_result["intent"] = result["intent"]
                    
                    # Add additional fields if present (for detailed mode)
                    if "alternative_phrasings" in result:
                        alt_phrasings = result["alternative_phrasings"]
                        if alt_phrasings and isinstance(alt_phrasings, list):
                            final_result["alternative_phrasings"] = [str(phrase) for phrase in alt_phrasings if phrase is not None]
                        else:
                            final_result["alternative_phrasings"] = alt_phrasings
                    
                    if "related_entities" in result:
                        related_entities = result["related_entities"]
                        if related_entities and isinstance(related_entities, list):
                            final_result["related_entities"] = [str(entity) for entity in related_entities if entity is not None]
                        else:
                            final_result["related_entities"] = related_entities
                    
                    # Build a comprehensive search query if requested
                    use_expanded_query = self.config.get("use_expanded_query", True)
                    if use_expanded_query:
                        # Build the expanded query
                        expanded_query_parts = [final_result["query_text"]]
                        
                        # Add terms from expanded_terms
                        expanded_terms = final_result.get("expanded_terms", [])
                        if expanded_terms:
                            # Ensure all items are strings
                            expanded_terms = [str(term) for term in expanded_terms if term is not None]
                            expanded_query_parts.extend(expanded_terms)
                            
                        # Add terms from alternative_phrasings
                        alt_phrasings = final_result.get("alternative_phrasings", [])
                        if alt_phrasings:
                            # Ensure all items are strings
                            alt_phrasings = [str(term) for term in alt_phrasings if term is not None]
                            expanded_query_parts.extend(alt_phrasings)
                        
                        # Create OR query
                        if len(expanded_query_parts) > 1:
                            # Ensure all parts are strings before joining
                            expanded_query_parts = [str(part) for part in expanded_query_parts if part is not None]
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
                                # Ensure all terms are strings before joining
                                all_terms = [str(term) for term in all_terms if term is not None]
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

    def _parse_query(self, query_text: str) -> Dict[str, Any]:
        """
        Basic parsing of query text without LLM
        
        Args:
            query_text: The raw query text
            
        Returns:
            dict: Extracted parameters
        """
        result = {"original_query": query_text}
        
        # Extract time period
        time_period = None
        
        # Check for time periods
        query_lower = query_text.lower()
        if "today" in query_lower:
            time_period = "today"
        elif "yesterday" in query_lower:
            time_period = "yesterday"
        elif "this week" in query_lower or "past week" in query_lower or "last week" in query_lower:
            time_period = "week"
        elif "this month" in query_lower or "past month" in query_lower or "last month" in query_lower:
            time_period = "month"
        
        result["time_period"] = time_period
        
        # Determine intention - default to search
        intent = "search"
        
        # Check for summarization intent
        if any(term in query_lower for term in ["summarize", "summary", "overview"]):
            intent = "summarize"
        # Check for analysis intent
        elif any(term in query_lower for term in ["analyze", "analysis", "explain", "understand"]):
            intent = "analyze"
        # Check for tracking intent
        elif any(term in query_lower for term in ["track", "follow", "development", "update", "latest", "current", "status"]):
            intent = "track_evolution"
        # Check for comparison intent
        elif any(term in query_lower for term in ["compare", "difference", "versus", "vs"]):
            intent = "compare"
        
        result["intent"] = intent
        
        # Extract entity information
        sender = None
        
        # Check for common query patterns
        if "what did " in query_lower:
            # Extract person after "what did" and before the next word
            sender_match = re.search(r"what did ([a-zA-Z\s]+) (say|talk|mention|post)", query_lower)
            if sender_match:
                sender = sender_match.group(1).strip()
        
        elif "who (said|talked|spoke|posted)" in query_lower:
            # Just identify this as a person search, let the LLM handle details
            result["search_mode"] = "person"
        
        # Handle common status queries
        if any(pattern in query_lower for pattern in ["what's the latest", "what is the latest", "status of", "update on"]):
            # Extract the topic they're asking about
            topic_match = None
            
            if "latest in " in query_lower or "latest on " in query_lower:
                topic_match = re.search(r"latest (in|on) ([a-zA-Z0-9\s]+)", query_lower)
            elif "status of " in query_lower:
                topic_match = re.search(r"status of ([a-zA-Z0-9\s]+)", query_lower)
            elif "update on " in query_lower:
                topic_match = re.search(r"update on ([a-zA-Z0-9\s]+)", query_lower)
            
            if topic_match:
                topic = topic_match.group(2).strip()
                result["query_text"] = topic
                result["intent"] = "track_evolution"
                
                # Set an appropriate time period if none was specified
                if not time_period:
                    result["time_period"] = "week"
        
        result["sender"] = sender
        
        return result

# Singleton instance
_instance = None

def get_query_processor():
    """Get the query processor singleton instance"""
    global _instance
    if _instance is None:
        _instance = QueryProcessor()
    return _instance 