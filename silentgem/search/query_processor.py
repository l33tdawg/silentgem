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
                    
                    # If basic parsing detected specific intents or query types, preserve them
                    # Simple status queries should always use basic parsing results
                    if basic_parsed.get("intent") == "simple_status":
                        # Override with basic parsing for simple status queries
                        advanced_result["intent"] = basic_parsed["intent"]
                        advanced_result["query_type"] = basic_parsed.get("query_type", "simple")
                        advanced_result["status_type"] = basic_parsed.get("status_type")
                        advanced_result["subject_person"] = basic_parsed.get("subject_person")
                        advanced_result["expanded_terms"] = basic_parsed.get("expanded_terms", [])
                    elif basic_parsed.get("intent") == "track_evolution" and basic_parsed.get("query_text"):
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
        
        # Ensure query_type is set (default to exploratory if not set)
        if "query_type" not in result:
            result["query_type"] = "exploratory"
            
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
        Process query using advanced LLM with structured output
        
        Args:
            query_text: The query text to process
            depth: Processing depth ("standard" or "detailed")
            
        Returns:
            dict: Processed query parameters or None if processing fails
        """
        try:
            llm_client = self.llm_client
            if not llm_client:
                logger.warning("No LLM client available for advanced query processing")
                return None
            
            # Configure based on depth
            if depth == "detailed":
                max_tokens = 400
                temp = 0.3
            else:
                max_tokens = 250
                temp = 0.4
            
            # Build system prompt
            system_prompt = """You are a query analysis assistant. Analyze the user's query and return a JSON object with the following structure:

{
  "processed_query": "cleaned and optimized version of the query",
  "expanded_terms": ["list", "of", "related", "search", "terms"],
  "time_period": "today|yesterday|week|month|null",
  "sender": "person name if query is about someone specific, otherwise null",
  "intent": "search|summarize|analyze|track_evolution|compare"
}

Guidelines:
- processed_query: Extract the MAIN ENTITY or TOPIC being asked about. For "what is X doing/working on?", use just "X"
- expanded_terms: For queries about "what is X doing/working on?", include ONLY close variations of X name (e.g., different capitalizations, common abbreviations). DO NOT add generic terms like "products", "partners", "projects" - keep it very focused on the entity name.
- time_period: Extract if mentioned, otherwise null
- sender: Only if asking about specific person
- intent: Determine the user's goal

Examples:
Query: "what is TeamAlpha working on?"
Response: {"processed_query": "TeamAlpha", "expanded_terms": ["teamalpha", "team alpha"], "time_period": null, "sender": null, "intent": "search"}

Query: "what happened with CompanyX yesterday?"
Response: {"processed_query": "CompanyX", "expanded_terms": ["CX"], "time_period": "yesterday", "sender": null, "intent": "search"}

Query: "what is john working on?"
Response: {"processed_query": "john", "expanded_terms": ["John"], "time_period": null, "sender": "john", "intent": "search"}

IMPORTANT: Keep expanded_terms MINIMAL - only exact name variations. Do NOT add related concepts, products, or generic terms.

