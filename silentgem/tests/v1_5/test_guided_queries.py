"""
Unit tests for guided_queries.py

Tests the GuidedQueryGenerator functionality including:
- LLM-based suggestion generation
- Fallback rule-based generation
- Response parsing
- Context building
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from silentgem.bot.guided_queries import (
    GuidedQueryGenerator,
    GuidedQuery,
    ExpandableTopic,
    ActionButton,
    GuidedQuerySuggestions
)


@pytest.fixture
def generator():
    """Create a GuidedQueryGenerator instance"""
    return GuidedQueryGenerator()


@pytest.fixture
def mock_search_results():
    """Create mock search results"""
    return [
        {
            'content': 'We need to deprecate the REST API by March 2025',
            'sender_name': 'Alice',
            'timestamp': 1699000000,
            'source_chat_id': 'dev_team'
        },
        {
            'content': 'GraphQL migration is scheduled for February',
            'sender_name': 'Bob',
            'timestamp': 1699001000,
            'source_chat_id': 'dev_team'
        },
        {
            'content': 'Authentication changes will require client updates',
            'sender_name': 'Charlie',
            'timestamp': 1699002000,
            'source_chat_id': 'announcements'
        },
    ] * 5  # 15 messages total


@pytest.fixture
def mock_search_metadata():
    """Create mock search metadata"""
    return {
        'total_messages': 15,
        'channels': ['dev_team', 'announcements'],
        'topics_found': {
            'REST deprecation': {
                'count': 5,
                'messages': []
            },
            'GraphQL migration': {
                'count': 7,
                'messages': []
            },
            'Authentication': {
                'count': 3,
                'messages': []
            }
        },
        'date_range': 'Nov 1-7, 2025',
        'top_contributors': ['Alice', 'Bob', 'Charlie']
    }


@pytest.fixture
def mock_conversation_history():
    """Create mock conversation history"""
    return [
        {'role': 'user', 'content': 'What are the recent updates?'},
        {'role': 'assistant', 'content': 'Here are the updates...'},
        {'role': 'user', 'content': 'What happened with APIs?'}
    ]


class TestGuidedQueryDataClasses:
    """Tests for data classes"""
    
    def test_guided_query_creation(self):
        """Test creating a GuidedQuery"""
        query = GuidedQuery(
            question="What are the deadlines?",
            reasoning="User needs timeline",
            category="deep_dive",
            relevance_score=0.9
        )
        
        assert query.question == "What are the deadlines?"
        assert query.category == "deep_dive"
        assert query.relevance_score == 0.9
    
    def test_expandable_topic_creation(self):
        """Test creating an ExpandableTopic"""
        topic = ExpandableTopic(
            id="graphql_migration",
            label="GraphQL Migration",
            message_count=22,
            reasoning="Large topic",
            priority=2
        )
        
        assert topic.id == "graphql_migration"
        assert topic.message_count == 22
        assert topic.priority == 2
    
    def test_action_button_creation(self):
        """Test creating an ActionButton"""
        button = ActionButton(
            type="timeline",
            label="📅 Timeline",
            callback_data="action:timeline",
            relevance="Shows progression"
        )
        
        assert button.type == "timeline"
        assert button.callback_data == "action:timeline"


class TestFallbackGeneration:
    """Tests for rule-based fallback generation"""
    
    @pytest.mark.asyncio
    async def test_fallback_generates_suggestions(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test that fallback mode generates suggestions"""
        generator.enable_llm_generation = False
        
        suggestions = await generator.generate_suggestions(
            query="What happened with APIs?",
            search_results=mock_search_results,
            search_metadata=mock_search_metadata
        )
        
        assert suggestions is not None
        assert len(suggestions.follow_up_questions) > 0
        assert len(suggestions.action_buttons) > 0
    
    @pytest.mark.asyncio
    async def test_fallback_suggests_largest_topic(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test that fallback suggests exploring the largest topic"""
        generator.enable_llm_generation = False
        
        suggestions = await generator.generate_suggestions(
            query="What happened?",
            search_results=mock_search_results,
            search_metadata=mock_search_metadata
        )
        
        # Should suggest exploring GraphQL (largest topic with 7 messages)
        questions = [q.question for q in suggestions.follow_up_questions]
        assert any("GraphQL" in q for q in questions)
    
    @pytest.mark.asyncio
    async def test_fallback_suggests_cross_channel(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test that fallback suggests cross-channel analysis when multiple channels"""
        generator.enable_llm_generation = False
        
        suggestions = await generator.generate_suggestions(
            query="What happened?",
            search_results=mock_search_results,
            search_metadata=mock_search_metadata
        )
        
        questions = [q.question for q in suggestions.follow_up_questions]
        assert any("channel" in q.lower() for q in questions)
    
    @pytest.mark.asyncio
    async def test_fallback_includes_expandable_topics(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test that fallback includes expandable topics for substantial content"""
        generator.enable_llm_generation = False
        
        # Modify metadata to have topics with enough messages
        mock_search_metadata['topics_found'] = {
            'Topic A': {'count': 10, 'messages': []},
            'Topic B': {'count': 5, 'messages': []},  # Below threshold
            'Topic C': {'count': 15, 'messages': []}
        }
        
        suggestions = await generator.generate_suggestions(
            query="Test",
            search_results=mock_search_results,
            search_metadata=mock_search_metadata
        )
        
        # Should only include topics with ≥8 messages
        assert len(suggestions.expandable_topics) == 2
        topic_counts = [t.message_count for t in suggestions.expandable_topics]
        assert all(count >= 8 for count in topic_counts)


class TestLLMGeneration:
    """Tests for LLM-based generation"""
    
    @pytest.mark.asyncio
    async def test_llm_generation_called_when_enabled(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test that LLM is called when enabled"""
        generator.enable_llm_generation = True
        
        # Mock LLM response
        mock_llm_response = json.dumps({
            "follow_up_questions": [
                {
                    "question": "What are the migration deadlines?",
                    "reasoning": "User needs timeline",
                    "category": "timeline"
                }
            ],
            "expandable_topics": [],
            "action_buttons": [],
            "reasoning": "Test reasoning"
        })
        
        with patch.object(generator.llm_client, 'complete', new=AsyncMock(return_value=mock_llm_response)):
            suggestions = await generator.generate_suggestions(
                query="What happened with APIs?",
                search_results=mock_search_results,
                search_metadata=mock_search_metadata
            )
            
            assert len(suggestions.follow_up_questions) == 1
            assert suggestions.follow_up_questions[0].question == "What are the migration deadlines?"
            generator.llm_client.complete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test that LLM failure triggers fallback"""
        generator.enable_llm_generation = True
        
        # Mock LLM to raise an exception
        with patch.object(generator.llm_client, 'complete', side_effect=Exception("LLM Error")):
            suggestions = await generator.generate_suggestions(
                query="What happened?",
                search_results=mock_search_results,
                search_metadata=mock_search_metadata
            )
            
            # Should still get suggestions from fallback
            assert suggestions is not None
            assert len(suggestions.follow_up_questions) > 0
    
    @pytest.mark.asyncio
    async def test_llm_malformed_json_falls_back(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test that malformed JSON from LLM triggers fallback"""
        generator.enable_llm_generation = True
        
        # Mock LLM to return invalid JSON
        with patch.object(generator.llm_client, 'complete', new=AsyncMock(return_value="Not valid JSON")):
            suggestions = await generator.generate_suggestions(
                query="What happened?",
                search_results=mock_search_results,
                search_metadata=mock_search_metadata
            )
            
            # Should fall back to rule-based
            assert suggestions is not None
            assert len(suggestions.follow_up_questions) > 0


class TestPromptBuilding:
    """Tests for LLM prompt construction"""
    
    def test_format_topics_for_llm(
        self, generator, mock_search_metadata
    ):
        """Test formatting topics for LLM"""
        formatted = generator._format_topics_for_llm(
            mock_search_metadata['topics_found']
        )
        
        assert "REST deprecation" in formatted
        assert "5 messages" in formatted or "5" in formatted
    
    def test_format_topics_empty(self, generator):
        """Test formatting empty topics"""
        formatted = generator._format_topics_for_llm({})
        assert "No specific topics" in formatted or "No topics" in formatted
    
    def test_format_conversation_for_llm(
        self, generator, mock_conversation_history
    ):
        """Test formatting conversation history for LLM"""
        formatted = generator._format_conversation_for_llm(
            mock_conversation_history
        )
        
        assert "USER:" in formatted
        assert "ASSISTANT:" in formatted
        assert "What happened with APIs?" in formatted
    
    def test_format_conversation_empty(self, generator):
        """Test formatting empty conversation"""
        formatted = generator._format_conversation_for_llm([])
        assert "No previous" in formatted or "previous" in formatted.lower()


class TestResponseParsing:
    """Tests for parsing LLM responses"""
    
    def test_parse_valid_json(self, generator):
        """Test parsing valid JSON response"""
        llm_response = json.dumps({
            "follow_up_questions": [
                {"question": "Q1", "reasoning": "R1", "category": "deep_dive"}
            ],
            "expandable_topics": [
                {"id": "topic1", "label": "Topic 1", "reasoning": "R", "priority": 1}
            ],
            "action_buttons": [
                {"type": "timeline", "label": "Timeline", "relevance": "useful"}
            ],
            "reasoning": "Overall reasoning"
        })
        
        data = generator._parse_llm_response(llm_response)
        
        assert "follow_up_questions" in data
        assert "expandable_topics" in data
        assert "action_buttons" in data
        assert "reasoning" in data
    
    def test_parse_json_with_extra_text(self, generator):
        """Test parsing JSON embedded in text"""
        llm_response = """Here's my analysis:
        
        {"follow_up_questions": [], "expandable_topics": [], "action_buttons": [], "reasoning": "Test"}
        
        Additional commentary."""
        
        data = generator._parse_llm_response(llm_response)
        assert data is not None
        assert "reasoning" in data
    
    def test_parse_invalid_json_raises(self, generator):
        """Test that invalid JSON raises exception"""
        with pytest.raises(json.JSONDecodeError):
            generator._parse_llm_response("Not JSON at all")
    
    def test_parse_missing_fields_adds_defaults(self, generator):
        """Test that missing fields get default values"""
        llm_response = json.dumps({
            "follow_up_questions": []
            # Missing other fields
        })
        
        data = generator._parse_llm_response(llm_response)
        
        assert "expandable_topics" in data
        assert "action_buttons" in data
        assert "reasoning" in data


class TestSuggestionConversion:
    """Tests for converting parsed data to suggestion objects"""
    
    def test_convert_follow_up_questions(self, generator):
        """Test converting follow-up questions"""
        data = {
            "follow_up_questions": [
                {"question": "Q1", "reasoning": "R1", "category": "deep_dive"},
                {"question": "Q2", "reasoning": "R2", "category": "timeline"}
            ],
            "expandable_topics": [],
            "action_buttons": [],
            "reasoning": "Test"
        }
        
        suggestions = generator._convert_to_suggestions(data, {})
        
        assert len(suggestions.follow_up_questions) == 2
        assert suggestions.follow_up_questions[0].question == "Q1"
        assert suggestions.follow_up_questions[0].category == "deep_dive"
    
    def test_convert_limits_max_suggestions(self, generator):
        """Test that conversion limits to max_suggestions"""
        generator.max_suggestions = 2
        
        data = {
            "follow_up_questions": [
                {"question": "Q1", "reasoning": "R", "category": "deep_dive"},
                {"question": "Q2", "reasoning": "R", "category": "deep_dive"},
                {"question": "Q3", "reasoning": "R", "category": "deep_dive"},
                {"question": "Q4", "reasoning": "R", "category": "deep_dive"}
            ],
            "expandable_topics": [],
            "action_buttons": [],
            "reasoning": "Test"
        }
        
        suggestions = generator._convert_to_suggestions(data, {})
        
        assert len(suggestions.follow_up_questions) == 2
    
    def test_convert_handles_string_questions(self, generator):
        """Test converting simple string questions (fallback format)"""
        data = {
            "follow_up_questions": ["Simple question 1", "Simple question 2"],
            "expandable_topics": [],
            "action_buttons": [],
            "reasoning": "Test"
        }
        
        suggestions = generator._convert_to_suggestions(data, {})
        
        assert len(suggestions.follow_up_questions) == 2
        assert suggestions.follow_up_questions[0].question == "Simple question 1"
    
    def test_convert_expandable_topics(self, generator):
        """Test converting expandable topics"""
        metadata = {
            'topics_found': {
                'topic1': {'count': 10, 'messages': []},
                'topic2': {'count': 15, 'messages': []}
            }
        }
        
        data = {
            "follow_up_questions": [],
            "expandable_topics": [
                {"id": "topic1", "label": "Topic 1", "reasoning": "R", "priority": 1},
                {"id": "topic2", "label": "Topic 2", "reasoning": "R", "priority": 2}
            ],
            "action_buttons": [],
            "reasoning": "Test"
        }
        
        suggestions = generator._convert_to_suggestions(data, metadata)
        
        assert len(suggestions.expandable_topics) == 2
        assert suggestions.expandable_topics[0].message_count == 10
        assert suggestions.expandable_topics[1].message_count == 15
    
    def test_convert_action_buttons(self, generator):
        """Test converting action buttons"""
        data = {
            "follow_up_questions": [],
            "expandable_topics": [],
            "action_buttons": [
                {"type": "timeline", "label": "Timeline", "relevance": "useful"},
                {"type": "save_template", "label": "Save", "relevance": "useful"}
            ],
            "reasoning": "Test"
        }
        
        suggestions = generator._convert_to_suggestions(data, {})
        
        assert len(suggestions.action_buttons) == 2
        assert suggestions.action_buttons[0].type == "timeline"
        assert suggestions.action_buttons[0].callback_data == "action:timeline"


class TestEdgeCases:
    """Tests for edge cases and error handling"""
    
    @pytest.mark.asyncio
    async def test_empty_search_results(self, generator):
        """Test with empty search results"""
        suggestions = await generator.generate_suggestions(
            query="Test",
            search_results=[],
            search_metadata={'total_messages': 0, 'channels': [], 'topics_found': {}}
        )
        
        assert suggestions is not None
        # Should still provide some basic suggestions
    
    @pytest.mark.asyncio
    async def test_no_conversation_history(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test with no conversation history"""
        suggestions = await generator.generate_suggestions(
            query="Test",
            search_results=mock_search_results,
            search_metadata=mock_search_metadata,
            conversation_history=None
        )
        
        assert suggestions is not None
        assert len(suggestions.follow_up_questions) > 0
    
    @pytest.mark.asyncio
    async def test_no_response_text(
        self, generator, mock_search_results, mock_search_metadata
    ):
        """Test with no response text"""
        suggestions = await generator.generate_suggestions(
            query="Test",
            search_results=mock_search_results,
            search_metadata=mock_search_metadata,
            response_text=None
        )
        
        assert suggestions is not None

