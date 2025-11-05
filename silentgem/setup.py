"""
Interactive setup wizard for SilentGem
"""

import os
import json
import asyncio
import httpx
import questionary
from questionary import Choice, Style as QuestionaryStyle
from colorama import Fore, Style, init
from pathlib import Path
from getpass import getpass
from pyrogram import Client, errors
from loguru import logger
from dotenv import load_dotenv

from silentgem.utils import ensure_dir_exists

# Initialize colorama
init(autoreset=True)

# Custom questionary style - works on both light and dark backgrounds
custom_style = QuestionaryStyle([
    ('qmark', 'fg:#0087ff bold'),
    ('question', 'bold'),
    ('answer', 'fg:#00af00 bold'),
    ('pointer', 'fg:#0087ff bold'),
    ('highlighted', 'fg:#0087ff bold'),
    ('selected', 'fg:#00af00'),
    ('separator', 'fg:#767676'),
    ('instruction', 'fg:#767676'),
    ('text', ''),
    ('disabled', 'fg:#767676 italic')
])

async def setup_wizard():
    """
    Run the interactive setup wizard to configure SilentGem
    """
    print(f"\n{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}✨ SilentGem Setup Wizard ✨{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}\n")
    print("This wizard will help you set up SilentGem with your Telegram account and translation API.")
    print(f"{Fore.CYAN}📝 Get your credentials from: {Fore.WHITE}https://my.telegram.org/apps{Style.RESET_ALL}\n")
    
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
    
    # LLM Engine selection
    print(f"\n{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
    llm_engine = await questionary.select(
        "Select which translation engine to use:",
        choices=[
            Choice("🌐  Google Gemini (cloud-based)", value='gemini'),
            Choice("💻  Ollama (local)", value='ollama')
        ],
        style=custom_style
    ).ask_async()
    print(f"{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
    
    if not llm_engine:
        print("❌ Setup cancelled.")
        return False
    gemini_api_key = ""
    ollama_url = "http://localhost:11434"
    ollama_model = "llama3"
    
    gemini_model = "gemini-1.5-pro"  # Default model
    
    if llm_engine == "gemini":
        llm_engine = "gemini"
        gemini_api_key = input("Enter your Google Gemini API key: ").strip()
        if not gemini_api_key:
            print("❌ Gemini API key cannot be empty. Please try again.")
            return False
        
        # Fetch available Gemini models
        print(f"\nFetching available Google Gemini models...")
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            
            # Get list of available models
            models = genai.list_models()
            gemini_models = [
                model for model in models 
                if 'generateContent' in model.supported_generation_methods
            ]
            
            if gemini_models:
                choices = [Choice("gemini-1.5-pro (recommended)", value="gemini-1.5-pro")]
                choices.extend([Choice(model.name.replace('models/', ''), value=model.name.replace('models/', '')) for model in gemini_models])
                
                gemini_model = await questionary.select(
                    "Select a Gemini model:",
                    choices=choices,
                    style=custom_style
                ).ask_async()
                
                if gemini_model:
                    print(f"✅ Selected model: {gemini_model}")
                else:
                    gemini_model = "gemini-1.5-pro"
                    print("Using default model: gemini-1.5-pro")
            else:
                print("⚠️  No models found. Using default: gemini-1.5-pro")
                gemini_model = "gemini-1.5-pro"
                
        except ImportError:
            print("⚠️  google-generativeai package not installed. Using default: gemini-1.5-pro")
            print("Install with: pip install google-generativeai")
            gemini_model = "gemini-1.5-pro"
        except Exception as e:
            print(f"⚠️  Error fetching models: {e}")
            print("Using default: gemini-1.5-pro")
            gemini_model = "gemini-1.5-pro"
            
    elif llm_engine == "ollama":
        llm_engine = "ollama"
        
        # Ollama configuration
        ollama_url = input("Enter Ollama API URL (press Enter for default 'http://localhost:11434'): ").strip() or "http://localhost:11434"
        
        # Try to connect to Ollama to list available models
        print(f"\nConnecting to Ollama at {ollama_url} to get available models...")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{ollama_url.rstrip('/')}/api/tags")
                
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    if models:
                        choices = [
                            Choice(f"{model.get('name', 'unknown')} ({model.get('size', 0) // (1024 * 1024)} MB)", 
                                  value=model.get('name', 'unknown'))
                            for model in models
                        ]
                        
                        ollama_model = await questionary.select(
                            "Select an Ollama model:",
                            choices=choices,
                            style=custom_style
                        ).ask_async()
                        
                        if not ollama_model:
                            ollama_model = models[0]["name"] if models else "llama3"
                    else:
                        print("No models found in Ollama. You may need to pull a model first.")
                        ollama_model = input("Enter Ollama model name (press Enter for default 'llama3'): ").strip() or "llama3"
                else:
                    print(f"❌ Error connecting to Ollama: HTTP {response.status_code}")
                    ollama_model = input("Enter Ollama model name (press Enter for default 'llama3'): ").strip() or "llama3"
                    
        except Exception as e:
            print(f"❌ Error connecting to Ollama: {e}")
            print("Make sure Ollama is running and accessible.")
            ollama_model = input("Enter Ollama model name (press Enter for default 'llama3'): ").strip() or "llama3"
            
    
    # Get the rest of the configuration
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
            llm_engine,
            gemini_api_key,
            gemini_model,
            ollama_url,
            ollama_model,
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
    
    # Success banner
    print(f"\n{Fore.GREEN}{'═' * 60}{Style.RESET_ALL}")
    print(f"{Fore.GREEN}✅ Setup Complete!{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{'═' * 60}{Style.RESET_ALL}")
    print(f"\n{Fore.CYAN}You can now run SilentGem with:{Style.RESET_ALL} {Fore.WHITE}python silentgem.py{Style.RESET_ALL}\n")
    return True

async def save_env_file(api_id, api_hash, llm_engine, gemini_key, gemini_model, ollama_url, ollama_model, session_name, target_language):
    """Save API credentials to .env file"""
    env_content = f"""# Telegram API credentials
TELEGRAM_API_ID={api_id}
TELEGRAM_API_HASH={api_hash}

# LLM Engine selection ("gemini" or "ollama")
LLM_ENGINE={llm_engine}

# Google Gemini API key and model (if using gemini)
GEMINI_API_KEY={gemini_key}
GEMINI_MODEL={gemini_model}

# Ollama settings (if using ollama)
OLLAMA_URL={ollama_url}
OLLAMA_MODEL={ollama_model}

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
        print("\n✅ Saved configuration to .env file")
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
    
    # Ask which chats to monitor using checkbox
    choices = []
    for chat in available_chats:
        chat_type = chat["type"]
        username = f" (@{chat['username']})" if chat["username"] else ""
        label = f"[{chat_type}] {chat['title']}{username} (ID: {chat['id']})"
        choices.append(Choice(label, value=chat))
    
    print(f"\n{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
    selected_chats = await questionary.checkbox(
        "Select chats to monitor for translation (SPACE to select, ENTER when done):",
        choices=choices,
        style=custom_style
    ).ask_async()
    print(f"{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
    
    if not selected_chats:
        # Create an empty mapping file
        with open("data/mapping.json", "w") as f:
            json.dump({}, f, indent=2)
        print("\n✅ Created empty mapping file data/mapping.json")
        return
    
    # Create mapping
    mapping = {}
    
    print("\n📋 For each selected chat, choose a target channel where translations should be sent")
    
    # Get available target channels
    target_channels = [c for c in available_chats if c["type"] == "channel"]
    
    for source_chat in selected_chats:
        print(f"\n🔹 Setting up: {source_chat['title']}")
        
        if not target_channels:
            print("⚠️  No channels available. Please enter channel ID manually:")
            target_id = input("> ").strip()
            if target_id:
                mapping[str(source_chat["id"])] = str(target_id)
                print(f"✅ Added mapping: '{source_chat['title']}' -> Channel ID {target_id}")
            continue
        
        # Create choices for target channels
        choices = []
        for chat in target_channels:
            username = f" (@{chat['username']})" if chat["username"] else ""
            label = f"{chat['title']}{username} (ID: {chat['id']})"
            choices.append(Choice(label, value=chat))
        
        choices.append(Choice("Enter channel ID manually", value=None))
        
        target_chat = await questionary.select(
            f"Select target channel for '{source_chat['title']}':",
            choices=choices,
            style=custom_style
        ).ask_async()
        
        if target_chat is False:  # User cancelled
            continue
            
        if target_chat is None:
            # Manual entry
            target_id = input("Enter channel ID: ").strip()
            if target_id:
                mapping[str(source_chat["id"])] = str(target_id)
                print(f"✅ Added mapping: '{source_chat['title']}' -> Channel ID {target_id}")
        else:
            # Selected from list
            mapping[str(source_chat["id"])] = str(target_chat["id"])
            print(f"✅ Added mapping: '{source_chat['title']}' -> {target_chat['title']}")
    
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

async def config_llm_settings():
    """
    Configure only the LLM-related settings without changing other settings
    """
    print(f"\n{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}🤖 SilentGem LLM Configuration{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}\n")
    print("This utility will help you update your LLM engine settings without changing other configuration.")
    
    # Load current configuration
    load_dotenv()
    current_llm_engine = os.getenv("LLM_ENGINE", "gemini").lower()
    current_gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    current_ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    current_ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
    
    # Display current settings
    print("\nCurrent settings:")
    print(f"LLM Engine: {current_llm_engine}")
    if current_llm_engine == "gemini":
        print(f"Gemini API Key: {current_gemini_api_key[:4]}{'*' * 12 if current_gemini_api_key else 'Not set'}")
    else:
        print(f"Ollama URL: {current_ollama_url}")
        print(f"Ollama Model: {current_ollama_model}")
    
    # LLM Engine selection
    print(f"\n{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
    llm_engine = await questionary.select(
        "Select which translation engine to use:",
        choices=[
            Choice('🌐  Google Gemini (cloud-based)', value='gemini'),
            Choice('💻  Ollama (local)', value='ollama'),
            Choice('❌  Quit without changing', value='quit')
        ],
        default=current_llm_engine,
        style=custom_style
    ).ask_async()
    print(f"{Fore.CYAN}{'─' * 60}{Style.RESET_ALL}")
    
    if not llm_engine or llm_engine == 'quit':
        print("Exiting without changes.")
        return True
    
    # Set defaults to current values
    gemini_api_key = current_gemini_api_key
    ollama_url = current_ollama_url
    ollama_model = current_ollama_model
    
    # Update based on selection
    if llm_engine == "gemini":
        llm_engine = "gemini"
        current_key_hidden = current_gemini_api_key[:4] + '*' * 12 if current_gemini_api_key else "Not set"
        print(f"\nCurrent Gemini API Key: {current_key_hidden}")
        
        if await questionary.confirm("Do you want to update the API key?", default=False, style=custom_style).ask_async():
            gemini_api_key = input("Enter your Google Gemini API key: ").strip()
            if not gemini_api_key:
                print("❌ Gemini API key cannot be empty. Using existing key.")
                gemini_api_key = current_gemini_api_key
                
    elif llm_engine == "ollama":
        llm_engine = "ollama"
        
        # Ollama URL
        print(f"\nCurrent Ollama URL: {current_ollama_url}")
        
        if await questionary.confirm("Do you want to update the Ollama URL?", default=False, style=custom_style).ask_async():
            new_url = input("Enter Ollama API URL (press Enter for default 'http://localhost:11434'): ").strip()
            ollama_url = new_url if new_url else "http://localhost:11434"
        
        # Ollama Model
        print(f"\nCurrent Ollama Model: {current_ollama_model}")
        
        if await questionary.confirm("Do you want to update the Ollama model?", default=False, style=custom_style).ask_async():
            # Try to connect to Ollama to list available models
            print(f"\nConnecting to Ollama at {ollama_url} to get available models...")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{ollama_url.rstrip('/')}/api/tags")
                    
                    if response.status_code == 200:
                        models = response.json().get("models", [])
                        if models:
                            choices = [
                                Choice(f"{model.get('name', 'unknown')} ({model.get('size', 0) // (1024 * 1024)} MB)", 
                                      value=model.get('name', 'unknown'))
                                for model in models
                            ]
                            
                            default_model = current_ollama_model if any(m.get('name') == current_ollama_model for m in models) else None
                            
                            selected_model = await questionary.select(
                                "Select an Ollama model:",
                                choices=choices,
                                default=default_model,
                                style=custom_style
                            ).ask_async()
                            
                            if selected_model:
                                ollama_model = selected_model
                        else:
                            print("No models found in Ollama. You may need to pull a model first.")
                            new_model = input(f"Enter Ollama model name (current: {current_ollama_model}): ").strip()
                            ollama_model = new_model if new_model else current_ollama_model
                    else:
                        print(f"❌ Error connecting to Ollama: HTTP {response.status_code}")
                        new_model = input(f"Enter Ollama model name (current: {current_ollama_model}): ").strip()
                        ollama_model = new_model if new_model else current_ollama_model
                        
            except Exception as e:
                print(f"❌ Error connecting to Ollama: {e}")
                print("Make sure Ollama is running and accessible.")
                new_model = input(f"Enter Ollama model name (current: {current_ollama_model}): ").strip()
                ollama_model = new_model if new_model else current_ollama_model
    
    # Preserve existing settings from .env file
    existing_env = {}
    try:
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_env[key.strip()] = value.strip()
    except FileNotFoundError:
        print("Warning: No existing .env file found. Creating a new one.")
        
    # Update only LLM-related settings
    existing_env["LLM_ENGINE"] = llm_engine
    existing_env["GEMINI_API_KEY"] = gemini_api_key
    existing_env["OLLAMA_URL"] = ollama_url
    existing_env["OLLAMA_MODEL"] = ollama_model
    
    # Write back to .env with updated values
    try:
        with open(".env", "w") as f:
            for key, value in existing_env.items():
                f.write(f"{key}={value}\n")
        print("\n✅ Updated LLM settings in .env file")
        return True
    except Exception as e:
        print(f"\n❌ Error updating .env file: {e}")
        return False

async def config_target_language():
    """
    Update only the target language setting
    """
    print(f"\n{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}🌍 Update Target Language{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═' * 60}{Style.RESET_ALL}\n")
    
    # Load current configuration
    load_dotenv()
    current_language = os.getenv("TARGET_LANGUAGE", "english")
    
    print(f"Current target language: {current_language}")
    new_language = input("Enter new target language (or press Enter to keep current): ").strip()
    
    if not new_language:
        print("Keeping current language setting.")
        return True
        
    # Preserve existing settings from .env file
    existing_env = {}
    try:
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_env[key.strip()] = value.strip()
    except FileNotFoundError:
        print("Warning: No existing .env file found. Creating a new one.")
        
    # Update only target language setting
    existing_env["TARGET_LANGUAGE"] = new_language
    
    # Write back to .env with updated values
    try:
        with open(".env", "w") as f:
            for key, value in existing_env.items():
                f.write(f"{key}={value}\n")
        print(f"\n✅ Updated target language to '{new_language}'")
        return True
    except Exception as e:
        print(f"\n❌ Error updating .env file: {e}")
        return False 