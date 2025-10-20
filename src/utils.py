import time
import discord
import os

TARGET_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")

def format_duration(seconds: int) -> str:
    if not seconds:
        return "Live"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"

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
    return f"{em}:{es:02} / {tm}:{ts:02}"

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
    raise ValueError("Invalid time format. Use ss, mm:ss or hh:mm:ss.")

def make_track_embed(info, requester):
    embed = discord.Embed(
        title="Added to Queue",
        description=f"[{info['title']}]({info.get('webpage_url','')})\nRequested by: {requester.mention}",
        color=discord.Color.blurple()
    )
    if info.get("thumbnail"):
        embed.set_thumbnail(url=info["thumbnail"])
    return embed

def make_queue_embed(player):
    embed = discord.Embed(title="Music Queue", color=discord.Color.blurple())
    if player.current:
        dur = player.current.get("duration")
        progress = format_progress(player.start_time, dur) if player.start_time else format_duration(dur)
        embed.add_field(
            name="Now Playing",
            value=f"[{player.current['title']}]({player.current.get('webpage_url','')})\n{progress} | By: {player.current.get('requester').mention}",
            inline=False
        )
        if player.current.get("thumbnail"):
            embed.set_image(url=player.current["thumbnail"])
    if player.queue:
        desc = ""
        for i, track in enumerate(player.queue[:10]):
            desc += f"{i+1}. [{track['title']}]({track.get('webpage_url','')}) ({format_duration(track.get('duration'))}) | By: {track.get('requester')}\n"
        if len(player.queue) > 10:
            desc += f"... and {len(player.queue)-10} more."
        embed.add_field(name="Up Next", value=desc, inline=False)
    return embed

async def ensure_voice(ctx):
    """Ensure bot is in a voice channel with the user."""
    if not ctx.voice_client:
        if ctx.author.voice:
            return await ctx.author.voice.channel.connect()
        await send_message(ctx, f"{ctx.author.mention}, you need to join a voice channel first.")
        return None
    return ctx.voice_client

async def send_message(ctx, content=None, embed=None, view=None, suppress_embeds=False):
    """Send the response only in target channel."""
    # Determine target channel
    channel = None
    if TARGET_CHANNEL_ID:
        channel = ctx.guild.get_channel(int(TARGET_CHANNEL_ID))
    if not channel:
        channel = ctx.channel

    await channel.send(content=content, embed=embed, view=view, suppress_embeds=suppress_embeds)
    
def is_duplicate(track, queue):
    """
    Check if a track is already in the queue.

    Args:
        track (dict): Track info, must contain 'url'.
        queue (list): List of track dicts.

    Returns:
        bool: True if duplicate exists, False otherwise.
    """
    track_url = track.get("webpage_url")
    if not track_url:
        return False  # cannot check without URL
    return any(item.get("webpage_url") == track_url for item in queue)