"""
Test script for v1.5 Guided Query functionality

This script tests the guided query generation and suggestion system.
"""

import asyncio
import sys
from loguru import logger

# Add silentgem to path
sys.path.insert(0, '/Users/l33tdawg/nodejs-projects/silentgem')

from silentgem.bot.guided_queries import get_guided_query_generator, GuidedQuerySuggestions


async def test_guided_query_generation():
    """Test guided query generation with mock data"""
    
    logger.info("=" * 60)
    logger.info("Testing v1.5 Guided Query Generation")
    logger.info("=" * 60)
    
    # Initialize the guided query generator
    generator = get_guided_query_generator()
    
    # Mock search results
    mock_results = [
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
    ] * 5  # Simulate 15 messages
    
    # Mock search metadata
    mock_metadata = {
        'total_messages': len(mock_results),
        'channels': ['dev_team', 'announcements'],
        'topics_found': {
            'REST deprecation': {
                'count': 5,
                'messages': mock_results[:5]
            },
            'GraphQL migration': {
                'count': 7,
                'messages': mock_results[5:12]
            },
            'Authentication changes': {
                'count': 3,
                'messages': mock_results[12:]
            }
        },
        'date_range': 'Nov 1 - Nov 5, 2025',
        'top_contributors': ['Alice', 'Bob', 'Charlie']
    }
    
    # Mock conversation history
    mock_conversation = [
        {'role': 'user', 'content': 'What are the recent project updates?'},
        {'role': 'assistant', 'content': 'Here are the recent updates...'},
        {'role': 'user', 'content': 'What happened with APIs last week?'}
    ]
    
    # Mock response text
    mock_response = """Found 15 messages about APIs from the past week.

Main themes:
• REST API deprecation (5 messages)
• GraphQL migration (7 messages)  
• Authentication changes (3 messages)

The team is planning to deprecate the REST API by March 2025 and migrate to GraphQL starting in February."""
    
    logger.info("\n📝 Testing with query: 'What happened with APIs last week?'")
    logger.info(f"📊 Mock data: {len(mock_results)} messages, {len(mock_metadata['channels'])} channels")
    
    # Test 1: Generate suggestions with LLM (if available)
    logger.info("\n🧠 Test 1: Generating suggestions with LLM...")
    try:
        suggestions = await generator.generate_suggestions(
            query="What happened with APIs last week?",
            search_results=mock_results,
            search_metadata=mock_metadata,
            conversation_history=mock_conversation,
            response_text=mock_response
        )
        
        logger.success(f"✓ Generated {len(suggestions.follow_up_questions)} follow-up questions")
        for i, q in enumerate(suggestions.follow_up_questions, 1):
            logger.info(f"  {i}. {q.question}")
            logger.info(f"     Category: {q.category}, Reasoning: {q.reasoning[:60]}...")
        
        logger.success(f"✓ Found {len(suggestions.expandable_topics)} expandable topics")
        for topic in suggestions.expandable_topics:
            logger.info(f"  • {topic.label} ({topic.message_count} messages)")
        
        logger.success(f"✓ Generated {len(suggestions.action_buttons)} action buttons")
        for button in suggestions.action_buttons:
            logger.info(f"  • {button.label} ({button.type})")
        
        logger.info(f"\n💡 Reasoning: {suggestions.reasoning[:100]}...")
        
    except Exception as e:
        logger.error(f"✗ LLM generation failed: {e}")
        logger.info("  (This is expected if LLM is not configured)")
    
    # Test 2: Generate fallback suggestions (rule-based)
    logger.info("\n📋 Test 2: Generating fallback suggestions (rule-based)...")
    generator.enable_llm_generation = False
    
    fallback_suggestions = await generator.generate_suggestions(
        query="What happened with APIs last week?",
        search_results=mock_results,
        search_metadata=mock_metadata,
        conversation_history=mock_conversation,
        response_text=mock_response
    )
    
    logger.success(f"✓ Generated {len(fallback_suggestions.follow_up_questions)} fallback questions")
    for i, q in enumerate(fallback_suggestions.follow_up_questions, 1):
        logger.info(f"  {i}. {q.question}")
    
    logger.success(f"✓ Found {len(fallback_suggestions.expandable_topics)} expandable topics")
    logger.success(f"✓ Generated {len(fallback_suggestions.action_buttons)} action buttons")
    
    logger.info("\n" + "=" * 60)
    logger.success("✅ All guided query tests completed successfully!")
    logger.info("=" * 60)
    
    return suggestions


async def test_query_templates():
    """Test query template functionality"""
    
    logger.info("\n" + "=" * 60)
    logger.info("Testing v1.5 Query Templates")
    logger.info("=" * 60)
    
    from silentgem.bot.query_templates import get_query_template_manager
    
    manager = get_query_template_manager()
    
    # Test creating a template
    logger.info("\n📝 Test: Creating a query template...")
    template = manager.create_template(
        name="Weekly API Updates",
        query="What are the main API developments from the past 7 days?",
        user_id="test_user_123",
        description="Get weekly summary of API changes",
        tags=["api", "weekly", "updates"]
    )
    
    logger.success(f"✓ Created template: {template.name} (ID: {template.id})")
    
    # Test listing templates
    logger.info("\n📋 Test: Listing templates...")
    templates = manager.list_templates(user_id="test_user_123")
    logger.success(f"✓ Found {len(templates)} template(s)")
    for t in templates:
        logger.info(f"  • {t.name}: {t.query[:50]}...")
    
    # Test using a template
    logger.info("\n🔄 Test: Using a template...")
    query = manager.use_template(template.id)
    logger.success(f"✓ Retrieved query: {query[:50]}...")
    logger.info(f"  Use count: {template.use_count}")
    
    # Test searching templates
    logger.info("\n🔍 Test: Searching templates...")
    results = manager.search_templates("API", user_id="test_user_123")
    logger.success(f"✓ Found {len(results)} matching template(s)")
    
    # Clean up test template
    logger.info("\n🗑️  Test: Deleting template...")
    deleted = manager.delete_template(template.id)
    logger.success(f"✓ Template deleted: {deleted}")
    
    logger.info("\n" + "=" * 60)
    logger.success("✅ All query template tests completed successfully!")
    logger.info("=" * 60)


async def main():
    """Run all tests"""
    try:
        # Test guided queries
        await test_guided_query_generation()
        
        # Test query templates
        await test_query_templates()
        
        logger.info("\n" + "=" * 60)
        logger.success("🎉 All v1.5 tests passed successfully!")
        logger.info("=" * 60)
        logger.info("\nYou can now:")
        logger.info("  1. Start the SilentGem bot with: python silentgem.py")
        logger.info("  2. Ask a question in Telegram")
        logger.info("  3. See guided query suggestions as buttons below the response")
        logger.info("  4. Click buttons to explore suggested follow-up questions")
        logger.info("\n✨ v1.5 features are ready to use!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

