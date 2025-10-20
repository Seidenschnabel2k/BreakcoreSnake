import random
import asyncio
import discord
import time
from src.music import get_player, ffmpeg_options
from src.utils import (
    ensure_voice,
    make_track_embed,
    make_queue_embed,
    parse_time,
    format_duration,
    send_message,
    TARGET_CHANNEL_ID,
)


def setup(bot):
    @bot.command(name="tits")
    async def join(ctx):
        """Join the caller's voice channel."""
        await ensure_voice(ctx)

    @bot.command(name="gtfo")
    async def leave(ctx):
        """Leave voice channel and clear the queue."""
        if ctx.voice_client:
            get_player(ctx.guild).clear()
            await ctx.voice_client.disconnect()
        else:
            await send_message(ctx, "I'm not in a voice channel.")

    @bot.command(name="p")
    async def play(ctx, *, query):
        """Add a track to the queue. Usage: p [index] <query>"""
        index = None
        query = query.strip()

        # Split first word (could be an index)
        parts = query.split(maxsplit=1)
        first = parts[0]

        try:
            index = int(first)
            if len(parts) == 1:
                return await send_message(
                    ctx, "Please provide a search query after the index."
                )
            query = parts[1].strip()
        except ValueError:
            pass

        vc = await ensure_voice(ctx)
        if not vc:
            return
        player = get_player(ctx.guild)
        if index is not None:
            if index > len(player.queue):
                return await send_message(ctx, "Index bigger than queue length.")
        infos, skipped = await player.add_track(
            query, ctx.author, playlist=False, index=index
        )

        embed = make_track_embed(infos[0], ctx.author, title=f"Add at Position {index + 1} of Queue" if index is not None else "Add to Queue")
        # If the VC is paused, don't resume or start playback — just add to queue.
        if vc.is_paused():
            embed.add_field(name="Note", value="Playback is currently paused.")
        elif not vc.is_playing():
            await player.play_next(interactor=ctx.author, bot=bot)

        await send_message(ctx, embed=embed)
        for track in skipped:
            await send_message(ctx, f"**{track['title']}** is already in the queue!")

    @bot.command(name="pl")
    async def playlist(ctx, *, query):
        """Add all tracks from a playlist URL/search to the queue."""
        vc = await ensure_voice(ctx)
        if not vc:
            return
        player = get_player(ctx.guild)
        infos, skipped = await player.add_track(query, ctx.author, playlist=True)

        # If paused, don't resume — just add playlist to queue.
        if vc.is_paused():
            await send_message(ctx, f"Added playlist with {len(infos)} tracks (playback is paused).")
        elif not vc.is_playing():
            await player.play_next(interactor=ctx.author, bot=bot)
            await send_message(ctx, f"Added playlist with {len(infos)} tracks.")
        else:
            await send_message(ctx, f"Added playlist with {len(infos)} tracks.")

        for track in skipped:
            await send_message(ctx, f"**{track['title']}** is already in the queue!")

    @bot.command(name="n")
    async def now(ctx, *, query):
        """Add a track to the priority queue."""
        vc = await ensure_voice(ctx)
        if not vc:
            return
        player = get_player(ctx.guild)
        infos, skipped = await player.add_track(
            query, ctx.author, playlist=False, prio=True
        )

        embed = make_track_embed(infos[0], ctx.author, title="Added to Priority Queue")
        # If VC is paused, don't resume — just add to priority queue.
        if vc.is_paused():
            embed.add_field(name="Note", value="Playback is currently paused.")
        elif not vc.is_playing():
            await player.play_next(interactor=ctx.author, bot=bot)
        else:
            await send_message(ctx, embed=embed)

        for track in skipped:
            await send_message(ctx, f"**{track['title']}** is already in the queue!")

    @bot.command(name="q")
    async def queue(ctx):
        """Show the current queue."""
        vc = await ensure_voice(ctx)
        player = get_player(ctx.guild)
        if not player.queue and not (
            ctx.voice_client and ctx.voice_client.is_playing()
        ):
            return await send_message(ctx, "Queue is empty.")
        embed = make_queue_embed(player)
        if vc.is_paused():
            embed.add_field(name="Note", value="Playback is currently paused.")
        await send_message(ctx, embed=embed)

    @bot.command(name="s")
    async def skip(ctx, index: int = 0):
        """Skip the current track or remove a queued track by index."""
        player = get_player(ctx.guild)
        vc = ctx.voice_client

        if not vc or not vc.is_playing():
            return await send_message(ctx, "Nothing is playing right now.")

        if index == 0:
            vc.stop()

            await player.play_next(interactor=ctx.author, bot=bot)
            
            await send_message(ctx, f"Skipped **{player.current['title']}** track.")
            
        else:
            if index > len(player.queue):
                return await send_message(ctx, "Index bigger than queue length.")
            skipped_track = player.queue.pop(index - 1)
            await send_message(ctx, f"Skipped **{skipped_track['title']}** from the queue.")

    @bot.command(name="stop")
    async def stop(ctx):
        """Stop playback and clear the queue."""
        if ctx.voice_client:
            get_player(ctx.guild).clear()
            ctx.voice_client.stop()
            await send_message(ctx, "Stopped and cleared the queue.")
            
    @bot.command(name="pause")
    async def toggle_pause(ctx):
        """Toggle pause/resume for the current track."""
        player = get_player(ctx.guild)
        vc = ctx.voice_client
        if not vc:
            return await send_message(ctx, "I'm not connected to a voice channel.")

        if vc.is_playing():
            # store elapsed at pause
            if player.start_time:
                player.paused_offset = time.time() - player.start_time
            else:
                player.paused_offset = None
            vc.pause()
            await send_message(ctx, f"Paused **{player.current['title']}**.")
        elif vc.is_paused():
            # restore start_time so elapsed = now - start_time resumes correctly
            if getattr(player, "paused_offset", None) is not None:
                player.start_time = time.time() - player.paused_offset
                player.paused_offset = None
                try:
                    if hasattr(vc, "source") and hasattr(vc.source, "start_time"):
                        vc.source.start_time = player.start_time
                except Exception:
                    pass
            vc.resume()
            await send_message(ctx, f"Resumed **{player.current['title']}**.")
        else:
            await send_message(ctx, "Nothing is currently playing.")

    @bot.command(name="clear")
    async def clear(ctx):
        """Clear the queue."""
        get_player(ctx.guild).clear()
        await send_message(ctx, "Cleared the queue.")

    @bot.command(name="shuffle")
    async def shuffle(ctx):
        """Shuffle the queue."""
        player = get_player(ctx.guild)
        random.shuffle(player.queue)
        await send_message(ctx, "Queue shuffled.")

    @bot.command(name="seek")
    async def seek(ctx, *, position: str):
        """Seek to a position in the current track. Use ss, mm:ss or hh:mm:ss."""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await send_message(ctx, "No song is currently playing.")
        try:
            seconds = parse_time(position)
        except ValueError:
            return await send_message(
                ctx, "Invalid time format. Use ss, mm:ss or hh:mm:ss."
            )
        current = ctx.voice_client.source
        # if not hasattr(current, "data"):
        #     return await send_message(ctx, "No metadata found for the current track.")
        info = current.data
        duration = info.get("duration")
        if duration and seconds >= duration:
            return await send_message(ctx, "Seek position is beyond track length.")

        ctx.voice_client.stop()

        seek_opts = ffmpeg_options.copy()
        seek_opts["before_options"] = (
            f"-ss {seconds} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        )
        source = discord.FFmpegPCMAudio(info["url"], **seek_opts)
        wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
        wrapped.data = info
        wrapped.start_time = time.time() - seconds
        ctx.voice_client.play(
            wrapped,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                get_player(ctx.guild).play_next(ctx.author, bot=bot), bot.loop
            ),
        )
        ctx.voice_client.source = wrapped
        await send_message(
            ctx, f"Seeked to {format_duration(seconds)} in **{info['title']}**"
        )

    @bot.command(name="h")
    async def help(ctx, *, command_name: str = None):
        """Show available commands and their short descriptions. Use 'help <command>' for details."""
        if command_name:
            cmd = bot.get_command(command_name)
            if not cmd:
                return await send_message(ctx, f"No command named `{command_name}`.")
            try:
                allowed = await cmd.can_run(ctx)
            except Exception:
                allowed = True
            if not allowed:
                return await send_message(ctx, "You cannot use that command.")
            doc = cmd.help or (cmd.callback.__doc__ or "No documentation available.")
            usage = f"`{cmd.qualified_name} {cmd.signature}`" if getattr(cmd, "signature", None) else f"`{cmd.qualified_name}`"
            embed = discord.Embed(title=f"Help: {cmd.name}", color=0x00FFAA)
            embed.add_field(name="Usage", value=usage, inline=False)
            embed.add_field(name="Description", value=doc, inline=False)
            return await send_message(ctx, embed=embed)

        embed = discord.Embed(title="Available Commands", color=0x00FFAA)
        for cmd in sorted(bot.commands, key=lambda c: c.name):
            try:
                allowed = await cmd.can_run(ctx)
            except Exception:
                allowed = False
            if not allowed:
                continue
            doc = cmd.help or (cmd.callback.__doc__ or "")
            short = doc.splitlines()[0] if doc else ""
            usage = f"`{cmd.qualified_name} {cmd.signature}`" if getattr(cmd, "signature", None) else f"`{cmd.qualified_name}`"
            embed.add_field(name=usage, value=short or "No description.", inline=False)

        if not embed.fields:
            return await send_message(ctx, "No available commands.")
        await send_message(ctx, embed=embed)

    @bot.command(name="clearbot")
    async def clearbot(ctx, limit: int = 1000):
        """Delete this bot's messages in the current channel (owner only). Usage: clearbot [limit]"""
        if not await bot.is_owner(ctx.author):
            return await send_message(ctx, "You are not the bot owner.")
        def _is_bot(m: discord.Message):
            return m.author == bot.user
        deleted = await ctx.channel.purge(limit=limit, check=_is_bot)
        await send_message(ctx, f"Deleted {len(deleted)} bot messages from this channel.")

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

    @bot.event
    async def on_message(message: discord.Message):
        prefix = bot.command_prefix

        if message.author.bot:
            return

        # only allow in target channel
        if TARGET_CHANNEL_ID and message.channel.id != TARGET_CHANNEL_ID:
            await bot.process_commands(message)
            return

        if prefix and message.content.startswith(prefix):
            await bot.process_commands(message)
            return

        ctx = await bot.get_context(message)
        try:
            # call the play command callback directly, passing the message content as the query
            await bot.get_command("p").callback(ctx, query=message.content)
            try:
                await message.delete()
            except Exception:
                pass
        except Exception as e:
            print(f"Error handling autoplay message: {e}")

        # Also allow the normal command processing in case the message contained a command.
        await bot.process_commands(message)
