FROM python:3.14-slim

# Install ffmpeg
RUN apt update && apt install -y ffmpeg && apt clean

# Set work directory
WORKDIR /app

# Copy project files
COPY src ./src/
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the bot/app
CMD ["python", "src/main.py"]
