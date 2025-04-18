#!/usr/bin/env python3
"""
SilentGem - A Telegram translator using Pyrogram and Google Gemini.
Created by Dhillon '@l33tdawg' Kannabhiran (l33tdawg@hitb.org)
"""

import os
import asyncio
import json
import argparse
import time
import signal
import sys
import glob
import shutil
import sqlite3
from pathlib import Path
from loguru import logger

from silentgem.config import validate_config, MAPPING_FILE, API_ID, API_HASH, GEMINI_API_KEY, SESSION_NAME
from silentgem.client import SilentGemClient
from silentgem.utils import ensure_dir_exists, get_chat_info
from silentgem.setup import setup_wizard
from silentgem.mapper import ChatMapper
from pyrogram import Client, errors
from pyrogram.enums import ChatType

# Add debug flag
DEBUG = os.environ.get("SILENTGEM_DEBUG", "0") == "1"

# Global variable to track active clients for clean shutdown
active_clients = []

# Global lock to prevent multiple client creations at once
client_lock = asyncio.Lock()

# Ensure necessary directories exist
ensure_dir_exists("data")
ensure_dir_exists("logs")

# ASCII art for startup
SILENTGEM_ASCII = """
███████╗██╗██╗     ███████╗███╗   ██╗████████╗ ██████╗ ███████╗███╗   ███╗
██╔════╝██║██║     ██╔════╝████╗  ██║╚══██╔══╝██╔════╝ ██╔════╝████╗ ████║
███████╗██║██║     █████╗  ██╔██╗ ██║   ██║   ██║  ███╗█████╗  ██╔████╔██║
╚════██║██║██║     ██╔══╝  ██║╚██╗██║   ██║   ██║   ██║██╔══╝  ██║╚██╔╝██║
███████║██║███████╗███████╗██║ ╚████║   ██║   ╚██████╔╝███████╗██║ ╚═╝ ██║
╚══════╝╚═╝╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚══════╝╚═╝     ╚═╝

        🔄 Telegram Translator using Google Gemini Flash Thinking 🔄
"""

def print_debug(*args, **kwargs):
    """Print only if debug mode is enabled"""
    if DEBUG:
        print("[DEBUG]", *args, **kwargs)

# Check if database is locked 
def check_and_fix_database_lock():
    """Check if database is locked and attempt to fix if needed"""
    # Find the .session file
    session_path = f"{SESSION_NAME}.session"
    session_files = glob.glob(f"{session_path}*")
    
    if not session_files:
        print("No session files found.")
        return False
    
    # Check for lock files
    lock_files = [f for f in session_files if f.endswith("-journal") or f.endswith("-wal") or f.endswith("-shm")]
    
    if lock_files:
        print(f"Found {len(lock_files)} database lock files:")
        for lf in lock_files:
            print(f" - {lf}")
            
        print("\nWould you like to clear database locks to fix 'database is locked' errors? (y/n)")
        print("(Recommended: Enter 'y' if you're experiencing issues)")
        choice = input("> ").strip().lower()
        
        if choice == 'y':
            print("Clearing database locks...")
            
            # First, try to make a backup of the session file
            backup_path = f"{session_path}.backup"
            try:
                if os.path.exists(session_path):
                    shutil.copy2(session_path, backup_path)
                    print(f"Session backup created at {backup_path}")
            except Exception as e:
                print(f"Warning: Failed to create backup: {e}")
            
            # Remove lock files
            for lf in lock_files:
                try:
                    os.remove(lf)
                    print(f"Removed: {lf}")
                except Exception as e:
                    print(f"Failed to remove {lf}: {e}")
            
            return True
        else:
            print("Lock files not cleared. You may experience 'database is locked' errors.")
            print("If you do, run the application with the --cleanup flag: ./silentgem.py --cleanup")
            return False
    
    return False

# Call at program start
check_and_fix_database_lock()

# Force exit helper
def force_exit(message="Force exiting..."):
    """Force exit the application when stuck"""
    print(message)
    # Use os._exit to bypass any cleanup that might be causing issues
    os._exit(1)

# Signal handler for graceful exit
def signal_handler(sig, frame):
    """Handle exit signals to cleanly shut down clients"""
    print("\nReceived exit signal. Shutting down clients...")
    
    # Set flag to indicate shutdown is requested
    signal_handler.shutdown_requested = True
    
    # Explicitly exit in case we're stuck
    if hasattr(signal_handler, 'force_exit_count'):
        signal_handler.force_exit_count += 1
        if signal_handler.force_exit_count >= 2:
            force_exit("Forcing immediate exit after multiple interrupts.")
    else:
        signal_handler.force_exit_count = 1

# Initialize the shutdown flag
signal_handler.shutdown_requested = False
signal_handler.force_exit_count = 0

