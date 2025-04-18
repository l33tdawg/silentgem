"""
Translation service using Google Gemini API
"""

import google.generativeai as genai
from loguru import logger

from silentgem.config import GEMINI_API_KEY, TARGET_LANGUAGE

# Configure the Google Gemini API
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
            return ""
        
        try:
            # Log some basic stats about the text
            print(f"📝 Processing text: {len(text)} characters, {len(text.split())} words")
            print(f"📌 Text sample: {text[:100]}...")
            
            # Construct the prompt
            prompt = self._build_prompt(text, source_language)
            print(f"🔍 Using prompt length: {len(prompt)} characters")
            
            # Get response from Gemini
            print("🧠 Sending to Google Gemini for translation...")
            print(f"⏳ Awaiting response from Gemini API...")
            
            try:
                response = await self.model.generate_content_async(prompt)
                print(f"✅ Received response from Gemini API")
            except Exception as e:
                print(f"❌ Gemini API error: {e}")
                raise
            
            # Extract and return the translation
            translated_text = response.text.strip()
            
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
            print(f"❌ Traceback: {traceback.format_exc()}")
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
            Please translate the following text from {source_language} to {TARGET_LANGUAGE}.
            Maintain the original formatting, tone, and meaning as closely as possible.
            Only provide the translation, with no additional comments or explanations.
            
            TEXT TO TRANSLATE:
            {text}
            """
        else:
            prompt = f"""
            Please identify the language of the following text and translate it to {TARGET_LANGUAGE}.
            Maintain the original formatting, tone, and meaning as closely as possible.
            Only provide the translation, with no additional comments or explanations.
            
            TEXT TO TRANSLATE:
            {text}
            """
        
        return prompt.strip() 