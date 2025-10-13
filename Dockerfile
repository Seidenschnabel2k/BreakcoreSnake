FROM python:3.11-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Set work directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir python-dotenv discord.py yt-dlp pynacl

# Run the bot/app
CMD ["python", "musicbot.py"]
