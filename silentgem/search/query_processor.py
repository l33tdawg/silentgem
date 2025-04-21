"""
Query processor for understanding natural language queries in Chat Insights
"""

import re
import time
from datetime import datetime, timedelta
from loguru import logger

from silentgem.config.insights_config import get_insights_config
from silentgem.translator import create_translator

class QueryProcessor:
    """Process natural language queries for the Chat Insights feature"""
    
    def __init__(self):
        """Initialize the query processor"""
        self.config = get_insights_config()
        self.translator = None
    
    async def process_query(self, query_text):
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
            }
            
            # Basic time period extraction (simple regex patterns)
            today_pattern = re.compile(r'\b(today|in the last day)\b', re.IGNORECASE)
            yesterday_pattern = re.compile(r'\b(yesterday|past day)\b', re.IGNORECASE)
            week_pattern = re.compile(r'\b(this week|past week|last 7 days|last seven days)\b', re.IGNORECASE)
            month_pattern = re.compile(r'\b(this month|past month|last 30 days|last thirty days)\b', re.IGNORECASE)
            
            # Check for time patterns
            if today_pattern.search(query_text):
                result["time_period"] = "today"
            elif yesterday_pattern.search(query_text):
                result["time_period"] = "yesterday"
            elif week_pattern.search(query_text):
                result["time_period"] = "week"
            elif month_pattern.search(query_text):
                result["time_period"] = "month"
            
            # Get query processing depth
            query_depth = self.config.get("query_processing_depth", "standard")
            
            # For basic processing, just use the original query with time extraction
            if query_depth == "basic":
                # Remove time-related phrases for cleaner query
                clean_query = query_text
                if result["time_period"]:
                    clean_query = today_pattern.sub("", clean_query)
                    clean_query = yesterday_pattern.sub("", clean_query)
                    clean_query = week_pattern.sub("", clean_query)
                    clean_query = month_pattern.sub("", clean_query)
                    # Clean up multiple spaces
                    clean_query = re.sub(r'\s+', ' ', clean_query).strip()
                
                result["query_text"] = clean_query
                return result
            
            # For standard and detailed processing, use LLM
            if query_depth in ["standard", "detailed"]:
                # Initialize translator if needed
                if not self.translator:
                    self.translator = await create_translator()
                
                # Use the same LLM as translation by default
                use_translation_llm = self.config.get("use_translation_llm", True)
                
                if use_translation_llm and self.translator:
                    # Process using translation LLM
                    processed_query = await self._process_with_llm(query_text, query_depth)
                    if processed_query:
                        result.update(processed_query)
                        return result
            
            # Fallback to basic processing if LLM fails
            clean_query = re.sub(r'\b(who|what|when|where|find|search|look for|show me|tell me about)\b', '', query_text, flags=re.IGNORECASE)
            clean_query = re.sub(r'\s+', ' ', clean_query).strip()
            result["query_text"] = clean_query
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return None
    
    async def _process_with_llm(self, query_text, depth="standard"):
        """
        Process query using the LLM
        
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
                You're a query analyzer for a chat search system. Extract the following from this user query:
                
                "{query_text}"
                
                Return ONLY a JSON object with these fields:
                - query_text: The main search terms (what to look for)
                - time_period: Timeframe (today, yesterday, week, month, or null)
                - sender: Person who sent the message (null if not specified)
                - intent: The intent (search, count, summarize)
                
                ONLY RETURN THE JSON, NO OTHER TEXT.
                """
            else:  # detailed
                prompt = f"""
                You're a query analyzer for a chat search system. Analyze this user query:
                
                "{query_text}"
                
                Return ONLY a JSON object with these fields:
                - query_text: The main search terms (what to look for)
                - time_period: Timeframe (today, yesterday, week, month, or null)
                - sender: Person who sent the message (null if not specified)
                - intent: The intent (search, count, summarize)
                - sentiment: Sentiment to look for (positive, negative, neutral, or null)
                - topic_focus: Main topic discussed (null if not applicable)
                - entities: Array of relevant entities mentioned
                
                ONLY RETURN THE JSON, NO OTHER TEXT.
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
                    logger.debug(f"Processed query with LLM: {result}")
                    return result
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON from LLM response: {json_str}")
            
            logger.warning(f"LLM response didn't contain valid JSON: {llm_response[:100]}...")
            return None
            
        except Exception as e:
            logger.error(f"Error processing query with LLM: {e}")
            return None 