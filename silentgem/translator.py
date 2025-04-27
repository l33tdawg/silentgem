"""
Translation service using Google Gemini API or Ollama
"""

import google.generativeai as genai
from loguru import logger
import httpx
import json
import asyncio
from abc import ABC, abstractmethod
import re  # Add import for regex

from silentgem.config import (
    GEMINI_API_KEY, TARGET_LANGUAGE, LLM_ENGINE,
    OLLAMA_URL, OLLAMA_MODEL
)

# Configure the Google Gemini API if we're using it
if LLM_ENGINE == "gemini":
    genai.configure(api_key=GEMINI_API_KEY)

class BaseTranslator(ABC):
    """Base class for all translator implementations"""
    
    @abstractmethod
    async def translate(self, text, source_language=None, max_tokens=None):
        """
        Translate or process text using LLM
        
        Args:
            text (str): Text to translate/process
            source_language (str, optional): Source language if known
            max_tokens (int, optional): Maximum tokens for response
            
        Returns:
            str: Processed text
        """
        pass
    
    def clean_translation(self, translated_text):
        """
        Clean up the translated text by removing common LLM commentary phrases
        
        Args:
            translated_text (str): Raw translated text from LLM
            
        Returns:
            str: Cleaned translation without commentary
        """
        if not translated_text:
            return ""
            
        # Common patterns to remove
        patterns = [
            # Explanatory prefixes
            r"^(here'?s the translation:?\s*)",
            r"^(that'?s a \w+ text!?\s*here'?s the translation:?\s*)",
            r"^(that'?s \w+ text!?\s*here'?s the translation:?\s*)",
            r"^(this (text|message) (is|appears to be) in \w+\.?\s*here'?s the translation:?\s*)",
            r"^(to maintain the original formatting,?.*?as follows:?\s*)",
            r"^(translating from \w+ to \w+:?\s*)",
            r"^(translation:?\s*)",
            r"^(translated text:?\s*)",
            r"^(in \w+:?\s*)",
            r"^(the \w+ translation(?: is| would be)?:?\s*)",
            r"^(\w+ translation:?\s*)",
            r"^(translated (?:to|into) \w+:?\s*)",
            r"^(i(?:'ll| will) translate this (?:text|message).*?:?\s*)",
            r"^(i(?:'ll| will) translate this .*?to \w+.*?\.?\s*\n)",
            r"^(i(?:'ve| have) translated (?:this|the) (?:text|message).*?:?\s*)",
            r"^(the text (?:has been|is) translated (?:to|into) \w+:?\s*)",
            
            # Explanatory suffixes
            r"(\n\s*this is the translation(?: of the text)? from \w+ to \w+\.?\s*$)",
            r"(\n\s*i'?ve translated the text while maintaining its original meaning\.?\s*$)",
            r"(\n\s*i hope this (translation|helps).*?$)",
            r"(\n\s*let me know if you need any clarification\.?\s*$)",
            r"(\n\s*please let me know if you need anything else\.?\s*$)",
            r"(\n\s*the above is.*?translation.*?$)",
            
            # Disclaimers
            r"(\n\s*note:.*?$)",
            r"(\n\s*disclaimer:.*?$)",
            r"(\n\s*\[?note that .*?$)",
            r"(\n\s*\[?please note .*?$)",
            
            # Language identification
            r"^(this appears to be (?:in )?[a-zA-Z\s]+\.?\s*)",
            r"^(the (?:text|message|content) is (?:in )?[a-zA-Z\s]+\.?\s*)",
            r"^(detecting language\.\.\.? [a-zA-Z\s]+\.?\s*)",
            
            # Remove any quotes around the entire text
            r'^"(.*)"$',
            r"^'(.*)'$",
            r"^`(.*)`$",

            # Additional patterns to match prompt instructions
            r"^(maintain the original formatting,? tone,? and meaning.*?)\n",
            r"(IMPORTANT INSTRUCTIONS:.*?(?=TEXT TO TRANSLATE|TRANSLATION IN))",
            r"^(- Return ONLY the translated text.*?\n)",
            r"^(- DO NOT.*?\n)",
            r"(You are a professional translator\..*?\n)",
            r"^(TEXT TO TRANSLATE:.*?\n)",
            r"^(TRANSLATION IN .*?:.*?\n)",
        ]
        
        # Apply all patterns
        cleaned_text = translated_text
        for pattern in patterns:
            cleaned_text = re.sub(pattern, "", cleaned_text, flags=re.IGNORECASE | re.DOTALL)
        
        # Fix the triple backticks to preserve content inside
        if "```" in cleaned_text:
            # First extract anything between triple backticks
            code_content = re.findall(r"```(?:\w*\n)?(.*?)```", cleaned_text, re.DOTALL)
            # Then remove all triple backticks and language specifiers
            cleaned_text = re.sub(r"```\w*\n?", "", cleaned_text)
            cleaned_text = re.sub(r"```", "", cleaned_text)
            # If we extracted content, make sure it's still included
            if code_content:
                for content in code_content:
                    if content.strip() and content.strip() not in cleaned_text:
                        cleaned_text = cleaned_text + "\n" + content.strip()
        
        # Remove lines that entirely consist of language identification
        cleaned_text = re.sub(r"^([A-Za-z]+:|\[[A-Za-z]+\]|\([A-Za-z]+\))\s*$", "", cleaned_text, flags=re.MULTILINE)
        
        # Remove lines with just "I'll translate" or similar
        cleaned_text = re.sub(r"^I['']ll translate.*$", "", cleaned_text, flags=re.MULTILINE | re.IGNORECASE)
        
        # Remove any extra newlines or spaces that might have been left
        cleaned_text = re.sub(r"\n{2,}", "\n", cleaned_text)  # Replace multiple newlines with single
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text

