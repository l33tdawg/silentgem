"""
Response formatter for formatting search results for display in Telegram
"""

from datetime import datetime
import time
from typing import List, Dict, Any, Optional
from loguru import logger

from silentgem.translator import create_translator
from silentgem.config.insights_config import get_insights_config

async def format_search_results(
    messages: List[Dict[str, Any]],
    query: str,
    parsed_query: Optional[Dict[str, Any]] = None,
    verbosity: str = "standard",
    include_quotes: bool = True,
    include_timestamps: bool = True,
    include_sender_info: bool = True
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
        
    Returns:
        str: Formatted response
    """
    try:
        if not messages:
            return f"No messages found matching your query: '{query}'"
        
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
                include_sender_info=include_sender_info
            )
        
        # Otherwise, use basic formatting
        return _format_basic(
            messages=messages,
            query=query,
            parsed_query=parsed_query,
            verbosity=verbosity,
            include_quotes=include_quotes,
            include_timestamps=include_timestamps,
            include_sender_info=include_sender_info
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
    include_sender_info: bool = True
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
    parsed_query: Optional[Dict[str, Any]],
    translator,
    verbosity: str = "standard",
    include_quotes: bool = True,
    include_timestamps: bool = True,
    include_sender_info: bool = True
) -> str:
    """
    Format search results using the LLM for natural language summarization
    """
    try:
        # Determine how many messages to include based on verbosity
        if verbosity == "concise":
            max_messages = min(5, len(messages))
        elif verbosity == "standard":
            max_messages = min(10, len(messages))
        else:  # detailed
            max_messages = min(15, len(messages))
        
        # Build prompt with message data
        prompt = f"""You are an assistant helping summarize search results from a chat history.

User query: "{query}"

I found {len(messages)} messages matching this query. Here are the details for the first {max_messages}:

"""
        
        # Add message details to prompt
        for i, msg in enumerate(messages[:max_messages]):
            prompt += f"MESSAGE {i+1}:\n"
            
            if include_sender_info and msg.get("sender_name"):
                prompt += f"From: {msg['sender_name']}\n"
            
            if include_timestamps and msg.get("timestamp"):
                dt = datetime.fromtimestamp(msg["timestamp"])
                time_str = dt.strftime("%Y-%m-%d %H:%M")
                prompt += f"Time: {time_str}\n"
            
            if msg.get("content"):
                prompt += f"Content: {msg['content']}\n"
            else:
                prompt += "Content: [No text content]\n"
            
            if msg.get("is_media"):
                prompt += f"Has media: Yes ({msg.get('media_type', 'unknown')})\n"
            
            prompt += "\n"
        
        # Add formatting instructions based on verbosity
        if verbosity == "concise":
            prompt += """
Please give a very brief response about these search results. Focus only on the most important information.
Format your response as follows:
1. A brief introduction (1 sentence)
2. A few bullet points with key findings
3. No quotes unless absolutely necessary

Keep the entire response under 150 words.
"""
        elif verbosity == "standard":
            prompt += """
Please summarize these search results in a clear, helpful way.
Format your response as follows:
1. An introduction summarizing what was found
2. Key points from the messages
3. Include a few brief quotes if relevant (max 1-2 sentences each)

Keep the entire response around 250 words.
"""
        else:  # detailed
            prompt += """
Please provide a comprehensive summary of these search results.
Format your response as follows:
1. A detailed introduction explaining what was found
2. Comprehensive coverage of the content with analysis
3. Include relevant quotes (marked clearly)
4. Mention specific senders and timestamps when relevant
5. A conclusion summarizing the main takeaways

Feel free to use formatting like bullet points and sections to enhance readability.
"""
        
        # Process with LLM
        try:
            response = await translator.translate(prompt, source_language="english")
            return response.strip()
        except Exception as e:
            logger.error(f"Error processing with LLM: {e}")
            # Fall back to basic formatting
            return _format_basic(
                messages=messages,
                query=query,
                parsed_query=parsed_query,
                verbosity=verbosity,
                include_quotes=include_quotes,
                include_timestamps=include_timestamps,
                include_sender_info=include_sender_info
            )
    
    except Exception as e:
        logger.error(f"Error formatting with LLM: {e}")
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