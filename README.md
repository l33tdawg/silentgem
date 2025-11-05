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
- Chat Insights for searching and analyzing conversation history (v1.1)
- Cross-chat contextual analysis for deeper insights (v1.2)
- Conversational, ChatGPT-like responses to queries (v1.2)
- ⚡ Ultra-fast performance with 2-3 second response times (v1.2.1)
- 🎯 Select from available Google Gemini models during setup (v1.3)
- 🎨 Interactive terminal menus with arrow-key navigation (v1.4)

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
- Choosing between Gemini AI or Ollama for translation with interactive menus
- Configuring API keys or local model settings
- Multi-selecting source chats to monitor (use SPACE to select)
- Setting up target channels for translations with visual selection

## Usage

Start SilentGem (interactive menu):
```bash
./silentgem.py
```

The interactive menu provides easy access to all features:
- 🚀 Start/stop translation service
- 📋 Manage chat mappings
- ⚙️ Configure settings
- 💡 Set up Chat Insights

Navigate with arrow keys, select with ENTER.

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

### Choosing Models

**Google Gemini**: During setup or when updating LLM settings, SilentGem fetches and displays all available Gemini models (e.g., gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash-exp). Simply select your preferred model from the list.

**Ollama**: When using Ollama, you can:
- Specify the URL (default: http://localhost:11434)
- Choose from models you've already pulled
- Change models without redoing the entire setup

## Chat Insights Feature

SilentGem includes a powerful Chat Insight feature that allows you to query your conversation history in your translated channels:

### Overview

Chat Insights automatically stores all translated messages in a local database and provides a natural language interface to search and analyze your conversation history through a **private Telegram bot**.

**How It Works:** The bot is completely private to you and works transparently. You simply direct message the bot to ask questions, and it searches all messages stored in your local database. **You don't need to add the bot to any channels**—it searches everything automatically because the messages are already stored locally on your system.

#### Latest Enhancements:

- **Cross-chat awareness**: Search and analyze information across all monitored channels
- **Larger context window**: Get more context around matched messages (15 messages before/after)
- **Unified insights**: See connections between information from different sources
- **Smart context organization**: Messages are grouped by chat for better understanding
- **Conversational responses**: Get natural, focused answers that synthesize information across messages
- **Topic tracking**: Better handling of questions like "What's the latest in Gaza?" or "What's the status of project X?"
- **Enhanced question understanding**: Improved pattern recognition for common query types
- **Contextual follow-up questions**: Smart detection of related questions for improved conversation flow
- **Topic transition detection**: Automatically identifies when conversation shifts to new topics
- **⚡ Ultra-Fast Performance**: Dramatically improved response times with sub-3 second responses (NEW in v1.2.1)
- **🎯 Concise Responses**: Direct, focused answers that avoid repetition and unnecessary verbosity (NEW in v1.2.2)

### Performance Improvements (v1.2.1 & v1.2.2)

SilentGem Chat Insights has received major performance and usability optimizations:

#### 🚀 Speed Improvements (v1.2.1)
- **5x faster response times**: Reduced from 9-10 seconds to 2-3 seconds for most queries
- **Intelligent caching**: Query results are cached for 5 minutes, providing instant responses for repeated queries
- **Optimized search strategies**: Direct keyword matching prioritized over complex semantic expansion
- **Parallel processing**: Multiple operations run concurrently for better performance

#### 🎯 Response Quality Improvements (v1.2.2)
- **Concise by default**: Responses are now direct and focused, avoiding unnecessary verbosity
- **Smart follow-up detection**: Automatically detects follow-up questions and avoids repeating information
- **Reduced context overhead**: Streamlined prompts focus on essential information only
- **Faster LLM processing**: Reduced token usage for quicker response generation

#### 🔧 Technical Optimizations
- **Simplified conversation analysis**: Skips complex analysis for better performance
- **Focused context collection**: Only includes recent conversation history when relevant
- **Optimized database queries**: Streamlined SQL operations with better indexing
- **Efficient response formatting**: Prioritizes direct answers over comprehensive analysis

#### 📊 Performance Metrics
- **Database search**: Sub-100ms for most queries
- **Cache hits**: Near-instantaneous responses (< 0.1s)
- **Response generation**: 2-3 seconds for most queries
- **Memory usage**: Optimized caching with automatic cleanup

These improvements make SilentGem Chat Insights feel truly responsive and provide focused, actionable answers without unnecessary verbosity.

### Setting Up Chat Insights

Chat Insights is enabled by default. You can customize its settings with:

```bash
python silentgem.py --setup-insights
```

During setup, you'll create a **private Telegram bot** that's exclusively for your use. The bot works transparently by searching your local message database—**you don't need to add it to any channels**. Simply direct message the bot to search across all your stored conversations.

#### Creating a Bot with BotFather

To create your private bot for Chat Insights:

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Start a chat with BotFather
3. Send the `/newbot` command
4. Follow the instructions to:
   - Set a name for your bot: We recommend using "SilentAsk" for consistency
   - Set a username for your bot: We recommend "silentask_bot" (or any name ending with "bot")
5. BotFather will give you a token (like `123456789:ABCDefGhIJKlmNoPQRsTUVwxyZ`)
6. Copy this token when prompted during the `--setup-insights` process

**Important**: This bot is completely private to you. It doesn't need to be added to any channels—it transparently searches all messages stored in your local database. Just open a direct message with your bot on Telegram and start asking questions about your conversations.

### Using Chat Insights

Chat Insights understands natural language queries and provides **conversational responses that synthesize information** from relevant messages, rather than just listing search results. It also uses the context of your ongoing conversation for better follow-up answers.

#### How to Use Your Private Bot

Simply open a direct message with your bot on Telegram and ask any question:

```
Who talked about APIs yesterday?
```

The bot searches **all messages stored in your local database** from all monitored channels—automatically and transparently. You don't need to add the bot to any channels for it to work.

**Optional**: If you prefer, you can also add the bot to specific channels and use the `/askgem` command:

```
/askgem Who talked about APIs yesterday?
```

But this is completely optional—direct messaging the bot is simpler and works exactly the same way.

### Example Queries

Chat Insights understands natural language queries. Simply direct message your bot and ask questions like:

- "What was discussed today?"
- "Show messages from yesterday about the project"
- "Find all mentions of APIs from last week"
- "What did Alice say about the database?"
- "Show discussions about the UI redesign"
- "Summarize what different groups are saying about the Ukraine situation"
- "Compare discussions about the new feature across all channels"

The bot searches **all your monitored channels** and provides conversational answers with clickable links to the original messages.

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

SilentGem is continuously improving with a focus on making Chat Insights a powerful daily assistant for managing information across channels.

### ✅ Version 1.2.1 - Performance Revolution (COMPLETED)

**Major performance breakthrough achieved:**
- **5x faster response times**: From 9-10 seconds down to 2-3 seconds
- **Intelligent caching system**: Instant responses for repeated queries
- **Optimized search algorithms**: Smart keyword matching with minimal LLM overhead
- **Enhanced database performance**: Sub-100ms search times
- **Memory optimization**: Efficient caching with automatic cleanup

### ✅ Version 1.2.2 - Response Quality & Search Enhancement (COMPLETED)

**Major improvements to response quality and search functionality:**
- **Comprehensive yet focused responses**: Well-structured answers (400-800 characters) with sufficient detail
- **Cross-chat search by default**: All searches now span across all monitored channels automatically
- **Media filtering**: Removed irrelevant media messages (photos, videos) that provide no value for analysis
- **Smart follow-up detection**: Avoids repeating information in follow-up questions
- **LLM-processed responses**: Intelligent synthesis instead of raw search result lists
- **Streamlined prompts**: Reduced complexity for faster processing and lower token usage

### ✅ Version 1.3 - Model Selection & Flexibility (COMPLETED)

**Enhanced model configuration and choice:**
- **Google Gemini model selection**: Choose from all available Gemini models during setup (gemini-1.5-pro, gemini-1.5-flash, gemini-2.0-flash-exp, etc.)
- **Dynamic model fetching**: Automatically retrieves current available models from Google's API
- **Persistent configuration**: Selected model stored in .env for consistent use across sessions
- **Easy model switching**: Update your Gemini model anytime via `--config-llm` without full reconfiguration

### ✅ Version 1.4 - Interactive Terminal Menus (COMPLETED)

**Modern CLI interface:**
- **Arrow-key navigation**: Navigate all menus with ↑↓ keys
- **Multi-select with checkboxes**: Use SPACE to select multiple chats
- **Visual feedback**: See your current selection highlighted
- **Better UX**: No more typing numbers or making typos

### ✅ Version 1.5 - Advanced Conversational Memory (COMPLETED)

**Intelligent conversation enhancement with guided exploration:**
- ✅ **Guided Queries**: AI-generated contextual follow-up questions as clickable buttons
- ✅ **Interactive Exploration**: Expand topics with one-click buttons for detailed information  
- ✅ **Query Templates**: Save and reuse common search patterns for efficiency
- ✅ **Smart Suggestions**: LLM analyzes conversation context to recommend relevant next questions
- ✅ **Topic Expansion**: Deep-dive into substantial topics directly from search results
- ✅ **Action Buttons**: Quick access to timeline views, contributor analysis, and template saving

**How It Works:**
When you ask the bot a question, it now provides intelligent follow-up suggestions as clickable Telegram buttons below the response. Simply tap a button to explore that direction - no typing required!

**Example:**
```
You: "What happened with APIs last week?"

Bot: [Provides detailed answer]

Buttons shown:
┌────────────────────────────────────────┐
│ 1️⃣ What are the migration deadlines?   │
├────────────────────────────────────────┤
│ 2️⃣ Show technical implementation...    │
├────────────────────────────────────────┤
│ 3️⃣ Who are the main contributors?      │
├────────────────────────────────────────┤
│ 📖 Expand: GraphQL Migration (22 msgs) │
├────────────────────────────────────────┤
│ [📅 Timeline]      [👥 Contributors]    │
└────────────────────────────────────────┘
```

Tap any button and the bot instantly processes that question!

### Version 1.6 - Proactive Assistant

Transforming from reactive search to proactive assistant:
- **Topic Alerts**: Set up notifications for topics you care about
- **Scheduled Digests**: Receive daily or weekly summaries of key discussions
- **Bidirectional Communication**: Reply to messages from within the chat insights interface
- **Topic Collections**: Create and organize collections of related information

## Author

Developed by Dhillon '@l33tdawg' Kannabhiran (l33tdawg@hitb.org)

## License

[MIT License](LICENSE) - Copyright © 2025 