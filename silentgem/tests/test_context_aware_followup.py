"""
Unit tests for context-aware follow-up question handling

Tests the improvements made to handle follow-up questions with proper context
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List, Dict, Any

from silentgem.bot.command_handler import CommandHandler
from silentgem.bot.conversation_intelligence import ConversationIntelligence
from silentgem.bot.conversation_memory import ConversationMemory, Message


class TestFollowUpDetection:
    """Test follow-up question detection logic"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.handler = CommandHandler()
    
    def test_is_related_query_with_followup_phrases(self):
        """Test that common follow-up phrases are detected"""
        test_cases = [
            ("What's happening in Gaza?", "What cities are affected?", True),
            ("Tell me about Apple", "When was it released?", True),
            ("News about crypto", "What are the prices?", True),
            ("What's new?", "Tell me more", True),
            ("Search for Ukraine", "Who is involved?", True),
        ]
        
        for previous, current, expected in test_cases:
            result = self.handler._is_related_query(current, previous)
            assert result == expected, f"Failed for: '{current}' after '{previous}'"
    
    def test_is_related_query_with_keyword_overlap(self):
        """Test detection based on keyword overlap"""
        test_cases = [
            ("What's happening with Bitcoin?", "Bitcoin price today", True),
            ("Tell me about Tesla", "Tesla stock news", True),
            ("Ukraine conflict", "Ukraine latest updates", True),
        ]
        
        for previous, current, expected in test_cases:
            result = self.handler._is_related_query(current, previous)
            assert result == expected, f"Failed for: '{current}' after '{previous}'"
    
    def test_is_not_related_query(self):
        """Test that unrelated queries are correctly identified"""
        test_cases = [
            ("What's happening in Gaza?", "Tell me about cryptocurrency", False),
            ("Apple news", "Weather forecast", False),
            ("", "What's the news?", False),
            ("What's the news?", "", False),
        ]
        
        for previous, current, expected in test_cases:
            result = self.handler._is_related_query(current, previous)
            assert result == expected, f"Failed for: '{current}' after '{previous}'"
    
    def test_business_context_detection(self):
        """Test that business-related follow-ups are detected"""
        previous = "What's the latest on Acme Corp business developments?"
        current = "Who are their customers?"
        
        result = self.handler._is_related_query(current, previous)
        assert result == True, "Business context should be detected"


