"""
Telegram bot implementation for SilentGem Chat Insights
"""

import os
import asyncio
from loguru import logger
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import RPCError, ApiIdInvalid, AuthKeyUnregistered

from silentgem.config import ensure_dir_exists, API_ID, API_HASH
from silentgem.config.insights_config import get_insights_config

class InsightsBot:
    """Telegram bot for chat insights"""
    
    def __init__(self):
        """Initialize the bot"""
        # Get the insights configuration
        self.config = get_insights_config()
        
        # Bot token
        self.token = self.config.get("bot_token")
        if not self.token:
            logger.error("No bot token configured for insights")
            raise ValueError("No bot token configured for insights")
        
        # The bot instance
        self.bot = None
        
        # For tracking the running state
        self._running = False
        self._tasks = {}
        
        # Reference to the command handler (will be set later)
        self.command_handler = None
    
    async def start(self):
        """Start the bot"""
        if self._running:
            logger.warning("Bot is already running")
            return
        
        try:
            # Create the bot client
            session_name = "silentgem_insights_bot"
            
            # Ensure sessions directory exists
            ensure_dir_exists("sessions")
            
            self.bot = Client(
                session_name,
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=self.token,
                workdir="sessions"
            )
            
            # Register message handlers
            self._register_handlers()
            
            # Start the bot
            await self.bot.start()
            
            # Update bot information
            me = await self.bot.get_me()
            self.config.set("bot_username", me.username)
            
            logger.info(f"Insights bot started as @{me.username}")
            
            # Set running flag
            self._running = True
            
            # Keep the bot running
            self._tasks["idle"] = asyncio.create_task(self._idle())
            
        except ApiIdInvalid:
            logger.error("API ID/hash is invalid")
            raise
        except AuthKeyUnregistered:
            logger.error("Bot token is invalid")
            raise
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise
    
    async def stop(self):
        """Stop the bot"""
        if not self._running:
            logger.warning("Bot is not running")
            return
        
        try:
            # Cancel all tasks
            for task_name, task in self._tasks.items():
                if not task.done():
                    logger.debug(f"Cancelling task: {task_name}")
                    task.cancel()
            
            # Wait a moment to let tasks clean up
            await asyncio.sleep(0.5)
            
            if self.bot:
                # Remove all handlers with improved error handling
                if hasattr(self.bot, 'dispatcher'):
                    try:
                        # Instead of removing all handlers at once, remove them one by one
                        for group in self.bot.dispatcher.groups:
                            # Make a copy of the list to safely iterate and remove
                            if group in self.bot.dispatcher.groups:
                                handlers = self.bot.dispatcher.groups[group].copy() if isinstance(self.bot.dispatcher.groups[group], list) else []
                                for handler in handlers:
                                    try:
                                        # Use a direct method call which is safer
                                        if handler in self.bot.dispatcher.groups[group]:
                                            self.bot.dispatcher.groups[group].remove(handler)
                                    except (ValueError, KeyError) as e:
                                        # Ignore errors about handlers not being in the list
                                        logger.debug(f"Couldn't remove handler: {e}")
                    except Exception as e:
                        # Catch any other dispatcher errors
                        logger.warning(f"Error removing handlers: {e}")
                
                # Stop the bot with block=False to avoid hanging
                await self.bot.stop(block=False)
                
                # Wait a moment for the stop to take effect
                await asyncio.sleep(1)
            
            logger.info("Insights bot stopped")
            
            # Clear running flag
            self._running = False
            
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
    
    def _register_handlers(self):
        """Register message handlers for the bot"""
        # Command handler for /askgem command
        @self.bot.on_message(filters.command("askgem") & filters.text)
        async def askgem_handler(client, message):
            """Handle /askgem command"""
            if self.command_handler:
                query = message.text.split("/askgem", 1)[1].strip()
                if query:
                    # Get verbosity setting
                    verbosity = self.config.get("response_verbosity", "standard")
                    
                    # Use new interface
                    response = await self.command_handler.handle_query(
                        query_text=query,
                        chat_id=message.chat.id,
                        user=message.from_user,
                        verbosity=verbosity
                    )
                    
                    # Send the response
                    await message.reply(response, quote=True)
                else:
                    await message.reply("Please provide a query with the command.\nExample: `/askgem Who talked about API yesterday?`", quote=True)
            else:
                await message.reply("Query processing is not available right now. Please try again later.", quote=True)
        
        # Handle regular messages (treat as queries if not a command)
        @self.bot.on_message(filters.text & (~filters.command("")))
        async def message_handler(client, message):
            """Handle regular messages as queries"""
            # Ignore messages in groups unless directly mentioned
            if message.chat.type in ["group", "supergroup"]:
                # Check if the bot was mentioned or replied to
                is_mentioned = False
                
                # Check if bot was mentioned
                if message.entities:
                    for entity in message.entities:
                        if entity.type == "mention":
                            mention = message.text[entity.offset:entity.offset + entity.length]
                            if mention == f"@{self.config.get('bot_username')}":
                                is_mentioned = True
                                break
                
                # Check if bot was replied to
                if message.reply_to_message and message.reply_to_message.from_user:
                    if message.reply_to_message.from_user.is_bot and message.reply_to_message.from_user.username == self.config.get("bot_username"):
                        is_mentioned = True
                
                if not is_mentioned:
                    # Not mentioned or replied to, ignore
                    return
            
            # Process as a query if command handler exists
            if self.command_handler:
                # Get verbosity setting
                verbosity = self.config.get("response_verbosity", "standard")
                
                # Use new interface
                response = await self.command_handler.handle_query(
                    query_text=message.text,
                    chat_id=message.chat.id,
                    user=message.from_user,
                    verbosity=verbosity
                )
                
                # Send the response
                await message.reply(response, quote=True)
    
    async def _idle(self):
        """Keep the bot running"""
        while self._running:
            await asyncio.sleep(1)
    
    async def send_message(self, chat_id, text, reply_to=None, quote=False, **kwargs):
        """Send a message using the bot"""
        if not self._running or not self.bot:
            logger.error("Bot is not running")
            return None
        
        try:
            return await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to,
                quote=quote,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    def set_command_handler(self, handler):
        """Set the command handler"""
        self.command_handler = handler
        
        # Override the _send_typing_action method to use our bot's send_chat_action
        original_send_typing = handler._send_typing_action
        
        async def send_typing_with_bot(chat_id):
            """Send typing action using the bot"""
            if self._running and self.bot:
                try:
                    await self.bot.send_chat_action(chat_id, "typing")
                except Exception as e:
                    logger.warning(f"Could not send typing action: {e}")
                    # Fall back to original implementation
                    await original_send_typing(chat_id)
        
        # Replace the method
        handler._send_typing_action = send_typing_with_bot
    
    async def add_to_chat(self, chat_id):
        """
        Add the bot to a chat (this can only be done by the user manually)
        We can only provide instructions
        """
        bot_username = self.config.get("bot_username")
        if not bot_username:
            logger.error("No bot username available")
            return False
        
        try:
            # Send a message with instructions to add the bot
            instructions = f"""
            To use chat insights features, please add the bot @{bot_username} to this chat.
            
            Steps:
            1. Open this chat in Telegram
            2. Click the chat name/title at the top
            3. Select "Add members"
            4. Search for @{bot_username}
            5. Select the bot and add it
            
            Once added, you can use /askgem commands or simply ask questions to the bot.
            Example: `/askgem Who talked about API yesterday?`
            """
            
            # Get the SilentGem client to send this message
            from silentgem.client import get_client
            client = get_client()
            
            # Send instructions
            await client.send_message(
                chat_id=chat_id,
                text=instructions.strip()
            )
            
            logger.info(f"Sent instructions to add bot to chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending bot add instructions: {e}")
            return False


# Singleton instance
_instance = None

def get_insights_bot():
    """Get the insights bot singleton instance"""
    global _instance
    if _instance is None:
        try:
            _instance = InsightsBot()
        except Exception as e:
            logger.error(f"Error creating insights bot: {e}")
            raise
    return _instance 