import time
import discord
import os

TARGET_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID")) if os.getenv("DISCORD_CHANNEL_ID") else None

def format_duration(seconds: int) -> str:
    if not seconds:
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
    raise ValueError("Invalid time format. Use ss, mm:ss or hh:mm:ss.")

def make_track_embed(info, requester, title="Added to Queue"):
    embed = discord.Embed(
        title=title,
        description=f"[{info['title']}]({info.get('webpage_url','')})\nRequested by: {requester.mention}",
        color=discord.Color.dark_red()
    )
    if info.get("thumbnail"):
        embed.set_thumbnail(url=info["thumbnail"])
    return embed

def make_queue_embed(player):
    embed = discord.Embed(title="Music Queue", color=discord.Color.dark_red())
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
    if player.now_queue:        
        desc = ""
        for i, track in enumerate(player.now_queue[:7]):
            desc += f"{i+1}. [{track['title']}]({track.get('webpage_url','')}) ({format_duration(track.get('duration'))}) | By: {track.get('requester').mention}\n"
        if len(player.now_queue) > 7:
            desc += f"... and {len(player.now_queue)-7} more."
        embed.add_field(name="-------------------- **Priority** --------------------", value=desc, inline=False)
    if player.queue:
        desc = ""
        for i, track in enumerate(player.queue[:8]):
            desc += f"{i+ len(player.now_queue) + 1}. [{track['title']}]({track.get('webpage_url','')}) ({format_duration(track.get('duration'))}) | By: {track.get('requester').mention}\n"
        if len(player.queue) > 8:
            desc += f"... and {len(player.queue)-8} more."
        embed.add_field(name="------------------ **Non-Priority** ------------------", value=desc, inline=False)
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
        channel = ctx.guild.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        channel = ctx.channel

    await channel.send(content=content, embed=embed, view=view, suppress_embeds=suppress_embeds)
    
def is_duplicate(track, queues):
    track_url = track.get("webpage_url")
    if not track_url:
        return False
    return any(
        item.get("webpage_url") == track_url
        for queue in queues
        for item in queue
    )