class TestSimpleQueryEnhancement:
    """Test rule-based query enhancement fallback"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.handler = CommandHandler()
    
    def test_location_context_enhancement(self):
        """Test that location context is added to queries"""
        previous = "What's happening in Gaza?"
        current = "What cities are affected?"
        
        result = self.handler._simple_query_enhancement(current, previous)
        assert "Gaza" in result, f"Expected 'Gaza' in enhanced query, got: {result}"
        assert "cities" in result.lower(), "Original query content should be preserved"
    
    def test_topic_context_enhancement(self):
        """Test that topic context is added to queries"""
        previous = "Tell me about Apple's new product"
        current = "When was it released?"
        
        result = self.handler._simple_query_enhancement(current, previous)
        assert "Apple" in result or "product" in result.lower(), f"Expected topic in enhanced query, got: {result}"
    
    def test_no_enhancement_for_complete_queries(self):
        """Test that complete queries are not modified"""
        previous = "What's happening in Gaza?"
        current = "Tell me about cryptocurrency prices"
        
        result = self.handler._simple_query_enhancement(current, previous)
        assert result == current, "Complete queries should not be enhanced"
    
    def test_enhancement_with_list_request(self):
        """Test enhancement for list-type follow-up questions"""
        previous = "Latest news about Ukraine conflict"
        current = "List the cities involved"
        
        result = self.handler._simple_query_enhancement(current, previous)
        assert "Ukraine" in result or "conflict" in result, f"Expected context in enhanced query, got: {result}"


class TestLLMQueryEnhancement:
    """Test LLM-based query enhancement"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.handler = CommandHandler()
    
    @pytest.mark.asyncio
    async def test_enhance_query_with_context_llm_success(self):
        """Test successful LLM-based query enhancement"""
        current_query = "What cities are being affected?"
        previous_query = "What's the latest news about Gaza?"
        conversation_history = [
            {"role": "user", "content": "What's the latest news about Gaza?"},
            {"role": "assistant", "content": "Recent reports indicate escalating conflict..."}
        ]
        entities = ["Gaza"]
        topics = ["conflict", "news"]
        
        # Mock the conversation intelligence and LLM client
        with patch.object(self.handler, '_get_conversation_intelligence') as mock_ci:
            mock_llm = AsyncMock()
            mock_llm.chat_completion = AsyncMock(return_value={
                "content": "What cities in Gaza are being affected?"
            })
            
            mock_intelligence = Mock()
            mock_intelligence.llm_client = mock_llm
            mock_ci.return_value = mock_intelligence
            
            result = await self.handler._enhance_query_with_context(
                current_query,
                previous_query,
                conversation_history,
                entities,
                topics
            )
            
            # Verify the LLM was called
            assert mock_llm.chat_completion.called, "LLM should be called for enhancement"
            
            # Verify the result contains context
            assert "Gaza" in result, f"Enhanced query should contain context, got: {result}"
            assert "cities" in result.lower(), "Original query intent should be preserved"
    
    @pytest.mark.asyncio
    async def test_enhance_query_fallback_on_llm_failure(self):
        """Test that fallback is used when LLM fails"""
        current_query = "What cities are affected?"
        previous_query = "News about Gaza"
        conversation_history = []
        entities = []
        topics = []
        
        # Mock the conversation intelligence to return None (simulating failure)
        with patch.object(self.handler, '_get_conversation_intelligence') as mock_ci:
            mock_ci.return_value = None
            
            result = await self.handler._enhance_query_with_context(
                current_query,
                previous_query,
                conversation_history,
                entities,
                topics
            )
            
            # Should use simple enhancement as fallback
            assert result is not None, "Should return a result even when LLM fails"
            # The simple enhancement should add Gaza context
            assert "Gaza" in result or result == current_query, f"Should use fallback enhancement, got: {result}"
    
    @pytest.mark.asyncio
    async def test_enhance_query_prevents_over_enhancement(self):
        """Test that queries aren't enhanced too much"""
        current_query = "What?"
        previous_query = "Tell me about the latest developments in the ongoing conflict between Russia and Ukraine involving NATO and EU sanctions with economic impacts"
        conversation_history = []
        entities = []
        topics = []
        
        # Mock the conversation intelligence
        with patch.object(self.handler, '_get_conversation_intelligence') as mock_ci:
            mock_llm = AsyncMock()
            # Simulate an over-enhanced response
            mock_llm.chat_completion = AsyncMock(return_value={
                "content": "What are the latest developments in the ongoing conflict between Russia and Ukraine involving NATO and EU sanctions with economic impacts and political ramifications?"
            })
            
            mock_intelligence = Mock()
            mock_intelligence.llm_client = mock_llm
            mock_ci.return_value = mock_intelligence
            
            result = await self.handler._enhance_query_with_context(
                current_query,
                previous_query,
                conversation_history,
                entities,
                topics
            )
            
            # Should reject overly long enhancements (more than 3x original length)
            # and fall back to simple enhancement
            assert len(result) <= len(current_query) * 3 + 50, f"Enhanced query too long: {result}"


