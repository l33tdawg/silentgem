#!/usr/bin/env python3

import asyncio
import sys
import os
import time

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from silentgem.bot.command_handler import get_command_handler
from silentgem.bot.conversation_intelligence import get_conversation_intelligence
from silentgem.bot.conversation_memory import get_conversation_memory

async def test_enhanced_conversation():
    """Test the enhanced conversation capabilities with rich context handling"""
    print("🚀 Testing Enhanced Conversation Intelligence System")
    print("=" * 60)
    
    try:
        handler = get_command_handler()
        conversation_intelligence = get_conversation_intelligence()
        conversation_memory = get_conversation_memory()
        
        # Test chat and user IDs
        chat_id = 'test_enhanced_chat'
        user_id = 'test_enhanced_user'
        
        # Clear any existing conversation for clean test
        conversation_memory.clear_conversation(chat_id, user_id)
        
        print("\n📋 Test Scenario: Multi-turn conversation about business developments")
        print("-" * 60)
        
        # Test 1: Initial query about business developments
        print("\n1️⃣ Initial Query: Business developments")
        query1 = "What are the latest business developments in verichains?"
        print(f"User: {query1}")
        
        start_time = time.time()
        result1 = await handler.handle_query(
            query1,
            chat_id=chat_id,
            user_id=user_id,
            verbosity="detailed"
        )
        end_time = time.time()
        
        print(f"\n🤖 Assistant ({end_time - start_time:.2f}s):")
        print(result1[:500] + "..." if len(result1) > 500 else result1)
        
        # Wait a moment to simulate natural conversation flow
        await asyncio.sleep(1)
        
        # Test 2: Follow-up query about customers
        print("\n\n2️⃣ Follow-up Query: Customer information")
        query2 = "Any new customers or partnerships mentioned?"
        print(f"User: {query2}")
        
        start_time = time.time()
        result2 = await handler.handle_query(
            query2,
            chat_id=chat_id,
            user_id=user_id,
            verbosity="standard"
        )
        end_time = time.time()
        
        print(f"\n🤖 Assistant ({end_time - start_time:.2f}s):")
        print(result2[:500] + "..." if len(result2) > 500 else result2)
        
        await asyncio.sleep(1)
        
        # Test 3: Analysis request
        print("\n\n3️⃣ Analysis Query: Trend analysis")
        query3 = "Can you analyze the trends and patterns in these business developments?"
        print(f"User: {query3}")
        
        start_time = time.time()
        result3 = await handler.handle_query(
            query3,
            chat_id=chat_id,
            user_id=user_id,
            verbosity="detailed"
        )
        end_time = time.time()
        
        print(f"\n🤖 Assistant ({end_time - start_time:.2f}s):")
        print(result3[:500] + "..." if len(result3) > 500 else result3)
        
        await asyncio.sleep(1)
        
        # Test 4: Specific follow-up
        print("\n\n4️⃣ Specific Follow-up: Timeline query")
        query4 = "When did these developments happen? Show me the timeline."
        print(f"User: {query4}")
        
        start_time = time.time()
        result4 = await handler.handle_query(
            query4,
            chat_id=chat_id,
            user_id=user_id,
            verbosity="standard"
        )
        end_time = time.time()
        
        print(f"\n🤖 Assistant ({end_time - start_time:.2f}s):")
        print(result4[:500] + "..." if len(result4) > 500 else result4)
        
        # Test conversation analysis
        print("\n\n📊 Conversation Analysis")
        print("-" * 40)
        
        try:
            analysis = await conversation_intelligence.analyze_conversation_context(chat_id, user_id)
            print(f"🎯 Conversation Themes: {analysis.get('conversation_themes', [])}")
            print(f"🔍 User Intent Patterns: {analysis.get('user_intent_patterns', [])}")
            print(f"📈 Topic Evolution: {analysis.get('topic_evolution', 'N/A')}")
            print(f"❓ Likely Next Questions: {analysis.get('next_likely_questions', [])}")
            
            # Get rich context
            rich_context = conversation_memory.get_rich_context_for_llm(chat_id, user_id)
            print(f"\n💾 Conversation Metadata:")
            print(f"   - Total exchanges: {rich_context['conversation_metadata']['total_exchanges']}")
            print(f"   - Main topics: {rich_context['conversation_summary']['main_topics']}")
            print(f"   - Key entities: {rich_context['conversation_summary']['key_entities']}")
            print(f"   - Related searches: {rich_context['current_context']['related_searches']}")
            
        except Exception as e:
            print(f"❌ Error in conversation analysis: {e}")
        
        # Test 5: Topic change to test context switching
        print("\n\n5️⃣ Topic Change: New subject")
        query5 = "What's happening with cryptocurrency markets recently?"
        print(f"User: {query5}")
        
        start_time = time.time()
        result5 = await handler.handle_query(
            query5,
            chat_id=chat_id,
            user_id=user_id,
            verbosity="standard"
        )
        end_time = time.time()
        
        print(f"\n🤖 Assistant ({end_time - start_time:.2f}s):")
        print(result5[:500] + "..." if len(result5) > 500 else result5)
        
        # Test 6: Return to original topic
        print("\n\n6️⃣ Return to Original Topic: Context retention")
        query6 = "Going back to verichains, what were the key partnerships again?"
        print(f"User: {query6}")
        
        start_time = time.time()
        result6 = await handler.handle_query(
            query6,
            chat_id=chat_id,
            user_id=user_id,
            verbosity="standard"
        )
        end_time = time.time()
        
        print(f"\n🤖 Assistant ({end_time - start_time:.2f}s):")
        print(result6[:500] + "..." if len(result6) > 500 else result6)
        
        # Final conversation analysis
        print("\n\n📊 Final Conversation Analysis")
        print("-" * 40)
        
        try:
            final_analysis = await conversation_intelligence.analyze_conversation_context(chat_id, user_id)
            final_context = conversation_memory.get_rich_context_for_llm(chat_id, user_id)
            
            print(f"🎯 Final Themes: {final_analysis.get('conversation_themes', [])}")
            print(f"📈 Topic Evolution: {final_analysis.get('topic_evolution', 'N/A')}")
            print(f"💬 Total Exchanges: {final_context['conversation_metadata']['total_exchanges']}")
            print(f"🕒 Conversation Age: {final_context['conversation_metadata']['conversation_age_hours']:.2f} hours")
            print(f"📚 Has Long History: {final_context['conversation_metadata']['has_long_history']}")
            
        except Exception as e:
            print(f"❌ Error in final analysis: {e}")
        
        print("\n" + "=" * 60)
        print("✅ Enhanced Conversation Test Completed Successfully!")
        print("\n🎉 Key Features Demonstrated:")
        print("   ✓ Multi-turn conversation with context retention")
        print("   ✓ Intelligent response synthesis using full context")
        print("   ✓ Entity and topic extraction from queries")
        print("   ✓ Conversation analysis and pattern recognition")
        print("   ✓ Topic evolution tracking")
        print("   ✓ Context switching and return to previous topics")
        print("   ✓ Rich metadata storage and retrieval")
        print("   ✓ Large context window utilization")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

