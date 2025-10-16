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
from logger import Logger

# -------------------- Setup --------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

TARGET_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")

if TOKEN is None:
    raise ValueError("No token found! Set DISCORD_TOKEN environment variable.")

intents = discord.Intents.default()
intents.message_content = True
if not os.getenv("DISCORD_DEBUG") is None:
    bot = commands.Bot(command_prefix="~", intents=intents)
    TARGET_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
else:
    bot = commands.Bot(command_prefix="!", intents=intents)

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -bufsize 96k",
}

ytdl_format_options = {
    "format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",
    "extract_flat": False,
}

playlist_ytdl_options = {
    "format": "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "default_search": "auto",
    "ignoreerrors": True,
}

logger = Logger()
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
        return f"{h:.0f}:{m:02.0f}:{s:02.0f}"
    else:
        return f"{m:02.0f}:{s:02.0f}"


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
        return f"{eh:.0f}:{em:02.0f}:{es:02.0f} / {th}:{tm:02.0f}:{ts:02.0f}"
    else:
        return f"{em:.0f}:{es:02.0f} / {tm:.0f}:{ts:02.0f}"


def parse_time(input_str: str) -> int:
    """Parses time string (ss, mm:ss, hh:mm:ss) into seconds."""
    parts = input_str.strip().split(":")
    if len(parts) == 1:
        return int(parts[0])  # seconds only
    elif len(parts) == 2:
        m, s = map(int, parts)
        return m * 60 + s
    elif len(parts) == 3:
        h, m, s = map(int, parts)
        return h * 3600 + m * 60 + s
    else:
        raise ValueError("Invalid time format. Use ss, mm:ss or hh:mm:ss.")


def is_duplicate(ctx, track_info):
    """Check if a track is already in the queue OR currently playing (by URL)."""
    track_url = track_info.get("webpage_url")

    # Check queue
    queue = music_queues.get(ctx.guild.id, [])
    if any(item.get("webpage_url") == track_url for item in queue):
        return True

    # Check currently playing
    if ctx.voice_client and ctx.voice_client.is_playing():
        current = ctx.voice_client.source
        if hasattr(current, "data") and current.data.get("webpage_url") == track_url:
            return True

    return False


async def send_message(ctx, content=None, embed=None, view=None,  suppress_embeds=False):
    """Send message either to target channel or fallback to ctx.channel."""
    channel = None
    if TARGET_CHANNEL_ID:
        print("found channel id")
        channel = bot.get_channel(int(TARGET_CHANNEL_ID))
        print(channel)
    if not channel:
        channel = ctx.channel  # fallback

    await channel.send(content=content, embed=embed, view=view, suppress_embeds=suppress_embeds)


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
            await bot.change_presence()
            return

        data = queue.pop(0)
        source = discord.FFmpegPCMAudio(data["url"], **ffmpeg_options)
        wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
        wrapped.data = data
        wrapped.start_time = time.time()

        ctx.voice_client.play(
            wrapped,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(ctx), bot.loop),
        )
        ctx.voice_client.source = wrapped

        await bot.change_presence(
            activity=discord.Activity(type=2, name=f"{data['title']}")
        )
    except Exception as e:
        error_msg = "".join(traceback.format_exception(
            type(e), e, e.__traceback__))
        print(error_msg)
        try:
            await send_message(ctx, f"Error while playing: ```{e}```")
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
        await send_message(ctx, f"An error occurred: ```{error}```")
    except discord.Forbidden:
        pass


# -------------------- Hooks --------------------


@bot.before_invoke
async def cleanup(ctx):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        await ctx.send(
            "I don't have permission to delete command messages. "
            "Please give me the 'Manage Messages' permission."
        )
    except discord.HTTPException as e:
        await ctx.send(f"Failed to delete the command message: {e}")


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
            info["requester"] = ctx.author
        music_queues[ctx.guild.id].insert(0, infos[0])

        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        else:
            await send_message(ctx, f"Added {infos[0]['title']} to the front of the queue.")


@bot.command(name="p")
async def play(ctx, *, url, interaction_user=None):
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
            info["requester"] = interaction_user or ctx.author
            # Log track using requester ID
            logger.log_track(info, requester_id=info["requester"].id)

            if is_duplicate(ctx, info):
                await send_message(ctx,
                                   f"The track **[{info['title']}]({info.get(
                                       'webpage_url', '')})** is already in the queue.",
                                   suppress_embeds=True
                                   )
                return

        music_queues[ctx.guild.id].extend(infos)

        if not ctx.voice_client.is_playing():
            await play_next(ctx)

        # Build embed
        embed = discord.Embed(
            title="Added to the queue",
            description=f"[{infos[0]['title']}]({infos[0].get('webpage_url', '')})\nRequested by: {
                info["requester"].mention}",
            color=discord.Color.blurple(),
        )

        if infos[0].get("thumbnail"):
            embed.set_thumbnail(url=infos[0]["thumbnail"])

        # Build a view with a repeat button
        view = discord.ui.View()

        class RepeatButton(discord.ui.Button):
            def __init__(self, info):
                super().__init__(style=discord.ButtonStyle.secondary, emoji="🔁", label="Repeat")
                self.info = info  # Store original track info dict

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.defer()

                # Call the same play command as if the user typed !p <url>
                await play(
                    ctx,
                    # replay using permanent webpage_url
                    url=self.info["webpage_url"],
                    interaction_user=interaction.user  # requester is the button clicker
                )

        view.add_item(RepeatButton(infos[0]))

        await send_message(ctx, embed=embed, view=view)


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
            info["requester"] = ctx.author
            # Log track using requester ID
            logger.log_track(info, requester_id=ctx.author.id)

        music_queues[ctx.guild.id].extend(infos)

        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        else:
            await send_message(ctx, f"Added playlist with {len(infos)} tracks to the queue.")


