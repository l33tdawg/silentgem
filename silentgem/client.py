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
            
        self.chat_mapping = {}
        logger.info("SilentGem client initialized")
    
    async def start(self):
        """Start the client and register handlers"""
        # Load the chat mapping
        self.chat_mapping = load_mapping()
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
            
            # Add a debug message handler that will catch ALL messages, not just from mapped chats
            @self.client.on_message()
            async def debug_all_messages(client, message):
                try:
                    chat_id = str(message.chat.id)
                    chat_title = message.chat.title if hasattr(message.chat, 'title') else 'Private'
                    print(f"\n🔍 DEBUG: Received message in chat {chat_id} ({chat_title})")
                    print(f"💬 Message content: {message.text or message.caption or '[No text content]'}")
                    print(f"🔗 Available mappings: {self.chat_mapping}")
                    
                    # Check if this chat is in our mapping
                    if chat_id in self.chat_mapping:
                        print(f"✅ This chat is in our mapping! Will process for translation.")
                        print(f"🔄 Will translate to target chat: {self.chat_mapping[chat_id]}")
                        
                        # Force process message here to ensure it gets translated
                        print(f"🔄 Manually triggering message processing...")
                        await self._handle_message(message)
                    else:
                        print(f"❌ This chat is NOT in our mapping. Message will be ignored.")
                        print(f"🔍 Chat ID: '{chat_id}' not found in keys: {list(self.chat_mapping.keys())}")
                except Exception as e:
                    print(f"❌ Error in debug message handler: {e}")
                    import traceback
                    print(f"❌ Traceback: {traceback.format_exc()}")
            
            # Register targeted message handler with verbose logging
            @self.client.on_message(filters.chat(list(self.chat_mapping.keys())))
            async def on_message(client, message):
                print(f"\n📩 Received message from chat {message.chat.id} ({message.chat.title if hasattr(message.chat, 'title') else 'Private'})")
                print(f"💬 Message content: {message.text or message.caption or '[No text content]'}")
                print(f"🔗 Chat mapping for this chat: {self.chat_mapping.get(str(message.chat.id), 'Not found')}")
                await self._handle_message(message)
            
            # Start periodic message checking for debugging
            asyncio.create_task(self._debug_check_messages())
            
            # Keep the client running
            await self._idle()
        except sqlite3.ProgrammingError as e:
            if "Cannot operate on a closed database" in str(e):
                logger.error("Database connection closed unexpectedly. Please restart the application.")
                logger.error("You can run 'python main.py --cleanup' to fix database issues.")
                print("\n❌ Database error: Connection closed unexpectedly")
                print("Please run 'python main.py --cleanup' to fix this issue")
                # Signal shutdown 
                if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
                    self._shutdown_future.set_result(None)
            else:
                raise
        except errors.RPCError as e:
            error_message = str(e).lower()
            if "migrate" in error_message or "phone_migrate" in error_message:
                logger.error(f"Telegram datacenter migration required: {e}")
                logger.error("Please run 'python main.py --cleanup' and then restart the application")
                print(f"\n❌ Telegram error: {e}")
                print("Please run 'python main.py --cleanup' and then restart")
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
            chat_id = str(message.chat.id)
            logger.debug(f"Received message in chat {chat_id}: {message.text[:50] if message.text else ''}")
            print(f"🔄 Processing message from chat {chat_id}")
            
            # Check if this chat is in our mapping
            if chat_id not in self.chat_mapping:
                logger.debug(f"Chat {chat_id} not in mapping, ignoring")
                print(f"❌ Chat {chat_id} not in mapping, ignoring")
                return
            
            target_chat_id = self.chat_mapping[chat_id]
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
        
        if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
            self._shutdown_future.set_result(None)
        
        try:
            if hasattr(self, 'client') and self.client.is_connected:
                await asyncio.wait_for(self.client.stop(), timeout=5)
                logger.info("Client stopped successfully")
            else:
                logger.info("Client was not running or already stopped")
        except asyncio.TimeoutError:
            logger.warning("Client stop operation timed out, proceeding anyway")
        except Exception as e:
            logger.error(f"Error stopping client: {e}")
        
        self._running = False 

    async def _debug_check_messages(self):
        """Periodically check for messages in monitored chats for debugging purposes"""
        try:
            # Wait for 10 seconds before starting checks to allow everything to initialize
            await asyncio.sleep(10)
            
            print("\n🔍 Starting periodic message checking for debugging purposes...")
            
            check_count = 0
            while hasattr(self, '_running') and self._running:
                check_count += 1
                try:
                    print(f"\n🔍 Debug check #{check_count}: Verifying chat access...")
                    
                    for source_id in self.chat_mapping.keys():
                        try:
                            # Try to get info about the chat
                            chat = await self.client.get_chat(source_id)
                            print(f"✅ Successfully accessed chat: {chat.title} (ID: {chat.id})")
                            
                            # Try to get the last 5 messages
                            print(f"🔍 Fetching last 5 messages from chat {chat.id}...")
                            messages = []
                            async for msg in self.client.get_chat_history(chat.id, limit=5):
                                messages.append(msg)
                            
                            if messages:
                                print(f"✅ Found {len(messages)} recent messages in chat {chat.id}")
                                for msg in messages:
                                    print(f"  - Message ID: {msg.id}, Date: {msg.date}")
                            else:
                                print(f"❌ No recent messages found in chat {chat.id}")
                        except Exception as e:
                            print(f"❌ Error accessing chat {source_id}: {e}")
                    
                except Exception as e:
                    print(f"❌ Error during debug check: {e}")
                
                # Wait 30 seconds before checking again
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            print("🔍 Debug message checking stopped")
        except Exception as e:
            print(f"❌ Error in debug message checking: {e}") 