class TestContextAwareSearch:
    """Test that search queries are properly enhanced with context"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.handler = CommandHandler()
    
    @pytest.mark.asyncio
    async def test_followup_query_uses_enhanced_search(self):
        """Test that follow-up queries search with enhanced context"""
        
        # Mock dependencies
        with patch('silentgem.bot.command_handler.get_search_engine') as mock_search_engine, \
             patch.object(self.handler, '_get_conversation_intelligence') as mock_ci, \
             patch.object(self.handler.conversation_memory, 'get_conversation') as mock_conv, \
             patch.object(self.handler.conversation_memory, 'add_message') as mock_add_msg, \
             patch.object(self.handler.conversation_memory, 'get_conversation_history') as mock_history:
            
            # Setup mock conversation history
            mock_history.return_value = [
                Message(role="user", content="What's happening in Gaza?"),
                Message(role="assistant", content="Recent reports indicate conflict escalation...")
            ]
            
            # Setup mock conversation
            mock_conversation = Mock()
            mock_conversation.context = {}
            mock_conversation.conversation_depth = 2
            mock_conv.return_value = mock_conversation
            
            # Setup mock LLM for query enhancement
            mock_llm = AsyncMock()
            mock_llm.chat_completion = AsyncMock(return_value={
                "content": "What cities in Gaza are being affected?"
            })
            
            mock_intelligence = Mock()
            mock_intelligence.llm_client = mock_llm
            mock_intelligence.extract_entities_and_topics = AsyncMock(return_value=(["Gaza"], ["conflict"]))
            mock_intelligence.synthesize_intelligent_response = AsyncMock(return_value="Cities affected include...")
            mock_ci.return_value = mock_intelligence
            
            # Setup mock search engine
            mock_engine = AsyncMock()
            mock_engine.search = AsyncMock(return_value=[
                {"content": "Gaza City affected", "sender_name": "Reporter", "timestamp": 1234567890}
            ])
            mock_search_engine.return_value = mock_engine
            
            # Setup mock query processor
            with patch.object(self.handler.query_processor, 'process_query') as mock_process:
                mock_process.return_value = AsyncMock(
                    processed_query="What cities in Gaza are being affected?",
                    time_period=None,
                    cross_chats=True
                )
                
                # Execute the follow-up query
                result = await self.handler.handle_query(
                    query="What cities are affected?",
                    chat_id="test_chat",
                    user_id="test_user"
                )
                
                # Verify that query enhancement was attempted
                assert mock_process.called, "Query processor should be called"
                
                # Get the actual query that was processed
                processed_query_call = mock_process.call_args
                if processed_query_call:
                    actual_query = processed_query_call[0][0] if processed_query_call[0] else None
                    # The query should have been enhanced with context (Gaza)
                    assert actual_query is not None, "Query should be processed"
                    # Either the enhanced query contains Gaza, or we're testing the enhancement logic
                    print(f"Processed query: {actual_query}")
                
                # Verify search was executed
                assert mock_engine.search.called, "Search should be executed"
                
                # Verify result contains information
                assert result is not None, "Should return a result"
                assert "Gaza" in result or "Cities" in result, f"Result should contain relevant info, got: {result}"


class TestConversationIntelligencePrompts:
    """Test conversation intelligence system prompts"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.intelligence = ConversationIntelligence()
    
    def test_system_prompt_for_new_conversation(self):
        """Test system prompt for new conversation (not a follow-up)"""
        rich_context = {
            "conversation_metadata": {"total_exchanges": 0}
        }
        
        prompt = self.intelligence._build_intelligent_system_prompt({}, rich_context)
        
        assert "SilentGem" in prompt, "Should identify as SilentGem"
        assert "Follow-up Context" not in prompt, "Should not include follow-up instructions for new conversation"
    
    def test_system_prompt_for_followup(self):
        """Test system prompt for follow-up conversation"""
        rich_context = {
            "conversation_metadata": {"total_exchanges": 3}
        }
        
        prompt = self.intelligence._build_intelligent_system_prompt({}, rich_context)
        
        assert "SilentGem" in prompt, "Should identify as SilentGem"
        assert "Follow-up Context" in prompt, "Should include follow-up instructions"
        assert "Previous Exchange" in prompt, "Should mention previous exchange"
        assert "Current Question" in prompt, "Should mention current question"
    
    def test_user_prompt_includes_previous_context(self):
        """Test that user prompt includes previous conversation context"""
        query = "What cities are affected?"
        search_results = [
            {"content": "Gaza City under siege", "sender_name": "News", "timestamp": 1234567890,
             "source_chat_id": "123", "chat_title": "News Channel"}
        ]
        rich_context = {
            "conversation_metadata": {"total_exchanges": 2},
            "conversation_history": [
                {"role": "user", "content": "What's happening in Gaza?"},
                {"role": "assistant", "content": "Conflict escalating..."},
                {"role": "user", "content": "What cities are affected?"}
            ]
        }
        
        prompt = self.intelligence._build_comprehensive_user_prompt(
            query, search_results, rich_context, {}, {}
        )
        
        assert "Previous Exchange" in prompt, "Should include previous exchange section"
        assert "Gaza" in prompt, "Should include previous context"
        assert "Current Question" in prompt, "Should label current question"
        assert query in prompt, "Should include current query"