class GeminiTranslator(BaseTranslator):
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
    
    async def translate(self, text, source_language=None, max_tokens=None):
        """
        Translate text using Gemini
        
        Args:
            text (str): Text to translate
            source_language (str, optional): Source language if known
            max_tokens (int, optional): Maximum tokens for response
            
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
                print(f"  - Max tokens: {max_tokens or 8192}")
                
                # For more reliable results, use generation config
                response = await self.model.generate_content_async(
                    prompt,
                    generation_config={
                        'temperature': 0.1,  # Low temperature for accurate translations
                        'top_p': 0.95,
                        'top_k': 40,
                        'max_output_tokens': max_tokens or 8192,  # Allow for longer translations
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
            
            # Clean the translation to remove commentary
            cleaned_translation = self.clean_translation(translated_text)
            print(f"🧹 Cleaned translation of commentary")
            
            # Only log a warning if we actually removed something substantial
            if len(translated_text) - len(cleaned_translation) > 20:
                print(f"⚠️ Removed {len(translated_text) - len(cleaned_translation)} characters of commentary")
                print(f"📝 Original: {translated_text[:150]}...")
                print(f"🧹 Cleaned: {cleaned_translation[:150]}...")
                
            # Determine source language from response if possible
            source_lang_detected = None
            if hasattr(response, 'prompt_feedback') and hasattr(response.prompt_feedback, 'block_reason_all'):
                for part in response.prompt_feedback.block_reason_all or []:
                    if part.get("reason_description", "").lower().startswith("detected language"):
                        source_lang_detected = part.get("reason_description")
                        break
                    
            if source_lang_detected:
                print(f"🔍 {source_lang_detected}")
            
            print(f"✅ Translation complete: {len(cleaned_translation)} characters, {len(cleaned_translation.split())} words")
            print(f"📌 Translation sample: {cleaned_translation[:100]}...")
            
            logger.debug(f"Translated: {text[:30]}... -> {cleaned_translation[:30]}...")
            return cleaned_translation
        
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
            
            IMPORTANT INSTRUCTIONS:
            - Return ONLY the translated text
            - DO NOT include phrases like "Here's the translation" or "Translation:"
            - DO NOT add any explanation, comments, or notes
            - DO NOT include the original text
            - DO NOT wrap the translation in quotes or code blocks
            - DO NOT state the source or target language
            
            TEXT TO TRANSLATE:
            {text}
            
            TRANSLATION IN {TARGET_LANGUAGE}:
            """
        else:
            prompt = f"""
            You are a professional translator. Translate the following text to {TARGET_LANGUAGE}.
            Maintain the original formatting, tone, and meaning as closely as possible.
            
            IMPORTANT INSTRUCTIONS:
            - Return ONLY the translated text
            - DO NOT include phrases like "Here's the translation" or "Translation:"
            - DO NOT add any explanation, comments, or notes
            - DO NOT include the original text
            - DO NOT wrap the translation in quotes or code blocks
            - DO NOT state the source or target language
            
            TEXT TO TRANSLATE:
            {text}
            
            TRANSLATION IN {TARGET_LANGUAGE}:
            """
        
        return prompt.strip()


