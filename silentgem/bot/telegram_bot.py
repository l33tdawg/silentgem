"""
Telegram bot implementation for SilentGem Chat Insights
"""

import os
import time
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
        
        # Shutdown event
        self.shutdown_event = asyncio.Event()
    
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
            
            # Initialize command handler with bot reference
            from silentgem.bot.command_handler import get_command_handler
            self.command_handler = get_command_handler(bot=self.bot, shutdown_event=self.shutdown_event)
            
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
    
    def _truncate_text(self, text, max_length):
        """
        Truncate text at word boundary for better readability
        
        Args:
            text: Text to truncate
            max_length: Maximum length
            
        Returns:
            Truncated text with ellipsis if needed
        """
        if len(text) <= max_length:
            return text
        
        # Find the last space before max_length
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length * 0.7:  # Only use space if it's not too far back
            truncated = truncated[:last_space]
        
        return truncated.rstrip('.,!?;:') + '...'
    
    def _create_inline_keyboard(self, suggestions):
        """
        Create an inline keyboard from guided query suggestions
        
        Args:
            suggestions: GuidedQuerySuggestions object
            
        Returns:
            InlineKeyboardMarkup or None if no suggestions
        """
        if not suggestions:
            return None
        
        keyboard = []
        
        # Add follow-up question buttons (max 3)
        # Use longer limit and smart truncation for better clarity
        for i, question in enumerate(suggestions.follow_up_questions[:3], 1):
            # Format: "1. Question text..."
            button_text = f"{i}. {self._truncate_text(question.question, 95)}"
            keyboard.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"suggest:{i-1}"  # Zero-indexed for array access
                )
            ])
        
        # Add expandable topic buttons (if any)
        for topic in suggestions.expandable_topics[:2]:  # Max 2 topics to avoid clutter
            topic_text = f"📖 {self._truncate_text(topic.label, 90)}"
            keyboard.append([
                InlineKeyboardButton(
                    text=topic_text,
                    callback_data=f"expand:{topic.id}"
                )
            ])
        
        # Add action buttons in a row (max 2 per row)
        action_row = []
        for button in suggestions.action_buttons[:4]:  # Max 4 action buttons
            action_row.append(
                InlineKeyboardButton(
                    text=button.label,
                    callback_data=button.callback_data
                )
            )
            # Add row every 2 buttons
            if len(action_row) == 2:
                keyboard.append(action_row)
                action_row = []
        
        # Add remaining action buttons if any
        if action_row:
            keyboard.append(action_row)
        
        return InlineKeyboardMarkup(keyboard) if keyboard else None
    
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
                    
                    # Check if guided queries are enabled
                    enable_guided = self.config.get("enable_guided_queries", True)
                    
                    # Use new interface with guided queries
                    response, suggestions = await self.command_handler.handle_query_with_suggestions(
                        query=query,
                        chat_id=str(message.chat.id),
                        user_id=str(message.from_user.id) if message.from_user else None,
                        verbosity=verbosity,
                        enable_guided_queries=enable_guided
                    )
                    
                    # Store suggestions for this user (for callback handling)
                    if suggestions:
                        user_key = f"{message.chat.id}:{message.from_user.id if message.from_user else 'unknown'}"
                        if not hasattr(self, '_user_suggestions'):
                            self._user_suggestions = {}
                        self._user_suggestions[user_key] = {
                            'suggestions': suggestions,
                            'original_query': query,
                            'timestamp': time.time()
                        }
                    
                    # Create inline keyboard from suggestions
                    reply_markup = self._create_inline_keyboard(suggestions) if suggestions else None
                    
                    # Send the response with buttons
                    await message.reply(response, quote=True, reply_markup=reply_markup)
                else:
                    await message.reply("Please provide a query with the command.\nExample: `/askgem Who talked about API yesterday?`", quote=True)
            else:
                await message.reply("Query processing is not available right now. Please try again later.", quote=True)
        
        # Handle regular messages (treat as queries if not a command)
        @self.bot.on_message(filters.text & (~filters.command("")))
        async def message_handler(client, message):
            """Handle regular messages as queries"""
            # Ignore translated messages and other SilentGem outputs
            if message.text:
                # Skip processing various SilentGem outputs
                silentgem_patterns = [
                    "🔄 Translated from", 
                    "📷 Photo from",
                    "🎥 Video from",
                    "📎 Document from",
                    "🎬 Animation from",
                    "🎭 Sticker from",
                    "🔠 Original (English) from"
                ]
                
                for pattern in silentgem_patterns:
                    if message.text.startswith(pattern):
                        # Skip processing SilentGem generated messages
                        return
                
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
                
                # Check if guided queries are enabled
                enable_guided = self.config.get("enable_guided_queries", True)
                
                # Use new interface with guided queries
                response, suggestions = await self.command_handler.handle_query_with_suggestions(
                    query=message.text,
                    chat_id=str(message.chat.id),
                    user_id=str(message.from_user.id) if message.from_user else None,
                    verbosity=verbosity,
                    enable_guided_queries=enable_guided
                )
                
                # Store suggestions for this user (for callback handling)
                if suggestions:
                    user_key = f"{message.chat.id}:{message.from_user.id if message.from_user else 'unknown'}"
                    if not hasattr(self, '_user_suggestions'):
                        self._user_suggestions = {}
                    self._user_suggestions[user_key] = {
                        'suggestions': suggestions,
                        'original_query': message.text,
                        'timestamp': time.time()
                    }
                
                # Create inline keyboard from suggestions
                reply_markup = self._create_inline_keyboard(suggestions) if suggestions else None
                
                # Send the response with buttons
                await message.reply(response, quote=True, reply_markup=reply_markup)
        
        # Handle callback queries (button clicks)
        @self.bot.on_callback_query()
        async def callback_query_handler(client, callback_query):
            """Handle button clicks from inline keyboards"""
            try:
                data = callback_query.data
                user_key = f"{callback_query.message.chat.id}:{callback_query.from_user.id}"
                
                # Get stored suggestions for this user
                user_data = getattr(self, '_user_suggestions', {}).get(user_key)
                
                if not user_data:
                    await callback_query.answer("Sorry, this session has expired. Please ask a new question.", show_alert=True)
                    return
                
                suggestions = user_data['suggestions']
                
                # Answer the callback to remove loading state
                await callback_query.answer()
                
                # Handle different callback types
                if data.startswith("suggest:"):
                    # User clicked a suggested follow-up question
                    question_index = int(data.split(":")[1])
                    
                    if question_index < len(suggestions.follow_up_questions):
                        suggested_question = suggestions.follow_up_questions[question_index].question
                        
                        # Process the suggested question as a new query
                        verbosity = self.config.get("response_verbosity", "standard")
                        enable_guided = self.config.get("enable_guided_queries", True)
                        
                        # Show thinking message
                        thinking_msg = await callback_query.message.reply(
                            f"🔍 {suggested_question}\n\n⏳ Searching..."
                        )
                        
                        response, new_suggestions = await self.command_handler.handle_query_with_suggestions(
                            query=suggested_question,
                            chat_id=str(callback_query.message.chat.id),
                            user_id=str(callback_query.from_user.id),
                            verbosity=verbosity,
                            enable_guided_queries=enable_guided
                        )
                        
                        # Update stored suggestions
                        if new_suggestions:
                            user_data['suggestions'] = new_suggestions
                            user_data['original_query'] = suggested_question
                            user_data['timestamp'] = time.time()
                        
                        # Delete thinking message
                        await thinking_msg.delete()
                        
                        # Create keyboard for new suggestions
                        reply_markup = self._create_inline_keyboard(new_suggestions) if new_suggestions else None
                        
                        # Send the new response
                        await callback_query.message.reply(
                            f"🔍 {suggested_question}\n\n{response}",
                            reply_markup=reply_markup
                        )
                    
                elif data.startswith("expand:"):
                    # User wants to expand a specific topic
                    topic_id = data.split(":", 1)[1]
                    
                    # Find the topic in suggestions
                    topic = None
                    for t in suggestions.expandable_topics:
                        if t.id == topic_id:
                            topic = t
                            break
                    
                    if topic:
                        # Create a more detailed query about this topic
                        expanded_query = f"Tell me more about {topic.label}"
                        
                        # Show thinking message
                        thinking_msg = await callback_query.message.reply(
                            f"📖 Expanding: {topic.label}\n\n⏳ Gathering details..."
                        )
                        
                        verbosity = "detailed"  # Use detailed verbosity for expansion
                        enable_guided = self.config.get("enable_guided_queries", True)
                        
                        response, new_suggestions = await self.command_handler.handle_query_with_suggestions(
                            query=expanded_query,
                            chat_id=str(callback_query.message.chat.id),
                            user_id=str(callback_query.from_user.id),
                            verbosity=verbosity,
                            enable_guided_queries=enable_guided
                        )
                        
                        # Delete thinking message
                        await thinking_msg.delete()
                        
                        # Create keyboard for new suggestions
                        reply_markup = self._create_inline_keyboard(new_suggestions) if new_suggestions else None
                        
                        # Send expanded information
                        await callback_query.message.reply(
                            f"📖 {topic.label}\n\n{response}",
                            reply_markup=reply_markup
                        )
                
                elif data.startswith("action:"):
                    # Handle action buttons
                    action_type = data.split(":", 1)[1]
                    
                    if action_type == "timeline":
                        # Show timeline view
                        await callback_query.message.reply(
                            "📅 Timeline view coming soon in v1.6!\n\nThis will show chronological progression of discussions."
                        )
                    
                    elif action_type == "contributors":
                        # Show top contributors
                        original_query = user_data.get('original_query', '')
                        contributors_query = f"Who are the main people discussing {original_query}?"
                        
                        thinking_msg = await callback_query.message.reply("⏳ Analyzing contributors...")
                        
                        response, _ = await self.command_handler.handle_query_with_suggestions(
                            query=contributors_query,
                            chat_id=str(callback_query.message.chat.id),
                            user_id=str(callback_query.from_user.id),
                            verbosity="standard",
                            enable_guided_queries=False
                        )
                        
                        await thinking_msg.delete()
                        await callback_query.message.reply(f"👥 Contributors\n\n{response}")
                    
                    elif action_type == "save_template":
                        # Save query as template (will be implemented in query_templates.py)
                        await callback_query.message.reply(
                            "💾 Query template saving coming soon!\n\nThis will allow you to save and reuse common queries."
                        )
                    
                    elif action_type == "export":
                        # Export results
                        await callback_query.message.reply(
                            "📤 Export functionality coming soon!\n\nThis will allow you to export search results to various formats."
                        )
                    
                    else:
                        await callback_query.answer("Unknown action", show_alert=True)
                
            except Exception as e:
                logger.error(f"Error handling callback query: {e}")
                import traceback
                traceback.print_exc()
                await callback_query.answer("An error occurred processing your request.", show_alert=True)
    
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
            logger.debug(f"Typing action requested for chat_id: {chat_id}")
            # Don't attempt any actual typing action - just silently succeed
            return
        
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