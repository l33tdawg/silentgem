"""
Command-line interface for SilentGem
"""

import os
import json
import asyncio
import argparse
from loguru import logger

from silentgem.mapper import ChatMapper
from silentgem.utils import get_chat_info, ensure_dir_exists
from silentgem.setup import setup_wizard
from silentgem.config import API_ID, API_HASH, SESSION_NAME

from pyrogram import Client, errors

async def list_mappings():
    """List all current chat mappings"""
    mapper = ChatMapper()
    mappings = mapper.get_all()
    
    if not mappings:
        print("No chat mappings found.")
        return
    
    print(f"\nCurrent Chat Mappings ({len(mappings)}):")
    print("-" * 80)
    
    for source_id, target_id in mappings.items():
        # Try to get chat info
        source_info = await get_chat_info(source_id)
        target_info = await get_chat_info(target_id)
        
        source_name = source_info["title"] if source_info else f"Unknown Chat ({source_id})"
        target_name = target_info["title"] if target_info else f"Unknown Channel ({target_id})"
        
        print(f"Source: {source_name} ({source_id})")
        print(f"Target: {target_name} ({target_id})")
        print("-" * 80)

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

async def list_available_chats():
    """List all available chats in your Telegram account"""
    print("Connecting to Telegram to retrieve your chats...")
    
    client = Client(
        SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH
    )
    
    try:
        await client.start()
        print("\n✅ Successfully connected to Telegram")
        
        # Get available dialogs (chats)
        print("\nRetrieving your chats (this may take a moment)...")
        available_chats = []
        available_channels = []
        
        async for dialog in client.get_dialogs():
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
                
                if chat.type == "channel":
                    available_channels.append(chat_info)
                else:
                    available_chats.append(chat_info)
        
        # Display available source chats (groups and supergroups)
        if available_chats:
            print(f"\nAvailable Source Chats (Groups) - {len(available_chats)}:")
            print("-" * 80)
            for i, chat in enumerate(available_chats, 1):
                chat_type = chat["type"]
                username = f" (@{chat['username']})" if chat["username"] else ""
                print(f"{i}. [{chat_type}] {chat['title']}{username} (ID: {chat['id']})")
        else:
            print("\n❌ No groups found in your account.")
            print("You need to join some groups first to monitor them for translation.")
        
        # Display available target channels
        if available_channels:
            print(f"\nAvailable Target Channels - {len(available_channels)}:")
            print("-" * 80)
            for i, chat in enumerate(available_channels, 1):
                username = f" (@{chat['username']})" if chat["username"] else ""
                print(f"{i}. {chat['title']}{username} (ID: {chat['id']})")
        else:
            print("\n❌ No channels found in your account.")
            print("You need to create some channels first to receive translations.")
        
        # Ask if user wants to add a mapping
        if available_chats and available_channels:
            print("\nWould you like to add a new chat mapping? (y/n)")
            choice = input("> ").strip().lower()
            
            if choice == 'y':
                await interactive_add_mapping(available_chats, available_channels)
        
    except errors.RPCError as e:
        print(f"\n❌ Error retrieving chats: {e}")
    finally:
        await client.stop()

async def interactive_add_mapping(source_chats, target_channels):
    """Add a mapping interactively by selecting from lists"""
    # Ask for source chat
    print("\nSelect a source chat to monitor (enter the number):")
    source_choice = input("> ").strip()
    
    try:
        source_idx = int(source_choice) - 1
        if source_idx < 0 or source_idx >= len(source_chats):
            print("❌ Invalid selection.")
            return
        
        source_chat = source_chats[source_idx]
        
        # Ask for target channel
        print(f"\nSelected source: {source_chat['title']}")
        print("\nSelect a target channel for translations (enter the number):")
        target_choice = input("> ").strip()
        
        target_idx = int(target_choice) - 1
        if target_idx < 0 or target_idx >= len(target_channels):
            print("❌ Invalid selection.")
            return
        
        target_channel = target_channels[target_idx]
        
        # Add the mapping
        mapper = ChatMapper()
        mapper.add(source_chat["id"], target_channel["id"])
        
        print(f"\n✅ Added mapping: {source_chat['title']} -> {target_channel['title']}")
        
    except ValueError:
        print("❌ Invalid input. Please enter a number.")
    except Exception as e:
        print(f"❌ Error adding mapping: {e}")

async def run_cli():
    """Run the CLI interface"""
    parser = argparse.ArgumentParser(description='SilentGem CLI')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Run the setup wizard')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all chat mappings')
    
    # List chats command
    list_chats_parser = subparsers.add_parser('chats', help='List all available chats and channels')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new chat mapping')
    add_parser.add_argument('source_id', help='Source chat ID')
    add_parser.add_argument('target_id', help='Target channel ID')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove a chat mapping')
    remove_parser.add_argument('source_id', help='Source chat ID to remove')
    
    args = parser.parse_args()
    
    # Ensure necessary directories exist
    ensure_dir_exists("data")
    ensure_dir_exists("logs")
    
    if args.command == 'setup':
        await setup_wizard()
    elif args.command == 'list':
        await list_mappings()
    elif args.command == 'chats':
        await list_available_chats()
    elif args.command == 'add':
        await add_mapping(args.source_id, args.target_id)
    elif args.command == 'remove':
        await remove_mapping(args.source_id)
    else:
        parser.print_help()

def main():
    """Entry point for CLI"""
    asyncio.run(run_cli())

if __name__ == "__main__":
    main() 