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
- Chat Insights for searching and analyzing conversation history (NEW in v1.1)
- Cross-chat contextual analysis for deeper insights (NEW in v1.2)

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
- `--setup-insights`: Configure Chat Insights feature
- `--clear-insights-history`: Clear stored message history used for Chat Insights
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

## Chat Insights Feature (v1.2)

SilentGem includes a powerful Chat Insight feature that allows you to query your conversation history in your translated channels:

### Overview

Chat Insights automatically stores all translated messages in a local database and provides a natural language interface to search and analyze your conversation history through a dedicated Telegram bot.

#### NEW: Cross-Chat Contextual Analysis

The latest version includes enhanced contextual analysis capabilities:
- **Cross-chat awareness**: Search and analyze information across all monitored channels
- **Larger context window**: Get more context around matched messages (15 messages before/after)
- **Unified insights**: See connections between information from different sources
- **Smart context organization**: Messages are grouped by chat for better understanding

### Setting Up Chat Insights

Chat Insights is enabled by default. You can customize its settings with:

```bash
python silentgem.py --setup-insights
```

During setup, you'll create a dedicated Telegram bot (via BotFather) that will be automatically added to your target channels.

#### Creating a Bot with BotFather

To create a bot for Chat Insights:

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Start a chat with BotFather
3. Send the `/newbot` command
4. Follow the instructions to:
   - Set a name for your bot: We recommend using "SilentAsk" for consistency
   - Set a username for your bot: We recommend "silentask_bot" (or any name ending with "bot")
5. BotFather will give you a token (like `123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ`)
6. Copy this token when prompted during the `--setup-insights` process

The bot will be automatically added to your target channels during setup, or you can manually add it later.

### Using Chat Insights

There are two ways to query your conversation history:

#### 1. Using the /askgem Command

In any target channel where the bot is present:

```
/askgem Who talked about APIs yesterday?
```

#### 2. Directly Messaging the Bot

You can also directly message the bot with your query:

```
Who talked about APIs yesterday?
```

### Example Queries

Chat Insights understands natural language queries. Examples:

- "What was discussed today?"
- "Show messages from yesterday about the project"
- "Find all mentions of APIs from last week"
- "What did Alice say about the database?"
- "Show discussions about the UI redesign"
- "Summarize what different groups are saying about the Ukraine situation"
- "Compare discussions about the new feature across all channels"

You can ask these questions in any target channel where the bot is present or in a direct message to the bot. The bot will search across all your channels and provide clickable links to the original messages.

### Privacy and Security

Your messages are stored locally on your system. You can configure:

- **Message retention periods**: Control how long messages are stored
- **Anonymization**: Remove sender information
- **Content filtering**: Store only metadata instead of full content

To clear all stored message history:

```bash
python silentgem.py --clear-insights-history
```

For more detailed documentation on Chat Insights, see `docs/chat_insights.md`

## Roadmap

### Version 1.3 - Bidirectional Communication

The next version will enable seamless bidirectional communication:

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