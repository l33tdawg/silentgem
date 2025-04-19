"""
Translation service using Google Gemini API or Ollama
"""

import google.generativeai as genai
from loguru import logger
import httpx
import json
import asyncio

from silentgem.config import (
    GEMINI_API_KEY, TARGET_LANGUAGE, LLM_ENGINE,
    OLLAMA_URL, OLLAMA_MODEL
)

# Configure the Google Gemini API if we're using it
if LLM_ENGINE == "gemini":
    genai.configure(api_key=GEMINI_API_KEY)

class GeminiTranslator:
    """Translator class using Google Gemini API"""
    
    def __init__(self):
        """Initialize the translator with the Gemini model"""
        try:
            print(f"🔧 Initializing Gemini API with key: {GEMINI_API_KEY[:4]}{'*' * 12}")
            print(f"🔧 Target language set to: {TARGET_LANGUAGE}")
            
            # Using the requested experimental model
            model_name = 'gemini-2.0-flash-thinking-exp-01-21'
            print(f"🔧 Setting up model: {model_name}")
            
            try:
                self.model = genai.GenerativeModel(model_name)
                print(f"✅ Successfully created Gemini model instance: {model_name}")
            except Exception as e:
                print(f"❌ Failed to create model {model_name}: {e}")
                
                # Try an alternative model as fallback
                print("🔄 Trying fallback model...")
                model_name = 'gemini-pro'
                self.model = genai.GenerativeModel(model_name)
                print(f"✅ Successfully created fallback Gemini model: {model_name}")
                
            # Store model name as a separate attribute
            self.model_name = model_name
            logger.info(f"Gemini translator initialized with model {model_name}")
        except Exception as e:
            logger.error(f"Error initializing Gemini translator: {e}")
            print(f"❌ Failed to initialize Gemini translator: {e}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")
            raise
    
    async def translate(self, text, source_language=None):
        """
        Translate text using Gemini
        
        Args:
            text (str): Text to translate
            source_language (str, optional): Source language if known
            
        Returns:
            str: Translated text
        """
        if not text or text.isspace():
            print("⚠️ Empty text received for translation, returning empty string")
            return ""
        
        try:
            # Log some basic stats about the text
            print(f"📝 Processing text: {len(text)} characters, {len(text.split())} words")
            print(f"📌 Text sample: {text[:100]}...")
            
            # Log target language
            print(f"🌐 Target language: {TARGET_LANGUAGE}")
            
            # Construct the prompt
            prompt = self._build_prompt(text, source_language)
            print(f"🔍 Using prompt length: {len(prompt)} characters")
            print(f"🔍 Prompt sample: {prompt[:150]}...")
            
            # Get response from Gemini
            print("🧠 Sending to Google Gemini for translation...")
            print(f"ℹ️ Model being used: {self.model_name}")
            print(f"⏳ Awaiting response from Gemini API...")
            
            try:
                # Print verbose information about the model and request
                print(f"📡 API request details:")
                print(f"  - Model: {self.model_name}")
                print(f"  - Temperature: 0.1")
                print(f"  - Max tokens: 8192")
                
                # For more reliable results, use generation config
                response = await self.model.generate_content_async(
                    prompt,
                    generation_config={
                        'temperature': 0.1,  # Low temperature for accurate translations
                        'top_p': 0.95,
                        'top_k': 40,
                        'max_output_tokens': 8192,  # Allow for longer translations
                    }
                )
                print(f"✅ Received response from Gemini API")
                
                # Log response details
                print(f"📡 Response details:")
                print(f"  - Has text attribute: {hasattr(response, 'text')}")
                print(f"  - Response type: {type(response)}")
                
                if not response or not hasattr(response, 'text'):
                    print(f"❌ Response has no text attribute: {response}")
                    raise ValueError("Empty or invalid response from Gemini API")
                
                # Print the raw response for debugging
                print(f"📡 Raw response text: {response.text[:150]}...")
                    
            except Exception as e:
                print(f"❌ Gemini API error: {e}")
                print(f"❌ Error type: {type(e).__name__}")
                logger.error(f"Gemini API error: {e}")
                
                # Try once more with a simpler prompt as fallback
                try:
                    print("🔄 Trying simplified fallback prompt...")
                    fallback_prompt = f"Translate this text to {TARGET_LANGUAGE}:\n\n{text}"
                    print(f"🔄 Fallback prompt: {fallback_prompt[:150]}...")
                    response = await self.model.generate_content_async(fallback_prompt)
                    print(f"✅ Received response from fallback prompt")
                except Exception as fallback_error:
                    print(f"❌ Fallback translation also failed: {fallback_error}")
                    print(f"❌ Fallback error type: {type(fallback_error).__name__}")
                    raise
            
            # Extract and return the translation
            translated_text = response.text.strip()
            
            if not translated_text:
                print("❌ Empty translation received")
                raise ValueError("Empty translation received from Gemini API")
            
            # Check if the response is actually a translation or just an error message
            if len(translated_text) < 5 and len(text) > 20:
                print(f"❌ Suspiciously short translation: '{translated_text}'")
                raise ValueError("Suspiciously short translation received")
                
            # Determine source language from response if possible
            source_lang_detected = None
            if hasattr(response, 'prompt_feedback') and hasattr(response.prompt_feedback, 'block_reason_all'):
                for part in response.prompt_feedback.block_reason_all or []:
                    if part.get("reason_description", "").lower().startswith("detected language"):
                        source_lang_detected = part.get("reason_description")
                        break
                    
            if source_lang_detected:
                print(f"🔍 {source_lang_detected}")
            
            print(f"✅ Translation complete: {len(translated_text)} characters, {len(translated_text.split())} words")
            print(f"📌 Translation sample: {translated_text[:100]}...")
            
            logger.debug(f"Translated: {text[:30]}... -> {translated_text[:30]}...")
            return translated_text
        
        except Exception as e:
            logger.error(f"Translation error: {e}")
            print(f"❌ Translation error: {e}")
            print(f"❌ Error details: {type(e).__name__}")
            import traceback
            error_trace = traceback.format_exc()
            print(f"❌ Traceback: {error_trace}")
            logger.error(f"Translation error traceback: {error_trace}")
            return f"[Translation Error: {str(e)}]"
    
    def _build_prompt(self, text, source_language=None):
        """
        Build a prompt for the translation
        
        Args:
            text (str): Text to translate
            source_language (str, optional): Source language if known
            
        Returns:
            str: Formatted prompt
        """
        if source_language:
            prompt = f"""
            You are a professional translator. Translate the following text from {source_language} to {TARGET_LANGUAGE}.
            Maintain the original formatting, tone, and meaning as closely as possible.
            Only provide the translated text, with no additional comments, explanations, or disclaimers.
            
            TEXT TO TRANSLATE:
            {text}
            
            TRANSLATION IN {TARGET_LANGUAGE}:
            """
        else:
            prompt = f"""
            You are a professional translator. Identify the language of the following text and translate it to {TARGET_LANGUAGE}.
            Maintain the original formatting, tone, and meaning as closely as possible.
            Only provide the translated text, with no additional comments, explanations, or disclaimers.
            
            TEXT TO TRANSLATE:
            {text}
            
            TRANSLATION IN {TARGET_LANGUAGE}:
            """
        
        return prompt.strip()


