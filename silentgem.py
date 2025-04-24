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
import traceback
from pathlib import Path
from loguru import logger
import threading
from colorama import Fore, Style

from silentgem.config import validate_config, MAPPING_FILE, API_ID, API_HASH, GEMINI_API_KEY, SESSION_NAME, DATA_DIR, LOG_LEVEL
from silentgem.client import SilentGemClient, get_client
from silentgem.utils import ensure_dir_exists, get_chat_info
from silentgem.setup import setup_wizard, config_llm_settings, config_target_language
from silentgem.mapper import ChatMapper
from pyrogram import Client, errors
from pyrogram.enums import ChatType

# Import chat insights setup
from silentgem.setup.insights_setup import setup_insights, clear_insights_history, upgrade_existing_channels_for_insights
from silentgem.bot.telegram_bot import get_insights_bot
from silentgem.bot.command_handler import get_command_handler

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
        # First check if these are just normal SQLite journal files
        # If it's just a single -journal file and the main session file exists, this is likely normal
        if len(lock_files) == 1 and os.path.exists(session_path) and lock_files[0].endswith("-journal"):
            # Try to open the database to check if it's actually locked
            try:
                # Attempt to connect to the database - if it succeeds, the database is not locked
                conn = sqlite3.connect(session_path)
                conn.close()
                # Database is fine, no need to prompt
                print_debug(f"Found journal file '{os.path.basename(lock_files[0])}' but database is not locked.")
                return False
            except sqlite3.OperationalError as e:
                # Only show the prompt if there's an actual lock issue
                if "database is locked" in str(e):
                    print(f"Database lock detected: {e}")
                else:
                    # Some other SQLite error, but not a lock - no need to prompt
                    print_debug(f"Database journal present but error is not a lock: {e}")
                    return False
        
        # If we get here, either multiple lock files exist or we confirmed the database is locked
        print(f"Found {len(lock_files)} database lock files:")
        for lf in lock_files:
            print(f" - {os.path.basename(lf)}")
            
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

# Global shutdown flags
shutdown_in_progress = False
force_shutdown_requested = False
menu_return_requested = True  # Always default to returning to menu
shutdown_timer = None
interrupt_count = 0  # Initialize interrupt counter

# For clean shutdown
def signal_handler(sig, frame):
    """Handle interrupts and shutdown signals - SIMPLIFIED."""
    print("\n🛑 Interrupt received. Exiting SilentGem...")
    
    # Just exit immediately, no messing around
    os._exit(0)

def force_menu_return():
    """Force return to menu after timeout - called by timer"""
    print("\n⚠️ Shutdown taking too long, forcing return to menu...")
    
    # Try to stop the client one last time
    try:
        from silentgem.client import _instance, get_client
        if _instance:
            # Set all flags
            if hasattr(_instance, '_force_shutdown'):
                _instance._force_shutdown = True
            if hasattr(_instance, '_running'):
                _instance._running = False
                
            # Use a safer way to reset the instance
            import silentgem.client
            silentgem.client._instance = None
            print("✅ Client instance cleared")
    except Exception as e:
        print(f"⚠️ Error clearing client: {e}")
    
    # Create an emergency timer to hard exit in 5 more seconds if we're still stuck
    emergency_timer = threading.Timer(5.0, lambda: os._exit(1))
    emergency_timer.daemon = True
    emergency_timer.start()
    
    # Raise a KeyboardInterrupt in the main thread
    # This will break out of the asyncio.sleep() in the monitoring loop
    import _thread
    _thread.interrupt_main()

def handle_slow_shutdown():
    global shutdown_timer, menu_return_requested
    print("\n⚠️ Shutdown is taking longer than expected...")
    print("🔄 Returning to menu...")
    
    # Ensure we return to menu
    menu_return_requested = True
    
    # Cancel shutdown timer if it exists
    if shutdown_timer:
        shutdown_timer.cancel()
        shutdown_timer = None
    
    # Try cleanup operations but continue even if there are errors
    try:
        # Force client instance to stop if it exists
        from silentgem.client import _instance
        if _instance is not None:
            if hasattr(_instance, '_running'):
                _instance._running = False
            if hasattr(_instance, '_force_shutdown'):
                _instance._force_shutdown = True
            if hasattr(_instance, '_shutdown_future') and not _instance._shutdown_future.done():
                try:
                    _instance._shutdown_future.set_result(None)
                except Exception:
                    pass
                
        # Attempt emergency cleanup
        try:
            asyncio.run(cleanup())
        except Exception as e:
            print(f"Error during emergency cleanup: {e}")
            # Continue to menu even if cleanup fails
    except Exception as e:
        print(f"Error during slow shutdown handling: {e}")
        # Always continue to menu regardless of any errors
    
    # Final confirmation that we're returning to menu
    print("\n✅ Ready to return to menu. Press Enter if menu doesn't appear.")

