"""
Command handler for processing user queries in the Chat Insights bot
"""

import asyncio
from loguru import logger

from silentgem.search.query_processor import QueryProcessor
from silentgem.utils.response_formatter import format_search_results
from silentgem.database.message_store import get_message_store
from silentgem.config.insights_config import get_insights_config

class CommandHandler:
    """Handles commands and queries for the Chat Insights bot"""
    
    def __init__(self):
        """Initialize the command handler"""
        self.message_store = get_message_store()
        self.config = get_insights_config()
        self.query_processor = QueryProcessor()
    
    async def handle_query(self, message, query_text):
        """
        Handle a query from a user
        
        Args:
            message: The message object from Telegram
            query_text: The query text to process
        """
        try:
            # Send typing action while processing
            await message.chat.send_action("typing")
            
            # Get the chat ID of the current chat (for reference)
            current_chat_id = str(message.chat.id)
            
            logger.info(f"Processing query: '{query_text}' from chat {current_chat_id}")
            
            # Process query and extract search parameters
            parsed_query = await self.query_processor.process_query(query_text)
            
            if parsed_query:
                # Use parsed parameters to search messages across ALL channels
                search_results = self.message_store.search_messages(
                    query=parsed_query.get("query_text"),
                    chat_id=None,  # No chat filter - search across all channels
                    time_period=parsed_query.get("time_period"),
                    limit=20
                )
                
                if search_results:
                    logger.info(f"Found {len(search_results)} results for query")
                    
                    # Format response based on verbosity settings
                    response_verbosity = self.config.get("response_verbosity", "standard")
                    include_quotes = self.config.get("include_quotes", True)
                    include_timestamps = self.config.get("include_timestamps", True)
                    include_sender_info = self.config.get("include_sender_info", True)
                    
                    # Generate response
                    response = await format_search_results(
                        search_results,
                        query=query_text,
                        parsed_query=parsed_query,
                        verbosity=response_verbosity,
                        include_quotes=include_quotes,
                        include_timestamps=include_timestamps,
                        include_sender_info=include_sender_info,
                        include_channel_info=True  # Add channel information
                    )
                    
                    # Send response
                    await message.reply(response, quote=True)
                    
                else:
                    logger.info("No results found for query")
                    await message.reply(
                        f"I couldn't find any messages matching '{query_text}'.\n\n"
                        f"Try a different query or check your search terms.", 
                        quote=True
                    )
            else:
                logger.warning(f"Failed to process query: {query_text}")
                await message.reply(
                    "I'm having trouble understanding your query. Please try to rephrase it or use more specific terms.",
                    quote=True
                )
                
        except Exception as e:
            logger.error(f"Error handling query: {e}")
            await message.reply(
                "I encountered an error while processing your query. Please try again later.",
                quote=True
            )


# Singleton instance
_instance = None

def get_command_handler():
    """Get the command handler singleton instance"""
    global _instance
    if _instance is None:
        _instance = CommandHandler()
    return _instance 