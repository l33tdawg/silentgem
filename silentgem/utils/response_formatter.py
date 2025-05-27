"""
Response formatting utilities for search results
"""

import re
import asyncio
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from loguru import logger

from silentgem.llm.llm_client import get_llm_client

# Performance settings
FAST_MODE = True  # Use simple formatting by default
MAX_LLM_MESSAGES = 10  # Limit messages sent to LLM
MAX_CONTENT_LENGTH = 300  # Limit content length for speed

async def format_search_results(
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
    conversation_history: Optional[List[Dict[str, str]]] = None,
    use_llm: bool = False  # New parameter to control LLM usage
) -> str:
    """
    Format search results into a readable response (optimized for speed)
    
    Args:
        messages: List of message dictionaries from search results
        query: Original search query
        parsed_query: Optional parsed query information
        translator: Optional translator function (deprecated)
        verbosity: Response verbosity level
        include_quotes: Whether to include message quotes
        include_timestamps: Whether to include timestamps
        include_sender_info: Whether to include sender information
        include_channel_info: Whether to include channel information
        context_messages: Optional context messages
        chat_messages_map: Optional mapping of chat IDs to messages
        conversation_history: Optional conversation history
        use_llm: Whether to use LLM for formatting (slower but more intelligent)
        
    Returns:
        Formatted response string
    """
    if not messages:
        return f"No messages found matching '{query}'"
    
    # Use fast formatting by default, LLM only when explicitly requested
    if use_llm and not FAST_MODE:
        try:
            return await _format_with_llm(
                messages=messages[:MAX_LLM_MESSAGES],  # Limit for speed
                query=query,
                parsed_query=parsed_query,
                translator=translator,
                verbosity=verbosity,
                include_quotes=include_quotes,
                include_timestamps=include_timestamps,
                include_sender_info=include_sender_info,
                include_channel_info=include_channel_info,
                context_messages=context_messages,
                chat_messages_map=chat_messages_map,
                conversation_history=conversation_history
            )
        except Exception as e:
            logger.warning(f"LLM formatting failed, falling back to basic: {e}")
            # Fall through to basic formatting
    
    # Use fast basic formatting
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
    Fast basic formatter without using LLM
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
        max_content_length = 80
        max_messages = min(3, len(messages))
    elif verbosity == "standard":
        max_content_length = 150
        max_messages = min(8, len(messages))
    else:  # detailed
        max_content_length = MAX_CONTENT_LENGTH
        max_messages = min(12, len(messages))
    
    # Group messages by chat for better organization
    if include_channel_info and len(set(msg.get('source_chat_id', 'unknown') for msg in messages)) > 1:
        # Multiple chats - group by chat
        chat_groups = {}
        for msg in messages[:max_messages]:
            chat_id = msg.get('source_chat_id') or msg.get('target_chat_id') or 'unknown'
            if chat_id not in chat_groups:
                chat_groups[chat_id] = []
            chat_groups[chat_id].append(msg)
        
        for chat_id, chat_messages in chat_groups.items():
            if len(chat_groups) > 1:
                response.append(f"**From Chat {chat_id}:**")
            
            for i, msg in enumerate(chat_messages[:5]):  # Limit per chat
                formatted_msg = _format_single_message(
                    msg, i + 1, max_content_length, include_quotes, 
                    include_timestamps, include_sender_info
                )
                response.append(formatted_msg)
            
            if len(chat_messages) > 5:
                response.append(f"... and {len(chat_messages) - 5} more from this chat")
            response.append("")
    else:
        # Single chat or no chat grouping - simple list
        for i, msg in enumerate(messages[:max_messages]):
            formatted_msg = _format_single_message(
                msg, i + 1, max_content_length, include_quotes, 
                include_timestamps, include_sender_info
            )
            response.append(formatted_msg)
    
    # Add footer if there are more messages
    if len(messages) > max_messages:
        response.append(f"... and {len(messages) - max_messages} more messages not shown.")
    
    # Add simple footer
    response.append("\n*Powered by SilentGem Insights*")
    
    return "\n".join(response)

def _format_single_message(
    msg: Dict[str, Any],
    index: int,
    max_content_length: int,
    include_quotes: bool,
    include_timestamps: bool,
    include_sender_info: bool
) -> str:
    """Format a single message for display"""
    parts = []
    
    # Message number
    parts.append(f"{index}.")
    
    # Sender info
    if include_sender_info:
        sender = msg.get('sender_name') or msg.get('sender') or 'Unknown'
        parts.append(f"**{sender}**")
    
    # Timestamp
    if include_timestamps:
        timestamp = msg.get('timestamp')
        if timestamp:
            try:
                if isinstance(timestamp, (int, float)):
                    dt = datetime.fromtimestamp(timestamp)
                else:
                    dt = datetime.fromisoformat(str(timestamp))
                time_str = dt.strftime("%m/%d %H:%M")
                parts.append(f"({time_str})")
            except:
                parts.append("(Unknown time)")
    
    # Content
    content = msg.get('content') or msg.get('text') or '[No content]'
    
    # Truncate long content
    if len(content) > max_content_length:
        content = content[:max_content_length] + "..."
    
    # Clean up content
    content = content.replace('\n', ' ').strip()
    
    if include_quotes:
        parts.append(f": \"{content}\"")
    else:
        parts.append(f": {content}")
    
    return " ".join(parts)

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