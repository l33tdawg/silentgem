# Chat Insights

This guide explains how to use the Chat Insights feature in SilentGem to search and analyze your translated conversations.

## Overview

Chat Insights allows you to query your translated conversation history in private channels. You can ask questions like "Who talked about APIs yesterday?" or "Show me messages about the project from last week" directly in your target channels.

### Enhanced Cross-Chat Context Analysis (v1.2)

The latest version includes powerful features for analyzing information across multiple chats:

- **Cross-chat awareness**: Search and analyze information across all your monitored channels
- **Intelligent context retrieval**: Gets context from before and after matched messages (15 messages in each direction)
- **Unified insights**: Identifies connections between information from different sources
- **Smart context organization**: Groups messages by chat for better understanding
- **Alternative term searching**: Uses smart language models to find related messages using alternative search terms

This makes Chat Insights especially powerful for monitoring multiple sources about the same topic (like news channels, discussion groups, etc.) and getting a comprehensive understanding of discussions happening across them.

## Setting Up Chat Insights

Chat Insights is enabled by default when you install SilentGem. You can customize the settings using:

```
python silentgem.py --setup-insights
```

During setup, you'll create a dedicated Telegram bot (via BotFather) that will be added to your target channels. This bot processes your queries and searches through your conversation history. We recommend naming this bot "SilentAsk" for consistency.

## Using Chat Insights

There are two ways to query your conversation history:

### 1. Using the /askgem Command

In any target channel where the bot is present, you can use the `/askgem` command followed by your query:

```
/askgem Who talked about APIs yesterday?
```

### 2. Directly Messaging the Bot

You can also directly message the bot with your query, without using any commands:

```
Who talked about APIs yesterday?
```

If you're in a group channel, you'll need to either:
- Mention the bot (@SilentAsk) in your message
- Reply to one of the bot's previous messages

The bot will search across all your channels when you directly message it, providing a unified view of your conversations. Results include clickable links to the original messages so you can easily navigate to the source.

## Example Queries

Chat Insights understands natural language queries. Here are some examples:

- **Time-based queries**:
  - "What was discussed today?"
  - "Show messages from yesterday about the project"
  - "Find all mentions of APIs from last week"

- **Person-specific queries**:
  - "What did Alice say about the database?"
  - "Show messages from Bob yesterday"

- **Topic-based queries**:
  - "Find all messages about deployment"
  - "Show discussions about the UI redesign"

- **Cross-chat analysis queries** (NEW):
  - "Summarize what different groups are saying about the Ukraine situation"
  - "Compare discussions about the new feature across all channels"
  - "What are the main differences in how Group A and Group B are discussing the topic?" 
  - "Find connections between the API discussion in the dev channel and project planning channel"

## Advanced Features

### Cross-Chat Context Analysis

The cross-chat context feature allows you to gain insights that span multiple conversations:

#### How It Works

1. **Broad Searching**: When you search for a topic, Chat Insights finds relevant messages across all your channels
2. **Context Expansion**: For each match, it retrieves surrounding messages (15 before and 15 after) for context
3. **Intelligent Organization**: The AI organizes messages by chat, maintaining the chronological flow
4. **Synthesis**: The AI analyzes connections between information from different sources
5. **Unified Response**: You get a comprehensive answer that synthesizes insights from all relevant channels

#### Best Use Cases

This feature is particularly powerful for:

- **News monitoring**: Track how different news sources report on the same topic
- **Project coordination**: See how discussions in different teams relate to each other
- **Research**: Gather comprehensive information on a topic from multiple sources
- **Intelligence analysis**: Find connections between discussions happening in different groups

## Privacy and Security

Your messages are stored locally on your system in an encrypted database. By default, all message content is stored, but you can customize this:

- **Store message metadata only**: Only store who sent what and when, not the content
- **Anonymize sender information**: Remove sender details 
- **Set retention policies**: Automatically delete older messages

These settings can be configured using `--setup-insights`.

## Clearing History

To clear all stored message history:

```
python silentgem.py --clear-insights-history
```

## Troubleshooting

### Bot Not Responding

If the bot doesn't respond to your queries:

1. Check that the bot is added to your target channel
2. Ensure SilentGem is running
3. Try restarting SilentGem
4. Check the logs for errors

### Query Not Returning Expected Results

If you're not getting the results you expect:

1. Try rephrasing your query to be more specific
2. Check if the time period you're referencing is correct
3. Ensure the topic you're searching for has been discussed in that channel
4. Try using simpler queries first, then add complexity

### Adding the Bot to New Channels

When you add a new target channel in SilentGem, you'll need to add the Chat Insights bot to that channel as well:

1. Open the channel in Telegram
2. Click the channel name/title at the top
3. Select "Add members"
4. Search for your bot by name (@SilentAsk)
5. Add the bot to the channel

## Advanced Usage

### Response Verbosity

You can control how detailed the responses are by configuring the "response_verbosity" setting:

- **Concise**: Brief summaries with minimal details
- **Standard**: Balanced information with some context
- **Detailed**: Comprehensive responses with full context

### Query Processing Depth

Control how deeply your queries are analyzed:

- **Basic**: Simple keyword matching
- **Standard**: Natural language understanding
- **Detailed**: Advanced semantic analysis 