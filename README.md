# SilentGem

A stealthy Telegram translator using Google Gemini AI.

## Description

SilentGem is a Telegram userbot that automatically translates messages from source chats (groups, channels) to your private target channels. It works silently in the background, using Google's Gemini AI for high-quality translation.

## Features

- Monitor multiple source chats simultaneously
- Translate to any language supported by Google Gemini
- Forward media with translated captions
- Preserve attribution to original senders
- Detect and skip already-English messages when target is English
- Interactive setup wizard for easy configuration
- CLI tools for managing chat mappings

## Requirements

- Python 3.7+
- Telegram API credentials (API ID and Hash)
- Google Gemini API key

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/silentgem.git
cd silentgem
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the setup wizard:
```bash
python main.py --setup
```

The setup wizard will guide you through:
- Setting up Telegram API credentials
- Configuring Google Gemini API key
- Selecting source chats to monitor
- Setting up target channels for translations

## Usage

Start the translation service:
```bash
python main.py
```

### Command-line options

- `--setup`: Run the setup wizard
- `--service`: Start the translation service directly (non-interactive)
- `--cleanup`: Clean up any database lock issues
- `--clear-mappings`: Reset all chat mappings
- `--version`: Show version information

## License

[MIT License](LICENSE) 