class OllamaTranslator(BaseTranslator):
    """Translator class using Ollama local LLM"""
    
    def __init__(self):
        """Initialize the translator with Ollama settings"""
        self.api_url = OLLAMA_URL.rstrip("/")
        self.model = OLLAMA_MODEL
        logger.info(f"Ollama translator initialized with model {self.model} at {self.api_url}")
    
    async def translate(self, text, source_language=None, max_tokens=None):
        """
        Process text using Ollama
        
        Args:
            text (str): Text to process
            source_language (str, optional): Source language if known
            max_tokens (int, optional): Maximum tokens for response
            
        Returns:
            str: Processed text
        """
        if not text or text.isspace():
            return ""
        
        try:
            # Construct the API endpoint
            endpoint = f"{self.api_url}/api/generate"
            
            # Construct the prompt
            prompt = self._build_prompt(text, source_language)
            
            # Prepare the request payload
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
            
            # Add max_tokens if provided
            if max_tokens:
                payload["options"]["num_predict"] = max_tokens
            
            # Make the API request
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint, 
                    json=payload,
                    timeout=120.0  # Longer timeout for larger content
                )
                
                # Check for successful response
                if response.status_code != 200:
                    error_msg = f"Ollama API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    return f"[Translation Error: {error_msg}]"
                
                # Parse the response
                result = response.json()
                
                # Extract and clean the generated text
                generated_text = result.get("response", "")
                
                # Clean the translation to remove commentary
                cleaned_text = self.clean_translation(generated_text.strip())
                
                # Return the cleaned output
                return cleaned_text
                
        except Exception as e:
            logger.error(f"Ollama translation error: {e}")
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
            
            IMPORTANT INSTRUCTIONS:
            - Return ONLY the translated text
            - DO NOT include phrases like "Here's the translation" or "Translation:"
            - DO NOT add any explanation, comments, or notes
            - DO NOT include the original text
            - DO NOT wrap the translation in quotes or code blocks
            - DO NOT state the source or target language
            
            TEXT TO TRANSLATE:
            {text}
            
            TRANSLATION IN {TARGET_LANGUAGE}:
            """
        else:
            prompt = f"""
            You are a professional translator. Translate the following text to {TARGET_LANGUAGE}.
            Maintain the original formatting, tone, and meaning as closely as possible.
            
            IMPORTANT INSTRUCTIONS:
            - Return ONLY the translated text
            - DO NOT include phrases like "Here's the translation" or "Translation:"
            - DO NOT add any explanation, comments, or notes
            - DO NOT include the original text
            - DO NOT wrap the translation in quotes or code blocks
            - DO NOT state the source or target language
            
            TEXT TO TRANSLATE:
            {text}
            
            TRANSLATION IN {TARGET_LANGUAGE}:
            """
        
        return prompt.strip()


# Function to create the appropriate translator based on configuration
async def create_translator():
    """Factory function to create the appropriate translator based on configuration"""
    if LLM_ENGINE == "gemini":
        return GeminiTranslator()
    elif LLM_ENGINE == "ollama":
        return OllamaTranslator()
    else:
        raise ValueError(f"Unknown LLM_ENGINE: {LLM_ENGINE}. Must be 'gemini' or 'ollama'")

async def test_translation_cleaning():
    """
    Test function to verify that translation cleaning is working correctly
    
    This can be run directly to check if the cleaning patterns are working:
    python -c "import asyncio; from silentgem.translator import test_translation_cleaning; asyncio.run(test_translation_cleaning())"
    """
    # Create sample responses with common commentary
    sample_responses = [
        "Here's the translation: Hello world",
        "That's Vietnamese text! Here's the translation: Xin chào",
        "This text is in Spanish. Here's the translation: Hello everyone",
        "To maintain the original formatting, tone, and meaning, I will translate as follows: Bonjour monde",
        "Translating from German to English: Hello world",
        "Translation: Good morning everyone",
        "I'll translate this text: This is a test",
        "The English translation is: This is just a test",
        "Hello world\n\nThis is the translation from Spanish to English.",
        "Hello world\n\nI've translated the text while maintaining its original meaning.",
        "Hello world\n\nI hope this translation helps!",
        "Hello world\n\nNote: Some cultural references may not translate perfectly.",
        "```\nHello world\n```",
        "[French]\nBonjour le monde",
        "I'll translate this message to English now.\nHello and welcome to our service.",
    ]
    
    # Create both translators
    translators = []
    try:
        translators.append(GeminiTranslator())
        print("Testing GeminiTranslator cleaning...")
    except Exception as e:
        print(f"Error creating GeminiTranslator: {e}")
    
    try:
        translators.append(OllamaTranslator())
        print("Testing OllamaTranslator cleaning...")
    except Exception as e:
        print(f"Error creating OllamaTranslator: {e}")
    
    # Test each translator
    for translator in translators:
        print(f"\nTesting {translator.__class__.__name__}:")
        for i, response in enumerate(sample_responses):
            cleaned = translator.clean_translation(response)
            print(f"Sample {i+1}:")
            print(f"  Original: {response[:50]}{'...' if len(response) > 50 else ''}")
            print(f"  Cleaned:  {cleaned[:50]}{'...' if len(cleaned) > 50 else ''}")
            
            if response == cleaned:
                print("  WARNING: No cleaning occurred!")
            elif len(response) - len(cleaned) < 5 and "Here's the translation" in response:
                print("  WARNING: Minimal cleaning, pattern may be missed!")
    
    print("\nLive translation test:")
    # Create a translator
    translator = await create_translator()
    
    # Test with a simple message that often gets commentary
    test_message = "Hola, ¿cómo estás hoy?"
    print(f"Testing translation of: {test_message}")
    
    result = await translator.translate(test_message)
    print(f"Translation result: {result}")
    
    if result.lower().startswith(("here", "that", "this text", "translat", "in english")):
        print("WARNING: Translation cleaning may not be working properly!")
    else:
        print("Translation cleaning appears to be working correctly!")

if __name__ == "__main__":
    # Run the test function if executed directly
    import asyncio
    asyncio.run(test_translation_cleaning()) 