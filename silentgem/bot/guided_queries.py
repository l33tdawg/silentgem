"""
Guided Query Generation Module for SilentGem v1.5

This module uses LLM intelligence to generate contextually relevant
follow-up questions, expandable topics, and action buttons based on
conversation history and search results.
"""

import json
import time
from typing import Dict, List, Any, Optional
from loguru import logger
from dataclasses import dataclass, field, asdict

from silentgem.llm.llm_client import get_llm_client


@dataclass
class GuidedQuery:
    """Represents a guided follow-up query suggestion"""
    question: str
    reasoning: str
    category: str  # "deep_dive", "cross_reference", "timeline", "people"
    relevance_score: float = 1.0


@dataclass
class ExpandableTopic:
    """Represents a topic that can be expanded for more details"""
    id: str
    label: str
    message_count: int
    reasoning: str
    priority: int = 1  # Higher = more important


@dataclass
class ActionButton:
    """Represents an action button (timeline, contributors, etc.)"""
    type: str  # "timeline", "contributors", "save_template", "export"
    label: str
    callback_data: str
    relevance: str


@dataclass
class GuidedQuerySuggestions:
    """Complete set of guided query suggestions"""
    follow_up_questions: List[GuidedQuery] = field(default_factory=list)
    expandable_topics: List[ExpandableTopic] = field(default_factory=list)
    action_buttons: List[ActionButton] = field(default_factory=list)
    reasoning: str = ""
    generated_at: float = field(default_factory=time.time)


