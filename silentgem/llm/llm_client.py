"""
LLM client for SilentGem to handle interaction with language models
"""

import os
import json
from typing import List, Dict, Any, Optional, Union
from loguru import logger

from silentgem.config.insights_config import get_insights_config

class LLMClient:
    """Client for interacting with language models (Google Gemini or Ollama)"""
    
    def __init__(self):
        """Initialize the LLM client"""
        self.config = get_insights_config()
        self.api_key = self.config.get("llm_api_key", os.environ.get("GEMINI_API_KEY", ""))
        self.model = self.config.get("llm_model", "gemini-pro")
        self.ollama_url = self.config.get("ollama_url", "http://localhost:11434")
        self._client = None
        self._client_type = None
        
        # Try to initialize client
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the client based on configuration"""
        try:
            # Initialize based on model type
            if "gemini" in self.model.lower():
                if not self.api_key:
                    logger.warning("No Gemini API key provided. Set GEMINI_API_KEY environment variable or configure in settings.")
                    return
                    
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=self.api_key)
                    self._client = genai
                    self._client_type = "gemini"
                    logger.info(f"Initialized Google Gemini client with model: {self.model}")
                except ImportError:
                    logger.error("Failed to import Google Generative AI library. Please install with: pip install google-generativeai")
            
            elif "ollama" in self.model.lower() or any(model in self.model.lower() for model in ["llama", "mistral", "solar", "phi"]):
                try:
                    import httpx
                    self._client = httpx.AsyncClient(base_url=self.ollama_url, timeout=60.0)
                    self._client_type = "ollama"
                    logger.info(f"Initialized Ollama client with model: {self.model} at {self.ollama_url}")
                except ImportError:
                    logger.error("Failed to import httpx library. Please install with: pip install httpx")
            else:
                logger.warning(f"Unsupported model type: {self.model}. Please use Gemini or Ollama models.")
                
        except Exception as e:
            logger.error(f"Error initializing LLM client: {e}")
            self._client = None
    
    async def chat_completion(self, 
                             messages: List[Dict[str, str]], 
                             model: Optional[str] = None,
                             temperature: float = 0.7,
                             max_tokens: int = 800,
                             **kwargs) -> Optional[Dict[str, Any]]:
        """
        Get a chat completion from the LLM
        
        Args:
            messages: List of message dictionaries with role and content
            model: Optional model name to use instead of default
            temperature: Creativity temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional model parameters
            
        Returns:
            Dictionary with completion response or None on failure
        """
        if not self._client:
            logger.warning("LLM client not initialized. Please set up your Gemini API key or Ollama instance.")
            return None
            
        try:
            model_name = model or self.model
            
            # Handle Gemini API
            if self._client_type == "gemini":
                # Check for a valid model name
                if "gemini" not in model_name.lower():
                    model_name = "gemini-1.5-pro"  # Default to a newer model
                    logger.info(f"Using default Gemini model: {model_name}")
                
                # Initialize model
                gemini_model = self._client.GenerativeModel(model_name)
                
                # Convert message format
                gemini_messages = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    
                    if role == "system" and gemini_messages:
                        # For system message, we'll just prepend to the first user message
                        # as Gemini doesn't directly support system messages
                        for i, m in enumerate(messages):
                            if m.get("role") == "user":
                                gemini_messages.append({"role": "user", "parts": [f"System: {content}\n\nUser: {m.get('content')}" ]})
                                break
                    elif role == "user":
                        gemini_messages.append({"role": "user", "parts": [content]})
                    elif role == "assistant":
                        gemini_messages.append({"role": "model", "parts": [content]})
                
                # Only process if we have valid messages
                if gemini_messages:
                    chat = gemini_model.start_chat(history=gemini_messages[:-1] if len(gemini_messages) > 1 else [])
                    response = chat.send_message(
                        gemini_messages[-1]["parts"][0],
                        generation_config={
                            "temperature": temperature,
                            "max_output_tokens": max_tokens,
                            **kwargs
                        }
                    )
                    
                    # Return in a format compatible with our expected interface
                    return {
                        "content": response.text,
                        "model": model_name,
                    }
            
            # Handle Ollama API
            elif self._client_type == "ollama":
                # Prepare messages for Ollama format
                ollama_messages = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    
                    # Map roles to Ollama format
                    if role == "system":
                        ollama_messages.append({"role": "system", "content": content})
                    elif role == "user":
                        ollama_messages.append({"role": "user", "content": content})
                    elif role == "assistant":
                        ollama_messages.append({"role": "assistant", "content": content})
                
                # Prepare request payload
                payload = {
                    "model": model_name,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                        **kwargs
                    }
                }
                
                # Send request to Ollama API
                response = await self._client.post("/api/chat", json=payload)
                response.raise_for_status()
                result = response.json()
                
                # Return in expected format
                if "message" in result and "content" in result["message"]:
                    return {
                        "content": result["message"]["content"],
                        "model": model_name,
                    }
                
                logger.warning(f"Unexpected response format from Ollama: {result}")
                return None
            
            logger.warning(f"Unsupported model type for chat completion: {model_name}")
            return None
                
        except Exception as e:
            logger.error(f"Error in chat completion: {e}")
            return None
    
    async def complete(self, 
                      prompt: str,
                      system: Optional[str] = None,
                      model: Optional[str] = None,
                      temperature: float = 0.7,
                      max_tokens: int = 800,
                      **kwargs) -> Optional[str]:
        """
        Get a completion from the LLM
        
        Args:
            prompt: The text prompt to send
            system: Optional system message
            model: Optional model name to use instead of default
            temperature: Creativity temperature (0.0 to 1.0)
            max_tokens: Maximum tokens in response
            **kwargs: Additional model parameters
            
        Returns:
            String with completion or None on failure
        """
        # Convert to chat format
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        
        messages.append({"role": "user", "content": prompt})
        
        # Use chat completion
        response = await self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        if response and "content" in response:
            return response["content"]
            
        return None

# Singleton instance
_instance = None

def get_llm_client() -> Optional[LLMClient]:
    """Get the LLM client singleton instance"""
    global _instance
    if _instance is None:
        _instance = LLMClient()
    return _instance 