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
    Format results using LLM for conversational responses, using internally grouped messages for context.
    """
    try:
        llm_client = get_llm_client()
        if not llm_client:
            logger.warning("LLM client not available for LLM formatting")
            # Fallback needs sanitized messages - attempt sanitization here too
            sanitized_fallback_messages = [] 
            for msg in messages:
                if isinstance(msg, dict): sanitized_fallback_messages.append(msg)
                # Add basic conversion if needed, similar to below
            return _format_simple_fallback(sanitized_fallback_messages, query)

        # --- START: Sanitize the input 'messages' list --- 
        safe_messages = []
        try:
            for msg in messages:
                msg_dict = None
                if isinstance(msg, dict):
                    msg_dict = msg
                elif hasattr(msg, 'id') and hasattr(msg, 'text') and hasattr(msg, 'chat'):
                    try:
                        msg_dict = {
                            'id': msg.id,
                            'text': msg.text or getattr(msg, 'content', ''),
                            'source_chat_id': str(getattr(msg.chat, 'id', 'unknown')),
                            'target_chat_id': str(getattr(msg.chat, 'id', 'unknown')),
                            'chat_id': str(getattr(msg.chat, 'id', 'unknown')), # Add chat_id for grouping
                            'sender_name': getattr(getattr(msg, 'from_user', None), 'first_name', 'Unknown'),
                            'timestamp': int(getattr(msg, 'date', datetime.now()).timestamp()) if hasattr(msg, 'date') else int(time.time()),
                            'content': msg.text or getattr(msg, 'content', ''),
                            'sender': getattr(getattr(msg, 'from_user', None), 'first_name', 'Unknown'),
                            'date': getattr(msg, 'date', datetime.now()).isoformat() if hasattr(msg, 'date') else datetime.now().isoformat(),
                            'chat_title': getattr(getattr(msg, 'chat', None), 'title', 'Unknown Chat')
                        }
                    except Exception as convert_err:
                        logger.warning(f"Failed to convert message-like object to dict in _format_with_llm: {convert_err}. Object: {type(msg)}")
                        msg_dict = None
                else:
                    logger.warning(f"Unexpected object type encountered in _format_with_llm input: {type(msg)}. Skipping.")
                    
                if isinstance(msg_dict, dict):
                    safe_messages.append(msg_dict)
        except Exception as e:
            logger.error(f"Error during message sanitization loop in _format_with_llm: {e}")
            # If sanitization fails badly, fallback is the only option
            return _format_simple_fallback(messages, query) # Use original messages for fallback if sanitization failed
        # --- END: Sanitize the input 'messages' list ---

        # Now, create chat_groups using the sanitized safe_messages
        chat_groups = defaultdict(list)
        for msg in safe_messages: # Use safe_messages here
            # Ensure msg is a dict (should be guaranteed by above loop, but double-check)
            if not isinstance(msg, dict):
                 logger.warning(f"Non-dict object found in safe_messages: {type(msg)}")
                 continue 
                 
            chat_id = msg.get("chat_id") or msg.get("source_chat_id") or msg.get("target_chat_id")
            if chat_id:
                # Add match info if available (you might need to pass this info differently now)
                # msg["match_info"] = { ... } # Placeholder - match info might need to come from elsewhere
                chat_groups[chat_id].append(msg)

        # Helper to format timestamps
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
            elif isinstance(timestamp, (int, float)):
                try:
                    timestamp = datetime.fromtimestamp(timestamp)
                except (OSError, ValueError):
                    return str(timestamp)
            
            if isinstance(timestamp, datetime):
                return timestamp.strftime("%Y-%m-%d %H:%M:%S")
            
            return str(timestamp)

        # Build the prompt for the LLM
        system_prompt = f"""You are an intelligent chat assistant analyzing conversation history for a user.

Your task is to provide a natural, conversational response to the user's query: "{query}"

Synthesize information from the messages provided into a cohesive answer.

Context:
- Messages are grouped by chat channel.
- Consider the chronology within each channel.

Guidelines:
1. Be conversational and natural.
2. Synthesize information across messages.
3. Address the user's question directly.
4. Include key details/quotes.
5. Don't just list messages - create a narrative.
6. Never say "I found X messages".

