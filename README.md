# SilentGem

A Telegram translator using Google Gemini AI or local LLMs via Ollama.

## Description

SilentGem is a Telegram userbot that automatically translates messages from source chats (groups, channels) to your private target channels. It works in the background, using either Google's Gemini AI or local LLMs via Ollama for high-quality translation.

## Features

- Monitor multiple source chats simultaneously
- Translate to any language supported by Google Gemini or your local LLM
- Choose between cloud-based (Gemini) or local (Ollama) translation engines
- Forward media with translated captions
- Preserve attribution to original senders
- Detect and skip already-English messages when target is English
- Interactive setup wizard for easy configuration
- CLI tools for managing chat mappings
- Update translation engines without redoing full setup

## Requirements

- Python 3.7+
- Telegram API credentials (API ID and Hash)
- Google Gemini API key (if using Gemini)
- Ollama installed and running (if using local LLMs)

## API Keys

### Obtaining Telegram API Credentials

1. Visit [my.telegram.org](https://my.telegram.org/auth) and log in with your Telegram account
2. Click on "API Development Tools"
3. Fill in the form with the following details:
   - App title: SilentGem (or any name you prefer)
   - Short name: silentgem (or any short name)
   - Platform: Desktop
   - Description: Telegram translator application
4. Click "Create Application"
5. You will receive your **API ID** (a number) and **API Hash** (a string)
6. Copy these credentials for use in the setup wizard

### Obtaining Google Gemini API Key

1. Visit [AI Studio](https://aistudio.google.com/)
2. Create or sign in to your Google account
3. Click "Get API key" in the top right corner
4. Create a new API key or use an existing one
5. Copy the API key for use in the setup wizard

### Setting Up Ollama (for local LLM translation)

1. Install Ollama from [ollama.ai](https://ollama.ai/)
2. Start the Ollama service
3. Pull a model like llama3 using `ollama pull llama3`
4. SilentGem will automatically detect available models

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/silentgem.git
cd silentgem
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the setup wizard:
```bash
./silentgem.py --setup
```

The setup wizard will guide you through:
- Setting up Telegram API credentials
- Choosing between Gemini AI or Ollama for translation
- Configuring API keys or local model settings
- Selecting source chats to monitor
- Setting up target channels for translations

## Usage

Start the translation service:
```bash
./silentgem.py
```

### Command-line options

- `--setup`: Run the setup wizard
- `--service`: Start the translation service directly (non-interactive)
- `--cleanup`: Clean up any database lock issues
- `--clear-mappings`: Reset all chat mappings
- `--config-llm`: Update LLM engine settings without redoing full setup
- `--config-language`: Update target language without redoing full setup
- `--version`: Show version information

### Switching Between Translation Engines

You can easily switch between Gemini and Ollama:

1. From the command line: `python silentgem.py --config-llm`
2. From the interactive menu: Select option 6 "Update LLM Settings"

### Using Ollama

When using Ollama, you can:
- Specify the URL (default: http://localhost:11434)
- Choose from models you've already pulled
- Change models without redoing the entire setup

## Roadmap

### Version 1.1 - Chat Insight Enhancement

Future versions of SilentGem will include a powerful chat insight feature that allows you to query your conversation history and communicate bidirectionally:

- **Message Storage System**: Automatic storage of all translated messages with metadata
- **Telegram Bot Integration**: Dedicated bot for interacting with your message history
- **Natural Language Query Interface**: Simplified commands to search and retrieve information:
  - `/askgem [query]` - Search and retrieve information from past conversations
  - Natural language queries without command prefix (e.g., "Who talked about the API yesterday?")

### Version 1.2 - Bidirectional Communication

Building on the chat insights, version 1.2 will enable seamless bidirectional communication:

- **Reply to Original Messages**: Send replies back to source chats with automatic translation
  - `/reply [message]` - Reply to the last message in original source chat
  - `/send [message]` - Send a new message to the original channel
- **Enhanced Search Capabilities**: Semantic search for concept-based queries
- **Conversation Summarization**: Get AI-generated summaries of past discussions
- **Secure & Private**: All features respect your privacy with user-owned data storage

## Author

Developed by Dhillon '@l33tdawg' Kannabhiran (l33tdawg@hitb.org)

## License

[MIT License](LICENSE) - Copyright © 2025 