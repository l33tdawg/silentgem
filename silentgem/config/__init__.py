"""
Configuration package for SilentGem
"""

import os
from pathlib import Path

# Define data directory path
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

# Ensure directory exists function
def ensure_dir_exists(directory):
    """Create directory if it doesn't exist"""
    Path(directory).mkdir(parents=True, exist_ok=True)
    return directory 