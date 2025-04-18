"""
Telegram client for SilentGem
"""

import asyncio
from pathlib import Path
from pyrogram import Client, filters, types, errors
from loguru import logger
import sqlite3

from silentgem.config import API_ID, API_HASH, SESSION_NAME, load_mapping, TARGET_LANGUAGE
from silentgem.translator import GeminiTranslator
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
        
        print("🔧 Initializing Gemini translator...")
        try:
            self.translator = GeminiTranslator()
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
                    return
                else:
                    logger.debug("Message has no text or caption, ignoring")
                    print("❌ Message has no text or caption, ignoring")
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
    
    async def _idle(self):
        """Keep the client running until stopped"""
        self._running = True
        self._shutdown_future = asyncio.Future()
        
        try:
            await self._shutdown_future
        except asyncio.CancelledError:
            logger.info("Client task cancelled")
        finally:
            self._running = False
    
    async def stop(self):
        """Stop the client gracefully"""
        logger.info("Stopping SilentGem client...")
        print("\n🛑 Stopping translation service...")
        
        # Mark that we're stopping
        self._running = False
        
        # Cancel all background tasks
        if hasattr(self, '_tasks'):
            for name, task in list(self._tasks.items()):
                if not task.done():
                    try:
                        print(f"🛑 Stopping {name} task...")
                        task.cancel()
                        try:
                            await asyncio.wait_for(task, timeout=1)
                        except (asyncio.TimeoutError, asyncio.CancelledError):
                            pass  # Expected during cancellation
                    except Exception as e:
                        print(f"⚠️ Error cancelling {name} task: {e}")
            
            self._tasks.clear()
            print("✅ All background tasks stopped")
        
        # Signal main loop to stop
        if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
            print("🛑 Signaling main loop to stop...")
            self._shutdown_future.set_result(None)
        
        # Stop the Telegram client
        try:
            if hasattr(self, 'client') and self.client.is_connected:
                print("🛑 Stopping Telegram client connection...")
                await asyncio.wait_for(self.client.stop(), timeout=3)
                logger.info("Client stopped successfully")
                print("✅ Telegram client disconnected")
            else:
                logger.info("Client was not running or already stopped")
                print("ℹ️ Telegram client was already disconnected")
        except asyncio.TimeoutError:
            logger.warning("Client stop operation timed out, proceeding anyway")
            print("⚠️ Telegram client disconnect timed out, but we'll continue")
        except Exception as e:
            logger.error(f"Error stopping client: {e}")
            print(f"⚠️ Error disconnecting Telegram: {e}")
        
        print("✅ Translation service stopped")
    
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
                            print(f"✅ Successfully verified access to chat: {chat.title} (ID: {chat.id})")
                        except Exception as e:
                            print(f"⚠️ Warning: Could not access source chat {first_source}: {e}")
        except asyncio.CancelledError:
            print("💓 Heartbeat stopped")
        except Exception as e:
            print(f"❌ Error in heartbeat: {e}")
            
    async def _sync_missed_messages(self):
        """Sync any messages that might have been missed while offline"""
        try:
            # Wait a moment to let everything initialize
            await asyncio.sleep(15)
            
            print("\n🔄 Checking for missed messages since last run...")
            
            for source_id in self.chat_mapping.keys():
                try:
                    # Get the last processed message ID for this chat
                    last_message_id = self.mapper.get_last_message_id(source_id)
                    
                    if last_message_id > 0:
                        print(f"🔍 Last processed message ID for chat {source_id}: {last_message_id}")
                        
                        # Get messages newer than the last processed ID
                        missed_messages = []
                        async for msg in self.client.get_chat_history(source_id, limit=20):
                            if msg.id > last_message_id:
                                missed_messages.append(msg)
                            else:
                                break  # No need to check older messages
                        
                        missed_messages.reverse()  # Process oldest first
                        
                        if missed_messages:
                            print(f"🔄 Found {len(missed_messages)} missed messages to process in chat {source_id}")
                            
                            for idx, msg in enumerate(missed_messages):
                                print(f"🔄 Processing missed message {idx+1}/{len(missed_messages)} (ID: {msg.id})")
                                await self._handle_message(msg)
                        else:
                            print(f"✅ No missed messages in chat {source_id}")
                    else:
                        print(f"ℹ️ No previous message state for chat {source_id}, starting fresh")
                        
                        # Just mark the latest message as processed so we don't translate old history
                        messages = []
                        async for msg in self.client.get_chat_history(source_id, limit=1):
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
            # Wait a moment to let everything initialize
            await asyncio.sleep(20)  # Wait longer to ensure sync completes first
            
            print("\n🔄 Starting active message polling as a fallback mechanism...")
            
            # Now continuously poll for new messages, using the message state tracker
            poll_count = 0
            while hasattr(self, '_running') and self._running:
                poll_count += 1
                if poll_count % 10 == 0:  # Only log every 10 polls to reduce spam
                    print(f"\n🔄 Active polling cycle #{poll_count}")
                
                for source_id in self.chat_mapping.keys():
                    try:
                        # Get the last processed message ID
                        last_message_id = self.mapper.get_last_message_id(source_id)
                        
                        # Get latest messages
                        new_messages = []
                        async for msg in self.client.get_chat_history(source_id, limit=5):
                            if msg.id > last_message_id:
                                new_messages.append(msg)
                            else:
                                break  # No need to continue once we hit previously seen messages
                        
                        # Process new messages in chronological order (oldest first)
                        if new_messages:
                            print(f"\n✅ Found {len(new_messages)} new messages in chat {source_id}")
                            new_messages.reverse()  # Reverse to process oldest first
                            
                            for msg in new_messages:
                                print(f"📥 Processing new message {msg.id} from active polling")
                                await self._handle_message(msg)
                    except Exception as e:
                        if poll_count % 10 == 0:  # Only log errors every 10 polls
                            print(f"❌ Error polling chat {source_id}: {e}")
                
                # Sleep between polling cycles
                await asyncio.sleep(10)  # Poll every 10 seconds
                
        except asyncio.CancelledError:
            print("🔄 Active message polling stopped")
            raise
        except Exception as e:
            print(f"❌ Error in active message polling: {e}")
            logger.error(f"Error in active message polling: {e}") 