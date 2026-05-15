# BreakcoreSnake Agent Guide

This guide contains highly context-specific information that an agent should know to operate efficiently in this repository.

## ⚠️ Operational Gotchas & Prerequisites
- **FFmpeg Dependency:** FFmpeg must be installed system-wide and accessible in the PATH for all audio processing.
- **Python Version:** The project requires Python 3.12+.
- **Secrets Handling:** Never hardcode secrets. Environment variables (DISCORD_TOKEN, SPOTIFY_CLIENT_ID, etc.) must be sourced from a local `.env` file.

## 🛠️ Setup & Execution Flow
1.  **Install Dependencies:** Always run `pip install -r requirements.txt` first.
2.  **Run Bot:** The main entry point is `venv/bin/python src/main.py`.
3.  **Core Libraries:** Note the dependency on `discord.py[voice]` and `yt-dlp` for functionality.

## 📚 Code Structure Quirks
- **Entrypoint:** The application logic resides in `musicbot.py`.
- **Bot Purpose:** The bot is a Discord music bot, and its commands are structured around voice channels and music queue management.
- **Data Sources:** Media sources are typically handled via `yt-dlp` integration.