# Modified to return to menu instead of exiting
def force_exit():
    global menu_return_requested, force_shutdown_requested
    print("\n⚠️ Forcing shutdown and returning to menu...")
    menu_return_requested = True
    force_shutdown_requested = True
    
    # Cancel any existing timer
    global shutdown_timer
    if shutdown_timer and shutdown_timer.is_alive():
        shutdown_timer.cancel()
    
    # Try to access any running client and force its running flag off
    try:
        from silentgem.client import _instance
        if _instance is not None and hasattr(_instance, '_running'):
            _instance._running = False
            if hasattr(_instance, '_force_shutdown'):
                _instance._force_shutdown = True
            if hasattr(_instance, '_shutdown_future') and not _instance._shutdown_future.done():
                _instance._shutdown_future.set_result(None)
                
        # Do a quick clean-up
        try:
            asyncio.create_task(cleanup())
        except Exception:
            pass
    except Exception:
        pass  # Ignore any errors
        
    # Do not set any emergency timers to exit the program

# Global variables for shutdown management
shutdown_in_progress = False
force_shutdown_requested = False
menu_return_requested = False

# Initialize the shutdown flag
signal_handler.shutdown_requested = False

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
    channel_name = f"silentgem-{source_chat['title']}"
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
        # Support both new naming convention "silentgem-X" and old "-silentgem" for backwards compatibility
        is_auto_created = channel.title.startswith("silentgem-") or "-silentgem" in channel.title
        
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

async def start_service(service=True, silent=False, load_from=None, monitoring_mode=False, return_to_menu=True):
    """
    Start the translation service with improved signal handling.
    
    Args:
        service: Whether this is being run in service mode
        silent: Whether to suppress output
        load_from: Optional path to load configuration from
        monitoring_mode: Whether to run in monitoring mode
        return_to_menu: Whether to return to the menu when done
        
    Returns:
        menu_return_requested: Boolean indicating if a return to menu was requested
    """
    # Declare all globals at the beginning to avoid syntax errors
    global menu_return_requested, force_shutdown_requested, shutdown_in_progress, shutdown_timer
    
    # Initialize variables to prevent scope issues
    shutdown_timer = None
    
    # Reset states at the start of a new session
    menu_return_requested = False
    force_shutdown_requested = False
    shutdown_in_progress = False
    signal_handler.shutdown_requested = False
    
    print("\n[INFO] Starting translation service. Press Ctrl+C to exit.")
    
    # Import client modules
    import silentgem.client
    from silentgem.client import SilentGemClient, get_client
    
    # Force clear any existing instance first
    if silentgem.client._instance is not None:
        try:
            existing_client = get_client()
            if existing_client:
                print("[INFO] Stopping previous client instance...")
                try:
                    # Force any existing instance to stop
                    existing_client._running = False
                    if hasattr(existing_client, '_force_shutdown'):
                        existing_client._force_shutdown = True
                    
                    # Wait briefly for graceful shutdown
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"[WARN] Error stopping previous client: {e}")
                
        except Exception as e:
            print(f"[WARN] Error accessing previous client: {e}")
        
        # Force clear the instance regardless
        silentgem.client._instance = None
    
    # Track the main event loop for proper shutdown
    main_loop = asyncio.get_event_loop()
    
    # Create a simpler signal handler that uses a direct approach
    def custom_signal_handler(sig, frame):
        print("\n🛑 Interrupt received. Shutting down service...")
        
        # We can access these variables directly since they're declared global at the function level
        global shutdown_timer
        
        # Set the signal handler flag
        signal_handler.shutdown_requested = True
        
        # Set menu return flag
        menu_return_requested = True
        
        # If already shutting down, force it
        if shutdown_in_progress:
            print("\n⚠️ Forcing shutdown now...")
            force_menu_return()
            return
            
        # Mark shutdown as in progress
        shutdown_in_progress = True
        
        # Create a timer to force return to menu if shutdown takes too long
        if shutdown_timer is None or not shutdown_timer.is_alive():
            shutdown_timer = threading.Timer(5.0, force_menu_return)
            shutdown_timer.daemon = True
            shutdown_timer.start()
    
    # Register our custom signal handler
    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGINT, custom_signal_handler)
    signal.signal(signal.SIGTERM, custom_signal_handler)
    
    try:
        # Create a new client instance
        runner = SilentGemClient()
        
        try:
            # Start the client
            await runner.start()
            print("\n✅ Service running. Press Ctrl+C to exit.")
            
            # Monitoring loop that checks for shutdown conditions
            while True:
                if signal_handler.shutdown_requested or menu_return_requested or force_shutdown_requested:
                    print("\n[INFO] Shutdown requested, stopping service...")
                    break
                
                try:
                    await asyncio.sleep(0.1)
                except KeyboardInterrupt:
                    print("\n🛑 Service interrupted. Exiting...")
                    menu_return_requested = True
                    break
                except asyncio.CancelledError:
                    print("\n🛑 Service operation cancelled.")
                    menu_return_requested = True
                    break
        
        except KeyboardInterrupt:
            print("\n🛑 Service interrupted. Exiting...")
            menu_return_requested = True
        
        finally:
            # Cleanup phase
            print("\n[INFO] Cleaning up...")
            
            # Stop the client
            try:
                if runner:
                    # Set all stop flags
                    runner._running = False
                    if hasattr(runner, '_force_shutdown'):
                        runner._force_shutdown = True
                    
                    # Wait briefly for graceful shutdown
                    await asyncio.sleep(0.5)
                    
                    # Clear instance reference
                    silentgem.client._instance = None
            except Exception as e:
                print(f"[WARN] Error during client cleanup: {e}")
            
            # Cancel any pending tasks in the event loop
            for task in asyncio.all_tasks(main_loop):
                if task is not asyncio.current_task():
                    task.cancel()
            
            # Cancel shutdown timer if it exists
            if shutdown_timer and hasattr(shutdown_timer, 'is_alive') and shutdown_timer.is_alive():
                shutdown_timer.cancel()
                shutdown_timer = None
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        menu_return_requested = True
    
    finally:
        # Restore original signal handlers
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)
        
        # Ensure we're leaving with clean state
        if silentgem.client._instance is not None:
            silentgem.client._instance = None
            
        # Final cleanup - avoid recursive calls
        try:
            # Only run cleanup if this isn't already part of a cleanup call
            if not getattr(start_service, '_in_cleanup', False):
                start_service._in_cleanup = True
                await cleanup()
                start_service._in_cleanup = False
        except Exception as e:
            print(f"[WARN] Error during final cleanup: {e}")
    
    print("\n[INFO] Service stopped.")
    
    # Always return to menu unless specifically set not to
    return menu_return_requested

