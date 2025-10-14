#!/usr/bin/env python
import os
import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import traceback
from dotenv import load_dotenv

# Read environment variable
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    raise ValueError("No token found! Set DISCORD_TOKEN environment variable.")

intents = discord.Intents.default()
intents.message_content = True  # Required for prefix commands
if not os.getenv("DISCORD_DEBUG") == None:
    bot = commands.Bot(command_prefix="~", intents=intents)
else:
    bot = commands.Bot(command_prefix="!", intents=intents)

# FFmpeg options for stable streaming
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -bufsize 64k'
}

# yt-dlp options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto'
}

playlist_ytdl_options = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'default_search': 'auto'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
pl_ytdl = youtube_dl.YoutubeDL(playlist_ytdl_options)

# Guild-specific queues
music_queues = {}

# -------------------- YTDLSource --------------------


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, playlist=False):
        loop = loop or asyncio.get_event_loop()
        ydl = pl_ytdl if playlist else ytdl

        # Extract info in a separate thread
        data = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=not stream))

        # Handle playlists
        if 'entries' in data:
            entries = [entry for entry in data['entries'] if entry]
            return entries
        else:
            return [data]

# -------------------- Playback --------------------


async def play_next(ctx):
    try:
        queue = music_queues.get(ctx.guild.id, [])
        if not queue:
            await ctx.send("Queue finished.")
            await bot.change_presence()
            return

        data = queue.pop(0)
        source = discord.FFmpegPCMAudio(data['url'], **ffmpeg_options)
        ctx.voice_client.play(
            discord.PCMVolumeTransformer(source, volume=0.5),
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(ctx), bot.loop)
        )
        await bot.change_presence(activity=discord.Activity(
            type=2, name=f"{data['title']}",))
        # await ctx.send(f"Now playing: {data['title']}")
    except Exception as e:
        error_msg = "".join(traceback.format_exception(
            type(e), e, e.__traceback__))
        print(error_msg)
        try:
            await ctx.send(f"Error while playing: ```{e}```")
        except discord.Forbidden:
            pass  # Can't send messages

# -------------------- Events --------------------


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")


@bot.event
async def on_command_error(ctx, error):
    # Log error and send if possible
    print(f"Error in command {ctx.command}: {error}")
    try:
        await ctx.send(f"An error occurred: ```{error}```")
    except discord.Forbidden:
        pass

# -------------------- Commands --------------------


@bot.command(name="tits")
async def join(ctx):
    if ctx.author.voice:
        await ctx.author.voice.channel.connect()
    else:
        await ctx.send("You need to be in a voice channel first.")


@bot.command(name="gtfo")
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        music_queues[ctx.guild.id] = []
    else:
        await ctx.send("I'm not in a voice channel.")


@bot.command(name="p")
async def play(ctx, *, url):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You need to join a voice channel first.")
            return

    async with ctx.typing():
        infos = await YTDLSource.from_url(url, loop=bot.loop, stream=True, playlist=False)
        if ctx.guild.id not in music_queues:
            music_queues[ctx.guild.id] = []

        music_queues[ctx.guild.id].extend(infos)

        # Play first track immediately if not already playing
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        else:
            await ctx.send(f"Added {len(infos)} track(s) to the queue.")


@bot.command(name="pl")
async def playlist(ctx, *, url):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You need to join a voice channel first.")
            return

    async with ctx.typing():
        infos = await YTDLSource.from_url(url, loop=bot.loop, stream=True, playlist=True)
        print(infos)
        if ctx.guild.id not in music_queues:
            music_queues[ctx.guild.id] = []

        # Limit playlist to 50 tracks to reduce lag
        infos = infos[:50]
        music_queues[ctx.guild.id].extend(infos)

        # Play first track immediately if not already playing
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        else:
            await ctx.send(f"Added playlist with {len(infos)} tracks to the queue.")


@bot.command(name="s")
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Skipped current track.")


@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        music_queues[ctx.guild.id] = []
        ctx.voice_client.stop()
        await ctx.send("Stopped and cleared the queue.")


@bot.command(name="q")
async def queue(ctx):
    queue = music_queues.get(ctx.guild.id, [])
    if not queue:
        await ctx.send("Queue is empty.")
    else:
        q = "\n".join([f"{i+1}. {track['title']}" for i,
                       track in enumerate(queue)])
        await ctx.send(f"Queue:\n{q}")


@bot.command(name="clear")
async def clear(ctx):
    if ctx.guild.id in music_queues:
        music_queues[ctx.guild.id] = []
    await ctx.send("Cleared the queue.")

# -------------------- Run Bot --------------------
if __name__ == "__main__":
    bot.run(TOKEN)
