"""
Telegram client for SilentGem
"""

import asyncio
from pathlib import Path
from pyrogram import Client, filters, types, errors
from loguru import logger
import sqlite3
import time
import os
import signal
import json
import re

from silentgem.config import API_ID, API_HASH, SESSION_NAME, load_mapping, TARGET_LANGUAGE, LLM_ENGINE
from silentgem.translator import create_translator
from silentgem.mapper import ChatMapper
from silentgem.database.message_store import get_message_store
from silentgem.config.insights_config import get_insights_config

class SilentGemClient:
    """Telegram userbot client for monitoring and translating messages"""
    
    def __init__(self):
        """Initialize the client and translator"""
        print("🔧 Initializing SilentGem client...")
        self.client = Client(
            SESSION_NAME,
            api_id=API_ID,
            api_hash=API_HASH,
            workdir=str(Path("."))
        )
        print("✅ Telegram client initialized")
        
        print(f"🔧 Initializing translator (using {LLM_ENGINE})...")
        try:
            # Initialize translator with await since create_translator is now async
            self.translator = None  # Will be initialized in start()
            print("✅ Translator initialization will be completed during startup")
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
        
        # For tracking running state
        self._running = False
        
        logger.info("SilentGem client initialized")
    
    async def start(self):
        """Start the client and register handlers"""
        # Initialize translator if not already done
        if self.translator is None:
            try:
                self.translator = await create_translator()
                print("✅ Translator initialized successfully")
            except Exception as e:
                print(f"❌ Failed to initialize translator: {e}")
                logger.error(f"Error initializing translator: {e}")
                raise

        # Load the chat mapping
        self.chat_mapping = self.mapper.get_all()
        if not self.chat_mapping:
            logger.warning("No chat mappings loaded, the bot won't translate any messages")
            print("⚠️ WARNING: No chat mappings found. The translator won't process any messages.")
            print("Please set up chat mappings first using the setup wizard or option 3 in the main menu.")
        else:
            logger.info(f"Loaded {len(self.chat_mapping)} chat mappings")
            print(f"✅ Loaded {len(self.chat_mapping)} chat mappings")
            print("Monitoring the following source chats:")
            for source_id in self.chat_mapping.keys():
                print(f" - Chat ID: {source_id} → Target: {self.chat_mapping[source_id]}")
        
        # Set up error handler - must accept client parameter
        @self.client.on_disconnect()
        async def on_disconnect(client):
            logger.warning("Client disconnected. Will attempt to reconnect.")
            print("⚠️ Telegram client disconnected. Attempting to reconnect...")
        
        # Start the client with error handling
        try:
            await self.client.start()
            me = await self.client.get_me()
            logger.info(f"Started as {me.first_name} ({me.id})")
            print(f"✅ Connected to Telegram as {me.first_name} ({me.id})")
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
                    print(f"📩 Received message from chat {message.chat.id} ({message.chat.title if hasattr(message.chat, 'title') else 'Private'})")
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
            sender_id = None
            if message.from_user:
                sender_id = str(message.from_user.id)
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
                        sent_message = None
                        if media_type == "photo":
                            sent_message = await self.client.send_photo(
                                chat_id=target_chat_id,
                                photo=message.photo.file_id,
                                caption=f"📷 Photo from {sender_name}"
                            )
                        elif media_type == "video":
                            sent_message = await self.client.send_video(
                                chat_id=target_chat_id,
                                video=message.video.file_id,
                                caption=f"🎥 Video from {sender_name}"
                            )
                        elif media_type == "document":
                            sent_message = await self.client.send_document(
                                chat_id=target_chat_id,
                                document=message.document.file_id,
                                caption=f"📎 Document from {sender_name}"
                            )
                        elif media_type == "animation":
                            sent_message = await self.client.send_animation(
                                chat_id=target_chat_id,
                                animation=message.animation.file_id,
                                caption=f"🎬 Animation from {sender_name}"
                            )
                        elif media_type == "sticker":
                            sent_message = await self.client.send_sticker(
                                chat_id=target_chat_id,
                                sticker=message.sticker.file_id
                            )
                            # Stickers can't have captions, so send a follow-up message
                            sent_message = await self.client.send_message(
                                chat_id=target_chat_id,
                                text=f"🎭 Sticker from {sender_name}"
                            )
                        print(f"✅ Media forwarded to {target_chat_id}")
                        
                        # Store in message database for chat insights
                        try:
                            # Get message store and config
                            message_store = get_message_store()
                            insights_config = get_insights_config()
                            
                            # Only store if we're configured to store messages
                            if insights_config.get("store_full_content", True):
                                # The caption becomes the content
                                caption = f"Media: {media_type} from {sender_name}"
                                
                                # Handle anonymization if enabled
                                display_sender = sender_name
                                if insights_config.get("anonymize_senders", False):
                                    display_sender = "Anonymous"
                                    
                                # Store the message
                                message_store.store_message(
                                    message_id=sent_message.id if sent_message else 0,
                                    original_message_id=message.id,
                                    source_chat_id=chat_id,
                                    target_chat_id=target_chat_id,
                                    sender_id=sender_id,
                                    sender_name=display_sender,
                                    content=caption,
                                    original_content=caption,
                                    source_language=None,
                                    target_language=None,
                                    is_media=True,
                                    media_type=media_type,
                                    is_forwarded=message.forward_date is not None
                                )
                                print(f"📝 Stored media message in database for chat insights")
                        except Exception as store_error:
                            logger.error(f"Error storing message in database: {store_error}")
                            print(f"❌ Could not store message: {store_error}")
                            # Continue processing even if storage fails
                            
                        # Only update the last message ID if successfully processed
                        self.mapper.update_last_message_id(chat_id, message.id)
                        print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
                    except Exception as e:
                        print(f"❌ Failed to forward media: {e}")
                        # DO NOT update the last message ID as processing failed
                        return
                    
                    return
                else:
                    logger.debug("Message has no text or caption, ignoring")
                    print("❌ Message has no text or caption, ignoring")
                    
                    # Still track the message ID if it has no content - this is probably fine to do
                    # even on error as empty messages don't need translation
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
                        sent_message = None
                        if media_type == "photo":
                            sent_message = await self.client.send_photo(
                                chat_id=target_chat_id,
                                photo=message.photo.file_id,
                                caption=f"📷 Photo from {sender_name}"
                            )
                        elif media_type == "video":
                            sent_message = await self.client.send_video(
                                chat_id=target_chat_id,
                                video=message.video.file_id,
                                caption=f"🎥 Video from {sender_name}"
                            )
                        elif media_type == "document":
                            sent_message = await self.client.send_document(
                                chat_id=target_chat_id,
                                document=message.document.file_id,
                                caption=f"📎 Document from {sender_name}"
                            )
                        elif media_type == "animation":
                            sent_message = await self.client.send_animation(
                                chat_id=target_chat_id,
                                animation=message.animation.file_id,
                                caption=f"🎬 Animation from {sender_name}"
                            )
                        elif media_type == "sticker":
                            sent_message = await self.client.send_sticker(
                                chat_id=target_chat_id,
                                sticker=message.sticker.file_id
                            )
                            # Stickers can't have captions, so send a follow-up message
                            sent_message = await self.client.send_message(
                                chat_id=target_chat_id,
                                text=f"🎭 Sticker from {sender_name}"
                            )
                        print(f"✅ Media forwarded to {target_chat_id}")
                        
                        # Store in message database for chat insights
                        try:
                            # Get message store and config
                            message_store = get_message_store()
                            insights_config = get_insights_config()
                            
                            # Only store if we're configured to store messages
                            if insights_config.get("store_full_content", True):
                                # The caption becomes the content
                                caption = f"Media: {media_type} from {sender_name}"
                                
                                # Handle anonymization if enabled
                                display_sender = sender_name
                                if insights_config.get("anonymize_senders", False):
                                    display_sender = "Anonymous"
                                    
                                # Store the message
                                message_store.store_message(
                                    message_id=sent_message.id if sent_message else 0,
                                    original_message_id=message.id,
                                    source_chat_id=chat_id,
                                    target_chat_id=target_chat_id,
                                    sender_id=sender_id,
                                    sender_name=display_sender,
                                    content=caption,
                                    original_content=caption,
                                    source_language=None,
                                    target_language=None,
                                    is_media=True,
                                    media_type=media_type,
                                    is_forwarded=message.forward_date is not None
                                )
                                print(f"📝 Stored media message in database for chat insights")
                        except Exception as store_error:
                            logger.error(f"Error storing message in database: {store_error}")
                            print(f"❌ Could not store message: {store_error}")
                            # Continue processing even if storage fails
                            
                        # Only mark as processed if we successfully forwarded the media
                        self.mapper.update_last_message_id(chat_id, message.id)
                        print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
                    except Exception as e:
                        print(f"❌ Failed to forward media: {e}")
                        # DO NOT update the last message ID as processing failed
                        return
                
                # If we didn't have media to forward, still mark as processed
                # since we're intentionally skipping very short messages
                else:
                    self.mapper.update_last_message_id(chat_id, message.id)
                    print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id} (skipped short text)")
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
                
                try:
                    sent_message = None
                    if media_type:
                        # Forward media with original caption
                        if media_type == "photo":
                            sent_message = await self.client.send_photo(
                                chat_id=target_chat_id,
                                photo=message.photo.file_id,
                                caption=formatted_message
                            )
                        elif media_type == "video":
                            sent_message = await self.client.send_video(
                                chat_id=target_chat_id,
                                video=message.video.file_id,
                                caption=formatted_message
                            )
                        elif media_type == "document":
                            sent_message = await self.client.send_document(
                                chat_id=target_chat_id,
                                document=message.document.file_id,
                                caption=formatted_message
                            )
                        elif media_type == "animation":
                            sent_message = await self.client.send_animation(
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
                            sent_message = await self.client.send_message(
                                chat_id=target_chat_id,
                                text=formatted_message
                            )
                    else:
                        # Just a text message
                        sent_message = await self.client.send_message(
                            chat_id=target_chat_id,
                            text=formatted_message,
                            disable_web_page_preview=True,
                        )
                    print(f"✅ Original message forwarded to {target_chat_id}")
                    
                    # Store in message database for chat insights
                    try:
                        # Get message store and config
                        message_store = get_message_store()
                        insights_config = get_insights_config()
                        
                        # Only store if we're configured to store messages
                        if insights_config.get("store_full_content", True):
                            # Handle anonymization if enabled
                            display_sender = sender_name
                            if insights_config.get("anonymize_senders", False):
                                display_sender = "Anonymous"
                                
                            # Store the message
                            message_store.store_message(
                                message_id=sent_message.id if sent_message else 0,
                                original_message_id=message.id,
                                source_chat_id=chat_id,
                                target_chat_id=target_chat_id,
                                sender_id=sender_id,
                                sender_name=display_sender,
                                content=text,  # Use original content since it wasn't translated
                                original_content=text,
                                source_language="english",
                                target_language="english",
                                is_media=media_type is not None,
                                media_type=media_type,
                                is_forwarded=message.forward_date is not None
                            )
                            print(f"📝 Stored message in database for chat insights")
                    except Exception as store_error:
                        logger.error(f"Error storing message in database: {store_error}")
                        print(f"❌ Could not store message: {store_error}")
                        # Continue processing even if storage fails
                    
                    # Only update last message ID if everything succeeded
                    self.mapper.update_last_message_id(chat_id, message.id)
                    print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
                except Exception as e:
                    print(f"❌ Failed to forward original English message: {e}")
                    # DO NOT update the last message ID as processing failed
                    return
                
                return
            
            # Translate the text
            logger.debug(f"Translating text: {text[:50]}...")
            print(f"🧠 Sending to {LLM_ENGINE} for translation...")
            
            try:
                translated_text = await self.translator.translate(text)
                logger.info(f"Translation complete: {translated_text[:50]}...")
                print(f"✅ Translation received: {translated_text[:100]}...")
                
                # Format message with sender info
                formatted_message = f"🔄 Translated from {sender_name}:\n\n{translated_text}"
                
                # Send to target channel - handle differently based on media type
                try:
                    print(f"📤 Sending translation to target chat {target_chat_id}...")
                    
                    sent_message = None
                    if media_type:
                        # Forward media with translated caption
                        if media_type == "photo":
                            sent_message = await self.client.send_photo(
                                chat_id=target_chat_id,
                                photo=message.photo.file_id,
                                caption=formatted_message
                            )
                        elif media_type == "video":
                            sent_message = await self.client.send_video(
                                chat_id=target_chat_id,
                                video=message.video.file_id,
                                caption=formatted_message
                            )
                        elif media_type == "document":
                            sent_message = await self.client.send_document(
                                chat_id=target_chat_id,
                                document=message.document.file_id,
                                caption=formatted_message
                            )
                        elif media_type == "animation":
                            sent_message = await self.client.send_animation(
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
                            sent_message = await self.client.send_message(
                                chat_id=target_chat_id,
                                text=formatted_message
                            )
                    else:
                        # Just a text message
                        sent_message = await self.client.send_message(
                            chat_id=target_chat_id,
                            text=formatted_message,
                            disable_web_page_preview=True,
                        )
                        
                    logger.info(f"Translation sent to {target_chat_id}")
                    print(f"✅ Translation sent to {target_chat_id}")
                    
                    # Store in message database for chat insights
                    try:
                        # Get message store and config
                        message_store = get_message_store()
                        insights_config = get_insights_config()
                        
                        # Only store if we're configured to store messages
                        if insights_config.get("store_full_content", True):
                            # Handle anonymization if enabled
                            display_sender = sender_name
                            if insights_config.get("anonymize_senders", False):
                                display_sender = "Anonymous"
                                
                            # Store the message
                            message_store.store_message(
                                message_id=sent_message.id if sent_message else 0,
                                original_message_id=message.id,
                                source_chat_id=chat_id,
                                target_chat_id=target_chat_id,
                                sender_id=sender_id,
                                sender_name=display_sender,
                                content=translated_text,
                                original_content=text,
                                source_language=None,  # We don't know the source language
                                target_language=TARGET_LANGUAGE,
                                is_media=media_type is not None,
                                media_type=media_type,
                                is_forwarded=message.forward_date is not None
                            )
                            print(f"📝 Stored message in database for chat insights")
                    except Exception as store_error:
                        logger.error(f"Error storing message in database: {store_error}")
                        print(f"❌ Could not store message: {store_error}")
                        # Continue processing even if storage fails
                    
                    # Only update message ID if message was successfully translated and sent
                    self.mapper.update_last_message_id(chat_id, message.id)
                    print(f"✅ Updated last processed message ID to {message.id} for chat {chat_id}")
                
                except Exception as e:
                    logger.error(f"Failed to send message to {target_chat_id}: {e}")
                    print(f"❌ Failed to send message to {target_chat_id}: {e}")
                    # DO NOT update the last message ID as sending failed
                    return
            
            except Exception as e:
                logger.error(f"Failed to translate message: {e}")
                print(f"❌ Failed to translate message: {e}")
                # DO NOT update the last message ID as translation failed
                return
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            print(f"❌ Error handling message: {e}")
            # DO NOT update the message ID when we have an error
            # This will allow the message to be tried again
            return
    
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
        """Stop the client"""
        logger.info("Stopping SilentGem client...")
        print("🛑 Stopping SilentGem client...")
        
        # Set running flag to False immediately
        self._running = False
        
        # Set force shutdown flag
        self._force_shutdown = True
        
        # Signal shutdown through future if it exists
        if hasattr(self, '_shutdown_future') and not self._shutdown_future.done():
            self._shutdown_future.set_result(None)
        
        # Cancel all pending tasks
        for task_name, task in list(self._tasks.items()):
            if not task.done() and not task.cancelled():
                logger.debug(f"Cancelling task {task_name}")
                task.cancel()
                try:
                    # Very short timeout to avoid hanging
                    await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass  # Expected during cancellation
                except Exception as e:
                    logger.error(f"Error cancelling task {task_name}: {e}")
        
        self._tasks.clear()

        try:
            # Stop the client with a timeout
            if hasattr(self, 'client') and self.client:
                if getattr(self.client, 'is_connected', False):
                    try:
                        # Use a very short timeout to avoid hanging
                        await asyncio.wait_for(self.client.stop(), timeout=1.0)
                        logger.info("Client stopped successfully")
                        print("✅ Client stopped successfully")
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        logger.warning("Client stop timed out, proceeding anyway")
                        print("⚠️ Client stop timed out, proceeding anyway")
                    except Exception as e:
                        logger.error(f"Error stopping client: {e}")
                        print(f"❌ Error stopping client: {e}")
                else:
                    logger.info("Client was not running, nothing to stop")
            else:
                logger.info("No client instance to stop")
        
        except Exception as e:
            logger.error(f"Error stopping client: {e}")
            print(f"❌ Error stopping client: {e}")
        
        # Ensure running flag is set to False
        self._running = False
        logger.info("SilentGem client stopped")
        
        return self  # Return self to allow method chaining

    async def stop_client(self):
        """Stop the client and clean up"""
        # Call the updated stop method which now returns self
        await self.stop()
        
        # Clear any resources
        self.chat_mapping = {}
        
        # Both _running and _force_shutdown flags are already set in stop()
        
        return self
    
    async def _heartbeat(self):
        """Periodically log a heartbeat to show the client is still running"""
        try:
            count = 0
            while hasattr(self, '_running') and self._running:
                await asyncio.sleep(60)  # Every minute
                count += 1
                print(f"💓 Heartbeat #{count}: SilentGem is running and listening for messages")
                
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
                
            print("🔄 Checking for missed messages since last run...")
            
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
                
            print("🔄 Starting active message polling as a fallback mechanism...")
            
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
                    print(f"🔄 Active polling cycle #{poll_count}")
                
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
                            print(f"✅ Found {len(new_messages)} new messages in chat {source_id}")
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

    async def start_client(self):
        """Start the client and return it"""
        if not self._running:
            await self.start()
            self._running = True
        return self

# Singleton instance
_instance = None

def get_client():
    """Get the SilentGemClient singleton instance"""
    global _instance
    if _instance is None:
        try:
            _instance = SilentGemClient()
        except Exception as e:
            logger.error(f"Error creating SilentGemClient: {e}")
            
    return _instance

def _clear_instance():
    """Clear the global client instance"""
    global _instance
    if _instance is not None:
        logger.info("Clearing SilentGemClient instance")
        _instance = None
    return True

# Add function to cleanly start the client
async def start_client():
    """Start the client singleton instance"""
    client = get_client()
    await client.start()
    return client 