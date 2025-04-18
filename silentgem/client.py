"""
Telegram client for SilentGem
"""

import asyncio
from pathlib import Path
from pyrogram import Client, filters, types, errors
from loguru import logger
import sqlite3
import time

from silentgem.config import API_ID, API_HASH, SESSION_NAME, load_mapping, TARGET_LANGUAGE, LLM_ENGINE
from silentgem.translator import create_translator
from silentgem.mapper import ChatMapper

class SilentGemClient:
    """Telegram userbot client for monitoring and translating messages"""
    
    def __init__(self):
        """Initialize the client and translator"""
        print("\n🔧 Initializing SilentGem client...")
        self.client = Client(
            SESSION_NAME,
            api_id=API_ID,
            api_hash=API_HASH,
            workdir=str(Path("."))
        )
        print("✅ Telegram client initialized")
        
        print(f"🔧 Initializing translator (using {LLM_ENGINE})...")
        try:
            self.translator = create_translator()
            print("✅ Translator initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize translator: {e}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")
            raise
        
        # Initialize chat mapper for state tracking
        self.mapper = ChatMapper()
        self.chat_mapping = {}
        
        # Store tasks to properly cancel them during shutdown
        self._tasks = {}
        
        logger.info("SilentGem client initialized")
    
    async def start(self):
        """Start the client and register handlers"""
        # Load the chat mapping
        self.chat_mapping = self.mapper.get_all()
        if not self.chat_mapping:
            logger.warning("No chat mappings loaded, the bot won't translate any messages")
            print("\n⚠️ WARNING: No chat mappings found. The translator won't process any messages.")
            print("Please set up chat mappings first using the setup wizard or option 3 in the main menu.")
        else:
            logger.info(f"Loaded {len(self.chat_mapping)} chat mappings")
            print(f"\n✅ Loaded {len(self.chat_mapping)} chat mappings")
            print("Monitoring the following source chats:")
            for source_id in self.chat_mapping.keys():
                print(f" - Chat ID: {source_id} → Target: {self.chat_mapping[source_id]}")
        
        # Set up error handler - must accept client parameter
        @self.client.on_disconnect()
        async def on_disconnect(client):
            logger.warning("Client disconnected. Will attempt to reconnect.")
            print("\n⚠️ Telegram client disconnected. Attempting to reconnect...")
        
        # Start the client with error handling
        try:
            await self.client.start()
            me = await self.client.get_me()
            logger.info(f"Started as {me.first_name} ({me.id})")
            print(f"\n✅ Connected to Telegram as {me.first_name} ({me.id})")
            print("Waiting for messages to translate... (Press Ctrl+C to stop)")
            
            # Start heartbeat to show the client is alive
            self._tasks['heartbeat'] = asyncio.create_task(self._heartbeat())
            
            # Convert chat mapping keys to integers if they're stored as strings
            chat_ids_to_monitor = []
            for chat_id in self.chat_mapping.keys():
                try:
                    # Try to convert to int if it's a string
                    chat_ids_to_monitor.append(int(chat_id))
                    print(f"✅ Added chat ID {chat_id} to monitoring list")
                except ValueError:
                    print(f"⚠️ Warning: Invalid chat ID format: {chat_id}")
                    
            if not chat_ids_to_monitor:
                print("⚠️ Warning: No valid chat IDs to monitor")
            else:
                print(f"✅ Monitoring {len(chat_ids_to_monitor)} chats: {chat_ids_to_monitor}")
            
            # Register targeted message handler with verbose logging
            @self.client.on_message(filters.chat(chat_ids_to_monitor))
            async def on_message(client, message):
                try:
                    print(f"\n📩 Received message from chat {message.chat.id} ({message.chat.title if hasattr(message.chat, 'title') else 'Private'})")
                    print(f"💬 Message content: {message.text or message.caption or '[No text content]'}")
                    print(f"🔗 Chat mapping for this chat: {self.chat_mapping.get(str(message.chat.id), 'Not found')}")
                    
                    if str(message.chat.id) in self.chat_mapping:
                        print(f"✅ Found chat ID {message.chat.id} in mappings, processing message")
                        await self._handle_message(message)
                    else:
                        print(f"⚠️ Chat ID {message.chat.id} not found in mappings, this message should have been filtered out")
                except Exception as e:
                    print(f"❌ Error in message handler: {e}")
                    logger.error(f"Error in message handler: {e}")
                    import traceback
                    print(f"❌ Traceback: {traceback.format_exc()}")
            
            # Start syncing missed messages
            self._tasks['sync'] = asyncio.create_task(self._sync_missed_messages())
            
            # Add active message polling as a fallback to event handlers
            self._tasks['polling'] = asyncio.create_task(self._active_message_polling())
            
            # Keep the client running
            await self._idle()
        except sqlite3.ProgrammingError as e:
            if "Cannot operate on a closed database" in str(e):
                logger.error("Database connection closed unexpectedly. Please restart the application.")
                logger.error("You can run 'python silentgem.py --cleanup' to fix database issues.")
                print("\n❌ Database error: Connection closed unexpectedly")
                print("Please run 'python silentgem.py --cleanup' to fix this issue")
                # Signal shutdown 
                if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
                    self._shutdown_future.set_result(None)
            else:
                raise
        except errors.RPCError as e:
            error_message = str(e).lower()
            if "migrate" in error_message or "phone_migrate" in error_message:
                logger.error(f"Telegram datacenter migration required: {e}")
                logger.error("Please run 'python silentgem.py --cleanup' and then restart the application")
                print(f"\n❌ Telegram error: {e}")
                print("Please run 'python silentgem.py --cleanup' and then restart")
                if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
                    self._shutdown_future.set_result(None)
            elif "flood" in error_message:
                logger.error(f"Telegram rate limit exceeded: {e}")
                logger.error("Please wait before trying again")
                print(f"\n❌ Telegram rate limit exceeded: {e}")
                print("Please wait before trying again")
                if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
                    self._shutdown_future.set_result(None)
            else:
                logger.error(f"Telegram RPC error: {e}")
                print(f"\n❌ Telegram error: {e}")
                if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
                    self._shutdown_future.set_result(None)
        except Exception as e:
            logger.error(f"Error starting client: {e}")
            print(f"\n❌ Error: {e}")
            # Signal shutdown
            if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
                self._shutdown_future.set_result(None)
    
    async def _handle_message(self, message):
        """Handle incoming messages from monitored chats"""
        try:
            # Update the last time we received a message through event handlers
            # This helps our polling system adapt its frequency
            if hasattr(self, 'client') and message._client == self.client:
                self._last_event_message_time = time.time()
            
            # Ensure chat_id is a string for consistent lookup
            chat_id = str(message.chat.id)
            logger.debug(f"Received message in chat {chat_id}: {message.text[:50] if message.text else ''}")
            print(f"🔄 Processing message from chat {chat_id}")
            
            # Debug mapping keys for troubleshooting
            print(f"🔍 Available mapping keys: {list(self.chat_mapping.keys())}")
            print(f"🔍 Chat ID type: {type(chat_id)}, Value: {chat_id}")
            
            # Check if this chat is in our mapping - try both string and int formats
            if chat_id in self.chat_mapping:
                target_chat_id = self.chat_mapping[chat_id]
                print(f"✅ Found target using string key: {target_chat_id}")
            elif chat_id.lstrip('-').isdigit() and str(int(chat_id)) in self.chat_mapping:
                # Try with normalized integer conversion
                target_chat_id = self.chat_mapping[str(int(chat_id))]
                print(f"✅ Found target using normalized integer key: {target_chat_id}")
            else:
                logger.debug(f"Chat {chat_id} not in mapping, ignoring")
                print(f"❌ Chat {chat_id} not in mapping, ignoring")
                print(f"❌ Available keys: {list(self.chat_mapping.keys())}")
                return
            
            logger.info(f"Processing message from {chat_id} to {target_chat_id}")
            print(f"✅ Found target chat {target_chat_id} for source chat {chat_id}")
            
            # Get sender information
            sender_name = "Unknown"
            if message.from_user:
                sender_name = message.from_user.first_name
                if message.from_user.last_name:
                    sender_name += f" {message.from_user.last_name}"
                if message.from_user.username:
                    sender_name += f" (@{message.from_user.username})"
            
            print(f"👤 Sender: {sender_name}")
            
            # Check message type
            media_type = None
            if message.photo:
                media_type = "photo"
                print("📷 Message contains a photo")
            elif message.video:
                media_type = "video"
                print("🎥 Message contains a video")
            elif message.document:
                media_type = "document"
                print("📎 Message contains a document")
            elif message.animation:
                media_type = "animation"
                print("🎬 Message contains an animation/GIF")
            elif message.sticker:
                media_type = "sticker"
                print("🎭 Message contains a sticker")
                
            # Extract content based on message type
            if not message.text and not message.caption:
                if media_type:
                    print(f"🖼️ Media message ({media_type}) without caption, forwarding without translation")
                    # Just forward media with a note about the sender
                    try:
                        if media_type == "photo":
                            await self.client.send_photo(
                                chat_id=target_chat_id,
                                photo=message.photo.file_id,
                                caption=f"📷 Photo from {sender_name}"
                            )
                        elif media_type == "video":
                            await self.client.send_video(
                                chat_id=target_chat_id,
                                video=message.video.file_id,
                                caption=f"🎥 Video from {sender_name}"
                            )
                        elif media_type == "document":
                            await self.client.send_document(
                                chat_id=target_chat_id,
                                document=message.document.file_id,
                                caption=f"📎 Document from {sender_name}"
                            )
                        elif media_type == "animation":
                            await self.client.send_animation(
                                chat_id=target_chat_id,
                                animation=message.animation.file_id,
                                caption=f"🎬 Animation from {sender_name}"
                            )
                        elif media_type == "sticker":
                            await self.client.send_sticker(
                                chat_id=target_chat_id,
                                sticker=message.sticker.file_id
                            )
                            # Stickers can't have captions, so send a follow-up message
                            await self.client.send_message(
                                chat_id=target_chat_id,
                                text=f"🎭 Sticker from {sender_name}"
                            )
                        print(f"✅ Media forwarded to {target_chat_id}")
                    except Exception as e:
                        print(f"❌ Failed to forward media: {e}")
                    
                    # UPDATE: Track message ID for media-only messages too
                    self.mapper.update_last_message_id(chat_id, message.id)
                    print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
                    return
                else:
                    logger.debug("Message has no text or caption, ignoring")
                    print("❌ Message has no text or caption, ignoring")
                    
                    # UPDATE: Still track the message ID even if it has no content
                    self.mapper.update_last_message_id(chat_id, message.id)
                    print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
                    return
            
            text = message.text or message.caption
            print(f"📝 Extracted text ({len(text)} chars): {text[:100]}...")
            
            # Skip if the message is too short (likely to be a reaction or emoji)
            if len(text) < 5:
                print("❌ Message too short, likely an emoji or reaction, skipping")
                if media_type:
                    print(f"🖼️ But message contains media ({media_type}), will forward that")
                    try:
                        if media_type == "photo":
                            await self.client.send_photo(
                                chat_id=target_chat_id,
                                photo=message.photo.file_id,
                                caption=f"📷 Photo from {sender_name}"
                            )
                        elif media_type == "video":
                            await self.client.send_video(
                                chat_id=target_chat_id,
                                video=message.video.file_id,
                                caption=f"🎥 Video from {sender_name}"
                            )
                        elif media_type == "document":
                            await self.client.send_document(
                                chat_id=target_chat_id,
                                document=message.document.file_id,
                                caption=f"📎 Document from {sender_name}"
                            )
                        elif media_type == "animation":
                            await self.client.send_animation(
                                chat_id=target_chat_id,
                                animation=message.animation.file_id,
                                caption=f"🎬 Animation from {sender_name}"
                            )
                        elif media_type == "sticker":
                            await self.client.send_sticker(
                                chat_id=target_chat_id,
                                sticker=message.sticker.file_id
                            )
                            # Stickers can't have captions, so send a follow-up message
                            await self.client.send_message(
                                chat_id=target_chat_id,
                                text=f"🎭 Sticker from {sender_name}"
                            )
                        print(f"✅ Media forwarded to {target_chat_id}")
                    except Exception as e:
                        print(f"❌ Failed to forward media: {e}")
                
                # UPDATE: Always track message ID
                self.mapper.update_last_message_id(chat_id, message.id)
                print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
                return
            
            # Detect if the message is likely in English already
            # This is a simple heuristic - it might need improvement
            english_words = {'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'I', 'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at'}
            words = set(text.lower().split())
            likely_english = len(words.intersection(english_words)) >= 4 and TARGET_LANGUAGE.lower() == 'english'
            
            if likely_english:
                print("🇬🇧 Message appears to be in English already and target is English, skipping translation")
                # Optionally, still forward message but with a note that it's original 
                formatted_message = f"🔠 Original (English) from {sender_name}:\n\n{text}"
                
                if media_type:
                    # Forward media with original caption
                    if media_type == "photo":
                        await self.client.send_photo(
                            chat_id=target_chat_id,
                            photo=message.photo.file_id,
                            caption=formatted_message
                        )
                    elif media_type == "video":
                        await self.client.send_video(
                            chat_id=target_chat_id,
                            video=message.video.file_id,
                            caption=formatted_message
                        )
                    elif media_type == "document":
                        await self.client.send_document(
                            chat_id=target_chat_id,
                            document=message.document.file_id,
                            caption=formatted_message
                        )
                    elif media_type == "animation":
                        await self.client.send_animation(
                            chat_id=target_chat_id,
                            animation=message.animation.file_id,
                            caption=formatted_message
                        )
                    elif media_type == "sticker":
                        # Stickers can't have captions, so send sticker followed by message
                        await self.client.send_sticker(
                            chat_id=target_chat_id,
                            sticker=message.sticker.file_id
                        )
                        await self.client.send_message(
                            chat_id=target_chat_id,
                            text=formatted_message
                        )
                else:
                    # Just a text message
                    await self.client.send_message(
                        chat_id=target_chat_id,
                        text=formatted_message,
                        disable_web_page_preview=True,
                    )
                print(f"✅ Original message forwarded to {target_chat_id}")
                
                # UPDATE: Track message ID for skipped translations too
                self.mapper.update_last_message_id(chat_id, message.id)
                print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
                return
            
            # Translate the text
            logger.debug(f"Translating text: {text[:50]}...")
            print(f"🧠 Sending to Gemini for translation...")
            translated_text = await self.translator.translate(text)
            logger.info(f"Translation complete: {translated_text[:50]}...")
            print(f"✅ Translation received: {translated_text[:100]}...")
            
            # Format message with sender info
            formatted_message = f"🔄 Translated from {sender_name}:\n\n{translated_text}"
            
            # Send to target channel - handle differently based on media type
            try:
                print(f"📤 Sending translation to target chat {target_chat_id}...")
                
                if media_type:
                    # Forward media with translated caption
                    if media_type == "photo":
                        await self.client.send_photo(
                            chat_id=target_chat_id,
                            photo=message.photo.file_id,
                            caption=formatted_message
                        )
                    elif media_type == "video":
                        await self.client.send_video(
                            chat_id=target_chat_id,
                            video=message.video.file_id,
                            caption=formatted_message
                        )
                    elif media_type == "document":
                        await self.client.send_document(
                            chat_id=target_chat_id,
                            document=message.document.file_id,
                            caption=formatted_message
                        )
                    elif media_type == "animation":
                        await self.client.send_animation(
                            chat_id=target_chat_id,
                            animation=message.animation.file_id,
                            caption=formatted_message
                        )
                    elif media_type == "sticker":
                        # Stickers can't have captions, so send sticker followed by translation
                        await self.client.send_sticker(
                            chat_id=target_chat_id,
                            sticker=message.sticker.file_id
                        )
                        await self.client.send_message(
                            chat_id=target_chat_id,
                            text=formatted_message
                        )
                else:
                    # Just a text message
                    await self.client.send_message(
                        chat_id=target_chat_id,
                        text=formatted_message,
                        disable_web_page_preview=True,
                    )
                    
                logger.info(f"Translation sent to {target_chat_id}")
                print(f"✅ Translation sent to {target_chat_id}")
            except Exception as e:
                logger.error(f"Failed to send message to {target_chat_id}: {e}")
                print(f"❌ Failed to send message to {target_chat_id}: {e}")
        
            # Update message ID in state tracker after successful processing
            self.mapper.update_last_message_id(chat_id, message.id)
            print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            print(f"❌ Error handling message: {e}")
            
            # Even if there's an error, try to update the message ID to avoid reprocessing
            try:
                self.mapper.update_last_message_id(str(message.chat.id), message.id)
                print(f"✅ Updated message ID to {message.id} despite error (to avoid reprocessing)")
            except Exception as err:
                print(f"❌ Failed to update message ID after error: {err}")
    
    async def _idle(self):
        """Keep the client running until stopped"""
        self._running = True
        self._shutdown_future = asyncio.Future()
        
        try:
            # Wait for shutdown signal with frequent checks
            while True:
                if self._shutdown_future.done():
                    break
                    
                # Check every 50ms for more responsive shutdown
                await asyncio.sleep(0.05)
                
                # Also directly check for external shutdown signals
                if hasattr(self, '_force_shutdown') and self._force_shutdown:
                    print("🛑 Force shutdown detected in idle loop")
                    break
        except asyncio.CancelledError:
            logger.info("Client task cancelled")
        except Exception as e:
            logger.error(f"Error in idle loop: {e}")
        finally:
            # Make sure we're fully stopped
            self._running = False
            # Ensure future is done if we broke out via direct check
            if not self._shutdown_future.done():
                self._shutdown_future.set_result(None)
            logger.info("Client idle loop complete")
    
    async def stop(self):
        """Stop the client and cancel all tasks."""
        print("\n⏹️ Stopping SilentGem client...")
        logger.info("Stopping SilentGem client")
        
        # CRITICAL: First thing, set running to False to stop all background tasks
        self._running = False
        
        # Ensure the shutdown future is set
        if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
            logger.info("Setting shutdown future")
            self._shutdown_future.set_result(None)
        
        # Check if force shutdown was requested from main process
        if hasattr(self, '_force_shutdown') and self._force_shutdown:
            logger.warning("Force shutdown requested - cancelling all tasks immediately")
            print("⚠️ Force shutdown mode - cancelling all tasks immediately")
        
        # Cancel all background tasks with a short timeout
        tasks_cancelled = 0
        for task_name, task in list(self._tasks.items()):
            if not task.done():
                print(f"📉 Cancelling task: {task_name}")
                task.cancel()
                tasks_cancelled += 1
                
                try:
                    # Very short timeout for each task to avoid hanging
                    await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    # Expected exceptions during cancellation
                    pass
                except Exception as e:
                    logger.error(f"Error waiting for task {task_name} to cancel: {e}")
        
        print(f"📉 Cancelled {tasks_cancelled} background tasks")
        self._tasks.clear()

        # Try to stop the Telegram client with reduced timeout to avoid hangs
        if hasattr(self, 'client'):
            try:
                logger.info("Stopping Telegram client connection")
                await asyncio.wait_for(self.client.stop(), timeout=1.5)
                logger.info("Telegram client stopped successfully")
                print("✅ Telegram client stopped successfully")
            except asyncio.TimeoutError:
                logger.warning("Telegram client stop timed out, but shutdown will continue")
                print("⚠️ Telegram client disconnect timed out, but shutdown will continue")
            except Exception as e:
                logger.error(f"Error stopping Telegram client: {e}")
                print(f"⚠️ Error stopping Telegram client: {e}")
        
        logger.info("SilentGem client stopped")
        print("✅ SilentGem client stopped")
    
    async def _heartbeat(self):
        """Periodically log a heartbeat to show the client is still running"""
        try:
            count = 0
            while hasattr(self, '_running') and self._running:
                await asyncio.sleep(60)  # Every minute
                count += 1
                print(f"\n💓 Heartbeat #{count}: SilentGem is running and listening for messages")
                
                # Every 5 minutes, print chat mappings to verify they're still correct
                if count % 5 == 0:
                    print(f"🔄 Active chat mappings ({len(self.chat_mapping)}):")
                    for source_id, target_id in self.chat_mapping.items():
                        print(f" - Source: {source_id} → Target: {target_id}")
                    
                    # Also verify we can access one of the source chats (take the first one)
                    if self.chat_mapping:
                        try:
                            first_source = list(self.chat_mapping.keys())[0]
                            chat = await self.client.get_chat(first_source)
                        except Exception as e:
                            print(f"⚠️ Warning: Could not access source chat {first_source}: {e}")
        except asyncio.CancelledError:
            print("💓 Heartbeat stopped")
        except Exception as e:
            print(f"❌ Error in heartbeat: {e}")
            
    async def _sync_missed_messages(self):
        """Sync any messages that might have been missed while offline"""
        try:
            # Wait a moment to let everything initialize, but check if we're shutting down first
            for _ in range(15):
                if not hasattr(self, '_running') or not self._running:
                    print("💤 Message sync cancelled - shutdown in progress")
                    return
                await asyncio.sleep(1)
            
            # Check again before proceeding with any work
            if not hasattr(self, '_running') or not self._running:
                print("💤 Message sync cancelled - shutdown in progress")
                return
                
            print("\n🔄 Checking for missed messages since last run...")
            
            for source_id in self.chat_mapping.keys():
                # Check for shutdown in each iteration
                if not hasattr(self, '_running') or not self._running:
                    print("💤 Message sync cancelled - shutdown in progress")
                    return
                    
                try:
                    # Get the last processed message ID for this chat
                    last_message_id = self.mapper.get_last_message_id(source_id)
                    
                    if last_message_id > 0:
                        print(f"🔍 Last processed message ID for chat {source_id}: {last_message_id}")
                        
                        # Get messages newer than the last processed ID
                        missed_messages = []
                        async for msg in self.client.get_chat_history(source_id, limit=20):
                            if not hasattr(self, '_running') or not self._running:
                                print("💤 Message history retrieval cancelled - shutdown in progress")
                                return
                            if msg.id > last_message_id:
                                missed_messages.append(msg)
                            else:
                                break  # No need to check older messages
                        
                        missed_messages.reverse()  # Process oldest first
                        
                        if missed_messages:
                            print(f"🔄 Found {len(missed_messages)} missed messages to process in chat {source_id}")
                            
                            for idx, msg in enumerate(missed_messages):
                                # Check for shutdown before each message processing
                                if not hasattr(self, '_running') or not self._running:
                                    print("💤 Message processing cancelled - shutdown in progress")
                                    return
                                print(f"🔄 Processing missed message {idx+1}/{len(missed_messages)} (ID: {msg.id})")
                                await self._handle_message(msg)
                        else:
                            print(f"✅ No missed messages in chat {source_id}")
                    else:
                        print(f"ℹ️ No previous message state for chat {source_id}, starting fresh")
                        
                        # Just mark the latest message as processed so we don't translate old history
                        messages = []
                        async for msg in self.client.get_chat_history(source_id, limit=1):
                            if not hasattr(self, '_running') or not self._running:
                                print("💤 History retrieval cancelled - shutdown in progress")
                                return
                            messages.append(msg)
                        
                        if messages:
                            latest_id = messages[0].id
                            self.mapper.update_last_message_id(source_id, latest_id)
                            print(f"✅ Initialized message tracking at ID {latest_id} for chat {source_id}")
                        else:
                            print(f"ℹ️ No messages found in chat {source_id}")
                            
                except Exception as e:
                    print(f"❌ Error syncing messages for chat {source_id}: {e}")
                    logger.error(f"Error syncing messages for chat {source_id}: {e}")
            
            print("✅ Message sync complete")
            
        except asyncio.CancelledError:
            print("🔄 Message sync cancelled")
            raise
        except Exception as e:
            print(f"❌ Error in message sync: {e}")
            logger.error(f"Error in message sync: {e}")

    async def _active_message_polling(self):
        """Actively poll for new messages in case event handlers aren't working"""
        try:
            # Wait a moment to let everything initialize but check shutdown flag repeatedly
            for _ in range(20):
                if not hasattr(self, '_running') or not self._running:
                    print("💤 Message polling cancelled - shutdown in progress")
                    return
                await asyncio.sleep(1)
            
            # Check again before proceeding with any work
            if not hasattr(self, '_running') or not self._running:
                print("💤 Message polling cancelled - shutdown in progress")
                return
                
            print("\n🔄 Starting active message polling as a fallback mechanism...")
            
            # Track last time we received a message through the event handler
            # Initialize with a property if it doesn't exist
            if not hasattr(self, '_last_event_message_time'):
                self._last_event_message_time = 0
            
            # Now continuously poll for new messages, using the message state tracker
            poll_count = 0
            # Start with a longer polling interval to reduce network traffic
            polling_interval = 30  # 30 seconds between polls
            
            while hasattr(self, '_running') and self._running:
                poll_count += 1
                if poll_count % 10 == 0:  # Only log every 10 polls to reduce spam
                    print(f"\n🔄 Active polling cycle #{poll_count}")
                
                # Check if we've received messages through event handlers recently
                # If yes, we can poll less frequently
                time_since_last_event = time.time() - self._last_event_message_time
                
                # If we've received a message via event handler in the last 5 minutes,
                # we can reduce polling frequency
                if self._last_event_message_time > 0 and time_since_last_event < 300:  # 5 minutes
                    # Event handlers seem to be working, use longer interval
                    polling_interval = 60  # 60 seconds
                    if poll_count % 10 == 0:
                        print(f"ℹ️ Event handlers active, using reduced polling frequency")
                else:
                    # No recent messages through event handlers, be more aggressive with polling
                    polling_interval = 30  # 30 seconds
                    if poll_count % 10 == 0 and self._last_event_message_time > 0:
                        print(f"ℹ️ No recent events, using standard polling frequency")
                
                for source_id in self.chat_mapping.keys():
                    # Check for shutdown before each chat processing
                    if not hasattr(self, '_running') or not self._running:
                        print("💤 Polling cancelled - shutdown in progress")
                        return
                        
                    try:
                        # Get the last processed message ID
                        last_message_id = self.mapper.get_last_message_id(source_id)
                        
                        # Get latest messages
                        new_messages = []
                        async for msg in self.client.get_chat_history(source_id, limit=5):
                            if not hasattr(self, '_running') or not self._running:
                                print("💤 History retrieval cancelled - shutdown in progress")
                                return
                            if msg.id > last_message_id:
                                new_messages.append(msg)
                            else:
                                break  # No need to continue once we hit previously seen messages
                        
                        # Process new messages in chronological order (oldest first)
                        if new_messages:
                            print(f"\n✅ Found {len(new_messages)} new messages in chat {source_id}")
                            new_messages.reverse()  # Reverse to process oldest first
                            
                            for msg in new_messages:
                                # Check for shutdown before processing each message
                                if not hasattr(self, '_running') or not self._running:
                                    print("💤 Message processing cancelled - shutdown in progress")
                                    return
                                print(f"📥 Processing new message {msg.id} from active polling")
                                await self._handle_message(msg)
                    except Exception as e:
                        if poll_count % 10 == 0:  # Only log errors every 10 polls
                            print(f"❌ Error polling chat {source_id}: {e}")
                
                # Sleep between polling cycles with frequent shutdown checks
                # Use our adaptive polling interval, but still check frequently for shutdown
                sleep_interval = 1  # Check for shutdown every second
                for _ in range(polling_interval):
                    if not hasattr(self, '_running') or not self._running:
                        return
                    await asyncio.sleep(sleep_interval)
                
        except asyncio.CancelledError:
            print("🔄 Active message polling stopped")
            raise
        except Exception as e:
            print(f"❌ Error in active message polling: {e}")
            logger.error(f"Error in active message polling: {e}") 