# Set up signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Utility function to safely stop a client
async def stop_client_safely(app):
    """Safely stop a Pyrogram client"""
    print("\nStopping client...")
    try:
        # Add a graceful shutdown with memory cleanup
        try:
            # Set a flag to avoid operations during shutdown
            app._shutdown_flag = True
            
            # Don't put None in the queue if we're being interrupted
            if not asyncio.current_task().cancelled():
                try:
                    app.dispatcher.updates_queue.put_nowait(None)
                except Exception:
                    pass
        except Exception:
            # Ignore errors in cleanup
            pass
            
        # Use a timeout for client stop to avoid hanging
        try:
            await asyncio.wait_for(app.stop(), timeout=3)
            print("Client stopped successfully.")
        except (asyncio.TimeoutError, asyncio.CancelledError):
            print("Client stop operation interrupted, but shutdown should complete.")
        except Exception as e:
            if "Cannot allocate memory" in str(e):
                print("Memory error during shutdown - this is expected and safe to ignore.")
            else:
                print(f"Error during client stop: {e}")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Interrupted during shutdown, forcing exit...")
        os._exit(1)  # Force exit as a last resort
    except MemoryError:
        print("Memory error during shutdown - this is expected and safe to ignore.")
    except Exception as e:
        print(f"Error stopping client: {e}")
        # Don't print traceback for memory errors to avoid more memory issues
        if "Cannot allocate memory" not in str(e):
            import traceback
            traceback.print_exc()
    
    # Remove from active clients list
    if app in active_clients:
        active_clients.remove(app)

# Safe client creation function with lock
async def create_telegram_client(session_name=SESSION_NAME):
    """Create a Telegram client safely with lock to prevent race conditions"""
    async with client_lock:
        # Check if we have any active clients that we can reuse
        for client in active_clients:
            if client.is_connected:
                print("Reusing existing Telegram client connection...")
                return client
        
        # Need to create a new client
        try:
            print("Creating new Telegram client...")
            app = Client(
                session_name,
                api_id=API_ID,
                api_hash=API_HASH
            )
            
            # Track the client for clean shutdown
            active_clients.append(app)
            
            try:
                await asyncio.wait_for(app.start(), timeout=30)
                print("✅ Client connected successfully.")
                return app
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    print("❌ Database is locked. Please restart the application.")
                    print("If the problem persists, try running the application with --setup flag.")
                    
                    # Remove files if they exist
                    check_and_fix_database_lock()
                    
                    # Remove the client from tracking
                    if app in active_clients:
                        active_clients.remove(app)
                    return None
                raise
            except Exception as e:
                print(f"❌ Error connecting client: {e}")
                # Remove the client from tracking
                if app in active_clients:
                    active_clients.remove(app)
                raise
                
        except Exception as e:
            print(f"❌ Error creating client: {e}")
            return None

async def is_configured():
    """Check if the application is configured"""
    # Check if .env file exists
    if not os.path.exists(".env"):
        logger.warning("No .env file found")
        return False
    
    # Check if all required environment variables are set
    if API_ID == 0:
        logger.warning("TELEGRAM_API_ID not set or invalid in .env file")
        return False
        
    if not API_HASH:
        logger.warning("TELEGRAM_API_HASH not set in .env file")
        return False
        
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set in .env file")
        return False
    
    # Check if mapping file exists
    if not os.path.exists(MAPPING_FILE):
        logger.warning(f"Mapping file {MAPPING_FILE} not found")
        return False
    
    # Check if mapping file is valid JSON with at least one entry
    try:
        with open(MAPPING_FILE, "r") as f:
            mapping = json.load(f)
        
        # We allow empty mappings - the user can add them later via CLI
        # But the file must exist and be valid JSON
        logger.info(f"Found {len(mapping)} chat mappings")
        
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in {MAPPING_FILE}")
        return False
    except Exception as e:
        logger.error(f"Error reading {MAPPING_FILE}: {e}")
        return False
    
    return True

async def list_mappings():
    """List all current chat mappings"""
    mapper = ChatMapper()
    mappings = mapper.get_all()
    
    if not mappings:
        print("No chat mappings found.")
        return
    
    print(f"\nCurrent Chat Mappings ({len(mappings)}):")
    print("-" * 80)
    
    # Check for session files and show diagnostic information
    session_path = f"{SESSION_NAME}.session"
    session_file_exists = os.path.exists(session_path)
    session_lock_files = glob.glob(f"{session_path}*-journal") + glob.glob(f"{session_path}*-wal") + glob.glob(f"{session_path}*-shm")
    
    if not session_file_exists:
        print("⚠️ No authentication session file found! You'll need to authenticate when starting the service.")
    elif session_lock_files:
        print(f"⚠️ Found {len(session_lock_files)} database lock files. This may cause connection issues.")
        print("   Run './silentgem.py --cleanup' and choose option 2 to fix this.")
    else:
        print("✅ Session file looks good. You should be able to start the service without re-authentication.")
    
    print("-" * 80)
    
    # Create a client to access chat information
    app = None
    try:
        print("Creating new Telegram client...")
        app = await create_telegram_client()
        if not app:
            print("❌ Failed to create Telegram client.")
            for source_id, target_id in mappings.items():
                print(f"Source: Unknown Chat ({source_id})")
                print(f"Target: Unknown Channel ({target_id})")
                print("-" * 80)
            return
        
        print("✅ Client connected successfully.")
        
        for source_id, target_id in mappings.items():
            # Get chat info using the active client
            try:
                source_chat = await app.get_chat(source_id)
                source_name = source_chat.title if hasattr(source_chat, "title") else getattr(source_chat, "first_name", f"Unknown Chat ({source_id})")
                
                target_chat = await app.get_chat(target_id)
                target_name = target_chat.title if hasattr(target_chat, "title") else getattr(target_chat, "first_name", f"Unknown Channel ({target_id})")
                
                print(f"Source: {source_name} ({source_id})")
                print(f"Target: {target_name} ({target_id})")
                print("-" * 80)
            except Exception as e:
                print(f"❌ Error getting chat info: {e}")
                print(f"Source: Unknown Chat ({source_id})")
                print(f"Target: Unknown Channel ({target_id})")
                print("-" * 80)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        # Clean up the client
        if app:
            print("Stopping client...")
            await stop_client_safely(app)
            print("Client stopped successfully.")

