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
    
    async def handle_query(self, query_text, chat_id, user=None, verbosity="standard"):
        """
        Handle a query from a user
        
        Args:
            query_text: The raw query text from the user
            chat_id: The ID of the chat where the query was sent
            user: User object or dict with information about the sender
            verbosity: Response verbosity (concise, standard, detailed)
            
        Returns:
            str: The formatted response to send back to the user
        """
        try:
            # Send typing action while processing
            if chat_id:
                await self._send_typing_action(chat_id)
                
            # Log the query
            if user:
                user_id = user.get("id", None) if isinstance(user, dict) else getattr(user, "id", None)
                user_name = user.get("name", None) if isinstance(user, dict) else getattr(user, "first_name", None)
                logger.info(f"Query from user {user_id} ({user_name}): {query_text}")
            else:
                logger.info(f"Query from unknown user: {query_text}")
            
            # Process the query
            query_processor = QueryProcessor()
            parsed_query = await query_processor.process_query(query_text)
            
            if not parsed_query:
                logger.warning(f"Failed to parse query: {query_text}")
                return "I'm sorry, I had trouble understanding your query. Could you please rephrase it?"
            
            # Search messages
            query_text_for_search = parsed_query.get("query_text", query_text)
            time_period = parsed_query.get("time_period", None)
            
            # Log the processed query
            logger.info(f"Processed query: {query_text_for_search}, time period: {time_period}")
            
            # Search for messages - this will search across all channels the bot has access to
            search_results = self.message_store.search_messages(
                query=query_text_for_search, 
                time_period=time_period,
                limit=30  # Increased limit to get more matches across channels
            )
            
            # Enhanced strategy for context retrieval
            # 1. Get more context for each search result (across channels)
            # 2. Gather additional messages related to the topic but didn't match the exact search
            all_context_messages = []
            chat_messages_map = {}  # Group messages by chat for better organization
            
            if search_results:
                # Set context window size - larger context window
                before_count = 15
                after_count = 15
                
                # Track which chats had matching messages
                matching_chats = set()
                for result in search_results:
                    source_chat = result.get('source_chat_id')
                    target_chat = result.get('target_chat_id')
                    if source_chat:
                        matching_chats.add(source_chat)
                    if target_chat:
                        matching_chats.add(target_chat)
                
                # For each search result, get context from all chats
                for result in search_results:
                    # Get context for this message with cross-chat context enabled
                    context = self.message_store.get_message_context(
                        message_id=result['id'],
                        source_chat_id=None,  # No chat filter - get context across all channels
                        before_count=before_count,
                        after_count=after_count,
                        cross_chat_context=True
                    )
                    
                    # Add these to our full context list
                    # Only add messages that aren't already in our results or context
                    for msg in context['before'] + context['after']:
                        if msg['id'] not in [m['id'] for m in search_results] and \
                           msg['id'] not in [m['id'] for m in all_context_messages]:
                            all_context_messages.append(msg)
                            
                            # Also track by chat for better organization
                            chat_id_key = msg.get('source_chat_id') or msg.get('target_chat_id')
                            if chat_id_key not in chat_messages_map:
                                chat_messages_map[chat_id_key] = []
                            chat_messages_map[chat_id_key].append(msg)
                
                # Perform a second search for related messages if there aren't enough context messages
                if len(all_context_messages) < 20 and parsed_query.get("search_alternatives"):
                    # Try to find related messages using alternative search terms
                    alternatives = parsed_query.get("search_alternatives", [])
                    if alternatives and isinstance(alternatives, list):
                        # Take the first 2 alternative search terms
                        for alt_term in alternatives[:2]:
                            if alt_term and isinstance(alt_term, str):
                                alt_results = self.message_store.search_messages(
                                    query=alt_term,
                                    time_period=time_period,
                                    limit=10
                                )
                                
                                # Add any new messages to our context
                                for msg in alt_results:
                                    if msg['id'] not in [m['id'] for m in search_results] and \
                                       msg['id'] not in [m['id'] for m in all_context_messages]:
                                        all_context_messages.append(msg)
                                        
                                        # Also track by chat
                                        chat_id_key = msg.get('source_chat_id') or msg.get('target_chat_id')
                                        if chat_id_key not in chat_messages_map:
                                            chat_messages_map[chat_id_key] = []
                                        chat_messages_map[chat_id_key].append(msg)
                
                # Add a special metadata message containing chat information to help the LLM understand the context
                if matching_chats:
                    metadata_msg = {
                        "id": -1,  # Special ID to indicate metadata
                        "metadata": True,
                        "content": f"This search found messages across {len(matching_chats)} different chat groups."
                    }
                    all_context_messages.append(metadata_msg)
                
                # Sort all context messages by timestamp
                all_context_messages.sort(key=lambda x: x.get('timestamp', 0) if not x.get('metadata', False) else 0)
                logger.info(f"Added {len(all_context_messages)} context messages to the {len(search_results)} search results from {len(chat_messages_map)} different chats")
            
            # Format the response
            if search_results:
                response = await format_search_results(
                    messages=search_results,
                    query=query_text,
                    parsed_query=parsed_query,
                    verbosity=verbosity,
                    context_messages=all_context_messages,
                    chat_messages_map=chat_messages_map  # Pass the chat grouping for better context organization
                )
            elif parsed_query:
                # No results but parsed query
                logger.info(f"No messages found for query: {query_text_for_search}")
                response = await format_search_results(
                    messages=[],
                    query=query_text,
                    parsed_query=parsed_query
                )
            else:
                # No results and couldn't parse query
                logger.warning(f"Failed to parse query: {query_text}")
                response = "I didn't find any messages matching your query. Could you try rephrasing or using different keywords?"
            
            return response
            
        except Exception as e:
            logger.error(f"Error handling query: {e}")
            return "I'm sorry, I encountered an error while processing your query. Please try again later."

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

def get_command_handler():
    """Get the command handler singleton instance"""
    global _instance
    if _instance is None:
        _instance = CommandHandler()
    return _instance 