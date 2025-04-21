"""
Response formatter for formatting search results for display in Telegram
"""

from datetime import datetime
import time
from typing import List, Dict, Any, Optional
from loguru import logger

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
    translator: Optional[BaseTranslator] = None,
    verbosity: str = "standard",
    include_quotes: bool = True,
    include_timestamps: bool = True,
    include_sender_info: bool = True,
    include_channel_info: bool = True,
    context_messages: Optional[List[Dict[str, Any]]] = None,
    chat_messages_map: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> str:
    """
    Format search results using LLM for better summarization and insights
    
    Args:
        messages: List of message dictionaries from the database
        query: Original query string
        parsed_query: Parsed query dictionary from NLU
        translator: Translator instance to use for LLM calls
        verbosity: Response verbosity (concise, standard, detailed)
        include_quotes: Whether to include original message quotes
        include_timestamps: Whether to include timestamps
        include_sender_info: Whether to include sender information
        include_channel_info: Whether to include channel information and links
        context_messages: Additional context messages from the conversation history
        chat_messages_map: Dictionary mapping chat IDs to lists of messages, for better organization
        
    Returns:
        str: LLM-formatted response
    """
    try:
        # Create translator if not provided
        if not translator:
            translator = await create_translator()
        
        # Get number of unique chat groups
        chat_groups = set()
        for msg in messages:
            source_chat = msg.get('source_chat_id')
            target_chat = msg.get('target_chat_id')
            if source_chat:
                chat_groups.add(source_chat)
            if target_chat:
                chat_groups.add(target_chat)
        
        # Format the messages for LLM input
        formatted_messages = []
        
        # Reformat message data for LLM prompt
        for idx, msg in enumerate(messages):
            # Format timestamps
            timestamp = datetime.fromtimestamp(msg.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Get sender info
            sender = msg.get('sender_name', 'Unknown')
            
            # Get channel info - always include for cross-chat awareness
            source_chat_id = msg.get('source_chat_id', None)
            target_chat_id = msg.get('target_chat_id', None)
            
            chat_id = target_chat_id or source_chat_id
            chat_info = f"\nChat Group: {chat_id}"
            
            # Format message text
            text = msg.get('content', '').strip()
            
            # Combine all information for this message
            formatted_msg = f"MATCHING MESSAGE {idx + 1}:\n"
            
            if include_sender_info:
                formatted_msg += f"From: {sender}\n"
                
            if include_timestamps:
                formatted_msg += f"Date: {timestamp}\n"
                
            formatted_msg += chat_info
            
            if include_quotes and text:
                formatted_msg += f"\nContent: {text}"
                
            formatted_messages.append(formatted_msg)
            
        # Build the LLM prompt
        prompt = f"""As an advanced Chat Insights assistant, analyze and synthesize information from multiple Telegram chat groups.

USER QUERY: "{query}"

This query returned {len(messages)} matching messages across {len(chat_groups)} different chat groups.

MATCHED MESSAGES:
{chr(10).join(formatted_messages)}

"""

        # Add context messages if provided
        if context_messages and len(context_messages) > 0:
            # Use the chat_messages_map if available for better organization
            if chat_messages_map and len(chat_messages_map) > 0:
                # Format context by chat group for clear organization
                chat_sections = []
                
                for chat_id, chat_messages in chat_messages_map.items():
                    # Sort by timestamp
                    chat_messages.sort(key=lambda x: x.get('timestamp', 0))
                    
                    # Format each conversation thread
                    thread_messages = []
                    
                    # Add header for this chat
                    thread_header = f"CONTEXT FROM CHAT GROUP {chat_id}:"
                    thread_messages.append(thread_header)
                    
                    for msg in chat_messages:
                        # Skip metadata messages
                        if msg.get('metadata', False):
                            continue
                            
                        # Format message content concisely
                        timestamp = datetime.fromtimestamp(msg.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M')
                        sender = msg.get('sender_name', 'Unknown')
                        text = msg.get('content', '').strip()
                        
                        # Add concise message
                        msg_text = f"{timestamp} - {sender}: {text}"
                        thread_messages.append(msg_text)
                    
                    # Only add this section if it has messages
                    if len(thread_messages) > 1:  # More than just the header
                        chat_sections.append("\n".join(thread_messages))
                
                # Add all chat sections to prompt
                if chat_sections:
                    prompt += f"""
ADDITIONAL CONTEXT FROM MULTIPLE CHAT GROUPS:
The following messages provide additional context from before and after the matching messages, organized by chat group.
Use this broad context to understand the bigger picture across different sources of information.

{chr(10).join(chat_sections)}

"""
            else:
                # Fall back to simpler context format if chat_messages_map not available
                # Check for metadata messages
                metadata_msgs = [msg for msg in context_messages if msg.get('metadata', False)]
                context_msgs = [msg for msg in context_messages if not msg.get('metadata', False)]
                
                # Format context messages
                formatted_context = []
                
                # Add any metadata messages first
                for meta_msg in metadata_msgs:
                    formatted_context.append(f"METADATA: {meta_msg.get('content', '')}")
                
                # Sort context messages by timestamp
                context_msgs.sort(key=lambda x: x.get('timestamp', 0))
                
                # Format each context message
                for i, ctx_msg in enumerate(context_msgs[:50]):  # Limit to 50 messages
                    # Format message content concisely
                    timestamp = datetime.fromtimestamp(ctx_msg.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M')
                    sender = ctx_msg.get('sender_name', 'Unknown')
                    chat_id = ctx_msg.get('source_chat_id') or ctx_msg.get('target_chat_id', 'Unknown')
                    text = ctx_msg.get('content', '').strip()
                    
                    # Add concise message with chat group info
                    msg_text = f"{timestamp} - {sender} [Chat: {chat_id}]: {text}"
                    formatted_context.append(msg_text)
                
                # Add context section to prompt
                if formatted_context:
                    prompt += f"""
ADDITIONAL CONTEXT FROM MULTIPLE CHAT GROUPS:
The following messages provide additional context from before and after the matching messages.
These are from various chat groups that may contain relevant information.

{chr(10).join(formatted_context)}

"""

        # Add instructions based on verbosity
        if verbosity == "concise":
            prompt += """
INSTRUCTIONS:
1. Create a VERY BRIEF summary (2-3 sentences maximum) of the information found.
2. Focus on directly answering the query with facts from the messages.
3. If information comes from multiple chat groups, synthesize it to provide a unified answer.
4. Consider the temporal relationships between messages across different groups.
5. Keep your response extremely concise.
6. DO NOT mention the search process or message numbers in your response.
"""
        elif verbosity == "detailed":
            prompt += """
INSTRUCTIONS:
1. Provide a comprehensive analysis of the information found across all chat groups.
2. Begin with a clear executive summary answering the original query.
3. Analyze patterns, connections, and contrasting information between different chat groups.
4. Identify key insights that emerge when considering all sources together.
5. Highlight temporal relationships and potential cause-effect patterns across chats.
6. Format your response in a well-structured way with clear sections.
7. If relevant, note differences in how the topic is discussed across different groups.
8. Make it clear when you're drawing connections across multiple sources.
9. End with the most significant conclusion supported by messages across all groups.
"""
        else:  # standard
            prompt += """
INSTRUCTIONS:
1. Provide a clear summary that directly answers the query (3-5 sentences).
2. Synthesize information from all relevant chat groups to provide a unified understanding.
3. Highlight any significant patterns or differences in how information appears across different groups.
4. Focus on making connections between related information from different sources.
5. Present a cohesive narrative that shows the bigger picture across all messages.
6. Keep the response focused and relevant to the query.
7. DO NOT mention message numbers or the search process in your response.
"""

        # Get response from LLM
        response = await translator.translate(prompt, max_tokens=1024)
        
        # Clean up the response if needed
        response = response.strip()
        
        return response
        
    except Exception as e:
        logger.error(f"Error formatting with LLM: {e}")
        # Fall back to basic formatting
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