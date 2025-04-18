"""
Interactive setup wizard for SilentGem
"""

import os
import json
import asyncio
from pathlib import Path
from getpass import getpass
from pyrogram import Client, errors
from loguru import logger

from silentgem.utils import ensure_dir_exists

async def setup_wizard():
    """
    Run the interactive setup wizard to configure SilentGem
    """
    print("\n=== SilentGem Setup Wizard ===\n")
    print("This wizard will help you set up SilentGem with your Telegram account and Google Gemini API key.")
    print("You'll need to provide your Telegram API credentials from https://my.telegram.org/apps")
    
    # Ensure necessary directories exist
    ensure_dir_exists("data")
    ensure_dir_exists("logs")
    
    # Get API credentials
    telegram_api_id = input("\nEnter your Telegram API ID: ").strip()
    # Validate API ID is a number
    try:
        int(telegram_api_id)
    except ValueError:
        print("❌ API ID must be a number. Please try again.")
        return False
        
    telegram_api_hash = input("Enter your Telegram API Hash: ").strip()
    if not telegram_api_hash:
        print("❌ API Hash cannot be empty. Please try again.")
        return False
        
    gemini_api_key = input("Enter your Google Gemini API key: ").strip()
    if not gemini_api_key:
        print("❌ Gemini API key cannot be empty. Please try again.")
        return False
        
    session_name = input("Enter a session name (or press Enter for 'silentgem'): ").strip() or "silentgem"
    target_language = input("Enter your preferred target language (or press Enter for 'english'): ").strip() or "english"
    
    # Try to log in and get chat list
    print("\nLogging in to Telegram to retrieve your chats...")
    client = Client(
        session_name,
        api_id=int(telegram_api_id),
        api_hash=telegram_api_hash,
        workdir=str(Path("."))
    )
    
    try:
        await client.start()
        print("\n✅ Successfully logged in!")
        
        # Save .env file only after successful login
        await save_env_file(
            telegram_api_id, 
            telegram_api_hash, 
            gemini_api_key,
            session_name,
            target_language
        )
        
        # Get chat mappings
        await setup_chat_mappings(client)
        
    except errors.BadRequest as e:
        print(f"\n❌ Invalid credentials: {e}")
        return False
    except errors.RPCError as e:
        print(f"\n❌ Error logging in: {e}")
        return False
    finally:
        await client.stop()
    
    # Verify the .env file was created properly
    if not os.path.exists(".env"):
        print("\n❌ Failed to create .env file.")
        return False
        
    print("\n🎉 Setup complete! You can now run SilentGem with: python silentgem.py")
    return True

async def save_env_file(api_id, api_hash, gemini_key, session_name, target_language):
    """Save API credentials to .env file"""
    env_content = f"""# Telegram API credentials
TELEGRAM_API_ID={api_id}
TELEGRAM_API_HASH={api_hash}

# Google Gemini API key
GEMINI_API_KEY={gemini_key}

# Mapping file path (default: data/mapping.json)
MAPPING_FILE=data/mapping.json

# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO

# Target language for translations (default: english)
TARGET_LANGUAGE={target_language}

# Session file name
SESSION_NAME={session_name}
"""
    
    try:
        with open(".env", "w") as f:
            f.write(env_content)
        print("\n✅ Saved API credentials to .env file")
        return True
    except Exception as e:
        print(f"\n❌ Error saving .env file: {e}")
        return False

