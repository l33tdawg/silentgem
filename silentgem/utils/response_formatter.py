"""
Response formatter for formatting search results for display in Telegram
"""

from datetime import datetime
import time
from typing import List, Dict, Any, Optional, Callable
from loguru import logger
from collections import defaultdict

from silentgem.translator import create_translator, BaseTranslator
from silentgem.config.insights_config import get_insights_config

async def format_search_results(
    messages: List[Dict[str, Any]],
    query: str,
    parsed_query: Optional[Dict[str, Any]] = None,
    verbosity: str = "standard",
    include_quotes: bool = True,
    include_timestamps: bool = True,
    include_sender_info: bool = True,
    include_channel_info: bool = True,
    context_messages: Optional[List[Dict[str, Any]]] = None,
    chat_messages_map: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> str:
    """
    Format search results for display in Telegram
    
    Args:
        messages: List of message dictionaries from the database
        query: Original query string
        parsed_query: Parsed query dictionary from NLU
        verbosity: Response verbosity level (concise, standard, detailed)
        include_quotes: Whether to include original message quotes
        include_timestamps: Whether to include timestamps
        include_sender_info: Whether to include sender information
        include_channel_info: Whether to include channel information and links
        context_messages: Additional context messages from the conversation history
        chat_messages_map: Dictionary mapping chat IDs to lists of messages, for better organization
        
    Returns:
        str: Formatted response
    """
    try:
        if not messages:
            # Enhanced empty results message
            empty_message = f"📭 No messages found matching your query: '{query}'"
            
            # Include enhanced query terms if available
            if parsed_query:
                # Add original query if different
                if parsed_query.get("original_query_text") and parsed_query.get("original_query_text") != query:
                    empty_message += f"\n\nOriginal query: '{parsed_query.get('original_query_text')}'"
                
                # Add search terms used
                if parsed_query.get("query_text") and " OR " in parsed_query.get("query_text"):
                    empty_message += f"\n\nI searched for: {parsed_query.get('query_text')}"
                
                # Add search alternatives if available
                if parsed_query.get("search_alternatives") and isinstance(parsed_query.get("search_alternatives"), list):
                    alternatives = parsed_query.get("search_alternatives")
                    if alternatives:
                        empty_message += "\n\nYou might want to try these alternative search terms:"
                        for i, alt in enumerate(alternatives[:3]):
                            empty_message += f"\n- {alt}"
                
                # Add time period info
                if parsed_query.get("time_period"):
                    time_period = parsed_query.get("time_period")
                    period_text = {
                        "today": "today",
                        "yesterday": "yesterday",
                        "week": "the past week",
                        "month": "the past month"
                    }.get(time_period, time_period)
                    empty_message += f"\n\nI searched in messages from {period_text}."
                
                empty_message += "\n\nTry broadening your search terms, or use different keywords related to your topic."
            
            return empty_message
        
        # Get insights configuration
        config = get_insights_config()
        
        # Determine if we should use LLM formatting
        query_depth = config.get("query_processing_depth", "standard")
        use_llm_format = query_depth in ["standard", "detailed"] and len(messages) > 0
        
        # If using standard depth or higher and LLM is available, use it for better formatting
        if use_llm_format and verbosity in ["standard", "detailed"]:
            # Get translator for formatting
            translator = await create_translator()
            
            # Format results using LLM
            return await _format_with_llm(
                messages=messages,
                query=query,
                parsed_query=parsed_query,
                translator=translator,
                verbosity=verbosity,
                include_quotes=include_quotes,
                include_timestamps=include_timestamps,
                include_sender_info=include_sender_info,
                include_channel_info=include_channel_info,
                context_messages=context_messages,
                chat_messages_map=chat_messages_map
            )
        
        # Otherwise, use basic formatting
        return _format_basic(
            messages=messages,
            query=query,
            parsed_query=parsed_query,
            verbosity=verbosity,
            include_quotes=include_quotes,
            include_timestamps=include_timestamps,
            include_sender_info=include_sender_info,
            include_channel_info=include_channel_info
        )
    
    except Exception as e:
        logger.error(f"Error formatting search results: {e}")
        # Return a simple fallback format
        return _format_simple_fallback(messages, query)

def _format_basic(
    messages: List[Dict[str, Any]],
    query: str,
    parsed_query: Optional[Dict[str, Any]] = None,
    verbosity: str = "standard",
    include_quotes: bool = True,
    include_timestamps: bool = True,
    include_sender_info: bool = True,
    include_channel_info: bool = False
) -> str:
    """
    Basic formatter without using LLM
    """
    # Format header based on query
    if parsed_query and "intent" in parsed_query:
        if parsed_query["intent"] == "count":
            header = f"Found {len(messages)} messages matching '{query}'"
        elif parsed_query["intent"] == "summarize":
            header = f"Summary of {len(messages)} messages about '{query}'"
        else:  # search
            header = f"Found {len(messages)} messages matching '{query}'"
    else:
        header = f"Found {len(messages)} messages matching '{query}'"
    
    # Add time period if available
    if parsed_query and parsed_query.get("time_period"):
        time_period = parsed_query["time_period"]
        if time_period == "today":
            header += " from today"
        elif time_period == "yesterday":
            header += " from yesterday"
        elif time_period == "week":
            header += " from the past week"
        elif time_period == "month":
            header += " from the past month"
    
    # Start building response
    response = [header, ""]
    
    # Determine max message content length based on verbosity
    if verbosity == "concise":
        max_content_length = 50
        max_messages = min(5, len(messages))
    elif verbosity == "standard":
        max_content_length = 100
        max_messages = min(10, len(messages))
    else:  # detailed
        max_content_length = 200
        max_messages = len(messages)
    
    # Format each message
    for i, msg in enumerate(messages[:max_messages]):
        # Skip if we've reached the maximum
        if i >= max_messages:
            break
            
        message_lines = []
        
        # Add channel info if requested
        if include_channel_info and msg.get("target_chat_id"):
            chat_title = f"Channel ID: {msg['target_chat_id']}"
            message_lines.append(f"📢 {chat_title}")
        
        # Add sender info
        if include_sender_info and msg.get("sender_name"):
            message_lines.append(f"👤 {msg['sender_name']}")
        
        # Add timestamp
        if include_timestamps and msg.get("timestamp"):
            # Format timestamp
            dt = datetime.fromtimestamp(msg["timestamp"])
            time_str = dt.strftime("%Y-%m-%d %H:%M")
            message_lines.append(f"🕒 {time_str}")
        
        # Add content
        if msg.get("content"):
            # Truncate content if necessary
            content = msg["content"]
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."
            
            # Format differently based on media type
            if msg.get("is_media"):
                media_type = msg.get("media_type", "media")
                message_lines.append(f"📎 {media_type.capitalize()} with caption: {content}")
            else:
                if include_quotes:
                    # Format as a quote
                    quoted_lines = [f"> {line}" for line in content.split("\n")]
                    message_lines.append("\n".join(quoted_lines))
                else:
                    message_lines.append(content)
        else:
            message_lines.append("[No text content]")
        
        # Add message link if possible
        if include_channel_info and msg.get("target_chat_id") and msg.get("message_id"):
            # Create a tg:// link that will work in Telegram
            link = f"tg://privatepost?channel={msg['target_chat_id'].replace('-100', '')}&post={msg['message_id']}"
            message_lines.append(f"🔗 [View Message]({link})")
        
        # Add to response
        response.append("\n".join(message_lines))
        
        # Add separator if not the last message
        if i < min(max_messages, len(messages)) - 1:
            response.append("\n" + "-" * 20 + "\n")
    
    # Add note if we truncated results
    if len(messages) > max_messages:
        response.append(f"\n... and {len(messages) - max_messages} more messages not shown.")
    
    return "\n".join(response)

async def _format_with_llm(
    messages: List[Dict[str, Any]],
    query: str,
    parsed_query: Optional[Dict[str, Any]] = None,
    translator: Optional[Callable] = None,
    verbosity: str = "standard",
    include_quotes: bool = True,
    include_timestamps: bool = True,
    include_sender_info: bool = True,
    include_channel_info: bool = True,
    context_messages: Optional[List[Dict[str, Any]]] = None,
    chat_messages_map: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> str:
    """
    Format search results using LLM for improved summarization and insights
    
    Args:
        messages: List of message dictionaries from search results
        query: Original search query
        parsed_query: Parsed query with metadata
        translator: Optional translation function
        verbosity: Verbosity level ("concise", "standard", or "detailed")
        include_quotes: Whether to include quotes in the response
        include_timestamps: Whether to include timestamps
        include_sender_info: Whether to include sender information
        include_channel_info: Whether to include channel information
        context_messages: Additional context messages from the conversation history
        chat_messages_map: Dictionary mapping chat IDs to lists of messages, for better organization
        
    Returns:
        Formatted response string
    """
    if not messages:
        return _("No messages found matching your query.")
    
    # Get LLM client
    llm_client = get_llm_client()
    if not llm_client:
        logger.warning("LLM client not available, falling back to simple formatting")
        return _format_simple_fallback(messages, query)
    
    try:
        # Organize messages by chat group
        chat_groups = defaultdict(list)
        for msg in messages:
            chat_id = msg.get("chat_id")
            if chat_id:
                # Check for match_type - useful for explaining how the message was found
                match_type = msg.get("match_type", "direct")
                matched_term = msg.get("matched_term", query)
                
                # Add match info to the message
                msg["match_info"] = {
                    "type": match_type,
                    "term": matched_term
                }
                
                chat_groups[chat_id].append(msg)
        
        # Format timestamps based on user preference
        def format_time(timestamp):
            if not timestamp:
                return ""
            
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp)
                except ValueError:
                    try:
                        timestamp = datetime.fromtimestamp(float(timestamp))
                    except (ValueError, TypeError):
                        return timestamp
            
            if isinstance(timestamp, (int, float)):
                timestamp = datetime.fromtimestamp(timestamp)
                
            if isinstance(timestamp, datetime):
                return timestamp.strftime("%Y-%m-%d %H:%M:%S")
            
            return str(timestamp)
        
        # Build the prompt for the LLM
        system_prompt = f"""You are a chat message analysis assistant, tasked with summarizing and providing insights from search results.

Search Query: "{query}"

Your task is to analyze messages matching this query and provide a helpful response based on the verbosity level requested:
- For "concise" responses: Provide a brief 1-2 sentence summary of the key points.
- For "standard" responses: Provide a balanced summary with key points and limited context.
- For "detailed" responses: Provide a comprehensive analysis with nuanced insights about the conversation.

Some messages were matched directly with the query terms, while others were found through semantic matching or alternative terms.
Consider how each message was found when analyzing relevance.

Format your response to be clear, helpful, and informative. Use natural language and don't include message IDs or technical details in your response.

Use bullet points or numbered lists when appropriate for clarity. Reference timestamps and senders if helpful for context."""

        prompt_parts = []
        prompt_parts.append(f"## Search Query: \"{query}\"")
        
        if parsed_query and parsed_query.get("expanded_queries"):
            expanded_terms = parsed_query.get("expanded_queries", [])
            prompt_parts.append(f"\n## Expanded Search Terms: {', '.join(expanded_terms)}")
        
        # Add matched messages section
        if chat_groups:
            prompt_parts.append("\n## Matched Messages:")
            for chat_id, msgs in chat_groups.items():
                chat_name = msgs[0].get("chat_title", f"Chat {chat_id}")
                prompt_parts.append(f"\n### Chat: {chat_name}")
                
                for msg in msgs:
                    # Format message content
                    content = msg.get("text", "").strip()
                    if not content:
                        content = "[Non-text content]"
                    
                    # Get sender info
                    sender = msg.get("sender", "Unknown")
                    
                    # Get timestamp
                    timestamp_str = ""
                    if include_timestamps and msg.get("timestamp"):
                        timestamp_str = f" [{format_time(msg.get('timestamp'))}]"
                    
                    # Get match info for this message
                    match_info = f"[Matched via: {msg.get('match_info', {}).get('type', 'direct')}]"
                    if msg.get('match_info', {}).get('type') == "semantic":
                        match_info = f"[Matched via semantic term: \"{msg.get('match_info', {}).get('term', query)}\"]"
                    
                    # Format the message for the prompt
                    formatted_msg = f"- **{sender}{timestamp_str}**: {content} {match_info}"
                    prompt_parts.append(formatted_msg)
                    
                    # Add context messages if available
                    if msg.get("context"):
                        prompt_parts.append("\n  **Context Messages:**")
                        for ctx_msg in msg.get("context", [])[:5]:  # Limit to 5 context messages
                            ctx_content = ctx_msg.get("text", "").strip()
                            if not ctx_content:
                                ctx_content = "[Non-text content]"
                            
                            ctx_sender = ctx_msg.get("sender", "Unknown")
                            
                            ctx_timestamp_str = ""
                            if include_timestamps and ctx_msg.get("timestamp"):
                                ctx_timestamp_str = f" [{format_time(ctx_msg.get('timestamp'))}]"
                            
                            ctx_formatted = f"  - **{ctx_sender}{ctx_timestamp_str}**: {ctx_content}"
                            prompt_parts.append(ctx_formatted)
                        prompt_parts.append("")  # Add an empty line after context
        
        # Add instructions based on verbosity
        prompt_parts.append("\n## Instructions:")
        
        if verbosity == "concise":
            prompt_parts.append("Provide a very brief 1-2 sentence summary of the key points from these messages. Focus only on the most important information directly relevant to the query.")
        
        elif verbosity == "detailed":
            prompt_parts.append("""Provide a comprehensive analysis of these search results, including:
1. A detailed summary of the key information found
2. Analysis of how the messages relate to each other and the search query
3. Any insights or patterns you notice in the conversation
4. Consider how some messages were found through semantic matching and evaluate their relevance
5. Mention specific details from the most relevant messages
""")
        
        else:  # standard verbosity
            prompt_parts.append("""Provide a balanced summary of these search results, including:
1. The key points relevant to the search query
2. Important context that helps understand the conversation
3. Brief mention of how messages were matched (direct or semantic)
4. Be concise while still covering the important information
""")
        
        # Build the final prompt
        user_prompt = "\n".join(prompt_parts)
        
        # Send to LLM
        response = llm_client.chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], model="gpt-3.5-turbo-16k", temperature=0.3, max_tokens=1024)
        
        if not response or not response.get("content"):
            logger.warning("Empty response from LLM, falling back to simple formatting")
            return _format_simple_fallback(messages, query)
        
        llm_response = response.get("content", "").strip()
        
        # Add citation footer
        footer = _("\n\nResults generated by SilentGem using AI-powered summarization.")
        return llm_response + footer
        
    except Exception as e:
        logger.error(f"Error formatting with LLM: {e}", exc_info=True)
        return _format_simple_fallback(messages, query)

def _format_simple_fallback(messages: List[Dict[str, Any]], query: str) -> str:
    """
    Simple fallback formatter when other methods fail
    """
    response = [f"Found {len(messages)} messages matching '{query}'", ""]
    
    for i, msg in enumerate(messages[:5]):  # Only show top 5
        timestamp = datetime.fromtimestamp(msg.get("timestamp", 0)).strftime("%Y-%m-%d %H:%M") if msg.get("timestamp") else "Unknown time"
        sender = msg.get("sender_name", "Unknown")
        content = msg.get("content", "[No content]")
        
        # Truncate long content
        if len(content) > 100:
            content = content[:100] + "..."
        
        response.append(f"{i+1}. From: {sender} at {timestamp}")
        response.append(f"   {content}")
        response.append("")
    
    if len(messages) > 5:
        response.append(f"... and {len(messages) - 5} more messages not shown.")
    
    return "\n".join(response)