async def add_mapping(source_id, target_id):
    """Add a new chat mapping"""
    # Validate the chats
    source_info = await get_chat_info(source_id)
    if not source_info:
        print(f"❌ Source chat {source_id} not found or not accessible.")
        return False
    
    target_info = await get_chat_info(target_id)
    if not target_info:
        print(f"❌ Target channel {target_id} not found or not accessible.")
        return False
    
    # Add the mapping
    mapper = ChatMapper()
    mapper.add(source_id, target_id)
    
    print(f"✅ Added mapping: {source_info['title']} -> {target_info['title']}")
    return True

async def remove_mapping(source_id):
    """Remove a chat mapping"""
    mapper = ChatMapper()
    result = mapper.remove(source_id)
    
    if result:
        print(f"✅ Removed mapping for source chat {source_id}")
        return True
    else:
        print(f"❌ No mapping found for source chat {source_id}")
        return False

async def create_target_channel(app, source_chat):
    """Create a new channel for translation output"""
    channel_name = f"{source_chat['title']}-silentgem"
    # Ensure name isn't too long (Telegram has a 128 character limit for chat titles)
    if len(channel_name) > 120:
        channel_name = channel_name[:117] + "..."
        
    print(f"\nCreating target channel: {channel_name}")
    try:
        new_channel = await app.create_channel(
            title=channel_name,
            description=f"Automatic translations from {source_chat['title']} by SilentGem"
        )
        
        # Get the full channel object
        channel_info = await app.get_chat(new_channel.id)
        
        chat_info = {
            "id": channel_info.id,
            "title": channel_info.title,
            "type": str(channel_info.type.name),
            "username": getattr(channel_info, "username", None)
        }
        
        print(f"✅ Channel created successfully: {channel_info.title} (ID: {channel_info.id})")
        return chat_info
    except Exception as e:
        print(f"❌ Error creating channel: {e}")
        return None

async def interactive_add_mapping(source_chats, target_channels, app=None):
    """Add a mapping interactively by selecting from lists"""
    
    all_source_chats = source_chats.copy()
    
    # Ask for source chat
    print("\nSelect a source chat to monitor (enter the number):")
    source_choice = input("> ").strip()
    
    try:
        source_idx = int(source_choice) - 1
        if source_idx < 0 or source_idx >= len(all_source_chats):
            print("❌ Invalid selection.")
            return False
        
        source_chat = all_source_chats[source_idx]
        
        # Present options for target: use existing channel or create new one
        print(f"\nSelected source: {source_chat['title']}")
        print("\nHow would you like to set up the target channel?")
        print("1. Use an existing channel")
        print("2. Create a new channel automatically")
        
        target_option = input("> ").strip()
        
        if target_option == "1":
            # Use existing channel
            if not target_channels:
                print("\n❌ No existing channels found.")
                print("Select option 2 to create a new channel.")
                return False
                
            print("\nSelect a target channel for translations (enter the number):")
            for i, channel in enumerate(target_channels, 1):
                username = f" (@{channel['username']})" if channel["username"] else ""
                print(f"{i}. {channel['title']}{username} (ID: {channel['id']})")
                
            target_choice = input("> ").strip()
            
            try:
                target_idx = int(target_choice) - 1
                if target_idx < 0 or target_idx >= len(target_channels):
                    print("❌ Invalid selection.")
                    return False
                
                target_channel = target_channels[target_idx]
            except ValueError:
                print("❌ Invalid input. Please enter a number.")
                return False
        
        elif target_option == "2":
            # Create new channel
            if not app:
                print("\n❌ Cannot create channel without active client.")
                print("Please use option 1 or try again later.")
                return False
                
            target_channel = await create_target_channel(app, source_chat)
            if not target_channel:
                print("\n❌ Failed to create target channel.")
                return False
        
        else:
            print("❌ Invalid option.")
            return False
        
        # Add the mapping
        mapper = ChatMapper()
        mapper.add(source_chat["id"], target_channel["id"])
        
        print(f"\n✅ Added mapping: {source_chat['title']} -> {target_channel['title']}")
        return True
        
    except ValueError:
        print("❌ Invalid input. Please enter a number.")
        return False
    except Exception as e:
        print(f"❌ Error adding mapping: {e}")
        return False