async def setup_chat_mappings(client):
    """
    Set up chat mappings by letting the user select source and target chats
    """
    # Get available dialogs (chats)
    print("\nRetrieving your chats (this may take a moment)...")
    available_chats = []
    
    try:
        # Use a timeout for get_dialogs to ensure it doesn't hang
        dialogs = []
        async for dialog in client.get_dialogs(limit=100):
            dialogs.append(dialog)
        
        for dialog in dialogs:
            chat = dialog.chat
            if chat.type in ["group", "supergroup", "channel"]:
                # Skip empty titles
                if not getattr(chat, "title", "").strip():
                    continue
                    
                chat_info = {
                    "id": chat.id,
                    "title": chat.title,
                    "type": chat.type,
                    "username": getattr(chat, "username", None)
                }
                available_chats.append(chat_info)
    except Exception as e:
        print(f"\n⚠️ Error retrieving chats: {e}")
    
    if not available_chats:
        print("\n⚠️ No groups or channels found in your account. You'll need to join some groups or create channels first.")
        print("You can manually configure chat mappings later using the CLI tool:")
        print("./silentgem-cli add SOURCE_CHAT_ID TARGET_CHANNEL_ID")
        
        # Create an empty mapping file
        with open("data/mapping.json", "w") as f:
            json.dump({}, f, indent=2)
            
        print("\n✅ Created empty mapping file data/mapping.json")
        return
    
    print(f"\nFound {len(available_chats)} groups and channels:")
    
    # Display available chats
    for i, chat in enumerate(available_chats, 1):
        chat_type = chat["type"]
        username = f" (@{chat['username']})" if chat["username"] else ""
        print(f"{i}. [{chat_type}] {chat['title']}{username} (ID: {chat['id']})")
    
    # Ask which chats to monitor
    print("\nNow select which chats you want to monitor for translation")
    print("Enter the numbers (comma-separated) or 'q' to quit:")
    
    selection = input("> ").strip()
    if selection.lower() == 'q':
        # Create an empty mapping file
        with open("data/mapping.json", "w") as f:
            json.dump({}, f, indent=2)
        print("\n✅ Created empty mapping file data/mapping.json")
        return
    
    # Process selection
    selected_indices = []
    try:
        for item in selection.split(","):
            idx = int(item.strip()) - 1
            if 0 <= idx < len(available_chats):
                selected_indices.append(idx)
    except ValueError:
        print("Invalid selection, using no chats.")
        selected_indices = []
    
    if not selected_indices:
        print("No chats selected.")
        # Create an empty mapping file
        with open("data/mapping.json", "w") as f:
            json.dump({}, f, indent=2)
        print("\n✅ Created empty mapping file data/mapping.json")
        return
    
    # Create mapping
    mapping = {}
    
    print("\nFor each selected chat, enter the ID of the channel where translations should be sent")
    print("You can create a new private channel in Telegram for each source.")
    
    for idx in selected_indices:
        source_chat = available_chats[idx]
        print(f"\nFor '{source_chat['title']}':")
        
        print("Available target channels:")
        
        # Display potential target channels (private channels are best)
        target_channels = [c for c in available_chats if c["type"] == "channel"]
        for i, chat in enumerate(target_channels, 1):
            username = f" (@{chat['username']})" if chat["username"] else ""
            print(f"{i}. {chat['title']}{username} (ID: {chat['id']})")
        
        print("\nEnter the number of the target channel, or the channel ID directly:")
        target_input = input("> ").strip()
        
        # Process target input
        try:
            if target_input.isdigit() and 1 <= int(target_input) <= len(target_channels):
                # User entered a number from the list
                target_idx = int(target_input) - 1
                target_chat = target_channels[target_idx]
                target_id = target_chat["id"]
            else:
                # User entered a channel ID directly
                target_id = target_input
                
            # Add to mapping
            mapping[str(source_chat["id"])] = str(target_id)
            print(f"✅ Added mapping: '{source_chat['title']}' -> Channel ID {target_id}")
            
        except (ValueError, IndexError):
            print(f"❌ Invalid selection for '{source_chat['title']}', skipping.")
    
    # Save mapping
    if mapping:
        with open("data/mapping.json", "w") as f:
            json.dump(mapping, f, indent=2)
        
        print(f"\n✅ Saved {len(mapping)} chat mappings to data/mapping.json")
    else:
        # Create an empty mapping file
        with open("data/mapping.json", "w") as f:
            json.dump({}, f, indent=2)
        print("\n✅ Created empty mapping file data/mapping.json") 