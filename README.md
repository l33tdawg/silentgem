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

## Chat Insights Feature

SilentGem includes a powerful Chat Insight feature that allows you to query your conversation history in your translated channels:

### Overview

Chat Insights automatically stores all translated messages in a local database and provides a natural language interface to search and analyze your conversation history through a dedicated Telegram bot.

**Important:** Since SilentGem already stores all messages in your local database, the bot does NOT need to be added to your source channels to search or analyze messages. The bot only needs to be present in channels where you want users to be able to issue commands and receive responses.

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

During setup, you'll create a dedicated Telegram bot (via BotFather). The bot only needs to be added to channels where you want to issue commands and receive responses, not to the source channels being monitored.

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

Chat Insights understands natural language queries and provides **conversational responses that synthesize information** from relevant messages, rather than just listing search results. It also uses the context of your ongoing conversation for better follow-up answers.

There are two ways to query your conversation history:

#### 1. Using the /askgem Command

In any channel where the bot is present:

```
/askgem Who talked about APIs yesterday?
```

The bot will search all messages stored in your local database, including messages from channels where the bot is not a member.

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

SilentGem is continuously improving with a focus on making Chat Insights a powerful daily assistant for managing information across channels.

### ✅ Version 1.2.1 - Performance Revolution (COMPLETED)

**Major performance breakthrough achieved:**
- **5x faster response times**: From 9-10 seconds down to 2-3 seconds
- **Intelligent caching system**: Instant responses for repeated queries
- **Optimized search algorithms**: Smart keyword matching with minimal LLM overhead
- **Enhanced database performance**: Sub-100ms search times
- **Memory optimization**: Efficient caching with automatic cleanup

### ✅ Version 1.2.2 - Response Quality Enhancement (COMPLETED)

**Focused on improving response quality and reducing verbosity:**
- **Concise responses by default**: Direct, focused answers without unnecessary elaboration
- **Smart follow-up detection**: Avoids repeating information in follow-up questions
- **Streamlined context processing**: Reduced prompt complexity for faster processing
- **Optimized conversation intelligence**: Simplified analysis for better performance
- **Reduced token usage**: Lower LLM costs and faster response generation

### Version 1.3 - Advanced Conversational Memory (Coming Soon)

Priority features planned for the next release:
- **Cross-session Conversation Context**: Remember previous interactions across different sessions for even more natural follow-up questions
- **Interactive Exploration**: Add buttons to responses for expanding details or exploring related topics
- **Guided Queries**: Get suggestions for follow-up questions related to your current topic
- **Query Templates**: Save and reuse common search patterns
- **Performance Analytics**: Built-in performance monitoring and optimization suggestions

### Version 1.4 - Proactive Assistant

Transforming from reactive search to proactive assistant:
- **Topic Alerts**: Set up notifications for topics you care about
- **Scheduled Digests**: Receive daily or weekly summaries of key discussions
- **Bidirectional Communication**: Reply to messages from within the chat insights interface
- **Topic Collections**: Create and organize collections of related information

### Version 1.5 - Knowledge Organization

Building a personal knowledge base from your conversations:
- **Custom Tagging**: Tag and categorize important messages for easy retrieval
- **Knowledge Persistence**: Save valuable insights for future reference
- **Task Extraction**: Identify action items from conversations
- **Reminder Integration**: Set reminders related to specific discussion topics

### Version 1.6 - Analytics & Visualization

Advanced analytical capabilities:
- **Sentiment Analysis**: Track the emotional tone of discussions
- **Topic Mapping**: Visual representation of related topics
- **Participation Analytics**: Identify key contributors on specific topics
- **Advanced Search**: Enhanced semantic search with better relevance and speed

## Author

Developed by Dhillon '@l33tdawg' Kannabhiran (l33tdawg@hitb.org)

## License

[MIT License](LICENSE) - Copyright © 2025 