async def display_menu():
    """Display the interactive menu"""
    # Reset signal handler state before showing menu
    signal_handler.shutdown_requested = False
    
    print("\n==== SilentGem Main Menu ====")
    print("1. Start Translation Service")
    print("2. List Current Mappings")
    print("3. List Available Chats & Channels")
    print("4. Remove Mapping")
    print("5. Run Setup Wizard")
    print("6. Update LLM Settings")
    print("7. Update Target Language")
    print("8. Chat Insights Settings")
    print("9. Exit")
    print("============================")
    
    choice = input("Enter your choice (1-9): ").strip()
    return choice

async def interactive_mode():
    """Run the app in interactive mode with a menu"""
    
    while True:
        try:
            print("\n==== SilentGem Main Menu ====")
            print("1. Start Translation Service")
            print("2. List Current Mappings")
            print("3. List Available Chats & Channels")
            print("4. Remove Mapping")
            print("5. Run Setup Wizard")
            print("6. Update LLM Settings")
            print("7. Update Target Language")
            print("8. Chat Insights Settings")
            print("9. Exit")
            print("============================")
            
            choice = input("Enter your choice (1-9): ").strip()
            
            if choice == '1':
                print("\n[INFO] Starting translation service. Press Ctrl+C to exit.")
                
                # Just exit the program when the service exits
                # This will completely bypass the menu
                await start_service()
                # start_service will exit the program, so we won't get here
                
            elif choice == '2':
                await list_mappings()
            elif choice == '3':
                await list_available_chats()
            elif choice == '4':
                await interactive_remove_mapping()
            elif choice == '5':
                # Use the imported setup_wizard directly
                await setup_wizard()
            elif choice == '6':
                # Use the imported config_llm_settings directly
                await config_llm_settings()
            elif choice == '7':
                # Use the imported config_target_language directly
                await config_target_language()
            elif choice == '8':
                # Chat Insights settings
                await setup_insights()
            elif choice == '9':
                print("Exiting SilentGem. Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please try again.")
                
            # Small pause before showing menu again
            await asyncio.sleep(0.2)
        except KeyboardInterrupt:
            # Handle Ctrl+C during menu display
            print("\n⚠️ Interrupted, returning to menu...")
            continue
        except Exception as e:
            print(f"\n❌ An error occurred: {e}")
            logger.error(f"Error in interactive mode: {e}")
            await asyncio.sleep(1)  # Pause to avoid tight error loop

