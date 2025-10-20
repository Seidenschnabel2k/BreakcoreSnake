import random
import asyncio
import discord
import time
from src.music import get_player,ffmpeg_options
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
        await ensure_voice(ctx)

    @bot.command(name="gtfo")
    async def leave(ctx):
        if ctx.voice_client:
            get_player(ctx.guild).clear()
            await ctx.voice_client.disconnect()
        else:
            await send_message(ctx, "I'm not in a voice channel.")

    @bot.command(name="p")
    async def play(ctx, *, query):
        vc = await ensure_voice(ctx)
        if not vc:
            return
        player = get_player(ctx.guild)
        infos, skipped = await player.add_track(query, ctx.author, playlist=False)
        if not vc.is_playing():
            await player.play_next(interactor=ctx.author, bot=bot)
        embed = make_track_embed(infos[0], ctx.author)
        await send_message(ctx, embed=embed)
        for track in skipped:
            await send_message(ctx, f"**{track['title']}** is already in the queue!")

    @bot.command(name="pl")
    async def playlist(ctx, *, query):
        vc = await ensure_voice(ctx)
        if not vc:
            return
        player = get_player(ctx.guild)
        infos, skipped = await player.add_track(query, ctx.author, playlist=True)
        if not vc.is_playing():
            await player.play_next(interactor=ctx.author, bot=bot)
        await send_message(ctx, f"Added playlist with {len(infos)} tracks.")
        for track in skipped:
            await send_message(ctx, f"**{track['title']}** is already in the queue!")

    @bot.command(name="n")
    async def now(ctx, *, query):
        vc = await ensure_voice(ctx)
        if not vc:
            return
        player = get_player(ctx.guild)
        infos, skipped = await player.add_track(query, ctx.author, playlist=False)
        player.queue.insert(0, infos[0])
        if not vc.is_playing():
            await player.play_next(interactor=ctx.author, bot=bot)
        else:
            embed = make_track_embed(infos[0], ctx.author)
            await send_message(ctx, embed=embed)
        for track in skipped:
            await send_message(ctx, f"**{track['title']}** is already in the queue!")

    @bot.command(name="q")
    async def queue(ctx):
        player = get_player(ctx.guild)
        if not player.queue and not (
            ctx.voice_client and ctx.voice_client.is_playing()
        ):
            return await send_message(ctx, "Queue is empty.")
        embed = make_queue_embed(player)
        await send_message(ctx, embed=embed)

    @bot.command(name="s")
    async def skip(ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await send_message(ctx, "Skipped current track.")

    @bot.command(name="stop")
    async def stop(ctx):
        if ctx.voice_client:
            get_player(ctx.guild).clear()
            ctx.voice_client.stop()
            await send_message(ctx, "Stopped and cleared the queue.")

    @bot.command(name="clear")
    async def clear(ctx):
        get_player(ctx.guild).clear()
        await send_message(ctx, "Cleared the queue.")

    @bot.command(name="shuffle")
    async def shuffle(ctx):
        player = get_player(ctx.guild)
        random.shuffle(player.queue)
        await send_message(ctx, "Queue shuffled.")

    @bot.command(name="seek")
    async def seek(ctx, *, position: str):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await send_message(ctx, "No song is currently playing.")
        try:
            seconds = parse_time(position)
        except ValueError:
            return await send_message(ctx, "Invalid time format. Use ss, mm:ss or hh:mm:ss.")
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
        await send_message(ctx, f"Seeked to {format_duration(seconds)} in **{info['title']}**")
        
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
