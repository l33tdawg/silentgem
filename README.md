# SilentGem

A Telegram translator using Google Gemini AI.

## Description

SilentGem is a Telegram userbot that automatically translates messages from source chats (groups, channels) to your private target channels. It works in the background, using Google's Gemini AI for high-quality translation.

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

## API Keys

### Obtaining Telegram API Credentials

1. Visit [my.telegram.org](https://my.telegram.org/auth) and log in with your Telegram account
2. Click on "API Development Tools"
3. Fill in the form with the following details:
   - App title: SilentGem (or any name you prefer)
   - Short name: silentgem (or any short name)
   - Platform: Desktop
   - Description: Telegram translator application
4. Click "Create Application"
5. You will receive your **API ID** (a number) and **API Hash** (a string)
6. Copy these credentials for use in the setup wizard

### Obtaining Google Gemini API Key

1. Visit [AI Studio](https://aistudio.google.com/)
2. Create or sign in to your Google account
3. Click "Get API key" in the top right corner
4. Create a new API key or use an existing one
5. Copy the API key for use in the setup wizard

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

## Author

Developed by Dhillon '@l33tdawg' Kannabhiran (l33tdawg@hitb.org)

## License

[MIT License](LICENSE) - Copyright © 2025 