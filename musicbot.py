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
    parts = input_str.strip().split(":")
    if len(parts) == 1:
        return int(parts[0])
    elif len(parts) == 2:
        m, s = map(int, parts)
        return m * 60 + s
    elif len(parts) == 3:
        h, m, s = map(int, parts)
        return h * 3600 + m * 60 + s
    else:
        raise ValueError("Invalid time format. Use ss, mm:ss or hh:mm:ss.")

def is_duplicate(guild: discord.Guild, track_info):
    track_url = track_info.get("webpage_url")
    queue = music_queues.get(guild.id, [])
    if any(item.get("webpage_url") == track_url for item in queue):
        return True
    vc = guild.voice_client
    if vc and vc.is_playing():
        current = vc.source
        if hasattr(current, "data") and current.data.get("webpage_url") == track_url:
            return True
    return False

async def send_message(ctx, content=None, embed=None, view=None, suppress_embeds=False):
    channel = None
    if TARGET_CHANNEL_ID:
        channel = bot.get_channel(int(TARGET_CHANNEL_ID))
    if not channel:
        channel = ctx.channel
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
            return [entry for entry in data["entries"] if entry]
        else:
            return [data]

# -------------------- Playback --------------------

async def play_next_guild(guild: discord.Guild, interactor: discord.Member = None):
    try:
        queue = music_queues.get(guild.id, [])
        if not queue:
            await bot.change_presence(activity=None)
            return

        data = queue.pop(0)
        vc: discord.VoiceClient = guild.voice_client
        if not vc:
            if interactor and interactor.voice and interactor.voice.channel:
                vc = await interactor.voice.channel.connect()
            else:
                print(f"No voice client and no interactor in VC for guild {guild.name}")
                return

        source = discord.FFmpegPCMAudio(data["url"], **ffmpeg_options)
        wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
        wrapped.data = data
        wrapped.start_time = time.time()

        def after_play(err):
            if err:
                print(f"Playback error: {err}")
            asyncio.run_coroutine_threadsafe(play_next_guild(guild, interactor), bot.loop)

        vc.play(wrapped, after=after_play)
        vc.source = wrapped

        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name=data['title'])
        )

    except Exception as e:
        print("".join(traceback.format_exception(type(e), e, e.__traceback__)))

async def repeat_from_url(guild: discord.Guild, url: str, requester: discord.User):
    infos = await YTDLSource.from_url(url, loop=bot.loop, stream=True, playlist=False)
    if guild.id not in music_queues:
        music_queues[guild.id] = []

    for info in infos:
        info["requester"] = requester
        logger.log_track(info, requester_id=requester.id)

    # Determine target channel
    channel = None
    if TARGET_CHANNEL_ID:
        channel = bot.get_channel(int(TARGET_CHANNEL_ID))
    if not channel:
        # Fallback to requester's guild text channel
        channel = requester.guild.system_channel or requester.guild.text_channels[0]
    
    async with channel.typing():
        # Check duplicates
        if is_duplicate(guild, infos[0]):
            await send_message(channel, f"**{infos[0]['title']}** is already in the queue or playing.")
            return infos[0]

        # Add to queue
        music_queues[guild.id].extend(infos)

        # Start playback if not playing
        vc = guild.voice_client
        interactor = requester if isinstance(requester, discord.Member) else None
        if not vc or not vc.is_playing():
            await play_next_guild(guild, interactor)

        # Send embedded message with repeat button
        embed = discord.Embed(
            title="Added to the queue",
            description=f"[{infos[0]['title']}]({infos[0].get('webpage_url', '')})\nRequested by: {requester.mention}",
            color=discord.Color.blurple()
        )
        if infos[0].get("thumbnail"):
            embed.set_thumbnail(url=infos[0]["thumbnail"])

        # Create view with repeat button
        view = discord.ui.View()
        class RepeatButton(discord.ui.Button):
            def __init__(self, info):
                super().__init__(style=discord.ButtonStyle.secondary, emoji="🔁", label="Repeat")
                self.info = info

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.defer()
                await repeat_from_url(interaction.guild, self.info["webpage_url"], requester=interaction.user)

        view.add_item(RepeatButton(infos[0]))
        await send_message(channel, embed=embed, view=view)

        return infos[0]


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

@bot.before_invoke
async def cleanup(ctx):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete command messages.")
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

