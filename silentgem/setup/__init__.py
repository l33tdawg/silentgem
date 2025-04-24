"""
Setup package for SilentGem
"""

from silentgem.setup.insights_setup import setup_insights, clear_insights_history

# Import the real implementations from silentgem/setup_utils.py
from silentgem.setup_utils import setup_wizard as real_setup_wizard
from silentgem.setup_utils import config_llm_settings as real_config_llm_settings
from silentgem.setup_utils import config_target_language as real_config_target_language

async def setup_wizard():
    """
    Run the interactive setup wizard to configure SilentGem
    """
    return await real_setup_wizard()

async def config_llm_settings():
    """
    Configure LLM settings
    """
    return await real_config_llm_settings()

async def config_target_language():
    """
    Configure target language
    """
    return await real_config_target_language() 