def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='SilentGem - A Telegram translator by Dhillon Kannabhiran.\nRuns in interactive menu mode by default.')
    parser.add_argument('--setup', action='store_true', help='Run the setup wizard')
    parser.add_argument('--version', action='store_true', help='Show version info')
    parser.add_argument('--service', action='store_true', help='Start the translation service directly without showing the interactive menu')
    parser.add_argument('--no-menu', action='store_true', help='Same as --service: run in service mode without interactive menu')
    parser.add_argument('--cleanup', action='store_true', help='Clean up session files and unlock database')
    parser.add_argument('--clear-mappings', action='store_true', help='Reset chat mappings when they cause issues')
    parser.add_argument('--config-llm', action='store_true', help='Update LLM/translator settings only')
    parser.add_argument('--config-language', action='store_true', help='Update target language setting only')
    parser.add_argument('--setup-insights', action='store_true', help='Configure Chat Insights feature')
    parser.add_argument('--clear-insights-history', action='store_true', help='Clear stored message history used for Chat Insights')
    parser.add_argument('--upgrade-insights', action='store_true', help='Upgrade existing channels to support Chat Insights')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    return parser.parse_args()

async def main():
    """Main entry point for SilentGem"""
    # Get command-line arguments
    args = parse_arguments()

    # Initialize logging with appropriate level
    init_logging(args.verbose)

    # Initialize data directory
    init_data_directory()
    
    # Show ASCII banner
    print(SILENTGEM_ASCII)
    
    # Show version and exit if requested
    if args.version:
        from silentgem import __version__
        print(f"SilentGem v{__version__}")
        return
    
    # Handle specific command-line flags that exit after execution
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
    
    if args.config_llm:
        success = await config_llm_settings()
        if success:
            print("LLM configuration updated successfully.")
        else:
            print("Failed to update LLM configuration.")
        return
    
    if args.config_language:
        success = await config_target_language()
        if success:
            print("Target language updated successfully.")
        else:
            print("Failed to update target language.")
        return
    
    if args.upgrade_insights:
        success = await upgrade_existing_channels_for_insights()
        if success:
            print("✅ Existing channels have been checked and instructions sent for adding the Chat Insights bot.")
        else:
            print("❌ Failed to upgrade existing channels for Chat Insights.")
        return
    
    if args.setup_insights:
        # Configure Chat Insights
        await setup_insights()
        return
        
    if args.clear_insights_history:
        # Clear insights history
        await clear_insights_history()
        return
    
    logger.info("Starting SilentGem")
    
    # Run setup wizard if explicitly requested or if not configured
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
    
    # Check if is first run for v1.1 or v1.2 (check version file)
    try:
        version_upgrade_file = os.path.join(DATA_DIR, "version_upgraded.txt")
        is_first_v11_run = False
        is_first_v12_run = False
        
        # Version file doesn't exist, so this is the first run of any version
        if not os.path.exists(version_upgrade_file):
            is_first_v11_run = True
            is_first_v12_run = True
        else:
            with open(version_upgrade_file, "r") as f:
                content = f.read().strip()
                if "1.1.0" not in content:
                    is_first_v11_run = True
                if "1.2.0" not in content:
                    is_first_v12_run = True
                    
        # If this is the first run of v1.1, check existing channels and upgrade them
        if is_first_v11_run:
            logger.info("First run of v1.1.0 detected. Checking for existing channels to upgrade...")
            try:
                from silentgem.config.insights_config import is_insights_configured
                
                # Only auto-upgrade if insights is configured
                if is_insights_configured():
                    await upgrade_existing_channels_for_insights()
                
                # Mark as upgraded
                with open(version_upgrade_file, "w") as f:
                    f.write("1.1.0\n")
            except Exception as e:
                logger.error(f"Error during v1.1.0 upgrade check: {e}")
                
        # If this is the first run of v1.2, perform 1.2-specific upgrades
        if is_first_v12_run:
            logger.info("First run of v1.2.0 detected. Applying v1.2.0 upgrades...")
            try:
                # Perform v1.2.0 specific upgrades here if needed
                
                # Mark as upgraded - append to file
                with open(version_upgrade_file, "a") as f:
                    f.write("1.2.0\n")
                    
                logger.info("Successfully applied v1.2.0 upgrades")
            except Exception as e:
                logger.error(f"Error during v1.2.0 upgrade check: {e}")
    except Exception as e:
        logger.error(f"Error checking version upgrade status: {e}")
    
    # Initialize client
    client = SilentGemClient()
    
    # SERVICE MODE: If service flag or no-menu flag is provided, start translation service directly
    if args.service or args.no_menu:
        print("\n[INFO] Starting in service mode (non-interactive)")
        try:
            await client.start()
            await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down")
            print("\nService stopped by user. Shutting down...")
        except Exception as e:
            logger.error(f"Error running SilentGem: {e}")
            print(f"\nError: {e}")
        finally:
            await client.stop()
            logger.info("SilentGem stopped")
        return
    
    # INTERACTIVE MODE (DEFAULT): No special flags provided, run in interactive menu mode
    try:
        # Skip starting the client - we'll do this only when the user selects option 1
        # This ensures we don't enter service mode by default
        
        # Start the insights bot if configured
        from silentgem.config.insights_config import is_insights_configured
        if is_insights_configured():
            try:
                # Initialize command handler and bot
                insights_bot = get_insights_bot()
                command_handler = get_command_handler()
                
                # Link the command handler to the bot
                insights_bot.set_command_handler(command_handler)
                
                # Start the bot
                await insights_bot.start()
                logger.info("Chat Insights bot started successfully")
            except Exception as e:
                logger.error(f"Failed to start Chat Insights bot: {e}")
        
        # Show interactive menu - this is the default behavior
        print("\n[INFO] Starting in interactive mode")
        await interactive_mode()
    except Exception as e:
        logger.error(f"Error in interactive mode: {e}")
        print(f"\nError in interactive mode: {e}")
    finally:
        # Make sure any resources are properly cleaned up
        await cleanup()

