#!/usr/bin/env python
import os
import time
import random
import asyncio
import traceback
import discord
from discord.ext import commands
import yt_dlp as youtube_dl
from dotenv import load_dotenv

# -------------------- Setup --------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    raise ValueError("No token found! Set DISCORD_TOKEN environment variable.")

intents = discord.Intents.default()
intents.message_content = True
if not os.getenv("DISCORD_DEBUG") is None:
    bot = commands.Bot(command_prefix="~", intents=intents)
else:
    bot = commands.Bot(command_prefix="!", intents=intents)

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -bufsize 64k",
}

ytdl_format_options = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",
    "extract_flat": False,
}

playlist_ytdl_options = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "default_search": "auto",
    "ignoreerrors": True,
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
pl_ytdl = youtube_dl.YoutubeDL(playlist_ytdl_options)

music_queues = {}

# -------------------- Helpers --------------------


def format_duration(seconds: int) -> str:
    if seconds is None:
        return "Live"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02}:{s:02}"
    else:
        return f"{m}:{s:02}"


def format_progress(start_time: float, total: int) -> str:
    if total is None:
        return "Live"
    elapsed = int(time.time() - start_time)
    if elapsed > total:
        elapsed = total
    em, es = divmod(elapsed, 60)
    eh, em = divmod(em, 60)
    tm, ts = divmod(total, 60)
    th, tm = divmod(tm, 60)
    if th:
        return f"{eh}:{em:02}:{es:02} / {th}:{tm:02}:{ts:02}"
    else:
        return f"{em}:{es:02} / {tm}:{ts:02}"


# -------------------- YTDLSource --------------------


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.start_time = None

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, playlist=False):
        loop = loop or asyncio.get_event_loop()
        ydl = pl_ytdl if playlist else ytdl
        data = await loop.run_in_executor(
            None, lambda: ydl.extract_info(url, download=not stream)
        )
        if "entries" in data:
            entries = [entry for entry in data["entries"] if entry]
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
        source = discord.FFmpegPCMAudio(data["url"], **ffmpeg_options)
        wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
        wrapped.data = data
        wrapped.start_time = time.time()

        ctx.voice_client.play(
            wrapped,
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop),
        )
        ctx.voice_client.source = wrapped

        await bot.change_presence(
            activity=discord.Activity(type=2, name=f"{data['title']}")
        )
    except Exception as e:
        error_msg = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        print(error_msg)
        try:
            await ctx.send(f"Error while playing: ```{e}```")
        except discord.Forbidden:
            pass


# -------------------- Events --------------------


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")


@bot.event
async def on_command_error(ctx, error):
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


@bot.command(name="n")
async def now(ctx, *, url):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You need to join a voice channel first.")
            return

    async with ctx.typing():
        infos = await YTDLSource.from_url(
            url, loop=bot.loop, stream=True, playlist=False
        )
        if ctx.guild.id not in music_queues:
            music_queues[ctx.guild.id] = []
        for info in infos:
            info["requester"] = str(ctx.author)
        music_queues[ctx.guild.id].insert(0, infos[0])

        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        else:
            await ctx.send(f"Added {infos[0]['title']} to the front of the queue.")


@bot.command(name="p")
async def play(ctx, *, url):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You need to join a voice channel first.")
            return

    async with ctx.typing():
        infos = await YTDLSource.from_url(
            url, loop=bot.loop, stream=True, playlist=False
        )
        if ctx.guild.id not in music_queues:
            music_queues[ctx.guild.id] = []
        for info in infos:
            info["requester"] = str(ctx.author)
        music_queues[ctx.guild.id].extend(infos)

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
        infos = await YTDLSource.from_url(
            url, loop=bot.loop, stream=True, playlist=True
        )
        if ctx.guild.id not in music_queues:
            music_queues[ctx.guild.id] = []
        for info in infos:
            info["requester"] = str(ctx.author)
        music_queues[ctx.guild.id].extend(infos)

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
    if not queue and not (ctx.voice_client and ctx.voice_client.is_playing()):
        await ctx.send("Queue is empty.")
        return

    embed = discord.Embed(title="Music Queue", color=discord.Color.blurple())

    # Currently playing
    if ctx.voice_client and ctx.voice_client.is_playing():
        current = ctx.voice_client.source
        if hasattr(current, "data"):
            info = current.data
            duration = info.get("duration")
            requester = info.get("requester", "Unknown")
            if hasattr(current, "start_time"):
                progress = format_progress(current.start_time, duration)
            else:
                progress = format_duration(duration)
            embed.add_field(
                name="Now Playing",
                value=f"[{info['title']}]({info.get('webpage_url', '')})\n"
                f"{progress} | By: {requester}",
                inline=False,
            )
            if "thumbnail" in info:
                embed.set_image(url=info["thumbnail"])
    else:
        embed.add_field(name="Now Playing", value="Nothing playing.", inline=False)

    # Queue list
    if queue:
        desc = ""
        for i, track in enumerate(queue[:10]):
            duration = format_duration(track.get("duration"))
            requester = track.get("requester", "Unknown")
            desc += (
                f"{i + 1}. [{track['title']}]({track.get('webpage_url', '')}) "
                f"({duration}) • By: {requester}\n"
            )
        if len(queue) > 10:
            desc += f"... and {len(queue) - 10} more."
        embed.add_field(name="Up Next", value=desc, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="clear")
async def clear(ctx):
    if ctx.guild.id in music_queues:
        music_queues[ctx.guild.id] = []
    await ctx.send("Cleared the queue.")


@bot.command()
async def shuffle(ctx):
    if ctx.guild.id in music_queues:
        random.shuffle(music_queues[ctx.guild.id])
    await ctx.send("Queue shuffled.")


# -------------------- Run Bot --------------------
if __name__ == "__main__":
    bot.run(TOKEN)
