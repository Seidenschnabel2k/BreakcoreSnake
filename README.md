# BreakcoreSnake

Music bot for Discord written in Python.

## Overview

BreakcoreSnake is a feature-rich Discord music bot, developed in Python. The bot allows users to play, queue, and control music playback directly from their Discord servers.

## Features

- Play music in voice channels
- Priority queue
- Queue and skip tracks
- Pause, resume, and stop playback
- Support for multiple audio sources (YouTube, etc.)
- Easy-to-use commands

## Installation

### Prerequisites

- Python 3.12+
- [FFmpeg](https://ffmpeg.org/) installed and available in your PATH
- Discord bot token ([How to get one](https://discordpy.readthedocs.io/en/stable/discord.html))

### Clone the Repository

```bash
git clone https://github.com/Paisson/BreakcoreSnake.git
cd BreakcoreSnake
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

1. Rename `example.env` to `.env` and insert your Discord bot token:

    ```
    DISCORD_TOKEN=your-token-here
    ```

2. Run the bot:

    ```bash
    python musicbot.py
    ```

3. Invite the bot to your server and use music commands!

## Docker

A Dockerfile is provided for easy deployment:

```bash
docker build -t breakcoresnake .
docker run --env DISCORD_TOKEN=your-token-here breakcoresnake
```

## TODO

### Upcoming

- Cookies
- Spotify function for Norman


### Completed

- ~~Start/Stop function~~
- ~~History and Statistic function~~
  - ~~url, elapsed_time, genre/tags(if possible), requester, title, when_played (time, date),  release_date~~
- ~~Search without link~~
- ~~Better Queue (Display thumbnail, hyperlink)~~
- ~~Clear Queue Message (clean up)~~
- ~~Clear specific song in queue~~
- ~~Timur prove~~

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

---

By [Paisson](https://github.com/Paisson) and another guy