async def cleanup():
    """Clean up resources on exit"""
    # Stop the translation client
    try:
        # Import here to ensure we have the latest version
        from silentgem.client import _instance
        
        # Only stop if an instance already exists, don't create one
        if _instance is not None:
            await _instance.stop_client()
            logger.info("Translation client stopped")
        else:
            logger.info("No translation client instance to stop")
    except Exception as e:
        logger.error(f"Error stopping translation client: {e}")
        
    # Stop the insights bot if running
    try:
        from silentgem.config.insights_config import is_insights_configured
        
        if is_insights_configured():
            from silentgem.bot.telegram_bot import get_insights_bot
            insights_bot = get_insights_bot()
            await insights_bot.stop()
            logger.info("Chat Insights bot stopped")
    except Exception as e:
        logger.error(f"Error stopping insights bot: {e}")

def init_logging(verbose=False):
    """Initialize logging with appropriate level"""
    # Set log level based on verbose flag
    log_level = "DEBUG" if verbose else LOG_LEVEL
    
    # Configure logger
    logger.remove()
    
    # File logging with full information (unchanged)
    logger.add(
        "logs/silentgem.log",
        rotation="10 MB",
        level=log_level,
        backtrace=True,
        diagnose=True,
    )
    
    # Custom print handler with line break control
    def custom_print_handler(message):
        # Remove trailing newlines and print with controlled formatting
        msg = message.rstrip()
        # Only add line break before certain messages that represent transitions
        if any(marker in msg for marker in [
            "Starting in", 
            "==== SilentGem", 
            "Waiting for messages",
            "Client stopped",
            "Keyboard interrupt",
            "Exiting SilentGem",
            "Setup wizard"
        ]):
            print(f"\n{msg}")
        else:
            print(msg)
    
    # Console logging with level prefix but no other metadata
    logger.add(
        custom_print_handler, 
        level=log_level,
        format="[{level.name}] {message}"
    )
    
    if verbose:
        logger.debug("Verbose logging enabled")

def init_data_directory():
    """Initialize the data directory"""
    # Ensure data directory exists
    ensure_dir_exists(DATA_DIR)
    ensure_dir_exists(os.path.dirname(MAPPING_FILE))

if __name__ == "__main__":
    try:
        asyncio.run(main()) 
    except KeyboardInterrupt:
        # Handle keyboard interrupt
        print("\nShutting down SilentGem...")
        asyncio.run(cleanup())
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        # Ensure cleanup happens even on unhandled exceptions
        asyncio.run(cleanup())
        sys.exit(1) 