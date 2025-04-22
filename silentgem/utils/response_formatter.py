"""
Response formatter for formatting search results for display in Telegram
"""

from datetime import datetime
import time
from typing import List, Dict, Any, Optional, Callable
from loguru import logger
from collections import defaultdict
import re

from silentgem.translator import create_translator, BaseTranslator
from silentgem.config.insights_config import get_insights_config
from silentgem.llm.llm_client import get_llm_client

async def format_search_results(
    messages: List[Dict[str, Any]],
    query: str,
    parsed_query: Optional[Dict[str, Any]] = None,
    verbosity: str = "standard",
    include_quotes: bool = True,
    include_timestamps: bool = True,
    include_sender_info: bool = True,
    include_channel_info: bool = True,
    chat_messages_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None
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
        chat_messages_map: Dictionary mapping chat IDs to lists of messages, for better organization
        conversation_history: History of the conversation for follow-up context
        
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
                chat_messages_map=chat_messages_map,
                conversation_history=conversation_history
            )
        
        # Otherwise, use basic formatting
        return await _format_basic(
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
    chat_messages_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None
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
        conversation_history: Conversation history for follow-up awareness
        
    Returns:
        Formatted response string
    """
    if not messages:
        return "No messages found matching your query."
    
    # Get LLM client
    llm_client = get_llm_client()
    if not llm_client:
        logger.warning("LLM client not available, falling back to simple formatting")
        return _format_simple_fallback(messages, query)
    
    try:
        # First make sure all messages are dicts with proper get method
        safe_messages = []
        for msg in messages:
            # If it's already a dict with get method
            if isinstance(msg, dict) and hasattr(msg, 'get'):
                safe_messages.append(msg)
            else:
                # For any other object type (like Message objects), convert to dict
                msg_dict = {}
                
                # Extract common fields with safe attribute access
                if hasattr(msg, 'id'):
                    msg_dict['id'] = msg.id
                
                if hasattr(msg, 'text'):
                    msg_dict['text'] = msg.text
                    msg_dict['content'] = msg.text  # Duplicate for compatibility
                elif hasattr(msg, 'content'):
                    msg_dict['content'] = msg.content
                    msg_dict['text'] = msg.content  # Duplicate for compatibility
                
                # Extract chat info
                if hasattr(msg, 'chat') and hasattr(msg.chat, 'id'):
                    msg_dict['chat_id'] = str(msg.chat.id)
                    msg_dict['source_chat_id'] = str(msg.chat.id)
                    msg_dict['target_chat_id'] = str(msg.chat.id)
                    if hasattr(msg.chat, 'title'):
                        msg_dict['chat_title'] = msg.chat.title
                
                # Extract sender info
                if hasattr(msg, 'from_user'):
                    sender_name = getattr(msg.from_user, 'first_name', 'Unknown')
                    if hasattr(msg.from_user, 'last_name') and msg.from_user.last_name:
                        sender_name += f" {msg.from_user.last_name}"
                    msg_dict['sender_name'] = sender_name
                    msg_dict['sender'] = sender_name
                
                # Extract timestamp
                if hasattr(msg, 'date'):
                    try:
                        if hasattr(msg.date, 'timestamp'):
                            msg_dict['timestamp'] = int(msg.date.timestamp())
                        else:
                            msg_dict['timestamp'] = int(time.time())
                    except:
                        msg_dict['timestamp'] = int(time.time())
                else:
                    msg_dict['timestamp'] = int(time.time())
                
                # Add to safe messages
                safe_messages.append(msg_dict)
        
        # Use the safe messages instead of the original ones
        messages = safe_messages
        
        # Organize messages by chat group
        chat_groups = defaultdict(list)
        for msg in messages:
            chat_id = msg.get("chat_id") or msg.get("source_chat_id") or msg.get("target_chat_id")
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
        
        # Build the prompt for the LLM - enhancing for more conversational responses
        system_prompt = f"""You are an intelligent chat assistant analyzing conversation history for a user.

Your task is to provide a natural, conversational response to the user's query: "{query}"

Rather than just showing search results, you should synthesize information from the messages into a cohesive answer that directly addresses the user's query. You are having a conversation with the user, not just returning search results.

Context:
- You have access to message history across multiple chat channels
- These messages were retrieved based on their relevance to the user's query
- Some messages match the query directly, others through semantic matching
- The user wants insights and understanding, not just raw data
- Consider the chronology of messages to understand how topics evolved

Guidelines:
1. Be conversational and natural in your response - as if you're having a direct conversation
2. Synthesize information across messages to form a coherent answer
3. Address the user's question directly rather than just listing what was found
4. Include specific details and quotes when they directly support your answer
5. If discussing multiple perspectives, present them in a balanced way
6. When appropriate, analyze trends or patterns in the conversation
7. Don't just list messages - create an informative narrative
8. Never say "I found X messages" - focus on the content and insights instead
9. When referring to messages or their sources, do so naturally within your response
10. For time-based queries, consider the chronology of information

Your response should feel like a knowledgeable friend answering a question, not a search engine returning results."""

        # Add context about verbosity
        if verbosity == "concise":
            system_prompt += "\nKeep your response brief and focused on the most important information - 2-3 sentences at most."
        elif verbosity == "detailed":
            system_prompt += "\nProvide a comprehensive answer that explores nuances, connections between information sources, and offers deeper analysis."
        else:  # standard
            system_prompt += "\nProvide a balanced response that covers the key information without unnecessary details."

        prompt_parts = []
        prompt_parts.append(f"## User Query: \"{query}\"")
        
        # Add context about expanded search terms
        if parsed_query and parsed_query.get("expanded_queries"):
            expanded_terms = parsed_query.get("expanded_queries", [])
            prompt_parts.append(f"\n## Related Concepts: {', '.join(expanded_terms)}")
        
        # Add matched messages section with improved organization
        if chat_groups:
            prompt_parts.append("\n## Messages by Chat Channel:")
            
            for chat_id, msgs in chat_groups.items():
                # Get chat title or default to chat ID
                chat_name = None
                for msg in msgs:
                    if msg.get("chat_title"):
                        chat_name = msg.get("chat_title")
                        break
                
                if not chat_name:
                    chat_name = f"Chat {chat_id}"
                    
                prompt_parts.append(f"\n### Channel: {chat_name}")
                
                # Sort messages by timestamp to preserve conversation flow
                msgs.sort(key=lambda m: m.get("timestamp", 0))
                
                # Add messages
                for msg in msgs:
                    # Format message content
                    content = msg.get("content", "").strip() or msg.get("text", "").strip()
                    if not content:
                        content = "[Non-text content]"
                    
                    # Get sender info
                    sender = msg.get("sender_name", "Unknown") or msg.get("sender", "Unknown")
                    
                    # Get timestamp
                    timestamp_str = ""
                    if include_timestamps and (msg.get("timestamp") or msg.get("date")):
                        timestamp_value = msg.get("timestamp") or msg.get("date")
                        timestamp_str = f" [{format_time(timestamp_value)}]"
                    
                    # Format the message for the prompt
                    formatted_msg = f"- **{sender}{timestamp_str}**: {content}"
                    prompt_parts.append(formatted_msg)
                    
                    # Include context messages if available
                    if msg.get("context") and True:
                        prompt_parts.append("\n  **Context messages:**")
                        for ctx_msg in msg.get("context", []):
                            ctx_content = ctx_msg.get("content", "").strip() or ctx_msg.get("text", "").strip()
                            if not ctx_content:
                                continue
                                
                            ctx_sender = ctx_msg.get("sender_name", "Unknown") or ctx_msg.get("sender", "Unknown")
                            ctx_time = ""
                            if include_timestamps and (ctx_msg.get("timestamp") or ctx_msg.get("date")):
                                ctx_time_value = ctx_msg.get("timestamp") or ctx_msg.get("date")
                                ctx_time = f" [{format_time(ctx_time_value)}]"
                                
                            ctx_formatted = f"  - **{ctx_sender}{ctx_time}**: {ctx_content}"
                            prompt_parts.append(ctx_formatted)
        
        # Add chat message maps if provided (for better context organization)
        if chat_messages_map and len(chat_messages_map) > 0:
            prompt_parts.append("\n## Extended Context by Channel:")
            
            for chat_id, chat_msgs in chat_messages_map.items():
                # Sort by timestamp
                chat_msgs.sort(key=lambda m: m.get("timestamp", 0))
                
                # Get chat title
                chat_title = None
                for msg in chat_msgs:
                    if msg.get("chat_title"):
                        chat_title = msg.get("chat_title")
                        break
                        
                if not chat_title:
                    chat_title = f"Chat {chat_id}"
                    
                prompt_parts.append(f"\n### Channel: {chat_title}")
                prompt_parts.append(f"Conversation flow ({len(chat_msgs)} messages):")
                
                # Add messages
                for msg in chat_msgs:
                    # Format message content
                    content = msg.get("content", "").strip() or msg.get("text", "").strip()
                    if not content:
                        content = "[Non-text content]"
                    
                    # Get sender info
                    sender = msg.get("sender_name", "Unknown") or msg.get("sender", "Unknown")
                    
                    # Get timestamp
                    timestamp_str = ""
                    if include_timestamps and (msg.get("timestamp") or msg.get("date")):
                        timestamp_value = msg.get("timestamp") or msg.get("date")
                        timestamp_str = f" [{format_time(timestamp_value)}]"
                    
                    # Format the message for the prompt
                    formatted_msg = f"- **{sender}{timestamp_str}**: {content}"
                    prompt_parts.append(formatted_msg)
        
        # Add conversation history if provided
        conversation_context = ""
        if conversation_history and len(conversation_history) > 1:  # More than just the current query
            # Extract previous exchanges for context
            conversation_context = "Previous conversation history:\n"
            for i, msg in enumerate(conversation_history[:-1]):  # Exclude current query
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                conversation_context += f"{role.capitalize()}: {content}\n"
        
        # Add specific instructions based on verbosity level
        if verbosity == "concise":
            prompt_parts.append("""
## Response Instructions
Provide a brief, conversational response that directly answers the user's question. 
Focus only on the most essential information without mentioning search details.
Keep it to 2-3 sentences maximum.
""")
        
        elif verbosity == "detailed":
            prompt_parts.append("""
## Response Instructions
Provide a comprehensive, conversational response that thoroughly addresses the user's question.
Synthesize information across all relevant messages and channels to create a complete picture.
Include analysis of different perspectives, trends over time, and connections between information sources.
Don't list messages - create a coherent narrative that directly answers the query with depth and insight.
""")
        
        else:  # standard verbosity
            prompt_parts.append("""
## Response Instructions
Provide a balanced, conversational response that addresses the user's question directly.
Synthesize the key information from relevant messages into a coherent answer.
Include important supporting details without overwhelming the user.
Focus on creating a helpful response rather than just reporting what was found.
""")
        
        # Emphasize conversational nature
        prompt_parts.append("""
## IMPORTANT
Your response should sound like a knowledgeable friend having a conversation, not a search engine reporting results.
Never start with phrases like "Based on the messages..." or "I found X messages...".
Simply answer the user's question directly in a natural, conversational way using the information provided.
""")
        
        # Build the final prompt
        user_prompt = "\n".join(prompt_parts)
        
        # Send to LLM with higher temperature for more natural responses
        response = await llm_client.chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], temperature=0.7, max_tokens=1024)
        
        if not response or not response.get("content"):
            logger.warning("Empty response from LLM, falling back to simple formatting")
            return _format_simple_fallback(messages, query)
        
        llm_response = response.get("content", "").strip()
        
        # Remove any phrases like "Based on the messages..." that might start the response
        llm_response = re.sub(r'^(Based on (the|your|these) (messages|search results|information).*?[,.] )', '', llm_response)
        llm_response = re.sub(r'^(I found|There are) \d+ messages.*?[,.] ', '', llm_response)
        
        # Add subtle attribution footer
        footer = "\n\n_Powered by SilentGem_"
        return llm_response + footer
        
    except Exception as e:
        logger.error(f"Error in LLM formatting: {e}")
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