"""
Conversation Intelligence Module for SilentGem

This module provides advanced conversation analysis, context synthesis,
and intelligent response generation leveraging large context windows
of modern LLMs (30k+ tokens).
"""

import json
import time
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger
from datetime import datetime, timedelta

from silentgem.llm.llm_client import get_llm_client
from silentgem.bot.conversation_memory import get_conversation_memory, Message
from silentgem.config.insights_config import get_insights_config

class ConversationIntelligence:
    """
    Advanced conversation intelligence system that provides:
    - Deep context analysis across conversation history
    - Intelligent topic tracking and evolution
    - Rich insight generation from search results
    - Sophisticated response synthesis
    - Multi-turn conversation understanding
    """
    
    def __init__(self):
        """Initialize the conversation intelligence system"""
        self.llm_client = get_llm_client()
        self.conversation_memory = get_conversation_memory()
        self.config = get_insights_config()
        
        # Context window management
        self.max_context_tokens = self.config.get("max_context_tokens", 25000)
        self.reserve_tokens_for_response = 3000
        self.available_context_tokens = self.max_context_tokens - self.reserve_tokens_for_response
    
    async def analyze_conversation_context(self, chat_id: str, user_id: str) -> Dict[str, Any]:
        """
        Perform deep analysis of conversation context
        
        Args:
            chat_id: Chat ID
            user_id: User ID
            
        Returns:
            Rich context analysis including themes, patterns, and insights
        """
        try:
            # Get rich context from conversation memory
            rich_context = self.conversation_memory.get_rich_context_for_llm(chat_id, user_id, max_history=30)
            
            if not rich_context["conversation_history"]:
                return {"analysis": "new_conversation", "themes": [], "patterns": []}
            
            # Prepare analysis prompt
            system_prompt = """You are an expert conversation analyst. Analyze the conversation history and provide insights about:

1. **Conversation Themes**: What are the main topics and themes being discussed?
2. **User Intent Patterns**: What patterns do you see in the user's questions and interests?
3. **Information Seeking Behavior**: How does the user prefer to receive information?
4. **Topic Evolution**: How have the topics evolved throughout the conversation?
5. **Knowledge Gaps**: What areas might the user want to explore further?
6. **Conversation Style**: What's the user's preferred communication style?

Return your analysis as a JSON object with these fields:
{
  "conversation_themes": ["theme1", "theme2", ...],
  "user_intent_patterns": ["pattern1", "pattern2", ...],
  "information_preferences": {
    "detail_level": "concise|standard|detailed",
    "prefers_analysis": true/false,
    "prefers_summaries": true/false,
    "prefers_specific_data": true/false
  },
  "topic_evolution": "description of how topics have evolved",
  "knowledge_gaps": ["gap1", "gap2", ...],
  "conversation_style": "description of user's communication style",
  "next_likely_questions": ["question1", "question2", ...],
  "recommended_insights": ["insight1", "insight2", ...]
}"""

            # Build context for analysis
            context_parts = []
            context_parts.append("## Conversation History:")
            
            for msg in rich_context["conversation_history"]:
                timestamp = msg.get("timestamp", "")
                role = msg.get("role", "")
                content = msg.get("content", "")
                query_type = msg.get("query_type", "")
                results_found = msg.get("results_found", "")
                
                context_parts.append(f"**{role.upper()}** [{timestamp}] {query_type}: {content}")
                if results_found:
                    context_parts.append(f"  → Found {results_found} results")
            
            # Add conversation summary
            summary = rich_context["conversation_summary"]
            context_parts.append(f"\n## Conversation Summary:")
            context_parts.append(f"- Conversation depth: {summary['depth']} exchanges")
            context_parts.append(f"- Main topics: {', '.join(summary['main_topics'])}")
            context_parts.append(f"- Key entities: {', '.join(summary['key_entities'])}")
            
            # Add current context
            current = rich_context["current_context"]
            context_parts.append(f"\n## Current Context:")
            context_parts.append(f"- Topic thread: {current['topic_thread']}")
            context_parts.append(f"- Recent searches: {', '.join(current['related_searches'])}")
            context_parts.append(f"- Insights provided: {', '.join(current['insights_provided'])}")
            
            user_prompt = "\n".join(context_parts)
            
            # Get analysis from LLM
            response = await self.llm_client.chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.3, max_tokens=1000)
            
            if response and response.get("content"):
                try:
                    analysis = json.loads(response["content"])
                    return analysis
                except json.JSONDecodeError:
                    logger.warning("Failed to parse conversation analysis JSON")
                    return {"analysis": "parse_error", "themes": [], "patterns": []}
            
            return {"analysis": "no_response", "themes": [], "patterns": []}
            
        except Exception as e:
            logger.error(f"Error analyzing conversation context: {e}")
            return {"analysis": "error", "themes": [], "patterns": []}
    
    async def synthesize_intelligent_response(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        chat_id: str,
        user_id: str,
        query_metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate an intelligent, context-aware response using the full context window
        
        Args:
            query: User's query
            search_results: Search results from the database
            chat_id: Chat ID
            user_id: User ID
            query_metadata: Additional metadata about the query
            
        Returns:
            Intelligent, synthesized response
        """
        try:
            if not self.llm_client:
                return self._fallback_response(query, search_results)
            
            # Get rich conversation context (skip complex analysis for speed)
            rich_context = self.conversation_memory.get_rich_context_for_llm(chat_id, user_id, max_history=10)
            
            # Build focused system prompt
            system_prompt = self._build_intelligent_system_prompt({}, rich_context)
            
            # Build focused user prompt
            user_prompt = self._build_comprehensive_user_prompt(
                query, search_results, rich_context, {}, query_metadata
            )
            
            # Estimate token usage and trim if necessary
            estimated_tokens = len(system_prompt) // 4 + len(user_prompt) // 4  # Rough estimate
            if estimated_tokens > self.available_context_tokens:
                user_prompt = self._trim_context_for_tokens(user_prompt, self.available_context_tokens - len(system_prompt) // 4)
            
            # Generate response
            response = await self.llm_client.chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.3, max_tokens=1200)
            
            if response and response.get("content"):
                return response["content"]
            else:
                return self._fallback_response(query, search_results)
                
        except Exception as e:
            logger.error(f"Error synthesizing intelligent response: {e}")
            return self._fallback_response(query, search_results)
    
    def _build_intelligent_system_prompt(
        self, 
        conversation_analysis: Dict[str, Any], 
        rich_context: Dict[str, Any]
    ) -> str:
        """Build a focused system prompt for direct, concise responses"""
        
        # Check if this is a follow-up question
        depth = rich_context.get("conversation_metadata", {}).get("total_exchanges", 0)
        is_followup = depth > 1
        
        base_prompt = """You are SilentGem, a direct information retrieval assistant. Answer questions factually using chat message data.

**Critical Rules - DO NOT VIOLATE**:
- NEVER use conversational fluff like "I'd be happy to help", "Let me explain", "I can help you understand"
- NEVER use phrases like "I found", "Based on", "According to", "It appears that", "It seems like"
- NEVER acknowledge the question or user - just answer it directly
- Start IMMEDIATELY with the answer/information
- State facts directly as if reporting findings

**Response Format**: 
- Lead with the most important information
- Keep it concise: 2-3 focused paragraphs maximum (400-800 characters)
- Use specific details from the messages (names, dates, specifics)
- No introductions, no conclusions, no "In summary" - just the facts

**Example BAD Response**:
"I'd be happy to help you understand how X works. Based on the messages, it appears that..."

**Example GOOD Response**:
"The review direction section focuses on app-based scams and VRC's advisory role. @quangtuanvrc sent an official letter to Satra introducing VRC's products..."

"""
        
        if is_followup:
            base_prompt += """**Follow-up Context**: This is a follow-up question in an ongoing conversation.
- Read the "Previous Exchange" section carefully to understand the conversation context
- The "Current Question" is what you need to answer NOW
- Use context from previous exchanges to inform your answer
- Answer the CURRENT question, incorporating relevant context naturally
- Don't repeat information already provided unless directly relevant to the new question
- If the current question asks for clarification or details about something mentioned previously, provide that specific information

"""
        
        base_prompt += """**Additional Guidelines**:
1. Every sentence should provide new information or value
2. Use bullet points for lists of items/people/events
3. Include specific names, dates, and numbers when available
4. Skip any meta-commentary about the search or what you're doing
5. For follow-ups: directly reference previous context without restating it
6. End when you've answered the question - no fluff closings

"""
        
        return base_prompt
    
    def _build_comprehensive_user_prompt(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        rich_context: Dict[str, Any],
        conversation_analysis: Dict[str, Any],
        query_metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build a focused user prompt with essential context"""
        
        prompt_parts = []
        
        # Include recent conversation context for follow-ups FIRST
        depth = rich_context.get("conversation_metadata", {}).get("total_exchanges", 0)
        if depth > 1 and rich_context.get("conversation_history"):
            # Get last 4 messages (2 exchanges) for better context
            recent_messages = rich_context["conversation_history"][-4:] if len(rich_context["conversation_history"]) >= 4 else rich_context["conversation_history"]
            if recent_messages:
                prompt_parts.append("## Previous Exchange:")
                for msg in recent_messages:
                    role = msg.get("role", "").upper()
                    content = msg.get("content", "")
                    # Show more of the previous context (not truncated too much)
                    if len(content) > 200:
                        content = content[:200] + "..."
                    prompt_parts.append(f"{role}: {content}")
                prompt_parts.append("\n---")
                prompt_parts.append("## Current Question:")
                prompt_parts.append(f"{query}")
                prompt_parts.append("---\n")
        else:
            # For new conversations, just show the query
            prompt_parts.append(f"## Query: {query}\n")
        
        # Search results - simplified format
        if search_results:
            prompt_parts.append(f"## Relevant Messages:")
            
            # Group by chat but limit to top results
            chat_groups = {}
            for result in search_results[:10]:  # Limit total results
                chat_id = result.get("source_chat_id") or result.get("target_chat_id") or "unknown"
                if chat_id not in chat_groups:
                    chat_groups[chat_id] = []
                chat_groups[chat_id].append(result)
            
            for chat_id, messages in chat_groups.items():
                chat_title = messages[0].get("chat_title", f"Chat {chat_id}")
                prompt_parts.append(f"\n**{chat_title}:**")
                
                # Sort by timestamp and limit
                messages.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                
                for msg in messages[:5]:  # Max 5 per chat
                    content = msg.get("content", "") or msg.get("text", "")
                    sender = msg.get("sender_name", "") or msg.get("sender", "Unknown")
                    timestamp = msg.get("timestamp")
                    
                    if timestamp:
                        try:
                            dt = datetime.fromtimestamp(timestamp)
                            time_str = dt.strftime("%m/%d %H:%M")
                        except:
                            time_str = "recent"
                    else:
                        time_str = "recent"
                    
                    # Truncate long messages
                    if len(content) > 300:
                        content = content[:300] + "..."
                    
                    prompt_parts.append(f"- {sender} ({time_str}): {content}")
            
            prompt_parts.append("")
        else:
            prompt_parts.append("## No matching messages found.\n")
        
        return "\n".join(prompt_parts)
    
    def _trim_context_for_tokens(self, content: str, max_tokens: int) -> str:
        """Trim content to fit within token limits while preserving important information"""
        # Rough estimation: 1 token ≈ 4 characters
        max_chars = max_tokens * 4
        
        if len(content) <= max_chars:
            return content
        
        # Try to preserve the structure by trimming from the middle (search results)
        lines = content.split('\n')
        
        # Keep the beginning (query and recent conversation) and end (instructions)
        keep_start = []
        keep_end = []
        middle_content = []
        
        in_search_results = False
        for line in lines:
            if "## Relevant Information" in line:
                in_search_results = True
                middle_content.append(line)
            elif "## Instructions" in line:
                in_search_results = False
                keep_end.append(line)
            elif in_search_results:
                middle_content.append(line)
            elif not keep_end:  # Before instructions
                keep_start.append(line)
            else:
                keep_end.append(line)
        
        # Combine and check length
        start_text = '\n'.join(keep_start)
        end_text = '\n'.join(keep_end)
        middle_text = '\n'.join(middle_content)
        
        available_for_middle = max_chars - len(start_text) - len(end_text) - 100  # Buffer
        
        if len(middle_text) > available_for_middle:
            # Trim middle content
            middle_text = middle_text[:available_for_middle] + "\n... (content trimmed for context window) ..."
        
        return start_text + '\n' + middle_text + '\n' + end_text
    
    def _fallback_response(self, query: str, search_results: List[Dict[str, Any]]) -> str:
        """Generate a fallback response when LLM is not available"""
        if not search_results:
            return f"No messages found matching your query: '{query}'"
        
        response_parts = [f"Found {len(search_results)} messages related to '{query}':\n"]
        
        for i, result in enumerate(search_results[:5], 1):
            content = result.get("content", "") or result.get("text", "")
            sender = result.get("sender_name", "") or result.get("sender", "Unknown")
            
            if len(content) > 150:
                content = content[:150] + "..."
            
            response_parts.append(f"{i}. **{sender}**: {content}")
        
        if len(search_results) > 5:
            response_parts.append(f"\n... and {len(search_results) - 5} more messages.")
        
        return "\n".join(response_parts)
    
    async def extract_entities_and_topics(self, text: str) -> Tuple[List[str], List[str]]:
        """
        Extract entities and topics from text using LLM
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (entities, topics)
        """
        try:
            if not self.llm_client or len(text.strip()) < 10:
                return [], []
            
            system_prompt = """Extract entities and topics from the given text. Return a JSON object with:
{
  "entities": ["person names", "company names", "locations", "specific things"],
  "topics": ["general themes", "subject areas", "discussion topics"]
}

Focus on:
- Entities: Specific named things (people, places, organizations, products)
- Topics: General themes or subject areas being discussed

Keep lists concise (max 10 items each)."""
            
            response = await self.llm_client.chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Text: {text[:1000]}"}  # Limit input length
            ], temperature=0.2, max_tokens=300)
            
            if response and response.get("content"):
                try:
                    result = json.loads(response["content"])
                    entities = result.get("entities", [])[:10]
                    topics = result.get("topics", [])[:10]
                    return entities, topics
                except json.JSONDecodeError:
                    pass
            
            return [], []
            
        except Exception as e:
            logger.warning(f"Error extracting entities and topics: {e}")
            return [], []

# Create a singleton instance
_conversation_intelligence_instance = None

def get_conversation_intelligence():
    """Get the conversation intelligence singleton instance"""
    global _conversation_intelligence_instance
    if _conversation_intelligence_instance is None:
        _conversation_intelligence_instance = ConversationIntelligence()
    return _conversation_intelligence_instance 