class OllamaTranslator:
    """Translator class using local Ollama API"""
    
    def __init__(self):
        """Initialize the translator with Ollama settings"""
        try:
            self.base_url = OLLAMA_URL.rstrip('/')
            self.model = OLLAMA_MODEL
            
            print(f"🔧 Initializing Ollama translator with URL: {self.base_url}")
            print(f"🔧 Using Ollama model: {self.model}")
            print(f"🔧 Target language set to: {TARGET_LANGUAGE}")
            
            # Store for logging
            self.model_name = f"ollama/{self.model}"
            
            logger.info(f"Ollama translator initialized with model {self.model}")
            print(f"✅ Ollama translator initialized")
            
        except Exception as e:
            logger.error(f"Error initializing Ollama translator: {e}")
            print(f"❌ Failed to initialize Ollama translator: {e}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")
            raise
    
    async def translate(self, text, source_language=None):
        """
        Translate text using Ollama
        
        Args:
            text (str): Text to translate
            source_language (str, optional): Source language if known
            
        Returns:
            str: Translated text
        """
        if not text or text.isspace():
            print("⚠️ Empty text received for translation, returning empty string")
            return ""
        
        try:
            # Log some basic stats about the text
            print(f"📝 Processing text: {len(text)} characters, {len(text.split())} words")
            print(f"📌 Text sample: {text[:100]}...")
            
            # Log target language
            print(f"🌐 Target language: {TARGET_LANGUAGE}")
            
            # Construct the prompt
            prompt = self._build_prompt(text, source_language)
            print(f"🔍 Using prompt length: {len(prompt)} characters")
            print(f"🔍 Prompt sample: {prompt[:150]}...")
            
            # Get response from Ollama
            print(f"🧠 Sending to Ollama ({self.model}) for translation...")
            print(f"⏳ Awaiting response from Ollama API...")
            
            try:
                # Print verbose information about the request
                print(f"📡 API request details:")
                print(f"  - Model: {self.model}")
                print(f"  - Temperature: 0.1")
                print(f"  - URL: {self.base_url}/api/generate")
                
                # Format request for Ollama
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.95,
                        "top_k": 40
                    }
                }
                
                # Use httpx for async HTTP requests
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"{self.base_url}/api/generate",
                        json=payload
                    )
                    
                    # Check response status
                    if response.status_code != 200:
                        print(f"❌ Ollama API error: {response.status_code} - {response.text}")
                        raise ValueError(f"Ollama API returned status code {response.status_code}")
                    
                    # Parse JSON response
                    response_data = response.json()
                    
                    # Extract the response text
                    if "response" not in response_data:
                        print(f"❌ Unexpected Ollama response format: {response_data}")
                        raise ValueError("Unexpected response format from Ollama API")
                    
                    translated_text = response_data["response"].strip()
                    print(f"✅ Received response from Ollama API")
                
            except Exception as e:
                print(f"❌ Ollama API error: {e}")
                print(f"❌ Error type: {type(e).__name__}")
                logger.error(f"Ollama API error: {e}")
                
                # Try with a simplified prompt as fallback
                try:
                    print("🔄 Trying simplified fallback prompt...")
                    fallback_prompt = f"Translate this text to {TARGET_LANGUAGE}:\n\n{text}"
                    print(f"🔄 Fallback prompt: {fallback_prompt[:150]}...")
                    
                    # Simplified fallback payload
                    fallback_payload = {
                        "model": self.model,
                        "prompt": fallback_prompt,
                        "stream": False
                    }
                    
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        response = await client.post(
                            f"{self.base_url}/api/generate",
                            json=fallback_payload
                        )
                        
                        if response.status_code != 200:
                            raise ValueError(f"Ollama API returned status code {response.status_code}")
                        
                        response_data = response.json()
                        translated_text = response_data["response"].strip()
                        print(f"✅ Received response from fallback prompt")
                
                except Exception as fallback_error:
                    print(f"❌ Fallback translation also failed: {fallback_error}")
                    print(f"❌ Fallback error type: {type(fallback_error).__name__}")
                    raise
            
            # Post-process and validate the translation
            if not translated_text:
                print("❌ Empty translation received")
                raise ValueError("Empty translation received from Ollama API")
            
            # Check if the response is actually a translation or just an error message
            if len(translated_text) < 5 and len(text) > 20:
                print(f"❌ Suspiciously short translation: '{translated_text}'")
                raise ValueError("Suspiciously short translation received")
            
            print(f"✅ Translation complete: {len(translated_text)} characters, {len(translated_text.split())} words")
            print(f"📌 Translation sample: {translated_text[:100]}...")
            
            logger.debug(f"Translated: {text[:30]}... -> {translated_text[:30]}...")
            return translated_text
        
        except Exception as e:
            logger.error(f"Translation error: {e}")
            print(f"❌ Translation error: {e}")
            print(f"❌ Error details: {type(e).__name__}")
            import traceback
            error_trace = traceback.format_exc()
            print(f"❌ Traceback: {error_trace}")
            logger.error(f"Translation error traceback: {error_trace}")
            return f"[Translation Error: {str(e)}]"
    
    def _build_prompt(self, text, source_language=None):
        """
        Build a prompt for the translation
        
        Args:
            text (str): Text to translate
            source_language (str, optional): Source language if known
            
        Returns:
            str: Formatted prompt
        """
        if source_language:
            prompt = f"""
            You are a professional translator. Translate the following text from {source_language} to {TARGET_LANGUAGE}.
            Maintain the original formatting, tone, and meaning as closely as possible.
            Only provide the translated text, with no additional comments, explanations, or disclaimers.
            
            TEXT TO TRANSLATE:
            {text}
            
            TRANSLATION IN {TARGET_LANGUAGE}:
            """
        else:
            prompt = f"""
            You are a professional translator. Identify the language of the following text and translate it to {TARGET_LANGUAGE}.
            Maintain the original formatting, tone, and meaning as closely as possible.
            Only provide the translated text, with no additional comments, explanations, or disclaimers.
            
            TEXT TO TRANSLATE:
            {text}
            
            TRANSLATION IN {TARGET_LANGUAGE}:
            """
        
        return prompt.strip()


# Function to create the appropriate translator based on configuration
def create_translator():
    """Factory function to create the appropriate translator based on configuration"""
    if LLM_ENGINE == "gemini":
        return GeminiTranslator()
    elif LLM_ENGINE == "ollama":
        return OllamaTranslator()
    else:
        raise ValueError(f"Unknown LLM_ENGINE: {LLM_ENGINE}. Must be 'gemini' or 'ollama'") 