class GuidedQueryGenerator:
    """
    Generates contextually relevant follow-up questions and suggestions
    using LLM analysis of conversation history and search results.
    """
    
    def __init__(self):
        """Initialize the guided query generator"""
        self.llm_client = get_llm_client()
        self.max_suggestions = 3
        self.enable_llm_generation = True  # Can be toggled for testing
    
    async def generate_suggestions(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        search_metadata: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None,
        response_text: Optional[str] = None
    ) -> GuidedQuerySuggestions:
        """
        Generate comprehensive guided query suggestions
        
        Args:
            query: The original user query
            search_results: List of message search results
            search_metadata: Metadata about search results (topics, channels, etc.)
            conversation_history: Recent conversation context
            response_text: The response we generated for the user
            
        Returns:
            GuidedQuerySuggestions with follow-up questions, topics, and actions
        """
        try:
            if self.enable_llm_generation:
                return await self._generate_with_llm(
                    query=query,
                    search_results=search_results,
                    search_metadata=search_metadata,
                    conversation_history=conversation_history or [],
                    response_text=response_text or ""
                )
            else:
                return self._generate_fallback(search_metadata)
                
        except Exception as e:
            logger.warning(f"Failed to generate guided queries: {e}")
            return self._generate_fallback(search_metadata)
    
    async def _generate_with_llm(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        search_metadata: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        response_text: str
    ) -> GuidedQuerySuggestions:
        """Generate suggestions using LLM analysis"""
        
        # Build comprehensive context for LLM
        context_prompt = self._build_llm_prompt(
            query=query,
            search_results=search_results,
            search_metadata=search_metadata,
            conversation_history=conversation_history,
            response_text=response_text
        )
        
        system_prompt = """You are an expert at generating direct, actionable follow-up questions for business chat analysis.

**Critical Requirements for Questions**:
1. Be SHORT and DIRECT (max 10-12 words)
2. Start with action words: "What", "Who", "When", "How", "Which"
3. Include SPECIFIC details from the conversation (names, projects, etc.)
4. No vague questions - be concrete and targeted
5. Each question should reveal NEW information, not rehash what was already answered

**Example BAD Questions** (too vague/generic):
- "Tell me more about this"
- "What else is happening?"
- "Can you provide more details?"

**Example GOOD Questions** (specific and actionable):
- "What's the timeline for Satra's PoC presentation?"
- "Who else is involved in the Bshield proposal?"
- "What templates were prepared for government agencies?"

Always respond with valid JSON following the exact schema provided."""
        
        try:
            # Call LLM to generate suggestions
            llm_response = await self.llm_client.complete(
                prompt=context_prompt,
                system=system_prompt,
                temperature=0.7,
                max_tokens=1000
            )
            
            # Parse LLM response
            suggestions_data = self._parse_llm_response(llm_response)
            
            # Convert to GuidedQuerySuggestions object
            return self._convert_to_suggestions(suggestions_data, search_metadata)
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._generate_fallback(search_metadata)
    
    def _build_llm_prompt(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        search_metadata: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        response_text: str
    ) -> str:
        """Build the prompt for LLM analysis"""
        
        # Extract topics from metadata
        topics_found = search_metadata.get("topics_found", {})
        channels = search_metadata.get("channels", [])
        total_messages = search_metadata.get("total_messages", len(search_results))
        
        # Format topics breakdown
        topics_text = self._format_topics_for_llm(topics_found)
        
        # Format recent conversation
        conversation_text = self._format_conversation_for_llm(conversation_history[-5:] if conversation_history else [])
        
        # Build the comprehensive prompt
        prompt = f"""Analyze this search conversation and suggest relevant follow-up questions.

## Context

**User's Query:** "{query}"

**Search Results:**
- Found {total_messages} messages across {len(channels)} channel(s)
- Channels: {', '.join(channels) if channels else 'N/A'}

**Topics Discovered:**
{topics_text}

**Recent Conversation History:**
{conversation_text}

**Response Provided to User:**
{response_text[:600] if response_text else 'N/A'}...

## Your Task

Generate 3 DIRECT, SPECIFIC follow-up questions (10-12 words max each):
1. **Deep Dive**: Ask about specific details mentioned (timelines, people, deliverables)
2. **Cross-Reference**: Compare specific entities/events (e.g., "How does X compare to Y?")
3. **Next Steps**: Ask about concrete actions or outcomes (e.g., "What's the deadline for X?")

**Question Formula**: [What/Who/When/How/Which] + [Specific Detail from Messages] + [Action/Outcome]?

Also identify:
- Which topics have enough content to warrant expansion (≥8 messages)
- What action buttons would be useful (timeline, contributors, etc.)

## Response Format (strict JSON)

{{
  "follow_up_questions": [
    {{
      "question": "What's the deadline for Satra's PoC presentation?",
      "reasoning": "Timeline details are crucial for project planning",
      "category": "deep_dive"
    }},
    {{
      "question": "Who besides @quangtuanvrc is working on the proposal?",
      "reasoning": "Identify all team members involved",
      "category": "people"
    }},
    {{
      "question": "Which government agencies received the templates?",
      "reasoning": "Understand scope of outreach efforts",
      "category": "cross_reference"
    }}
  ],
  "expandable_topics": [
    {{
      "id": "topic_key",
      "label": "Human-readable topic name",
      "reasoning": "Why this topic is worth expanding",
      "priority": 1-3
    }}
  ],
  "action_buttons": [
    {{
      "type": "timeline|contributors|save_template|export",
      "label": "Button text",
      "relevance": "Why this button is useful here"
    }}
  ],
  "reasoning": "Overall explanation of your suggestion strategy"
}}

IMPORTANT RULES: 
- Questions MUST be SHORT (max 12 words) and DIRECT
- Use SPECIFIC names, projects, or topics from the actual messages
- Start with: What/Who/When/How/Which/Where
- NO generic questions like "Tell me more", "What else?", "Can you provide more context?"
- Each question should ask about ONE specific thing
- Only suggest expandable topics that have substantial content (≥8 messages)
- Questions should be immediately answerable from the chat history
"""
        
        return prompt
    
    def _format_topics_for_llm(self, topics_found: Dict[str, Any]) -> str:
        """Format topics in a readable way for the LLM"""
        if not topics_found:
            return "No specific topics identified"
        
        formatted = []
        for topic, data in topics_found.items():
            if isinstance(data, dict):
                count = data.get('count', 0)
                messages = data.get('messages', [])
                
                # Get a sample sender if available
                sample_sender = "unknown"
                if messages and len(messages) > 0:
                    sample_sender = messages[0].get('sender_name', 'unknown')
                
                formatted.append(f"- **{topic}**: {count} messages (e.g., from {sample_sender})")
            else:
                formatted.append(f"- **{topic}**: {data} messages")
        
        return '\n'.join(formatted) if formatted else "No topics found"
    
    def _format_conversation_for_llm(self, history: List[Dict[str, str]]) -> str:
        """Format recent conversation for LLM context"""
        if not history:
            return "No previous conversation context"
        
        formatted = []
        for msg in history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')[:200]  # Truncate long messages
            formatted.append(f"{role.upper()}: {content}")
        
        return '\n'.join(formatted)
    
    def _parse_llm_response(self, llm_response: str) -> Dict[str, Any]:
        """Parse and validate LLM JSON response"""
        try:
            # Try to extract JSON from response (in case LLM adds extra text)
            json_match = llm_response.strip()
            if not json_match.startswith('{'):
                # Try to find JSON block
                start = llm_response.find('{')
                end = llm_response.rfind('}') + 1
                if start >= 0 and end > start:
                    json_match = llm_response[start:end]
            
            data = json.loads(json_match)
            
            # Validate structure
            if 'follow_up_questions' not in data:
                data['follow_up_questions'] = []
            if 'expandable_topics' not in data:
                data['expandable_topics'] = []
            if 'action_buttons' not in data:
                data['action_buttons'] = []
            if 'reasoning' not in data:
                data['reasoning'] = "Generated by LLM"
            
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"LLM response was: {llm_response}")
            raise
    
    def _convert_to_suggestions(
        self,
        data: Dict[str, Any],
        search_metadata: Dict[str, Any]
    ) -> GuidedQuerySuggestions:
        """Convert parsed LLM data to GuidedQuerySuggestions object"""
        
        # Convert follow-up questions
        follow_ups = []
        for q_data in data.get('follow_up_questions', [])[:self.max_suggestions]:
            if isinstance(q_data, dict):
                follow_ups.append(GuidedQuery(
                    question=q_data.get('question', ''),
                    reasoning=q_data.get('reasoning', ''),
                    category=q_data.get('category', 'general'),
                    relevance_score=1.0
                ))
            elif isinstance(q_data, str):
                # Fallback if LLM returns simple strings
                follow_ups.append(GuidedQuery(
                    question=q_data,
                    reasoning="Generated suggestion",
                    category="general"
                ))
        
        # Convert expandable topics
        topics = []
        for t_data in data.get('expandable_topics', []):
            if isinstance(t_data, dict):
                topics.append(ExpandableTopic(
                    id=t_data.get('id', ''),
                    label=t_data.get('label', ''),
                    message_count=search_metadata.get('topics_found', {}).get(t_data.get('id', ''), {}).get('count', 0),
                    reasoning=t_data.get('reasoning', ''),
                    priority=t_data.get('priority', 1)
                ))
        
        # Convert action buttons
        buttons = []
        for b_data in data.get('action_buttons', []):
            if isinstance(b_data, dict):
                btn_type = b_data.get('type', 'custom')
                buttons.append(ActionButton(
                    type=btn_type,
                    label=b_data.get('label', btn_type.title()),
                    callback_data=f"action:{btn_type}",
                    relevance=b_data.get('relevance', '')
                ))
        
        return GuidedQuerySuggestions(
            follow_up_questions=follow_ups,
            expandable_topics=topics,
            action_buttons=buttons,
            reasoning=data.get('reasoning', 'Generated by LLM analysis')
        )
    
    def _generate_fallback(self, search_metadata: Dict[str, Any]) -> GuidedQuerySuggestions:
        """Generate basic rule-based suggestions when LLM is unavailable"""
        
        total_messages = search_metadata.get('total_messages', 0)
        channels = search_metadata.get('channels', [])
        topics_found = search_metadata.get('topics_found', {})
        
        # Generate basic follow-up questions
        follow_ups = []
        
        if len(topics_found) > 0:
            # Suggest exploring the largest topic
            largest_topic = max(topics_found.items(), key=lambda x: x[1].get('count', 0) if isinstance(x[1], dict) else 0)
            follow_ups.append(GuidedQuery(
                question=f"Tell me more about {largest_topic[0]}",
                reasoning=f"This topic has the most messages ({largest_topic[1].get('count', 0) if isinstance(largest_topic[1], dict) else 0})",
                category="deep_dive"
            ))
        
        if len(channels) > 1:
            follow_ups.append(GuidedQuery(
                question="How do different channels discuss this topic?",
                reasoning="Multiple channels have relevant content",
                category="cross_reference"
            ))
        
        follow_ups.append(GuidedQuery(
            question="Who are the main contributors to this discussion?",
            reasoning="Identify key people involved",
            category="people"
        ))
        
        # Generate expandable topics
        topics = [
            ExpandableTopic(
                id=topic_id,
                label=f"{topic_id} ({data.get('count', 0) if isinstance(data, dict) else data} messages)",
                message_count=data.get('count', 0) if isinstance(data, dict) else 0,
                reasoning="Substantial topic worth exploring",
                priority=2 if (data.get('count', 0) if isinstance(data, dict) else 0) > 15 else 1
            )
            for topic_id, data in topics_found.items()
            if (data.get('count', 0) if isinstance(data, dict) else 0) >= 8
        ]
        
        # Generate action buttons
        buttons = [
            ActionButton(
                type="timeline",
                label="📅 Show Timeline",
                callback_data="action:timeline",
                relevance="View chronological progression"
            ),
            ActionButton(
                type="save_template",
                label="💾 Save Query",
                callback_data="action:save_template",
                relevance="Reuse this query later"
            )
        ]
        
        return GuidedQuerySuggestions(
            follow_up_questions=follow_ups[:self.max_suggestions],
            expandable_topics=topics,
            action_buttons=buttons,
            reasoning="Generated using rule-based fallback"
        )


# Singleton instance
_guided_query_generator = None

def get_guided_query_generator() -> GuidedQueryGenerator:
    """Get the guided query generator singleton"""
    global _guided_query_generator
    if _guided_query_generator is None:
        _guided_query_generator = GuidedQueryGenerator()
    return _guided_query_generator

