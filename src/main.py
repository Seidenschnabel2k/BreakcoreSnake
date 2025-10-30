import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import commands as music_commands

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DEBUG = os.getenv("DISCORD_DEBUG")


intents = discord.Intents.default()
intents.message_content = True
PREFIX = "~" if DEBUG else "!"

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

music_commands.setup(bot)

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")

if __name__ == "__main__":
    bot.run(TOKEN)