async def delete_channel_if_auto_created(channel_id, existing_app=None):
    """Delete a channel if it was auto-created by SilentGem"""
    app = None
    try:
        # Use existing client if provided, otherwise create new one
        if existing_app and existing_app.is_connected:
            app = existing_app
            print("Using existing Telegram connection...")
        else:
            app = await create_telegram_client()
            if not app:
                print("Failed to create Telegram client.")
                return False
        
        # Get the channel info
        try:
            channel = await app.get_chat(channel_id)
        except Exception as e:
            print(f"Error retrieving channel info: {e}")
            return False
        
        # Check if this was a SilentGem auto-created channel (by name)
        is_auto_created = "-silentgem" in channel.title
        
        if is_auto_created:
            print(f"Detected auto-created channel: {channel.title}")
            
            # Attempt to delete the channel
            try:
                # For channels, we use delete_channel
                if channel.type == ChatType.CHANNEL:
                    await app.delete_channel(channel_id)
                    print(f"✅ Auto-created channel {channel.title} has been deleted.")
                    return True
                # For groups, we use leave_chat
                else:
                    await app.leave_chat(channel_id)
                    print(f"✅ Left the group {channel.title}.")
                    return True
            except Exception as e:
                print(f"Error deleting channel: {e}")
                return False
        else:
            print(f"Channel '{channel.title}' was not auto-created by SilentGem, keeping it.")
            return False
            
    except Exception as e:
        print(f"Error checking/deleting channel: {e}")
        return False
    finally:
        # Only stop the client if we created it (not if we're using an existing one)
        if app and app != existing_app and app in active_clients:
            await stop_client_safely(app)

async def interactive_remove_mapping():
    """Remove a mapping interactively with a numbered list"""
    app = None
    try:
        print("Creating new Telegram client...")
        # Create a client that we can reuse for multiple operations
        app = await create_telegram_client()
        if not app:
            print("❌ Failed to connect to Telegram. Please try again later.")
            return
            
        print("✅ Client connected successfully.")
    
        # Get all current mappings
        mapper = ChatMapper()
        mappings = mapper.get_all()
        
        if not mappings:
            print("No mappings found to remove.")
            return
        
        print("\nCurrent Mappings:")
        print("-" * 80)
        
        mapping_list = []
        index = 1
        
        # Resolve chat names using our existing client
        for source_id, target_id in mappings.items():
            try:
                # Get source chat info
                source_chat = await app.get_chat(source_id)
                source_name = source_chat.title if hasattr(source_chat, "title") else getattr(source_chat, "first_name", f"Unknown Chat ({source_id})")
                
                # Get target chat info
                target_chat = await app.get_chat(target_id)
                target_name = target_chat.title if hasattr(target_chat, "title") else getattr(target_chat, "first_name", f"Unknown Channel ({target_id})")
                
                print(f"{index}. {source_name} -> {target_name}")
                mapping_list.append((source_id, target_id, source_name, target_name))
                index += 1
            except Exception as e:
                # If we can't resolve the chat, still include it in the list with generic names
                print(f"{index}. Unknown Chat ({source_id}) -> Unknown Channel ({target_id}) - Error: {e}")
                mapping_list.append((source_id, target_id, f"Unknown Chat ({source_id})", f"Unknown Channel ({target_id})"))
                index += 1
        
        if not mapping_list:
            print("No mappings could be resolved.")
            return
        
        # Ask for selection
        print("\nSelect a mapping to remove (enter the number):")
        choice = input("> ").strip()
        
        try:
            selection = int(choice) - 1
            if selection < 0 or selection >= len(mapping_list):
                print("❌ Invalid selection.")
                return
            
            source_id, target_id, source_name, target_name = mapping_list[selection]
            
            # Ask for confirmation
            print(f"\nRemove mapping: {source_name} -> {target_name}? (y/n)")
            confirm = input("> ").strip().lower()
            
            if confirm != 'y':
                print("Operation cancelled.")
                return
            
            # Remove the mapping
            result = mapper.remove(source_id)
            
            if result:
                print(f"✅ Removed mapping for {source_name}")
                
                # Ask if the user wants to delete the target channel
                print(f"\nWould you like to delete the target channel '{target_name}'? (y/n)")
                delete_choice = input("> ").strip().lower()
                
                if delete_choice == 'y':
                    # Attempt to delete the channel if it was auto-created
                    # Pass the existing client to avoid creating a new one
                    deleted = await delete_channel_if_auto_created(target_id, app)
                    if not deleted:
                        print(f"The channel was not deleted automatically as it wasn't auto-created by SilentGem.")
                        print(f"You can delete it manually from the Telegram app if needed.")
                else:
                    print(f"Target channel '{target_name}' has been kept.")
                    
            else:
                print(f"❌ Failed to remove mapping for {source_name}")
            
        except ValueError:
            print("❌ Invalid input. Please enter a number.")
        except Exception as e:
            print(f"❌ Error removing mapping: {e}")
            
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        # Clean up our client
        if app:
            print("Stopping client...")
            await stop_client_safely(app)
            print("Client stopped successfully.")