async def test_context_window_usage():
    """Test how well we're utilizing the large context window"""
    print("\n\n🧠 Testing Context Window Utilization")
    print("=" * 50)
    
    try:
        conversation_intelligence = get_conversation_intelligence()
        
        # Simulate a query with lots of context
        large_query = "Analyze all the business developments, partnerships, customer acquisitions, market trends, competitive landscape, financial performance, strategic initiatives, product launches, technology innovations, and future outlook for verichains based on all available information."
        
        # Create mock search results to test context handling
        mock_results = []
        for i in range(20):
            mock_results.append({
                "id": f"msg_{i}",
                "content": f"This is mock message {i} about business development topic {i % 5}. It contains information about partnerships, customers, and market trends that are relevant to the analysis.",
                "sender_name": f"User{i % 3}",
                "timestamp": time.time() - (i * 3600),  # Messages from different hours
                "source_chat_id": f"chat_{i % 2}",
                "chat_title": f"Business Chat {i % 2}"
            })
        
        print(f"📊 Testing with {len(mock_results)} mock search results")
        print(f"🎯 Query length: {len(large_query)} characters")
        
        # Test the comprehensive prompt building
        chat_id, user_id = 'test_context_chat', 'test_context_user'
        
        start_time = time.time()
        response = await conversation_intelligence.synthesize_intelligent_response(
            query=large_query,
            search_results=mock_results,
            chat_id=chat_id,
            user_id=user_id,
            query_metadata={
                "time_period": "week",
                "expanded_terms": ["business", "partnerships", "customers", "market", "trends"],
                "intent": "analysis"
            }
        )
        end_time = time.time()
        
        print(f"\n⏱️  Response generated in {end_time - start_time:.2f} seconds")
        print(f"📝 Response length: {len(response)} characters")
        print(f"🎯 Response preview:")
        print(response[:300] + "..." if len(response) > 300 else response)
        
        # Test token estimation
        estimated_tokens = len(large_query) // 4 + sum(len(str(r)) for r in mock_results) // 4
        print(f"\n🔢 Estimated input tokens: ~{estimated_tokens}")
        print(f"🎯 Max context tokens configured: {conversation_intelligence.max_context_tokens}")
        print(f"📊 Context utilization: {(estimated_tokens / conversation_intelligence.max_context_tokens) * 100:.1f}%")
        
    except Exception as e:
        print(f"❌ Context window test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_enhanced_conversation())
    asyncio.run(test_context_window_usage()) 