@bot.command(name="s")
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await send_message(ctx, "Skipped current track.")


@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        music_queues[ctx.guild.id] = []
        ctx.voice_client.stop()
        await send_message(ctx, "Stopped and cleared the queue.")


@bot.command(name="q")
async def queue(ctx):
    queue = music_queues.get(ctx.guild.id, [])
    if not queue and not (ctx.voice_client and ctx.voice_client.is_playing()):
        await send_message(ctx, "Queue is empty.")
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
                f"{progress} | By: {requester.mention}",
                inline=False,
            )
            if "thumbnail" in info:
                embed.set_image(url=info["thumbnail"])
    else:
        embed.add_field(name="Now Playing",
                        value="Nothing playing.", inline=False)

    # Queue list
    if queue:
        desc = ""
        for i, track in enumerate(queue[:10]):
            duration = format_duration(track.get("duration"))
            requester = track.get("requester", "Unknown")
            desc += (
                f"{i + 1}. [{track['title']}]({track.get('webpage_url', '')}) "
                f"({duration}) | By: {requester}\n"
            )
        if len(queue) > 10:
            desc += f"... and {len(queue) - 10} more."
        embed.add_field(name="Up Next", value=desc, inline=False)

    await send_message(ctx, embed=embed)


@bot.command(name="clear")
async def clear(ctx):
    if ctx.guild.id in music_queues:
        music_queues[ctx.guild.id] = []
    await send_message(ctx, "Cleared the queue.")


@bot.command()
async def shuffle(ctx):
    if ctx.guild.id in music_queues:
        random.shuffle(music_queues[ctx.guild.id])
    await send_message(ctx, "Queue shuffled.")


@bot.command(name="seek")
async def seek(ctx, *, position: str):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await send_message(ctx, "No song is currently playing.")
        return

    try:
        seconds = parse_time(position)
    except ValueError:
        await send_message(ctx, "Invalid time format. Use ss, mm:ss or hh:mm:ss.")
        return

    current = ctx.voice_client.source
    if not hasattr(current, "data"):
        await send_message(ctx, "No metadata found for the current track.")
        return

    info = current.data
    duration = info.get("duration")
    if duration and seconds >= duration:
        await send_message(ctx, "Seek position is beyond track length.")
        return

    # Stop current playback
    ctx.voice_client.stop()

    # Restart with seek
    seek_opts = ffmpeg_options.copy()
    seek_opts["before_options"] = (
        f"-ss {seconds} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    )
    source = discord.FFmpegPCMAudio(info["url"], **seek_opts)
    wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
    wrapped.data = info
    wrapped.start_time = time.time() - seconds  # shift timeline correctly

    ctx.voice_client.play(
        wrapped,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(ctx), bot.loop),
    )
    ctx.voice_client.source = wrapped

    await send_message(ctx, f"Seeked to {format_duration(seconds)} in **{info['title']}**")


# Could refactor to use seek logic but for now just copying logic inside function
@bot.command(name="chapter")
async def chapter(ctx, number: int):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await send_message(ctx, "No song is currently playing.")
        return

    current = ctx.voice_client.source
    if not hasattr(current, "data"):
        await send_message(ctx, "No metadata found for the current track.")
        return

    info = current.data
    chapters = info.get("chapters")
    if not chapters:
        await send_message(ctx, "This track has no chapter markers.")
        return

    if number < 1 or number > len(chapters):
        await send_message(ctx,
                           f"Invalid chapter number. This track has {
                               len(chapters)} chapters."
                           )
        return

    ch = chapters[number - 1]
    start = int(ch.get("start_time", 0))

    # Stop current playback
    ctx.voice_client.stop()

    # Restart from chapter start
    seek_opts = ffmpeg_options.copy()
    seek_opts["before_options"] = (
        f"-ss {start} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    )
    source = discord.FFmpegPCMAudio(info["url"], **seek_opts)
    wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
    wrapped.data = info
    wrapped.start_time = time.time() - start

    ctx.voice_client.play(
        wrapped,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(ctx), bot.loop),
    )
    ctx.voice_client.source = wrapped

    await send_message(ctx,
                       f"Skipped to chapter {
                           number}: **{ch.get('title', '(Untitled)')}** at {format_duration(start)}"
                       )


@bot.command(name="chapters")
async def chapters(ctx):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await send_message(ctx, "No song is currently playing.")
        return

    current = ctx.voice_client.source
    if not hasattr(current, "data"):
        await send_message(ctx, "No metadata found for the current track.")
        return

    info = current.data
    chapters = info.get("chapters")
    if not chapters:
        await send_message(ctx, "This track has no chapter markers.")
        return

    lines = []
    for i, ch in enumerate(chapters, start=1):
        start = int(ch.get("start_time", 0))
        title = ch.get("title", "(Untitled)")
        lines.append(f"**{i}.** [{format_duration(start)}] {title}")

    msg = "\n".join(lines)
    await send_message(ctx, f"Chapters for **{info['title']}**:\n{msg}")


# -------------------- Run Bot --------------------
if __name__ == "__main__":
    bot.run(TOKEN)