async def list_available_chats():
    """List all available chats in your Telegram account"""
    import traceback
    import sys
    
    print("\n==== DEBUGGING ====")
    print(f"Python version: {sys.version}")
    print(f"Pyrogram version: {__import__('pyrogram').__version__}")
    print(f"Debug mode: {'Enabled' if DEBUG else 'Disabled'}")
    print("==== END SYSTEM INFO ====\n")
    
    print("Connecting to Telegram to retrieve your chats...")
    
    # Create the client safely using our utility function
    app = await create_telegram_client()
    if not app:
        print("Failed to connect to Telegram. Please restart the application.")
        return False
    
    try:
        print(f"Successfully connected as: {(await app.get_me()).first_name}")
        
        # Get available dialogs (chats)
        print("\nRetrieving your chats (this may take a moment)...")
        available_chats = []
        available_channels = []
        
        try:
            print("\nAttempting to get dialogs...")
            # Get dialogs properly - collect async results with timeout
            dialog_count = 0
            
            # Set a time limit for dialog fetching to prevent hanging
            start_time = time.time()
            max_time = 60  # seconds
            
            async def fetch_dialogs():
                nonlocal dialog_count
                try:
                    async for dialog in app.get_dialogs():
                        # Check if we're shutting down
                        if hasattr(app, '_shutdown_flag') and app._shutdown_flag:
                            break
                            
                        # Check time limit
                        if time.time() - start_time > max_time:
                            print("Dialog fetching time limit reached.")
                            break
                            
                        dialog_count += 1
                        if dialog_count % 10 == 0:
                            print(f"Retrieved {dialog_count} dialogs so far...")
                        
                        yield dialog
                except Exception as e:
                    print(f"Error in fetch_dialogs: {e}")
                    raise
            
            async for dialog in fetch_dialogs():
                # Check if we're shutting down
                if hasattr(app, '_shutdown_flag') and app._shutdown_flag:
                    print("Stopping dialog retrieval due to shutdown signal.")
                    break
                    
                chat = dialog.chat
                chat_title = getattr(chat, "title", "[No title]")
                chat_id = chat.id
                chat_type = chat.type
                
                print(f"Processing dialog: {chat_title} ({chat_id}) - Type: {chat_type}")
                
                # Fix: ChatType is now an enum in Pyrogram 2.x
                if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
                    # Skip empty titles
                    if not getattr(chat, "title", "").strip():
                        print(f"Skipping chat {chat_id} (empty title)")
                        continue
                        
                    chat_info = {
                        "id": chat_id,
                        "title": chat_title,
                        "type": str(chat_type.name),
                        "username": getattr(chat, "username", None)
                    }
                    
                    # Include channels as potential source chats
                    if chat_type == ChatType.CHANNEL:
                        print(f"Found channel: {chat_title} ({chat_id})")
                        available_chats.append(chat_info)  # Add channels to available source chats
                        available_channels.append(chat_info)  # Also keep them as potential target channels
                    else:
                        print(f"Found group: {chat_title} ({chat_id})")
                        available_chats.append(chat_info)
                else:
                    print(f"Skipping chat type: {chat_type}")
            
            print(f"Dialog retrieval complete. Found {dialog_count} total dialogs.")
            print(f"Found {len(available_chats)} potential source chats and {len(available_channels)} potential target channels.")
            
        except errors.AuthKeyUnregistered:
            print("\n❌ Authentication key is no longer registered. You might need to log in again.")
            print("Try running the setup wizard with '--setup' flag.")
            return False
        except errors.SessionExpired:
            print("\n❌ Your session has expired. You need to log in again.")
            print("Try running the setup wizard with '--setup' flag.")
            return False
        except errors.Unauthorized:
            print("\n❌ You're not authorized. You might need to log in again.")
            print("Try running the setup wizard with '--setup' flag.")
            return False
        except errors.FloodWait as e:
            print(f"\n❌ Flood wait error: You need to wait {e.value} seconds before trying again.")
            return False
        except Exception as e:
            print(f"\n⚠️ Error while getting dialogs: {str(e)}")
            print("\nFull error traceback:")
            traceback.print_exc()
            
            # If we have an issue, try the fallback method
            print("\nTrying alternative method to retrieve chats...")
            
            # Try to get some known chat IDs if the user provided them
            known_chat_ids = []
            if os.path.exists("chat_ids.txt"):
                print("Found chat_ids.txt file, reading IDs...")
                with open("chat_ids.txt", "r") as f:
                    for line in f:
                        line = line.strip()
                        # Skip empty lines and comments
                        if not line or line.startswith('#'):
                            continue
                            
                        try:
                            chat_id = int(line)
                            known_chat_ids.append(chat_id)
                            print(f"Added chat ID: {chat_id}")
                        except ValueError:
                            print(f"Invalid chat ID in chat_ids.txt: {line}")
                            continue
            
            print(f"Found {len(known_chat_ids)} known chat IDs")
            
            # If we have some known IDs, try to fetch them directly
            if known_chat_ids:
                for chat_id in known_chat_ids:
                    # Check if we're shutting down
                    if hasattr(app, '_shutdown_flag') and app._shutdown_flag:
                        print("Stopping chat retrieval due to shutdown signal.")
                        break
                        
                    try:
                        print(f"Fetching chat {chat_id}...")
                        chat = await app.get_chat(chat_id)
                        chat_title = getattr(chat, "title", "[No title]")
                        chat_type = chat.type
                        
                        print(f"Retrieved chat: {chat_title} ({chat_id}) - Type: {chat_type}")
                        
                        # Fix: ChatType is now an enum in Pyrogram 2.x
                        if chat_type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
                            if not getattr(chat, "title", "").strip():
                                print(f"Skipping chat {chat_id} (empty title)")
                                continue
                            
                            chat_info = {
                                "id": chat_id,
                                "title": chat_title, 
                                "type": str(chat_type.name),
                                "username": getattr(chat, "username", None)
                            }
                            
                            # Include channels as potential source chats
                            if chat_type == ChatType.CHANNEL:
                                print(f"Found channel: {chat_title}")
                                available_chats.append(chat_info)  # Add to available source chats
                                available_channels.append(chat_info)  # Also keep as potential target
                            else:
                                print(f"Found group: {chat_title}")
                                available_chats.append(chat_info)
                    except Exception as e:
                        print(f"Error fetching chat {chat_id}: {e}")
            else:
                print("No known chat IDs to try.")
                print("To add chat IDs, create a file named 'chat_ids.txt' with one chat ID per line.")
                
            print("\nIf you know the ID of a specific chat you want to monitor, you can")
            print("add it manually by selecting option 4 from the main menu.")
        
        print("\n==== CHAT SUMMARY ====")
        print(f"Source chats found: {len(available_chats)}")
        print(f"Target channels found: {len(available_channels)}")
        print("==== END SUMMARY ====\n")
        
        # Display available source chats (groups, supergroups, and channels)
        if available_chats:
            print(f"\nAvailable Source Chats - {len(available_chats)}:")
            print("-" * 80)
            for i, chat in enumerate(available_chats, 1):
                chat_type = chat["type"]
                username = f" (@{chat['username']})" if chat["username"] else ""
                print(f"{i}. [{chat_type}] {chat['title']}{username} (ID: {chat['id']})")
        else:
            print("\n❌ No suitable chats found in your account.")
            print("You need to join some groups or channels first to monitor them for translation.")
            print("If you have groups/channels, try these troubleshooting steps:")
            print("1. Open Telegram and make sure you can see your groups/channels")
            print("2. Check internet connection and try again")
            print("3. Add chats manually using their IDs (option 4 in the main menu)")
        
        # Display available target channels
        if available_channels:
            print(f"\nAvailable Target Channels - {len(available_channels)}:")
            print("-" * 80)
            for i, chat in enumerate(available_channels, 1):
                username = f" (@{chat['username']})" if chat["username"] else ""
                print(f"{i}. {chat['title']}{username} (ID: {chat['id']})")
            
            print("\nNOTE: You can also create a new target channel automatically when adding a mapping.")
        else:
            print("\n❌ No existing channels found in your account.")
            print("You can create a new channel automatically when adding a mapping.")
        
        # Ask if user wants to add a mapping
        if available_chats:
            print("\nWould you like to add a new chat mapping? (y/n)")
            choice = input("> ").strip().lower()
            
            if choice == 'y':
                await interactive_add_mapping(available_chats, available_channels, app)
                return True
        else:
            print("\nWould you like to add a mapping manually using chat IDs? (y/n)")
            choice = input("> ").strip().lower()
            
            if choice == 'y':
                await interactive_add_mapping_menu()
                return True
        
        return False
    except errors.RPCError as e:
        print(f"\n❌ Error retrieving chats: {e}")
        print("\nFull error traceback:")
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("\nFull error traceback:")
        traceback.print_exc()
        return False
    finally:
        # Use the safe stop method
        if app and app in active_clients:
            await stop_client_safely(app)

