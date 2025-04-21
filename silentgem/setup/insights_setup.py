"""
Setup wizard for Chat Insights feature
"""

import os
import asyncio
import time
from pathlib import Path
from loguru import logger

from pyrogram import Client

from silentgem.config import API_ID, API_HASH, SESSION_NAME, ensure_dir_exists
from silentgem.config.insights_config import get_insights_config, is_insights_configured
from silentgem.database.message_store import get_message_store
from silentgem.bot.telegram_bot import get_insights_bot

class InsightsSetup:
    """Setup wizard for Chat Insights feature"""
    
    def __init__(self):
        """Initialize the setup wizard"""
        self.config = get_insights_config()
        self.message_store = get_message_store()
    
    async def run_setup(self):
        """Run the setup wizard"""
        print("\n=== Chat Insights Setup ===")
        print("This will help you set up the Chat Insights feature for SilentGem.")
        print("This feature allows you to query your translation history using natural language.")
        print("You will need to create a Telegram bot and add it to your target channels.")
        
        # Check if already configured
        if self.config.is_configured():
            print("\nChat Insights is already configured.")
            if not await self._prompt_yes_no("Do you want to update the configuration?", default=False):
                return True
        
        # Bot token
        await self._setup_bot_token()
        
        # Storage settings
        await self._setup_storage()
        
        # Query processing
        await self._setup_query_processing()
        
        # Privacy settings
        await self._setup_privacy()
        
        # Response formatting
        await self._setup_response_formatting()
        
        print("\n✅ Chat Insights configuration complete!")
        print("The bot will now be automatically added to all your target channels.")
        
        # Add bot to all target channels
        await self._add_bot_to_channels()
        
        return True
    
    async def _setup_bot_token(self):
        """Set up the bot token"""
        print("\n--- Bot Setup ---")
        print("You need to create a bot on Telegram using @BotFather:")
        print("1. Open Telegram and search for @BotFather")
        print("2. Send /newbot command")
        print("3. Follow the instructions to create a bot")
        print("   - Suggested name: SilentAsk")
        print("   - Suggested username: silentask_bot (or any name ending with 'bot')")
        print("4. BotFather will give you a token (like 123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ)")
        
        current_token = self.config.get("bot_token", "")
        if current_token:
            print(f"\nCurrent bot token: {current_token[:5]}...{current_token[-5:]}")
            if not await self._prompt_yes_no("Do you want to use a different bot?", default=False):
                return
        
        while True:
            token = await self._prompt("Enter your bot token from BotFather")
            if token and ":" in token and len(token) > 20:
                # Test the token
                print("Testing bot token...")
                try:
                    # Try to create a temporary bot client to test the token
                    bot = Client(
                        "temp_bot_test",
                        api_id=API_ID,
                        api_hash=API_HASH,
                        bot_token=token,
                        in_memory=True
                    )
                    await bot.start()
                    me = await bot.get_me()
                    await bot.stop()
                    
                    print(f"✅ Token validated! Bot name: @{me.username}")
                    
                    # Save the token and username
                    self.config.set("bot_token", token)
                    self.config.set("bot_username", me.username)
                    self.config.set("bot_name", me.first_name)
                    
                    print(f"Bot credentials saved.")
                    return
                except Exception as e:
                    print(f"❌ Invalid bot token: {e}")
                    if not await self._prompt_yes_no("Try again?", default=True):
                        return
            else:
                print("❌ Invalid token format. Make sure it contains ':' and is at least 20 characters.")
                if not await self._prompt_yes_no("Try again?", default=True):
                    return
    
    async def _setup_storage(self):
        """Set up storage settings"""
        print("\n--- Storage Settings ---")
        
        # Message retention
        print("\nHow long do you want to keep messages in the database?")
        print("1. 30 days")
        print("2. 90 days")
        print("3. 1 year")
        print("4. Unlimited (default)")
        
        retention_choice = await self._prompt("Select an option (1-4)", default="4")
        retention_days = {
            "1": 30,
            "2": 90,
            "3": 365,
            "4": 0  # Unlimited
        }.get(retention_choice, 0)
        
        self.config.set("message_retention_days", retention_days)
        
        # Database location (advanced, keep default for most users)
        default_db_path = str(Path(os.path.join("data", "messages.db")))
        db_path = await self._prompt(
            "Database path (press Enter for default)",
            default=default_db_path
        )
        self.config.set("storage_location", db_path)
        
        # Backup frequency
        backup_days = await self._prompt(
            "How often to create database backups (days, 0 for no backups)",
            default="7"
        )
        try:
            backup_days = int(backup_days)
            self.config.set("backup_frequency_days", backup_days)
        except ValueError:
            print("Invalid number, using default (7 days)")
            self.config.set("backup_frequency_days", 7)
    
    async def _setup_query_processing(self):
        """Set up query processing settings"""
        print("\n--- Query Processing Settings ---")
        
        # Use translation LLM or separate LLM
        use_translation_llm = await self._prompt_yes_no(
            "Use the same LLM for query processing as translation?",
            default=True
        )
        self.config.set("use_translation_llm", use_translation_llm)
        
        # Query processing depth
        print("\nQuery processing depth determines how much AI processing is used:")
        print("1. Basic - Simple keyword matching (fastest)")
        print("2. Standard - Better understanding of natural language (default)")
        print("3. Detailed - Advanced analysis with topic detection (uses more tokens)")
        
        depth_choice = await self._prompt("Select an option (1-3)", default="2")
        depth = {
            "1": "basic",
            "2": "standard",
            "3": "detailed"
        }.get(depth_choice, "standard")
        
        self.config.set("query_processing_depth", depth)
    
    async def _setup_privacy(self):
        """Set up privacy settings"""
        print("\n--- Privacy Settings ---")
        
        # Store full content
        store_full = await self._prompt_yes_no(
            "Store full message content? (No = store only metadata)",
            default=True
        )
        self.config.set("store_full_content", store_full)
        
        # Anonymize senders
        anonymize = await self._prompt_yes_no(
            "Anonymize sender information?",
            default=False
        )
        self.config.set("anonymize_senders", anonymize)
        
        # Encrypt sensitive data
        encrypt = await self._prompt_yes_no(
            "Encrypt sensitive data? (adds extra processing)",
            default=False
        )
        self.config.set("encrypt_sensitive_data", encrypt)
        
        # Auto-purge
        auto_purge = await self._prompt_yes_no(
            "Automatically purge old messages? (based on retention period)",
            default=False
        )
        self.config.set("auto_purge_enabled", auto_purge)
    
    async def _setup_response_formatting(self):
        """Set up response formatting settings"""
        print("\n--- Response Formatting Settings ---")
        
        # Verbosity
        print("\nHow verbose should responses be?")
        print("1. Concise - Brief bullet points")
        print("2. Standard - Normal paragraphs (default)")
        print("3. Detailed - Comprehensive answers")
        
        verbosity_choice = await self._prompt("Select an option (1-3)", default="2")
        verbosity = {
            "1": "concise",
            "2": "standard",
            "3": "detailed"
        }.get(verbosity_choice, "standard")
        
        self.config.set("response_verbosity", verbosity)
        
        # Include quotes
        include_quotes = await self._prompt_yes_no(
            "Include original message quotes in responses?",
            default=True
        )
        self.config.set("include_quotes", include_quotes)
        
        # Include timestamps
        include_timestamps = await self._prompt_yes_no(
            "Include timestamps in responses?",
            default=True
        )
        self.config.set("include_timestamps", include_timestamps)
        
        # Include sender info
        include_sender_info = await self._prompt_yes_no(
            "Include sender information in responses?",
            default=True
        )
        self.config.set("include_sender_info", include_sender_info)
    
    async def _add_bot_to_channels(self):
        """Add the bot to all target channels"""
        from silentgem.config import load_mapping
        from silentgem.client import SilentGemClient
        
        # Get the mapping of source chats to target chats
        mapping = load_mapping()
        if not mapping:
            print("No chat mappings found. Please set up chat mappings first.")
            return
        
        # Get bot username
        bot_username = self.config.get("bot_username")
        if not bot_username:
            print("Bot username not found. Please set up the bot first.")
            return
        
        # Create a temporary client instance
        client = SilentGemClient()
        
        try:
            # Start the client
            await client.start()
            
            # For each target chat, send instructions to add the bot
            target_chats = set(mapping.values())
            print(f"\nFound {len(target_chats)} target chats to add the bot to:")
            
            for target_chat_id in target_chats:
                try:
                    # Get the chat info
                    chat = await client.client.get_chat(target_chat_id)
                    chat_title = getattr(chat, "title", target_chat_id)
                    
                    print(f"\n- Adding bot to {chat_title} ({target_chat_id})")
                    
                    # Send instructions
                    instructions = f"""
                    📱 **Chat Insights Bot Setup**
                    
                    To use the chat insights feature, please add @{bot_username} to this chat:
                    
                    1. Open Telegram and go to this chat
                    2. Tap the chat name at the top
                    3. Select "Add members"
                    4. Search for @{bot_username}
                    5. Tap the bot to add it
                    
                    Once added, you can ask questions about past conversations by:
                    - Using the /askgem command followed by your question
                    - Or just typing your question to the bot
                    
                    Example: `/askgem What was discussed about APIs yesterday?`
                    """
                    
                    await client.client.send_message(
                        chat_id=target_chat_id,
                        text=instructions.strip()
                    )
                    print(f"✅ Sent instructions for chat {chat_title}")
                    
                except Exception as e:
                    print(f"❌ Failed to send instructions to chat {target_chat_id}: {e}")
        
        except Exception as e:
            print(f"❌ Error during bot setup: {e}")
        finally:
            # Stop the client
            await client.stop()
    
    async def _prompt(self, question, default=None):
        """Prompt the user for input"""
        default_text = f" [{default}]" if default else ""
        response = input(f"{question}{default_text}: ").strip()
        if not response and default is not None:
            return default
        return response
    
    async def _prompt_yes_no(self, question, default=True):
        """Prompt the user for a yes/no question"""
        default_text = "Y/n" if default else "y/N"
        response = input(f"{question} [{default_text}]: ").strip().lower()
        if not response:
            return default
        return response.startswith("y")


