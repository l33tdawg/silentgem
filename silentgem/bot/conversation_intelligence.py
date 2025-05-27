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
            
            # Get conversation analysis
            conversation_analysis = await self.analyze_conversation_context(chat_id, user_id)
            
            # Get rich conversation context
            rich_context = self.conversation_memory.get_rich_context_for_llm(chat_id, user_id, max_history=25)
            
            # Build comprehensive system prompt
            system_prompt = self._build_intelligent_system_prompt(conversation_analysis, rich_context)
            
            # Build user prompt with all available context
            user_prompt = self._build_comprehensive_user_prompt(
                query, search_results, rich_context, conversation_analysis, query_metadata
            )
            
            # Estimate token usage and trim if necessary
            estimated_tokens = len(system_prompt) // 4 + len(user_prompt) // 4  # Rough estimate
            if estimated_tokens > self.available_context_tokens:
                user_prompt = self._trim_context_for_tokens(user_prompt, self.available_context_tokens - len(system_prompt) // 4)
            
            # Generate response
            response = await self.llm_client.chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.4, max_tokens=2000)
            
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
        """Build a sophisticated system prompt based on conversation analysis"""
        
        base_prompt = """You are SilentGem, an advanced AI assistant specializing in analyzing and synthesizing information from chat conversations and message histories. You have access to a comprehensive database of messages and conversations.

Your core capabilities:
- Deep analysis of conversation patterns and themes
- Intelligent synthesis of information across multiple sources
- Context-aware responses that build on previous conversations
- Insightful connections between different pieces of information
- Adaptive communication style based on user preferences

"""
        
        # Add conversation-specific context
        if conversation_analysis.get("conversation_themes"):
            themes = ", ".join(conversation_analysis["conversation_themes"])
            base_prompt += f"**Current Conversation Themes**: {themes}\n\n"
        
        if conversation_analysis.get("user_intent_patterns"):
            patterns = ", ".join(conversation_analysis["user_intent_patterns"])
            base_prompt += f"**User Intent Patterns**: {patterns}\n\n"
        
        # Add communication style guidance
        info_prefs = conversation_analysis.get("information_preferences", {})
        detail_level = info_prefs.get("detail_level", "standard")
        
        if detail_level == "concise":
            base_prompt += "**Communication Style**: The user prefers concise, direct responses. Be brief but comprehensive.\n\n"
        elif detail_level == "detailed":
            base_prompt += "**Communication Style**: The user appreciates detailed, thorough analysis. Provide comprehensive insights and connections.\n\n"
        else:
            base_prompt += "**Communication Style**: Provide balanced responses with key insights and supporting details.\n\n"
        
        # Add conversation depth context
        depth = rich_context.get("conversation_metadata", {}).get("total_exchanges", 0)
        if depth > 10:
            base_prompt += "**Conversation Context**: This is an ongoing, in-depth conversation. Build on previous discussions and provide sophisticated analysis.\n\n"
        elif depth > 3:
            base_prompt += "**Conversation Context**: This is a developing conversation. Reference previous topics and build connections.\n\n"
        else:
            base_prompt += "**Conversation Context**: This is a new or early conversation. Provide clear, foundational insights.\n\n"
        
        base_prompt += """**Response Guidelines**:
1. **Synthesize, don't just summarize**: Create insights by connecting information across sources
2. **Be conversational and natural**: Respond as a knowledgeable colleague, not a search engine
3. **Build on conversation history**: Reference and build upon previous discussions
4. **Provide actionable insights**: Go beyond just presenting information
5. **Identify patterns and trends**: Look for connections across time and sources
6. **Anticipate follow-up questions**: Address likely next questions
7. **Use rich context**: Leverage the full conversation history for deeper understanding

**Never say**: "I found X messages" or "Here are the search results" - instead synthesize the information naturally.
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
        """Build a comprehensive user prompt with all available context"""
        
        prompt_parts = []
        
        # Current query
        prompt_parts.append(f"## Current Query\n{query}\n")
        
        # Query context if available
        if query_metadata:
            if query_metadata.get("time_period"):
                prompt_parts.append(f"**Time Period**: {query_metadata['time_period']}")
            if query_metadata.get("expanded_terms"):
                prompt_parts.append(f"**Related Terms Searched**: {', '.join(query_metadata['expanded_terms'])}")
            prompt_parts.append("")
        
        # Conversation history (recent exchanges)
        if rich_context.get("conversation_history"):
            prompt_parts.append("## Recent Conversation History")
            recent_messages = rich_context["conversation_history"][-10:]  # Last 10 messages
            
            for msg in recent_messages:
                role = msg.get("role", "").upper()
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "")
                query_type = msg.get("query_type", "")
                
                if query_type:
                    prompt_parts.append(f"**{role}** [{timestamp}] ({query_type}): {content}")
                else:
                    prompt_parts.append(f"**{role}** [{timestamp}]: {content}")
                
                if msg.get("results_found"):
                    prompt_parts.append(f"  → {msg['results_found']} results found")
            
            prompt_parts.append("")
        
        # Conversation insights
        if conversation_analysis.get("topic_evolution"):
            prompt_parts.append(f"## Topic Evolution\n{conversation_analysis['topic_evolution']}\n")
        
        if conversation_analysis.get("knowledge_gaps"):
            gaps = ", ".join(conversation_analysis["knowledge_gaps"])
            prompt_parts.append(f"## Potential Knowledge Gaps\n{gaps}\n")
        
        # Search results organized by relevance and time
        if search_results:
            prompt_parts.append(f"## Relevant Information ({len(search_results)} sources)")
            
            # Group by chat/source for better organization
            chat_groups = {}
            for result in search_results:
                chat_id = result.get("source_chat_id") or result.get("target_chat_id") or "unknown"
                if chat_id not in chat_groups:
                    chat_groups[chat_id] = []
                chat_groups[chat_id].append(result)
            
            for chat_id, messages in chat_groups.items():
                chat_title = messages[0].get("chat_title", f"Chat {chat_id}")
                prompt_parts.append(f"\n### From {chat_title}")
                
                # Sort by timestamp
                messages.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                
                for msg in messages[:15]:  # Limit per chat to manage context
                    content = msg.get("content", "") or msg.get("text", "")
                    sender = msg.get("sender_name", "") or msg.get("sender", "Unknown")
                    timestamp = msg.get("timestamp")
                    
                    if timestamp:
                        try:
                            dt = datetime.fromtimestamp(timestamp)
                            time_str = dt.strftime("%Y-%m-%d %H:%M")
                        except:
                            time_str = str(timestamp)
                    else:
                        time_str = "Unknown time"
                    
                    # Truncate very long messages
                    if len(content) > 500:
                        content = content[:500] + "..."
                    
                    prompt_parts.append(f"- **{sender}** [{time_str}]: {content}")
            
            prompt_parts.append("")
        else:
            prompt_parts.append("## No Direct Matches Found\nNo specific messages matched the search criteria.\n")
        
        # Conversation summary for context
        summary = rich_context.get("conversation_summary", {})
        if summary.get("main_topics") or summary.get("key_entities"):
            prompt_parts.append("## Conversation Context Summary")
            if summary.get("main_topics"):
                prompt_parts.append(f"**Main Topics Discussed**: {', '.join(summary['main_topics'])}")
            if summary.get("key_entities"):
                prompt_parts.append(f"**Key Entities**: {', '.join(summary['key_entities'])}")
            prompt_parts.append("")
        
        # Expected next questions for proactive insights
        if conversation_analysis.get("next_likely_questions"):
            questions = conversation_analysis["next_likely_questions"][:3]  # Top 3
            prompt_parts.append(f"## Likely Follow-up Questions\n{', '.join(questions)}\n")
        
        prompt_parts.append("## Instructions")
        prompt_parts.append("Provide a comprehensive, insightful response that:")
        prompt_parts.append("1. Directly addresses the current query")
        prompt_parts.append("2. Synthesizes information from all relevant sources")
        prompt_parts.append("3. Builds on the conversation history and context")
        prompt_parts.append("4. Provides actionable insights and analysis")
        prompt_parts.append("5. Anticipates and addresses likely follow-up questions")
        prompt_parts.append("6. Maintains a natural, conversational tone")
        
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