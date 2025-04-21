"""
Tests for the Chat Insights feature
"""

import pytest
import os
import asyncio
import json
from unittest.mock import patch, MagicMock

from silentgem.config.insights_config import get_insights_config, is_insights_configured
from silentgem.bot.command_handler import get_command_handler
from silentgem.bot.telegram_bot import get_insights_bot
from silentgem.search.query_processor import QueryProcessor
from silentgem.utils.response_formatter import format_search_results
from silentgem.database.message_store import get_message_store

# Sample test messages
TEST_MESSAGES = [
    {
        "id": 1,
        "message_id": 101,
        "original_message_id": 201,
        "source_chat_id": "source123",
        "target_chat_id": "target456",
        "sender_id": "user123",
        "sender_name": "Test User",
        "timestamp": 1620000000,  # Some timestamp
        "content": "This is a test message about APIs",
        "original_content": "This is a test message about APIs",
        "source_language": "en",
        "target_language": "en",
        "is_media": False,
        "media_type": None,
        "is_forwarded": False
    },
    {
        "id": 2,
        "message_id": 102,
        "original_message_id": 202,
        "source_chat_id": "source123",
        "target_chat_id": "target456",
        "sender_id": "user456",
        "sender_name": "Another User",
        "timestamp": 1620010000,  # A bit later
        "content": "I'm working on the database API",
        "original_content": "I'm working on the database API",
        "source_language": "en",
        "target_language": "en",
        "is_media": False,
        "media_type": None,
        "is_forwarded": False
    }
]

@pytest.fixture
def mock_message_store():
    """Mock the message store"""
    with patch('silentgem.database.message_store.MessageStore') as MockStore:
        mock_instance = MockStore.return_value
        mock_instance.search_messages.return_value = TEST_MESSAGES
        yield mock_instance

@pytest.fixture
def mock_translator():
    """Mock the translator"""
    mock = MagicMock()
    mock.translate = asyncio.coroutine(lambda text, source_language: json.dumps({
        "query_text": "API",
        "time_period": "week",
        "sender": None,
        "intent": "search"
    }))
    return mock

class TestInsights:
    """Tests for the Chat Insights feature"""
    
    @pytest.mark.asyncio
    async def test_query_processor(self, mock_translator):
        """Test that the query processor correctly processes queries"""
        query_processor = QueryProcessor()
        query_processor.translator = mock_translator
        
        # Test basic query processing
        parsed_query = await query_processor.process_query("Who talked about APIs this week?")
        
        # Verify results - basic time extraction should work even without LLM
        assert parsed_query is not None
        assert "original_query" in parsed_query
        assert parsed_query["original_query"] == "Who talked about APIs this week?"
        
        # Test LLM query processing
        parsed_query = await query_processor._process_with_llm("Who talked about APIs this week?")
        assert parsed_query is not None
        assert parsed_query["query_text"] == "API"
        assert parsed_query["time_period"] == "week"
    
    @pytest.mark.asyncio
    async def test_response_formatter(self, mock_translator):
        """Test that the response formatter correctly formats results"""
        # Test basic formatting
        response = await format_search_results(
            messages=TEST_MESSAGES,
            query="API",
            verbosity="concise",
            include_quotes=True,
            include_timestamps=True,
            include_sender_info=True
        )
        
        # Verify basic formatting worked
        assert "Found 2 messages matching 'API'" in response
        assert "Test User" in response
        assert "Another User" in response
        assert "This is a test message about APIs" in response
        assert "I'm working on the database API" in response
    
    @pytest.mark.asyncio
    async def test_command_handler(self, mock_message_store):
        """Test that the command handler correctly handles queries"""
        with patch('silentgem.search.query_processor.QueryProcessor') as MockQP:
            # Setup the mock query processor
            mock_qp_instance = MockQP.return_value
            mock_qp_instance.process_query = asyncio.coroutine(lambda query: {
                "original_query": query,
                "query_text": "API",
                "time_period": "week",
                "sender": None,
                "intent": "search"
            })
            
            # Create a mock message for testing
            mock_message = MagicMock()
            mock_message.chat.id = "target456"
            mock_message.reply = asyncio.coroutine(lambda text, quote: None)
            mock_message.chat.send_action = asyncio.coroutine(lambda action: None)
            
            # Test the command handler
            handler = get_command_handler()
            await handler.handle_query(mock_message, "Who talked about APIs this week?")
            
            # Verify the message store was searched
            mock_message_store.search_messages.assert_called_once()
            search_args = mock_message_store.search_messages.call_args[1]
            assert search_args["query"] == "API"
            assert search_args["chat_id"] == "target456"
            
            # Verify a response was sent
            mock_message.reply.assert_called_once()
    
    def test_insights_config(self):
        """Test that the insights config functions correctly"""
        # Test default config
        config = get_insights_config()
        assert isinstance(config, object)
        
        # Test setting and getting values
        config.set("test_key", "test_value")
        assert config.get("test_key") == "test_value"
        
        # Test configuration check
        is_configured = is_insights_configured()
        assert isinstance(is_configured, bool) 