async def setup_insights():
    """Run the insights setup wizard"""
    return await InsightsSetup().run_setup()

async def clear_insights_history():
    """Clear all stored message history"""
    print("\n=== Clear Chat Insights History ===")
    print("This will permanently delete all stored message history.")
    print("This action cannot be undone.")
    
    confirmation = input("Type 'DELETE' to confirm: ").strip()
    if confirmation != "DELETE":
        print("Operation cancelled.")
        return False
    
    try:
        message_store = get_message_store()
        result = message_store.clear_all_messages()
        if result:
            print("✅ All message history has been cleared.")
            return True
        else:
            print("❌ Failed to clear message history.")
            return False
    except Exception as e:
        print(f"❌ Error clearing message history: {e}")
        return False

async def upgrade_existing_channels_for_insights():
    """
    Upgrade existing chat mappings to support Chat Insights
    This function is called when a user upgrades to v1.1
    """
    try:
        print("\n=== Upgrading Existing Channels for Chat Insights ===")
        print("This will check your existing target channels and add the Chat Insights bot to them.")
        
        # Check if insights is configured
        if not is_insights_configured():
            print("\nChat Insights is not yet configured. Please run --setup-insights first.")
            return False
        
        # Get the bot username
        config = get_insights_config()
        bot_username = config.get("bot_username")
        
        if not bot_username:
            print("\nNo Chat Insights bot configured. Please run --setup-insights first.")
            return False
            
        # Get all existing mappings
        from silentgem.mapper import ChatMapper
        mapper = ChatMapper()
        mappings = mapper.get_all()
        
        if not mappings:
            print("\nNo existing chat mappings found.")
            return True
            
        # Get the client
        from silentgem.client import get_client
        client = get_client()
        
        # Get the insights bot
        insights_bot = get_insights_bot()
        
        # Keep track of channels that need the bot
        channels_to_upgrade = []
        
        print(f"\nFound {len(mappings)} existing chat mappings. Checking target channels...")
        
        # Check each target channel to see if it needs the bot
        for source_id, target_id in mappings.items():
            try:
                # Get chat info
                target_chat = await client.get_chat(target_id)
                chat_name = getattr(target_chat, "title", f"Chat {target_id}")
                
                # Check if the bot is already a member
                try:
                    bot_member = await client.get_chat_member(target_id, f"@{bot_username}")
                    if bot_member:
                        print(f"✅ Bot @{bot_username} is already in {chat_name}")
                        continue
                except Exception:
                    # Bot is not a member
                    channels_to_upgrade.append({
                        "id": target_id,
                        "name": chat_name
                    })
                    print(f"🔄 Target channel {chat_name} needs to add the Chat Insights bot")
            except Exception as e:
                print(f"⚠️ Could not check channel {target_id}: {e}")
        
        if not channels_to_upgrade:
            print("\n✅ All existing channels already have Chat Insights bot.")
            return True
            
        print(f"\nFound {len(channels_to_upgrade)} channels that need to add the Chat Insights bot.")
        print("To enable Chat Insights in these channels, you need to add the bot manually:")
        
        for channel in channels_to_upgrade:
            print(f"\n📣 Channel: {channel['name']}")
            await insights_bot.add_to_chat(channel['id'])
            
        print("\n✅ Sent instructions to all channels that need to be upgraded.")
        print("\nIMPORTANT: You need to manually add the bot to each channel following the instructions")
        print("that were sent to those channels. Chat Insights will only work in channels where the bot is present.")
        
        return True
    
    except Exception as e:
        print(f"\n❌ Error upgrading channels for Chat Insights: {e}")
        import traceback
        traceback.print_exc()
        return False 