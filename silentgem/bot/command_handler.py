"""
Command handler for processing user queries in the Chat Insights bot
"""

import asyncio
from loguru import logger

from silentgem.search.query_processor import get_query_processor
from silentgem.utils.response_formatter import format_search_results
from silentgem.database.message_store import get_message_store
from silentgem.config.insights_config import get_insights_config
from silentgem.search.search_engine import get_search_engine

class CommandHandler:
    """Handles commands and queries for the Chat Insights bot"""
    
    def __init__(self, bot=None, shutdown_event=None):
        """Initialize the command handler"""
        self.message_store = get_message_store()
        self.config = get_insights_config()
        self.query_processor = get_query_processor()
        self.bot = bot
        self.shutdown_event = shutdown_event or asyncio.Event()
    
    async def handle_query(self, 
                    query=None, 
                    query_text=None, 
                    user_id=None, 
                    user=None, 
                    chat_id=None, 
                    message_id=None, 
                    reply_to_message_id=None, 
                    callback=None,
                    verbosity=None):
        """
        Handle a natural language query from a user
        
        Args:
            query: The text query from the user (legacy parameter)
            query_text: The text query from the user (new parameter)
            user_id: Telegram user ID (legacy parameter)
            user: Telegram User object (new parameter)
            chat_id: Telegram chat ID
            message_id: Message ID that triggered the command (optional)
            reply_to_message_id: Message ID to reply to (optional)
            callback: Function to call with response (optional)
            verbosity: Response verbosity level (optional)
            
        Returns:
            None
        """
        try:
            # Handle parameter compatibility
            query = query_text or query
            if user and not user_id:
                user_id = user.id
            
            # Use the configured verbosity if none specified
            if not verbosity:
                verbosity = self.config.get("verbosity", "standard")
            
            # Check if shutting down
            if self.shutdown_event.is_set():
                logger.info("Ignoring query - shutdown in progress")
                return
            
            # Send typing indicator if bot is available
            if self.bot:
                try:
                    await self.bot.send_chat_action(chat_id, 'typing')
                except Exception as e:
                    logger.warning(f"Error sending typing action: {e}")
            
            # Process query with NLU
            processed_query = await self.query_processor.process_query(query)
            
            if not processed_query or not isinstance(processed_query, dict):
                logger.error("Failed to process query")
                await callback(chat_id, "❌ Sorry, I had trouble understanding your query. Please try rephrasing.")
                return
            
            # Extract parameters from processed query
            query_text = processed_query.get("query_text") or query
            time_period = processed_query.get("time_period")
            sender = processed_query.get("sender")
            intent = processed_query.get("intent", "search")
            
            logger.info(f"Processed query - Intent: {intent}, Time: {time_period}, Query: {query_text}")
            
            # Send intermediate message for long-running searches
            intermediate_msg = None
            if callback:
                if intent == "search":
                    intermediate_txt = f"🔍 Searching for information about '{query}'..."
                elif intent == "summarize":
                    intermediate_txt = f"📊 Analyzing conversations about '{query}'..."
                elif intent == "analyze":
                    intermediate_txt = f"🧠 Performing deep analysis on '{query}'..."
                else:
                    intermediate_txt = f"⏳ Processing your request about '{query}'..."
                    
                intermediate_msg = await callback(chat_id, intermediate_txt)
            
            # Execute search
            search_engine = get_search_engine()
            
            # Get verbosity setting from config for context collection
            collect_extensive_context = verbosity in ["standard", "detailed"]
            
            # Determine strategies based on query and search settings
            strategies = processed_query.get("search_strategies", ["direct", "semantic"])
            
            # Set time limits based on time_period
            time_limit = None
            if time_period:
                # Convert time period to actual datetime range
                from datetime import datetime, timedelta
                now = datetime.now()
                
                if time_period == "today":
                    start_time = now - timedelta(days=1)
                elif time_period == "yesterday":
                    start_time = now - timedelta(days=2)
                    end_time = now - timedelta(days=1)
                elif time_period == "week":
                    start_time = now - timedelta(days=7)
                elif time_period == "month":
                    start_time = now - timedelta(days=30)
                else:
                    start_time = None
                    
                if time_period != "yesterday":
                    end_time = now
                    
                if start_time:
                    time_limit = (start_time, end_time)
            
            # Search with enhanced parameters
            messages, metadata = await search_engine.search(
                query=query_text,
                sender=sender,
                max_results=50 if verbosity == "detailed" else 30,
                collect_context=collect_extensive_context,
                max_context_per_message=10 if verbosity == "concise" else 20,
                time_limit=time_limit,
                strategies=strategies,
                parsed_query=processed_query
            )
            
            # If no results, try fallback strategies
            if not messages:
                logger.info(f"No results with primary strategy, trying fallback approach")
                
                # Try with original query if processed query is different
                if processed_query.get("original_query") != query_text:
                    messages, metadata = await search_engine.search(
                        query=processed_query.get("original_query", query),
                        sender=sender,
                        max_results=50 if verbosity == "detailed" else 30,
                        collect_context=collect_extensive_context,
                        max_context_per_message=10 if verbosity == "concise" else 20,
                        time_limit=time_limit,
                        strategies=["direct", "fuzzy"],  # Use direct and fuzzy as fallback
                    )
            
            # If we have results, format and send them
            if messages:
                # Format search results with enhanced context
                formatted_results = await format_search_results(
                    messages=messages, 
                    query=query, 
                    parsed_query=processed_query, 
                    verbosity=verbosity,
                    include_quotes=(verbosity != "concise"),
                    include_timestamps=True,
                    include_sender_info=True,
                    include_channel_info=True,
                )
                
                # Send the response
                if callback:
                    await callback(chat_id, formatted_results)
                else:
                    return formatted_results
                
                # If this was a successful search and we have an intermediate message ID, delete it
                if intermediate_msg and hasattr(intermediate_msg, 'message_id') and self.bot:
                    try:
                        await self.bot.delete_messages(chat_id, intermediate_msg.message_id)
                    except Exception as e:
                        logger.warning(f"Failed to delete intermediate message: {e}")
            else:
                # No results
                no_results_message = f"📭 No messages found matching your query: '{query}'"
                
                # Add some helpful context if available
                if "expanded_terms" in processed_query and processed_query["expanded_terms"]:
                    expanded_terms = processed_query["expanded_terms"]
                    no_results_message += "\n\nTry searching for these related terms:"
                    for term in expanded_terms[:3]:
                        no_results_message += f"\n• {term}"
                elif "search_alternatives" in processed_query and processed_query["search_alternatives"]:
                    alt_terms = processed_query["search_alternatives"]
                    no_results_message += "\n\nYou might want to try these alternative search terms:"
                    for term in alt_terms[:3]:
                        no_results_message += f"\n• {term}"
                
                if callback:
                    await callback(chat_id, no_results_message)
                else:
                    return no_results_message
                
                # If this was an unsuccessful search and we have an intermediate message ID, delete it
                if intermediate_msg and hasattr(intermediate_msg, 'message_id') and self.bot:
                    try:
                        await self.bot.delete_messages(chat_id, intermediate_msg.message_id)
                    except Exception as e:
                        logger.warning(f"Failed to delete intermediate message: {e}")
        
        except Exception as e:
            logger.error(f"Error handling query: {e}")
            if callback:
                await callback(chat_id, f"❌ Sorry, something went wrong while processing your query. Error: {str(e)}")
            else:
                return f"❌ Error: {str(e)}"

    async def _send_typing_action(self, chat_id):
        """
        Send typing action to indicate the bot is processing
        This function is designed to be overridden by implementations
        that have a specific way to send typing actions.
        
        Args:
            chat_id: The chat ID to send the typing action to
        """
        # This is a placeholder - the Telegram bot will override this
        pass

# Singleton instance
_instance = None

def get_command_handler(bot=None, shutdown_event=None):
    """Get the command handler singleton instance"""
    global _instance
    if _instance is None:
        _instance = CommandHandler(bot, shutdown_event)
    return _instance 