async def interactive_add_mapping_menu():
    """Add a mapping by entering IDs directly"""
    try:
        source_id = input("Enter source chat ID: ").strip()
        target_id = input("Enter target channel ID: ").strip()
        
        await add_mapping(source_id, target_id)
    except Exception as e:
        print(f"❌ Error adding mapping: {e}")

async def start_service():
    """Start the translation service"""
    print("\nStarting SilentGem translation service...")
    print("Press Ctrl+C to return to the menu.")
    
    # Reset shutdown flags
    signal_handler.shutdown_requested = False
    signal_handler.force_exit_count = 0
    
    # Set up client
    client = None
    try:
        client = SilentGemClient()
        
        # Set up a cancellable task
        async def run_forever():
            try:
                await client.start()
                print("\nService started successfully. Monitoring chats for messages to translate.")
                
                while True:
                    # Check for shutdown request
                    if signal_handler.shutdown_requested:
                        break
                    await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                # This is expected when we cancel the task
                logger.info("Service task cancelled")
                raise
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    print("\n❌ Error: Database is locked. Please run './silentgem.py --cleanup' to fix this issue.")
                    force_exit("\nExit and run './silentgem.py --cleanup'")
                raise
            except sqlite3.ProgrammingError as e:
                if "Cannot operate on a closed database" in str(e):
                    print("\n❌ Error: Database connection closed. Please run './silentgem.py --cleanup' to fix this issue.")
                    force_exit("\nExit and run './silentgem.py --cleanup'")
                raise
            except MemoryError:
                print("\nMemory allocation error detected. Emergency shutdown.")
                force_exit("Forcing exit due to memory constraints.")
        
        # Create and start the task
        task = None
        try:
            # Start the task
            task = asyncio.create_task(run_forever())
            
            # Wait for the task to complete (should only happen if cancelled or if there's an error)
            await task
        except asyncio.CancelledError:
            print("\nService cancellation requested...")
        except KeyboardInterrupt:
            print("\nKeyboard interrupt detected...")
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                print("\n❌ Error: Database is locked. Please run './silentgem.py --cleanup' to fix this issue.")
            logger.error(f"Database error: {e}")
        except sqlite3.ProgrammingError as e:
            if "Cannot operate on a closed database" in str(e):
                print("\n❌ Error: Database connection closed. Please run './silentgem.py --cleanup' to fix this issue.")
            logger.error(f"Database error: {e}")
        except MemoryError:
            print("\nMemory error detected during service run.")
            force_exit("Forcing exit due to memory constraints.")
        except Exception as e:
            logger.error(f"Error running SilentGem: {e}")
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print("\n❌ Error: Database is locked. Please run './silentgem.py --cleanup' to fix this issue.")
        logger.error(f"Database error during startup: {e}")
    except Exception as e:
        logger.error(f"Error starting service: {e}")
    finally:
        # Clean up
        if task and not task.done():
            logger.info("Cancelling running task...")
            try:
                task.cancel()
                # Wait for the task to be cancelled (with timeout)
                await asyncio.wait_for(task, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # This is expected
                pass
            except MemoryError:
                force_exit("Forcing exit due to memory constraints during cleanup.")
            except Exception as e:
                logger.error(f"Error during task cancellation: {e}")
        
        # Stop the client
        if client:
            try:
                await client.stop()
            except MemoryError:
                force_exit("Forcing exit due to memory constraints during client shutdown.")
            except Exception as e:
                logger.error(f"Error stopping client: {e}")
        
        print("\nService stopped. Returning to menu...")

async def display_menu():
    """Display the interactive menu"""
    print("\n==== SilentGem Main Menu ====")
    print("1. Start Translation Service")
    print("2. List Current Mappings")
    print("3. List Available Chats & Channels")
    print("4. Remove Mapping")
    print("5. Run Setup Wizard")
    print("6. Exit")
    print("============================")
    
    choice = input("Enter your choice (1-6): ").strip()
    return choice

async def interactive_mode():
    """Run the app in interactive mode with a menu"""
    while True:
        choice = await display_menu()
        
        if choice == '1':
            await start_service()
        elif choice == '2':
            await list_mappings()
        elif choice == '3':
            await list_available_chats()
        elif choice == '4':
            await interactive_remove_mapping()
        elif choice == '5':
            await setup_wizard()
        elif choice == '6':
            print("Exiting SilentGem. Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")
        
        # No longer pausing - just return to menu directly

async def main():
    """Main entry point for SilentGem"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='SilentGem - A Telegram translator by Dhillon Kannabhiran')
    parser.add_argument('--setup', action='store_true', help='Run the setup wizard')
    parser.add_argument('--version', action='store_true', help='Show version info')
    parser.add_argument('--service', action='store_true', help='Start the translation service without menu')
    parser.add_argument('--cleanup', action='store_true', help='Clean up session files and unlock database')
    parser.add_argument('--clear-mappings', action='store_true', help='Reset chat mappings when they cause issues')
    args = parser.parse_args()
    
    # Show ASCII banner
    print(SILENTGEM_ASCII)
    
    # Show version and exit if requested
    if args.version:
        from silentgem import __version__
        print(f"SilentGem v{__version__}")
        return
    
    # Handle cleanup request
    if args.cleanup:
        print("Performing cleanup operation...")
        print("\nThis will fix 'database is locked' and 'Cannot operate on a closed database' errors.")
        
        # Find session files and locks
        session_path = f"{SESSION_NAME}.session"
        session_files = glob.glob(f"{session_path}*")
        
        if not session_files:
            print("No session files found to clean up.")
            return
        
        print("\nCleanup options:")
        print("1. Full cleanup (backup and remove all session files - requires re-authentication)")
        print("2. Fix locks only (preserve authentication data, only remove lock files)")
        choice = input("\nEnter your choice (1/2): ").strip()
        
        if choice == "1":
            # Create backup directory
            backup_dir = "backups"
            ensure_dir_exists(backup_dir)
            
            # Backup and remove files
            backup_time = time.strftime("%Y%m%d-%H%M%S")
            backup_path = os.path.join(backup_dir, f"session-backup-{backup_time}")
            ensure_dir_exists(backup_path)
            
            print(f"\nFound {len(session_files)} session files to clean up:")
            for file in session_files:
                print(f" - {file}")
            
            for file in session_files:
                try:
                    filename = os.path.basename(file)
                    shutil.copy2(file, os.path.join(backup_path, filename))
                    print(f"Backed up: {file} -> {os.path.join(backup_path, filename)}")
                    
                    os.remove(file)
                    print(f"Removed: {file}")
                except Exception as e:
                    print(f"Error handling {file}: {e}")
            
            print(f"\n✅ Full cleanup completed. All session files have been backed up to {backup_path}")
            print("You will need to re-authenticate when you restart SilentGem.")
        
        elif choice == "2":
            # Only remove lock files, preserve the main session file
            lock_files = [f for f in session_files if f.endswith("-journal") or f.endswith("-wal") or f.endswith("-shm")]
            main_session = session_path
            
            if lock_files:
                print(f"\nFound {len(lock_files)} lock files to clean up:")
                for file in lock_files:
                    print(f" - {file}")
                    
                # Create backup directory for safety
                backup_dir = "backups"
                ensure_dir_exists(backup_dir)
                backup_time = time.strftime("%Y%m%d-%H%M%S")
                backup_path = os.path.join(backup_dir, f"locks-backup-{backup_time}")
                ensure_dir_exists(backup_path)
                
                # Remove lock files
                for file in lock_files:
                    try:
                        filename = os.path.basename(file)
                        shutil.copy2(file, os.path.join(backup_path, filename))
                        print(f"Backed up: {file} -> {os.path.join(backup_path, filename)}")
                        
                        os.remove(file)
                        print(f"Removed: {file}")
                    except Exception as e:
                        print(f"Error handling {file}: {e}")
                    
                print(f"\n✅ Lock files have been removed. Authentication data has been preserved.")
                print("You should be able to start SilentGem without re-authenticating.")
            else:
                print("No lock files found to clean up.")
        else:
            print("Invalid choice. Cleanup cancelled.")
        
        print("\nIf you had mappings set up, they are preserved in the data/mapping.json file.")
        return
    
    # Handle clear-mappings request
    if args.clear_mappings:
        print("🔄 Resetting chat mappings...")
        
        if os.path.exists(MAPPING_FILE):
            # Create backup directory
            backup_dir = "data/backups"
            ensure_dir_exists(backup_dir)
            
            # Backup and reset the mapping file
            backup_time = time.strftime("%Y%m%d-%H%M%S")
            backup_path = os.path.join(backup_dir, f"mapping-backup-{backup_time}.json")
            
            try:
                shutil.copy2(MAPPING_FILE, backup_path)
                print(f"✅ Backed up existing mappings to {backup_path}")
                
                # Reset mapping file to empty dict
                with open(MAPPING_FILE, "w") as f:
                    json.dump({}, f, indent=2)
                    
                print("✅ Chat mappings have been reset to empty")
                print("You can now run the setup wizard to create new mappings.")
            except Exception as e:
                print(f"❌ Error resetting mappings: {e}")
        else:
            print("No mapping file found. Creating a new empty mapping file.")
            ensure_dir_exists(os.path.dirname(MAPPING_FILE))
            with open(MAPPING_FILE, "w") as f:
                json.dump({}, f, indent=2)
            print("✅ Created new empty mapping file")
        
        return
    
    logger.info("Starting SilentGem")
    
    # Run setup wizard if explicitly requested
    if args.setup:
        logger.info("Setup flag provided, running setup wizard")
        success = await setup_wizard()
        if not success:
            logger.error("Setup wizard failed. Please try again.")
            return
    
    # Check if app is configured
    configured = await is_configured()
    
    if not configured:
        logger.info("SilentGem is not configured, running setup wizard")
        print("\nSilentGem needs to be configured. Running setup wizard...")
        
        success = await setup_wizard()
        if not success:
            logger.error("Setup wizard failed. Please try again.")
            return
            
        # Check configuration again after setup
        configured = await is_configured()
        if not configured:
            logger.error("Configuration is still invalid after setup. Please try again.")
            return
    
    # If service flag is provided, start translation service directly
    if args.service:
        client = SilentGemClient()
        try:
            await client.start()
            await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down")
        except Exception as e:
            logger.error(f"Error running SilentGem: {e}")
        finally:
            await client.stop()
            logger.info("SilentGem stopped")
        return
    
    # Otherwise, show interactive menu
    await interactive_mode()

if __name__ == "__main__":
    asyncio.run(main()) 