@bot.command(name="p")
async def play(ctx, *, url, interaction_user=None):
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

        for info in infos:
            info["requester"] = interaction_user or ctx.author
            logger.log_track(info, requester_id=info["requester"].id)

            if is_duplicate(ctx.guild, info):
                await send_message(ctx,
                                   f"The track **[{info['title']}]({info.get('webpage_url', '')})** is already in the queue.",
                                   suppress_embeds=True)
                return

        music_queues[ctx.guild.id].extend(infos)
        if not ctx.voice_client.is_playing():
            await play_next_guild(ctx.guild, interactor=ctx.author)

        # Embed
        embed = discord.Embed(
            title="Added to the queue",
            description=f"[{infos[0]['title']}]({infos[0].get('webpage_url', '')})\nRequested by: {infos[0]['requester'].mention}",
            color=discord.Color.blurple()
        )
        if infos[0].get("thumbnail"):
            embed.set_thumbnail(url=infos[0]["thumbnail"])

        # Repeat button
        view = discord.ui.View()
        class RepeatButton(discord.ui.Button):
            def __init__(self, info):
                super().__init__(style=discord.ButtonStyle.secondary, emoji="🔁", label="Repeat")
                self.info = info

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.defer()
                if is_duplicate(interaction.guild, self.info):
                    await send_message(interaction, f"**{self.info['title']}** is already in the queue or playing.")
                    return
                await repeat_from_url(interaction.guild, self.info["webpage_url"], requester=interaction.user)

        view.add_item(RepeatButton(infos[0]))
        await send_message(ctx, embed=embed, view=view)

# -------------------- Remaining Commands --------------------

@bot.command(name="n")
async def now(ctx, *, url):
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

        for info in infos:
            info["requester"] = ctx.author

        # Insert first track at the front of the queue
        music_queues[ctx.guild.id].insert(0, infos[0])

        if not ctx.voice_client.is_playing():
            await play_next_guild(ctx.guild, interactor=ctx.author)
        else:
            await send_message(ctx, f"Added {infos[0]['title']} to the front of the queue.")

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
        if ctx.guild.id not in music_queues:
            music_queues[ctx.guild.id] = []

        for info in infos:
            info["requester"] = ctx.author
            logger.log_track(info, requester_id=ctx.author.id)

        music_queues[ctx.guild.id].extend(infos)

        if not ctx.voice_client.is_playing():
            await play_next_guild(ctx.guild, interactor=ctx.author)
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

    # Now playing
    if ctx.voice_client and ctx.voice_client.is_playing():
        current = ctx.voice_client.source
        if hasattr(current, "data"):
            info = current.data
            duration = info.get("duration")
            requester = info.get("requester", "Unknown")
            progress = format_progress(current.start_time, duration) if hasattr(current, "start_time") else format_duration(duration)
            embed.add_field(
                name="Now Playing",
                value=f"[{info['title']}]({info.get('webpage_url', '')})\n{progress} | By: {requester.mention}",
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
            desc += f"{i + 1}. [{track['title']}]({track.get('webpage_url', '')}) ({duration}) | By: {requester}\n"
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

    ctx.voice_client.stop()
    seek_opts = ffmpeg_options.copy()
    seek_opts["before_options"] = f"-ss {seconds} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    source = discord.FFmpegPCMAudio(info["url"], **seek_opts)
    wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
    wrapped.data = info
    wrapped.start_time = time.time() - seconds

    ctx.voice_client.play(
        wrapped,
        after=lambda e: asyncio.run_coroutine_threadsafe(play_next_guild(ctx.guild, ctx.author), bot.loop)
    )
    ctx.voice_client.source = wrapped

    await send_message(ctx, f"Seeked to {format_duration(seconds)} in **{info['title']}**")

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
        await send_message(ctx, f"Invalid chapter number. This track has {len(chapters)} chapters.")
        return
    ch = chapters[number - 1]
    start = int(ch.get("start_time", 0))

    ctx.voice_client.stop()
    seek_opts = ffmpeg_options.copy()
    seek_opts["before_options"] = f"-ss {start} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    source = discord.FFmpegPCMAudio(info["url"], **seek_opts)
    wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
    wrapped.data = info
    wrapped.start_time = time.time() - start

    ctx.voice_client.play(
        wrapped,
        after=lambda e: asyncio.run_coroutine_threadsafe(play_next_guild(ctx.guild, ctx.author), bot.loop)
    )
    ctx.voice_client.source = wrapped

    await send_message(ctx, f"Skipped to chapter {number}: **{ch.get('title', '(Untitled)')}** at {format_duration(start)}")

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

# Disable default help
bot.remove_command("help")
@bot.command(name="h")
async def help_command(ctx):
    embed = discord.Embed(title="Music Bot Commands", description="Here’s a list of available commands:", color=discord.Color.blurple())
    commands_info = {
        "!tits": "Join your voice channel.",
        "!gtfo": "Leave the voice channel and clear queue.",
        "!p <url/query>": "Play a song (or add to queue).",
        "!n <url/query>": "Play a song immediately (skips queue).",
        "!pl <playlist_url>": "Play an entire playlist.",
        "!q": "Show the current queue.",
        "!s": "Skip the current track.",
        "!stop": "Stop playback and clear queue.",
        "!clear": "Clear the queue.",
        "!shuffle": "Shuffle the queue.",
        "!seek <time>": "Seek within the current track (e.g. 1:23).",
        "!chapters": "List chapters in the current track.",
        "!chapter <n>": "Jump to a specific chapter number.",
        "!h": "Show this help message."
    }
    for cmd, desc in commands_info.items():
        embed.add_field(name=cmd, value=desc, inline=False)
    await send_message(ctx, embed=embed)

# -------------------- Run Bot --------------------
if __name__ == "__main__":
    bot.run(TOKEN)