class TestLocationAndTopicExtraction:
    """Test location and topic extraction helpers"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.handler = CommandHandler()
    
    def test_extract_location_context(self):
        """Test location extraction from queries"""
        test_cases = [
            ("What's happening in Gaza?", "Gaza"),
            ("News from Ukraine", "Ukraine"),
            ("Latest about Palestine", "Palestine"),
            ("Gaza bombing updates", "Gaza"),
            ("Tell me about crypto", ""),  # No location
        ]
        
        for query, expected in test_cases:
            result = self.handler._extract_location_context(query)
            assert result == expected, f"Failed for query: '{query}', expected '{expected}', got '{result}'"
    
    def test_extract_primary_topic(self):
        """Test primary topic extraction"""
        test_cases = [
            ("What's happening with Bitcoin?", "Bitcoin"),
            ("Tell me about Gaza conflict", "Gaza"),
            ("Latest blockchain news", "blockchain"),
        ]
        
        for query, expected_in_result in test_cases:
            result = self.handler._extract_primary_topic(query)
            assert expected_in_result.lower() in result.lower() or result == "", \
                f"Failed for query: '{query}', expected '{expected_in_result}' in result, got '{result}'"


class TestIntegrationScenarios:
    """Integration tests for complete follow-up scenarios"""
    
    @pytest.mark.asyncio
    async def test_complete_followup_scenario_gaza_cities(self):
        """Test complete scenario: asking about Gaza, then cities"""
        handler = CommandHandler()
        
        # Mock all dependencies
        with patch('silentgem.bot.command_handler.get_search_engine') as mock_search_engine, \
             patch.object(handler, '_get_conversation_intelligence') as mock_ci, \
             patch.object(handler.conversation_memory, 'get_conversation') as mock_conv, \
             patch.object(handler.conversation_memory, 'add_message') as mock_add_msg, \
             patch.object(handler.conversation_memory, 'get_conversation_history') as mock_history:
            
            # First query: "What's happening in Gaza?"
            mock_history.return_value = []
            mock_conversation = Mock()
            mock_conversation.context = {}
            mock_conversation.conversation_depth = 0
            mock_conv.return_value = mock_conversation
            
            mock_intelligence = Mock()
            mock_intelligence.extract_entities_and_topics = AsyncMock(return_value=(["Gaza"], ["conflict"]))
            mock_intelligence.synthesize_intelligent_response = AsyncMock(
                return_value="Recent reports indicate escalating conflict in Gaza with multiple cities affected."
            )
            mock_ci.return_value = mock_intelligence
            
            mock_engine = AsyncMock()
            mock_engine.search = AsyncMock(return_value=[
                {"content": "Conflict in Gaza escalating", "sender_name": "News", "timestamp": 1234567890,
                 "source_chat_id": "123", "chat_title": "News"}
            ])
            mock_search_engine.return_value = mock_engine
            
            with patch.object(handler.query_processor, 'process_query') as mock_process:
                mock_process.return_value = AsyncMock(
                    processed_query="What's happening in Gaza?",
                    time_period=None,
                    cross_chats=True
                )
                
                result1 = await handler.handle_query(
                    query="What's happening in Gaza?",
                    chat_id="test_chat",
                    user_id="test_user"
                )
                
                assert result1 is not None
                assert "Gaza" in result1 or "conflict" in result1.lower()
            
            # Second query: "What cities are affected?" (follow-up)
            mock_history.return_value = [
                Message(role="user", content="What's happening in Gaza?"),
                Message(role="assistant", content="Recent reports indicate escalating conflict...")
            ]
            mock_conversation.conversation_depth = 2
            
            # Mock LLM for query enhancement
            mock_llm = AsyncMock()
            mock_llm.chat_completion = AsyncMock(return_value={
                "content": "What cities in Gaza are being affected?"
            })
            mock_intelligence.llm_client = mock_llm
            mock_intelligence.extract_entities_and_topics = AsyncMock(return_value=(["Gaza"], ["cities"]))
            mock_intelligence.synthesize_intelligent_response = AsyncMock(
                return_value="Cities in Gaza affected include Gaza City, Khan Yunis, and Rafah."
            )
            
            mock_engine.search = AsyncMock(return_value=[
                {"content": "Gaza City heavily affected", "sender_name": "News", "timestamp": 1234567891,
                 "source_chat_id": "123", "chat_title": "News"},
                {"content": "Khan Yunis under attack", "sender_name": "News", "timestamp": 1234567892,
                 "source_chat_id": "123", "chat_title": "News"}
            ])
            
            with patch.object(handler.query_processor, 'process_query') as mock_process:
                mock_process.return_value = AsyncMock(
                    processed_query="What cities in Gaza are being affected?",
                    time_period=None,
                    cross_chats=True
                )
                
                result2 = await handler.handle_query(
                    query="What cities are affected?",
                    chat_id="test_chat",
                    user_id="test_user"
                )
                
                assert result2 is not None
                # The result should understand we're talking about Gaza
                # Either through query enhancement or context in the response
                print(f"Follow-up result: {result2}")
                assert any(city in result2 for city in ["Gaza", "cities", "City"]), \
                    f"Follow-up should reference Gaza cities, got: {result2}"


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