Your response should feel like a knowledgeable friend answering a question."""

        # Add context about verbosity
        if verbosity == "concise":
            system_prompt += "\nKeep your response brief and focused - 2-3 sentences max."
        elif verbosity == "detailed":
            system_prompt += "\nProvide a comprehensive answer exploring nuances and connections."
        else:  # standard
            system_prompt += "\nProvide a balanced response covering key information."

        prompt_parts = []
        prompt_parts.append(f"## User Query: \"{query}\"")
        
        if parsed_query and parsed_query.get("expanded_queries"):
             expanded_terms = parsed_query.get("expanded_queries", [])
             prompt_parts.append(f"\n## Related Concepts Searched: {', '.join(expanded_terms)}")

        # Add messages using the internally created chat_groups
        if chat_groups:
            prompt_parts.append("\n## Relevant Messages by Channel:")
            
            for chat_id, msgs in chat_groups.items():
                # Get chat title from the first message (best effort)
                chat_title = msgs[0].get("chat_title", f"Chat {chat_id}") if msgs else f"Chat {chat_id}"
                    
                prompt_parts.append(f"\n### Channel: {chat_title}")
                
                # Sort messages by timestamp
                try:
                    msgs.sort(key=lambda m: m.get("timestamp", 0))
                except Exception as sort_err:
                    logger.warning(f"Could not sort messages for chat {chat_id}: {sort_err}")

                prompt_parts.append(f"Conversation flow ({len(msgs)} messages):")
                
                # Add messages for this chat
                for msg in msgs:
                    # msg should already be a dict due to sanitization at the start
                    content = msg.get("content", "").strip() or msg.get("text", "").strip() or "[Non-text content]"
                    sender = msg.get("sender_name", "Unknown") or msg.get("sender", "Unknown")
                    timestamp_str = ""
                    if include_timestamps:
                        timestamp_value = msg.get("timestamp") or msg.get("date")
                        if timestamp_value:
                            timestamp_str = f" [{format_time(timestamp_value)}]"
                    
                    formatted_msg = f"- **{sender}{timestamp_str}**: {content}"
                    prompt_parts.append(formatted_msg)
        else:
             prompt_parts.append("\n## Relevant Messages:")
             prompt_parts.append("(No messages found or processed)")

        # Add conversation history (ensure dicts)
        if conversation_history and len(conversation_history) > 1:
            prompt_parts.append("\n## Previous Conversation Context:")
            for i, msg in enumerate(conversation_history[:-1]):
                if isinstance(msg, dict):
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    prompt_parts.append(f"{role.capitalize()}: {content}")
                else:
                     logger.warning(f"Skipping non-dict item in conversation_history: {type(msg)}")

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
        
        # Add safety log for long prompts
        if len(user_prompt) > 15000: # Arbitrary limit, adjust as needed
            logger.warning(f"Very long prompt generated for LLM ({len(user_prompt)} chars). Consider reducing context or message count.")
        elif len(user_prompt) > 8000:
            logger.debug(f"Prompt length for LLM: {len(user_prompt)} chars.")

        # Send to LLM
        response = await llm_client.chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], temperature=0.7, max_tokens=1024)
        
        if not response or not response.get("content"):
            logger.warning("Empty response from LLM, falling back to simple formatting")
            # Use the sanitized safe_messages for fallback
            return _format_simple_fallback(safe_messages, query)
        
        llm_response = response.get("content", "").strip()
        
        # Basic post-processing
        llm_response = re.sub(r'^Based on (the|your|these) (messages|search results|information).*?[,.:]\s*', '', llm_response, flags=re.IGNORECASE)
        llm_response = re.sub(r'^I found \d+ messages.*?[,.:]\s*', '', llm_response, flags=re.IGNORECASE)
        llm_response = re.sub(r'^Here is a summary.*?[,.:]\s*', '', llm_response, flags=re.IGNORECASE)
        
        # Add subtle attribution footer
        footer = "\n\n*Powered by SilentGem Insights*"
        # Ensure footer isn't added if response is empty
        return llm_response + footer if llm_response else "Sorry, I couldn't generate a response based on the information found."
        
    except Exception as e:
        logger.error(f"Error in LLM formatting: {e}", exc_info=True)
        # Use the sanitized safe_messages for fallback
        return _format_simple_fallback(safe_messages if 'safe_messages' in locals() else messages, query)

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