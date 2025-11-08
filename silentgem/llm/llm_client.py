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
        
        # Determine the model based on configured LLM engine
        llm_engine = os.environ.get("LLM_ENGINE", "gemini").lower()
        if llm_engine == "gemini":
            default_model = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
        else:
            default_model = os.environ.get("OLLAMA_MODEL", "llama3")
        
        self.model = self.config.get("llm_model", default_model)
        self.ollama_url = self.config.get("ollama_url", os.environ.get("OLLAMA_URL", "http://localhost:11434"))
        self._client = None
        self._client_type = None
        
        # Try to initialize client
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the client based on configuration"""
        try:
            # Check if we should use Ollama based on config
            use_ollama = self.config.get("use_ollama", True)  # Default to True
            ollama_models = ["llama", "mistral", "solar", "phi", "llama3", "mixtral", "yi"]
            
            # Determine if the model is an Ollama model
            is_ollama_model = (
                use_ollama or 
                "ollama" in self.model.lower() or 
                any(model in self.model.lower() for model in ollama_models)
            )
            
            # Initialize Ollama first if it's enabled or the model suggests it
            if is_ollama_model:
                try:
                    import httpx
                    self._client = httpx.AsyncClient(base_url=self.ollama_url, timeout=60.0)
                    self._client_type = "ollama"
                    
                    # If model still has gemini prefix but we're using Ollama, switch to a default
                    if "gemini" in self.model.lower():
                        self.model = "llama3"
                        
                    logger.info(f"Initialized Ollama client with model: {self.model} at {self.ollama_url}")
                    return  # Successfully initialized Ollama
                except ImportError:
                    logger.error("Failed to import httpx library. Please install with: pip install httpx")
            
            # Fall back to Gemini if Ollama wasn't used or failed
            if "gemini" in self.model.lower():
                if not self.api_key:
                    logger.warning("No Gemini API key provided. Set GEMINI_API_KEY environment variable or configure in settings.")
                    return
                    
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=self.api_key)
                    
                    # Check if the model is available
                    try:
                        # Use a newer model by default for better compatibility
                        if self.model == "gemini-pro":
                            self.model = "gemini-1.5-pro"
                            
                        # Test model initialization without making an API call
                        genai.GenerativeModel(self.model)
                        
                        self._client = genai
                        self._client_type = "gemini"
                        logger.info(f"Initialized Google Gemini client with model: {self.model}")
                    except Exception as model_error:
                        logger.error(f"Error with Gemini model {self.model}: {model_error}")
                        logger.info("Falling back to gemini-1.5-pro model")
                        self.model = "gemini-1.5-pro"
                        try:
                            genai.GenerativeModel(self.model)
                            self._client = genai
                            self._client_type = "gemini"
                            logger.info(f"Initialized Google Gemini client with model: {self.model}")
                        except Exception as fallback_error:
                            logger.error(f"Error with fallback Gemini model: {fallback_error}")
                except ImportError:
                    logger.error("Failed to import Google Generative AI library. Please install with: pip install google-generativeai")
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
            logger.warning(f"LLM client not initialized. Client type: {self._client_type}. Please set up your Gemini API key or Ollama instance.")
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
            logger.error(f"Error in chat completion with {self._client_type} client: {e}")
            logger.debug(f"Error details: {type(e).__name__}: {str(e)}")
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
            content = response["content"]
            if content:
                return content
            else:
                logger.warning("LLM returned empty content in response")
                return None
        else:
            logger.warning(f"LLM response missing 'content' field or is None. Response: {response}")
            return None

# Singleton instance
_instance = None

def get_llm_client() -> Optional[LLMClient]:
    """Get the LLM client singleton instance"""
    global _instance
    if _instance is None:
        _instance = LLMClient()
    return _instance 