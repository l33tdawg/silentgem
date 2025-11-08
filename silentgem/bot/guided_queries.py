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
3. MUST reference SPECIFIC things mentioned in the response we just gave to the user
4. Build naturally on the current conversation - ask about details, next steps, or related aspects
5. Include SPECIFIC details from the response (names, projects, events, documents, numbers)
6. Focus on CONTENT, not meta-information (channels, message counts, contributors)
7. Each question should help the user dig deeper into what they're currently exploring
8. Ask about topics, events, people, timelines, outcomes - NOT about channels or technical details

**Example BAD Questions** (too generic or meta-focused):
❌ "Tell me more about Channel -1002339138388"
❌ "How do different channels discuss this topic?"
❌ "What else is happening?"
❌ "Who are the main contributors to this discussion?"

**Example GOOD Questions** (content-focused and specific):
✅ "What was the conversion rate for the Spring New Product Launch Event?"
✅ "When is the Q2 Work Plan scheduled to begin?"
✅ "What templates were prepared for government agencies?"
✅ "Who is [team member] developing the Business Plan for?"

**Golden Rule**: Ask about WHAT people are discussing (content), not WHERE they're discussing it (channels).

**CRITICAL OUTPUT REQUIREMENT**: 
Respond with ONLY valid JSON. Do NOT include any explanatory text, comments, or notes before or after the JSON.
Your entire response must be a single JSON object, nothing else."""
        
        try:
            # Call LLM to generate suggestions
            logger.debug("Calling LLM for guided query generation...")
            llm_response = await self.llm_client.complete(
                prompt=context_prompt,
                system=system_prompt,
                temperature=0.7,
                max_tokens=1000
            )
            
            # Check if LLM response is valid
            if llm_response is None:
                logger.warning("LLM returned None, falling back to rule-based generation")
                return self._generate_fallback(search_metadata)
            
            logger.debug(f"LLM response received (length: {len(llm_response) if llm_response else 0})")
            
            # Log first 500 chars for debugging
            if llm_response:
                logger.debug(f"LLM response preview: {llm_response[:500]}")
            
            # Parse LLM response
            suggestions_data = self._parse_llm_response(llm_response)
            
            # Convert to GuidedQuerySuggestions object
            return self._convert_to_suggestions(suggestions_data, search_metadata)
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            logger.debug(f"Falling back to rule-based generation due to: {type(e).__name__}")
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

## Current Conversation Context (MOST IMPORTANT)

**User Just Asked:** "{query}"

**We Just Responded With:**
{response_text[:1200] if response_text else 'N/A'}...

👆 FOCUS YOUR QUESTIONS ON THE SPECIFIC DETAILS IN THIS RESPONSE

**Recent Conversation History:**
{conversation_text}

## Additional Context

**Topics Discovered:**
{topics_text}

**Search Stats:**
- Found {total_messages} messages across {len(channels)} channel(s)

## Your Task

Generate 3 DIRECT, SPECIFIC follow-up questions (10-12 words max each) that:
1. **Build on what was JUST discussed** in the response above
2. **Deep Dive**: Ask about specific details mentioned in the response (timelines, people, deliverables)
3. **Explore Related**: Ask about related aspects mentioned but not fully explained
4. **Next Steps**: Ask about concrete actions or outcomes referenced

**Question Formula**: [What/Who/When/How/Which] + [Specific Detail from Response] + [Action/Outcome]?

**Key Rule**: Questions MUST reference specific things mentioned in the response we just gave, NOT generic topics.

Also identify:
- Which topics have enough content to warrant expansion (≥8 messages)
- What action buttons would be useful (timeline, contributors, etc.)

## Response Format (strict JSON)

{{
  "follow_up_questions": [
    {{
      "question": "What was the conversion rate mentioned in the response?",
      "reasoning": "Response mentioned conversion rate but didn't specify the number",
      "category": "deep_dive"
    }},
    {{
      "question": "Who else is working with [person mentioned in response]?",
      "reasoning": "Response mentioned this person - user might want to know collaborators",
      "category": "people"
    }},
    {{
      "question": "When is the [event from response] scheduled?",
      "reasoning": "Response mentioned this event - timeline would be helpful",
      "category": "timeline"
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
- Use SPECIFIC names, projects, events, or documents from the actual messages
- Start with: What/Who/When/How/Which/Where
- Focus on CONTENT: events, people, timelines, outcomes, documents
- NEVER ask about channels, channel IDs, or meta-information
- NO generic questions like "Tell me more", "What else?", "Can you provide more context?"
- Each question should ask about ONE specific thing mentioned in the messages
- Only suggest expandable topics that have substantial content (≥8 messages)
- Questions should be immediately answerable from the chat history

**Examples of context-aware follow-ups**:
If response mentions "Spring New Product Launch Event attracted 500 customers":
✅ "What was the conversion rate for the Spring New Product Launch Event?"
✅ "When did the Spring New Product Launch Event take place?"

If response mentions "Business Plan is being developed by [team member]":
✅ "What is the timeline for the Business Plan?"
✅ "Who else is working on the Business Plan?"

If response mentions "Q2 Work Plan includes new initiatives":
✅ "What specific initiatives are in the Q2 Work Plan?"
✅ "When does the Q2 Work Plan start?"

**What to avoid**:
❌ Generic questions not tied to the response: "What else is happening?"
❌ Channel references: "Tell me more about Channel -1002339138388"
❌ Meta questions: "How do different channels discuss this?"
❌ Questions about things NOT mentioned in the response
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
                topic_type = data.get('type', 'general')
                
                # Get sample content snippet to give context
                sample_snippet = ""
                if messages and len(messages) > 0:
                    sample_content = messages[0].get('content', '') or messages[0].get('text', '')
                    if sample_content:
                        sample_snippet = f" - \"{sample_content[:80]}...\""
                
                formatted.append(f"- **{topic}** ({topic_type}): {count} messages{sample_snippet}")
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
    
    def _parse_llm_response(self, llm_response: Optional[str]) -> Dict[str, Any]:
        """Parse and validate LLM JSON response"""
        try:
            # Check if response is None or empty
            if llm_response is None:
                logger.error("LLM returned None response")
                raise ValueError("LLM response is None")
            
            if not llm_response or not llm_response.strip():
                logger.error("LLM returned empty response")
                raise ValueError("LLM response is empty")
            
            # Try to extract JSON from response (in case LLM adds extra text)
            json_match = llm_response.strip()
            
            # Find the first complete JSON object by counting braces
            if not json_match.startswith('{'):
                start_pos = llm_response.find('{')
                if start_pos < 0:
                    logger.error(f"No JSON object found in LLM response")
                    logger.debug(f"LLM response was: {llm_response[:500]}")
                    raise ValueError("No JSON object found in response")
                json_match = llm_response[start_pos:]
            
            # Extract first complete JSON object by tracking brace depth
            brace_count = 0
            in_string = False
            escape_next = False
            end_pos = -1
            
            for i, char in enumerate(json_match):
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\':
                    escape_next = True
                    continue
                    
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break
            
            if end_pos > 0:
                json_match = json_match[:end_pos]
            
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
            logger.debug(f"LLM response was: {llm_response[:500] if llm_response else 'None'}")
            raise
        except ValueError as e:
            logger.error(f"Invalid LLM response: {e}")
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
        top_contributors = search_metadata.get('top_contributors', [])
        
        # Generate basic follow-up questions
        follow_ups = []
        
        # Find topics that are NOT just channel IDs
        content_topics = {
            topic: data for topic, data in topics_found.items()
            if isinstance(data, dict) and data.get('type') != 'channel'
        }
        
        if content_topics:
            # Suggest exploring the largest content topic
            largest_topic = max(content_topics.items(), key=lambda x: x[1].get('count', 0) if isinstance(x[1], dict) else 0)
            topic_name = largest_topic[0]
            topic_type = largest_topic[1].get('type', 'topic')
            
            # Generate a more specific question based on topic type
            if topic_type == 'event':
                follow_ups.append(GuidedQuery(
                    question=f"What were the results of the {topic_name}?",
                    reasoning="Follow up on event outcomes",
                    category="deep_dive"
                ))
            elif topic_type == 'document':
                follow_ups.append(GuidedQuery(
                    question=f"What are the key points in the {topic_name}?",
                    reasoning="Explore document details",
                    category="deep_dive"
                ))
            else:
                follow_ups.append(GuidedQuery(
                    question=f"What are the latest updates on {topic_name}?",
                    reasoning="Get current status",
                    category="deep_dive"
                ))
        
        # Ask about people if we found contributors
        if top_contributors and len(top_contributors) > 0:
            main_contributor = top_contributors[0]
            follow_ups.append(GuidedQuery(
                question=f"What is {main_contributor} working on?",
                reasoning="Focus on key contributor's activities",
                category="people"
            ))
        
        # Ask about timeline
        if total_messages > 5:
            follow_ups.append(GuidedQuery(
                question="What is the timeline for this project?",
                reasoning="Understand time-based progression",
                category="timeline"
            ))
        
        # Only add generic question if we have nothing better
        if not follow_ups:
            follow_ups.append(GuidedQuery(
                question="What are the next steps being discussed?",
                reasoning="Identify action items",
                category="deep_dive"
            ))
        
        # Generate expandable topics (exclude pure channel topics if possible)
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
            and (not isinstance(data, dict) or data.get('type') != 'channel')  # Prefer non-channel topics
        ]
        
        # If no content topics, include channel topics as fallback
        if not topics:
            topics = [
                ExpandableTopic(
                    id=topic_id,
                    label=f"{topic_id} ({data.get('count', 0) if isinstance(data, dict) else data} messages)",
                    message_count=data.get('count', 0) if isinstance(data, dict) else 0,
                    reasoning="Channel discussion",
                    priority=1
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