Return ONLY the JSON object, no other text."""
            
            # Process with LLM
            response = await llm_client.chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Query: {query_text}"}
            ], temperature=temp, max_tokens=max_tokens)
            
            if not response or not response.get("content"):
                logger.warning("Empty response from LLM during advanced query processing")
                return self._create_fallback_result(query_text)
                
            try:
                # Extract JSON from response
                content = response.get("content", "")
                
                # Try direct JSON parsing first
                try:
                    result = json.loads(content)
                    logger.debug(f"Successfully parsed JSON from LLM response")
                except json.JSONDecodeError:
                    # Try to extract JSON with regex
                    logger.info("Direct JSON parsing failed, trying regex extraction")
                    json_match = re.search(r'({[\s\S]*})', content)
                    
                    if json_match:
                        json_str = json_match.group(1)
                        try:
                            result = json.loads(json_str)
                            logger.debug(f"Successfully extracted JSON with regex")
                        except json.JSONDecodeError:
                            logger.warning("Regex JSON extraction failed, using fallback parsing")
                            result = self._parse_json_fallback(content, query_text)
                    else:
                        logger.warning("No JSON found in LLM response, using fallback")
                        result = self._create_fallback_result(query_text)
                
                if not result or not isinstance(result, dict):
                    logger.warning("Invalid result from JSON parsing, using fallback")
                    return self._create_fallback_result(query_text)
                
                # Build a final result dictionary with safe defaults
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
                
                # Create expanded query if we have expanded terms - but limit to avoid over-matching
                if final_result.get("expanded_terms"):
                    expanded_query_parts = [final_result["query_text"]]
                    
                    # Add expanded terms but limit to 2 additional terms max
                    for term in final_result["expanded_terms"][:2]:  # Limit to 2 additional terms
                        if term and term not in expanded_query_parts:
                            term_str = str(term)
                            # Only add if it's a close variation (not too different from original)
                            if len(term_str) > 1:  # Skip single character terms
                                expanded_query_parts.append(term_str)
                    
                    # Create OR query only if we have reasonable expansions
                    if len(expanded_query_parts) > 1 and len(expanded_query_parts) <= 3:  # Max 3 terms total
                        # Ensure all parts are strings before joining
                        expanded_query_parts = [str(part) for part in expanded_query_parts if part is not None]
                        final_result["query_text"] = " OR ".join(expanded_query_parts)
                        logger.debug(f"Expanded query: {final_result['query_text']}")
                
                return final_result
                
            except Exception as e:
                logger.warning(f"Error processing LLM response: {e}")
                return self._create_fallback_result(query_text)
                
        except Exception as e:
            logger.error(f"Error in advanced query processing with LLM: {e}")
            return self._create_fallback_result(query_text)
    
    def _parse_json_fallback(self, content: str, query_text: str) -> Dict[str, Any]:
        """
        Fallback JSON parsing when standard parsing fails
        
        Args:
            content: The LLM response content
            query_text: Original query text
            
        Returns:
            dict: Parsed result or fallback
        """
        try:
            # Try to extract individual fields using regex
            result = {}
            
            # Extract processed_query
            processed_match = re.search(r'"processed_query"\s*:\s*"([^"]*)"', content)
            if processed_match:
                result["processed_query"] = processed_match.group(1)
            
            # Extract expanded_terms array
            terms_match = re.search(r'"expanded_terms"\s*:\s*\[(.*?)\]', content, re.DOTALL)
            if terms_match:
                terms_str = terms_match.group(1)
                terms = re.findall(r'"([^"]*)"', terms_str)
                result["expanded_terms"] = terms
            
            # Extract time_period
            time_match = re.search(r'"time_period"\s*:\s*"([^"]*)"', content)
            if time_match:
                time_val = time_match.group(1)
                result["time_period"] = time_val if time_val != "null" else None
            
            # Extract sender
            sender_match = re.search(r'"sender"\s*:\s*"([^"]*)"', content)
            if sender_match:
                sender_val = sender_match.group(1)
                result["sender"] = sender_val if sender_val != "null" else None
            
            # Extract intent
            intent_match = re.search(r'"intent"\s*:\s*"([^"]*)"', content)
            if intent_match:
                result["intent"] = intent_match.group(1)
            
            return result if result else self._create_fallback_result(query_text)
            
        except Exception as e:
            logger.warning(f"Fallback JSON parsing failed: {e}")
            return self._create_fallback_result(query_text)
    
    def _create_fallback_result(self, query_text: str) -> Dict[str, Any]:
        """
        Create a fallback result when all parsing fails
        
        Args:
            query_text: Original query text
            
        Returns:
            dict: Basic fallback result
        """
        return {
            "query_text": query_text,
            "original_query_text": query_text,
            "expanded_terms": [],
            "search_strategies": ["direct", "semantic"],
            "time_period": None,
            "sender": None,
            "intent": "search"
        }

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
        query_type = "exploratory"  # Default query type
        
        # Check for simple yes/no status questions FIRST (highest priority)
        # Note: These patterns must NOT match "what is X working on?" type questions
        simple_status_patterns = [
            (r'\b(is|are|was|were|did)\s+(\w+)\s+(on\s+leave|on vacation|out of office|ooo|away|absent|off)\b', 'leave_status'),
            (r'\b(is|are|was|were)\s+(\w+)\s+(available|here|in office|present)\b', 'availability_status'),
            # Match "is X working" only if NOT followed by "on" (to avoid "working on")
            (r'\b(is|are|was|were)\s+(\w+)\s+working(?!\s+on)\b', 'availability_status'),
            (r'\b(did|has|have)\s+(\w+)\s+(attend|join|go to|participate)', 'attendance_status'),
            (r'\b(is|are|was|were)\s+(\w+)\s+(sick|ill|unwell)', 'health_status'),
        ]
        
        for pattern, status_type in simple_status_patterns:
            match = re.search(pattern, query_lower)
            if match:
                intent = "simple_status"
                query_type = "simple"
                person = match.group(2) if len(match.groups()) >= 2 else None
                result["status_type"] = status_type
                result["subject_person"] = person
                
                # Build search query that includes person name AND status terms
                search_terms = []
                if person:
                    search_terms.append(person)
                
                # Expand search terms for leave status
                if status_type == "leave_status":
                    status_keywords = [
                        "leave", "vacation", "OOO", "out of office", 
                        "PTO", "time off", "away", "off", "holiday",
                        "annual leave", "sick leave", "not available"
                    ]
                    result["expanded_terms"] = status_keywords
                    # Create query: person AND (keyword1 OR keyword2 OR ...)
                    if person:
                        result["query_text"] = f"{person} {' '.join(status_keywords[:3])}"
                    else:
                        result["query_text"] = " OR ".join(status_keywords[:5])
                        
                elif status_type == "availability_status":
                    status_keywords = [
                        "available", "in office", "working", "here", 
                        "present", "back", "returned"
                    ]
                    result["expanded_terms"] = status_keywords
                    if person:
                        result["query_text"] = f"{person} {' '.join(status_keywords[:3])}"
                    else:
                        result["query_text"] = " OR ".join(status_keywords[:5])
                        
                elif status_type == "attendance_status":
                    status_keywords = [
                        "attended", "joined", "went to", "participated",
                        "was at", "showed up", "present at"
                    ]
                    result["expanded_terms"] = status_keywords
                    if person:
                        result["query_text"] = f"{person} {' '.join(status_keywords[:3])}"
                    else:
                        result["query_text"] = " OR ".join(status_keywords[:5])
                        
                elif status_type == "health_status":
                    status_keywords = [
                        "sick", "ill", "unwell", "not feeling well",
                        "sick leave", "medical leave"
                    ]
                    result["expanded_terms"] = status_keywords
                    if person:
                        result["query_text"] = f"{person} {' '.join(status_keywords[:3])}"
                    else:
                        result["query_text"] = " OR ".join(status_keywords[:5])
                break
        
        # Check for summarization intent
        if intent != "simple_status":
            if any(term in query_lower for term in ["summarize", "summary", "overview"]):
                intent = "summarize"
                query_type = "exploratory"
            # Check for analysis intent
            elif any(term in query_lower for term in ["analyze", "analysis", "explain", "understand"]):
                intent = "analyze"
                query_type = "exploratory"
            # Check for tracking intent
            elif any(term in query_lower for term in ["track", "follow", "development", "update", "latest", "current", "status"]):
                intent = "track_evolution"
                query_type = "exploratory"
            # Check for comparison intent
            elif any(term in query_lower for term in ["compare", "difference", "versus", "vs"]):
                intent = "compare"
                query_type = "exploratory"
        
        result["intent"] = intent
        result["query_type"] = query_type
        
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

    async def _process_with_llm(self, query_text, depth="standard"):
        """
        Process query using the translation LLM (legacy method)
        
        Args:
            query_text: The raw query text
            depth: The processing depth (standard or detailed)
            
        Returns:
            dict: Extracted parameters or fallback result
        """
        try:
            # Simplified prompt for better JSON compliance
            prompt = f"""
            Analyze this search query and return a JSON object with these fields:
            
            Query: "{query_text}"
            
            Return JSON with:
            - processed_query: cleaned search terms
            - expanded_terms: related search terms (max 5)
            - time_period: today|yesterday|week|month|null
            - sender: person name or null
            - intent: search|summarize|analyze|track_evolution|compare
            
            Return ONLY valid JSON, no other text.
            """
            
            # Process with LLM
            llm_response = await self.translator.translate(prompt, source_language="english")
            
            if not llm_response:
                logger.warning("Empty response from legacy LLM")
                return self._create_fallback_result(query_text)
            
            # Extract JSON from response (handle potential formatting issues)
            import json
            import re
            
            try:
                # Try direct JSON parsing first
                result = json.loads(llm_response)
                logger.debug(f"Successfully parsed JSON from legacy LLM")
            except json.JSONDecodeError:
                # Try to find JSON-like content in the response
                logger.info("Direct JSON parsing failed, trying regex extraction")
                json_match = re.search(r'({[\s\S]*})', llm_response)
                
                if json_match:
                    json_str = json_match.group(1)
                    try:
                        result = json.loads(json_str)
                        logger.debug(f"Successfully extracted JSON with regex")
                    except json.JSONDecodeError:
                        logger.warning("Regex JSON extraction failed, using fallback parsing")
                        result = self._parse_json_fallback(llm_response, query_text)
                else:
                    logger.warning("No JSON found in legacy LLM response, using fallback")
                    return self._create_fallback_result(query_text)
            
            if not result or not isinstance(result, dict):
                logger.warning("Invalid result from legacy LLM, using fallback")
                return self._create_fallback_result(query_text)
            
            # Convert legacy format to new format
            final_result = {
                "original_query_text": query_text,
                "time_period": result.get("time_period"),
                "sender": result.get("sender"),
                "intent": result.get("intent", "search"),
            }
            
            # Build a comprehensive search query with all extracted insights
            if "processed_query" in result:
                # Extract the original query for reference
                processed_query = result.get("processed_query", query_text)
                final_result["query_text"] = processed_query
                
                # Build expanded terms list
                expanded_terms = []
                
                # Add expanded terms if available
                if "expanded_terms" in result:
                    terms = result.get("expanded_terms", [])
                    if isinstance(terms, list):
                        expanded_terms.extend([str(term) for term in terms if term])
                
                # Filter and deduplicate terms
                if expanded_terms:
                    expanded_terms = list(set(expanded_terms))  # Remove duplicates
                    final_result["expanded_terms"] = expanded_terms
                    
                    # Use the enhanced query for searching if configured - but be conservative
                    use_expanded_query = self.config.get("use_expanded_query", True)
                    if use_expanded_query and expanded_terms:
                        # Create OR query combining original and expanded terms (limit to 2 additional)
                        all_terms = [processed_query] + expanded_terms[:2]  # Limit expansion
                        # Ensure all terms are strings before joining
                        all_terms = [str(term) for term in all_terms if term is not None and len(str(term)) > 1]
                        # Only expand if we have 3 or fewer terms total
                        if len(all_terms) <= 3:
                            final_result["query_text"] = " OR ".join(all_terms)
                            logger.info(f"Enhanced search query: {final_result['query_text']}")
            else:
                # No processed query found, use original
                final_result["query_text"] = query_text
            
            return final_result
            
        except Exception as e:
            logger.error(f"Error processing query with legacy LLM: {e}")
            return self._create_fallback_result(query_text)

# Singleton instance
_instance = None

def get_query_processor():
    """Get the query processor singleton instance"""
    global _instance
    if _instance is None:
        _instance = QueryProcessor()
    return _instance 