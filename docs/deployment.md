# SilentGem Deployment Guide

This guide covers different ways to deploy SilentGem on various platforms.

## Local Deployment

### Prerequisites
- Python 3.10+
- Telegram API credentials
- Google Gemini API key

### Setup

1. Clone the repository and navigate to the project directory
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your API credentials
4. Copy `data/mapping.json.example` to `data/mapping.json` and configure your chat mappings
5. Run the bot: `python silentgem.py`

## Server Deployment

### DigitalOcean / VPS

1. Set up a new VPS with Ubuntu
2. Install Python and required dependencies
3. Clone the repository
4. Install Python dependencies: `pip install -r requirements.txt`
5. Configure environment variables and mapping
6. Use systemd or supervisor to keep the bot running:

```ini
# /etc/systemd/system/silentgem.service
[Unit]
Description=SilentGem Telegram translator
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/silentgem
ExecStart=/usr/bin/python3 /path/to/silentgem/silentgem.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start the service:
```
sudo systemctl enable silentgem
sudo systemctl start silentgem
```

### Fly.io Deployment

1. Install the Fly CLI
2. Create a `fly.toml` file:

```toml
app = "silentgem"
primary_region = "lax"

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"

[processes]
  app = "python silentgem.py"

[mounts]
  source = "silentgem_data"
  destination = "/app/data"
```

3. Create a volume for persistent data:
```
fly volumes create silentgem_data --size 1
```

4. Create secrets for your API keys:
```
fly secrets set TELEGRAM_API_ID=your_api_id
fly secrets set TELEGRAM_API_HASH=your_api_hash
fly secrets set GEMINI_API_KEY=your_gemini_key
```

5. Deploy the app:
```
fly launch
```

## Android Deployment with Termux

1. Install Termux from F-Droid (not Play Store)
2. Update packages:
```
pkg update && pkg upgrade
```

3. Install Python and Git:
```
pkg install python git
```

4. Clone the repository:
```
git clone https://github.com/yourusername/silentgem.git
cd silentgem
```

5. Install dependencies:
```
pip install -r requirements.txt
```

6. Configure your `.env` and `mapping.json` files
7. Run the bot:
```
python silentgem.py
```

8. To keep it running in the background when you close Termux:
```
nohup python silentgem.py > logs/output.log 2>&1 &
```

## Maintaining Your Deployment

### Updating

To update your deployment:

1. Pull the latest code:
```
git pull origin main
```

2. Install any new dependencies:
```
pip install -r requirements.txt
```

3. Restart the service (if using systemd):
```
sudo systemctl restart silentgem
```

### Checking Logs

To view logs:

- Systemd service: `journalctl -u silentgem`
- Direct logs: Check the `logs/silentgem.log` file

### Backup

Always backup your:
- `.env` file
- `data/mapping.json` file
- `*.session` files (Telegram session files) 