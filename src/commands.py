import random
import asyncio
import discord
from discord.ext import commands
import time
from datetime import datetime, timedelta
from music import get_player, FFMPEG_OPTIONS, YTDLSource
from analytics import Analytics
from spotify import SpotifyResolver
from utils import (
    ensure_voice,
    make_track_embed,
    make_queue_embed,
    parse_time,
    format_duration,
    send_message,
    TARGET_CHANNEL_ID,
)


def setup(bot):
    spotify = SpotifyResolver()

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
        """Add a track to the queue. Usage: p <query>"""
        query = query.strip()

        if spotify.is_spotify_url(query):
            url_type = spotify.get_url_type(query)
            if url_type != "track":
                return await send_message(
                    ctx,
                    "Spotify albums/playlists should be queued with `pl`.",
                )
            try:
                query = await spotify.to_youtube_music_query(query)
            except ValueError as e:
                return await send_message(ctx, str(e))
            except Exception as e:
                return await send_message(ctx, f"Failed to resolve Spotify track: {e}")

        vc = await ensure_voice(ctx)
        if not vc:
            return
        player = get_player(ctx.guild)

        infos, skipped = await player.add_track(
            query, ctx.author, playlist=False
        )

        embed = make_track_embed(infos[0], ctx.author, title="Add to Queue")
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

        if spotify.is_spotify_url(query):
            url_type = spotify.get_url_type(query)
            if url_type == "track":
                return await send_message(
                    ctx,
                    "Spotify tracks should be queued with `p`.",
                )

            async with ctx.typing():
                await send_message(ctx, "Processing Spotify album/playlist... This may take a moment.")
                try:
                    yt_queries = await spotify.to_youtube_music_queries(query)
                except ValueError as e:
                    return await send_message(ctx, str(e))
                except Exception as e:
                    return await send_message(ctx, f"Failed to resolve Spotify URL: {e}")

                infos = []
                skipped = []
                for yt_query in yt_queries:
                    added_infos, skipped_infos = await player.add_track(
                        yt_query,
                        ctx.author,
                        playlist=False,
                    )
                    infos.extend(added_infos)
                    skipped.extend(skipped_infos)

            added_count = max(0, len(infos) - len(skipped))
            message = f"Added {added_count} tracks from Spotify {url_type}."
            if vc.is_paused():
                message += " (playback is paused)."
            else:
                message += "."

            if not vc.is_paused() and not vc.is_playing() and added_count > 0:
                await player.play_next(interactor=ctx.author, bot=bot)

            await send_message(ctx, message)
            if skipped:
                await send_message(ctx, f"Skipped {len(skipped)} duplicate tracks already in queue.")
            return

        async with ctx.typing():
            await send_message(ctx, "Processing playlist... This may take a moment.")
            infos, skipped = await player.add_track(query, ctx.author, playlist=True)

        # Get playlist URL from first track if available
        playlist_url = None
        if infos and infos[0].get("webpage_url"):
            # Extract playlist ID from the URL if it's a playlist
            url = infos[0].get("webpage_url", "")
            if "playlist" in url:
                playlist_url = url.split("&index=")[0] if "&index=" in url else url

        message = f"Added playlist with {len(infos)} tracks"
        if playlist_url:
            message += f"\n{playlist_url}"
        if vc.is_paused():
            message += " (playback is paused)."
        else:
            message += "."

        # If paused, don't resume — just add playlist to queue.
        if vc.is_paused():
            await send_message(ctx, message)
        elif not vc.is_playing():
            await player.play_next(interactor=ctx.author, bot=bot)
            await send_message(ctx, message)
        else:
            await send_message(ctx, message)

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
            await send_message(ctx, embed=embed)
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

            # await player.play_next(interactor=ctx.author, bot=bot)
            
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
        """Seek to a position in the current track."""
        vc = ctx.voice_client

        if not vc or not vc.is_playing():
            return await send_message(ctx, "No song is currently playing.")

        try:
            seconds = parse_time(position)
        except ValueError:
            return await send_message(ctx, "Invalid time format. Use ss, mm:ss or hh:mm:ss.")

        current = vc.source
        info = current.data
        duration = info.get("duration")

        if duration and seconds >= duration:
            return await send_message(ctx, "Seek position is beyond track length.")

        vc.stop()

        fresh_source = await YTDLSource.from_url(
            info["webpage_url"], loop=bot.loop, stream=True
        )

        fresh_info = fresh_source.data
        real_url = fresh_info["url"]

        seek_opts = FFMPEG_OPTIONS.copy()
        seek_opts = {
            "before_options": (
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
            ),
            "options": f"-vn -ss {seconds}"
}

        # FFmpeg source using fresh URL
        source = discord.FFmpegPCMAudio(real_url, **seek_opts)

        wrapped = discord.PCMVolumeTransformer(source, volume=current.volume)
        wrapped.data = fresh_info
        wrapped.start_time = time.time() - seconds

        vc.play(
            wrapped,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                get_player(ctx.guild).play_next(ctx.author, bot=bot), bot.loop
            ),
        )

        vc.source = wrapped

        await send_message(
            ctx, f"Seeked to {format_duration(seconds)} in **{fresh_info['title']}**"
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
    async def clearbot(ctx, limit: int = 10):
        """Delete this bot's messages in the current channel (owner only). Usage: clearbot [limit]"""
        if not await bot.is_owner(ctx.author):
            return await send_message(ctx, "You are not the bot owner.")
        def _is_bot(m: discord.Message):
            return m.author == bot.user
        deleted = await ctx.channel.purge(limit=limit, check=_is_bot)
        await send_message(ctx, f"Deleted {len(deleted)} bot messages from this channel.")
        
        
        
    @bot.command(name="wrap")
    async def music_wrap(ctx, timeframe: str = "all", user: discord.User = None):
        """Generate a music wrap with analytics and metrics. Usage: wrap [all|month|year] [@user]"""
        await ctx.typing()
        
        try:
            # Parse timeframe
            start_date = None
            end_date = datetime.now()
            timeframe_display = "All Time"
            
            if timeframe.lower() == "month":
                start_date = end_date - timedelta(days=30)
                timeframe_display = "Last 30 Days"
            elif timeframe.lower() == "year":
                start_date = end_date - timedelta(days=365)
                timeframe_display = "Last Year"
            elif timeframe.lower() != "all":
                # Check if first arg is a user mention
                if timeframe.startswith("<@"):
                    # It's actually a user, not a timeframe
                    user = await commands.UserConverter().convert(ctx, timeframe)
                    timeframe = "all"
                    timeframe_display = "All Time"
            
            # Clean up old images before generating new ones
            Analytics.cleanup_old_images()
            
            # Create analytics instance with time filters
            analytics = Analytics(start_date=start_date, end_date=end_date)
            
            if analytics.is_empty():
                return await send_message(ctx, f"No music data available for {timeframe_display.lower()}. Start queuing songs!")

            async def resolve_user_name(user_id: int) -> str:
                member = ctx.guild.get_member(user_id) if ctx.guild else None
                if member:
                    return member.display_name

                cached_user = bot.get_user(user_id)
                if cached_user:
                    return cached_user.name

                try:
                    fetched_user = await bot.fetch_user(user_id)
                    return fetched_user.name
                except Exception:
                    return f"User {user_id}"
            
            # If user specified, show user-specific wrap
            if user:
                user_stats = analytics.get_user_stats(user.id)
                if not user_stats:
                    return await send_message(ctx, f"No data available for {user.mention}")
                
                # Generate user summary image
                await send_message(ctx, f"Generating wrap for {user.mention}...")
                summary_path = analytics.create_user_summary(user.id, user_name=user.name)
                
                # Create embed with user stats
                embed = discord.Embed(
                    title=f"Music Wrap - {user.name} ({timeframe_display})",
                    color=discord.Color.purple(),
                    description="Here's your personalized music wrap!"
                )
                
                total_hours = user_stats['total_duration'] / 3600
                embed.add_field(name="Total Songs", value=f"{user_stats['total_songs']}", inline=True)
                embed.add_field(name="Total Duration", value=f"{total_hours:.1f} hours", inline=True)
                embed.add_field(name="Top Genre", 
                              value=next(iter(user_stats['top_genres'].keys())) if user_stats['top_genres'] else "Unknown", 
                              inline=True)
                
                if user_stats['top_genres']:
                    genres_str = "\n".join([f"{g}: {c}" for g, c in list(user_stats['top_genres'].items())[:5]])
                    embed.add_field(name="Top Genres", value=genres_str, inline=False)
                
                if user_stats['top_songs']:
                    songs_str = "\n".join([f"{s}: {c}" for s, c in list(user_stats['top_songs'].items())[:5]])
                    embed.add_field(name="Top Songs", value=songs_str, inline=False)
                
                # Send summary image
                await send_message(ctx, embed=embed)
                try:
                    with open(summary_path, 'rb') as f:
                        await ctx.channel.send(file=discord.File(f, filename="user_wrap.png"))
                except Exception as e:
                    print(f"Error sending user wrap image: {e}")
                    
            else:
                # Server-wide wrap
                await send_message(ctx, "Generating server-wide wrap... This may take a moment.")

                requester_ids = [int(uid) for uid in analytics.df['requester_id'].dropna().unique().tolist()]
                user_name_map = {}
                for requester_id in requester_ids:
                    user_name_map[requester_id] = await resolve_user_name(requester_id)
                analytics.user_name_map = user_name_map
                
                # Generate all visualization images
                images_to_send = []
                
                # Activity heatmap
                try:
                    heatmap_path = analytics.create_activity_heatmap()
                    images_to_send.append(("Activity Heatmap", heatmap_path))
                except Exception as e:
                    print(f"Error creating heatmap: {e}")
                
                # Top posters
                try:
                    posters_path = analytics.create_top_posters_chart()
                    images_to_send.append(("Top Requesters", posters_path))
                except Exception as e:
                    print(f"Error creating top posters chart: {e}")
                
                # Longest posters
                try:
                    longest_path = analytics.create_longest_posters_chart()
                    images_to_send.append(("Longest Duration", longest_path))
                except Exception as e:
                    print(f"Error creating longest posters chart: {e}")
                
                # Genres
                try:
                    genres_path = analytics.create_genres_chart()
                    images_to_send.append(("Top Genres", genres_path))
                except Exception as e:
                    print(f"Error creating genres chart: {e}")
                
                # Years
                try:
                    years_path = analytics.create_years_chart()
                    images_to_send.append(("Songs by Year", years_path))
                except Exception as e:
                    print(f"Error creating years chart: {e}")
                
                # Most played songs
                try:
                    played_path = analytics.create_most_played_chart()
                    images_to_send.append(("Most Played Songs", played_path))
                except Exception as e:
                    print(f"Error creating most played chart: {e}")
                
                # Create main summary embed
                embed = discord.Embed(
                    title=f"Server Music Wrap ({timeframe_display})",
                    color=discord.Color.gold(),
                    description="Here's your server's music wrap!"
                )
                
                total_songs = len(analytics.df)
                total_duration = analytics.df['duration'].sum() or 0
                total_hours = total_duration / 3600
                
                embed.add_field(name="Total Songs Queued", value=f"{total_songs}", inline=True)
                embed.add_field(name="Total Duration", value=f"{total_hours:.1f} hours", inline=True)
                
                top_posters = analytics.get_top_posters(5)
                if top_posters:
                    posters_str = "\n".join([f"<@{p['user_id']}>: {p['count']} songs" for p in top_posters])
                    embed.add_field(name="Top Requesters", value=posters_str, inline=False)
                
                top_genres = analytics.get_top_genres(5)
                if top_genres:
                    genres_str = "\n".join([f"{g['genre']}: {g['count']}" for g in top_genres])
                    embed.add_field(name="Top Genres", value=genres_str, inline=False)
                
                top_songs = analytics.get_most_played_songs(5)
                if top_songs:
                    songs_str = "\n".join([f"{s['title']}: {s['count']} times" for s in top_songs[:5]])
                    embed.add_field(name="Most Played", value=songs_str, inline=False)
                
                top_years = analytics.get_top_years(3)
                if top_years:
                    years_str = "\n".join([f"{y['year']}: {y['count']} songs" for y in top_years])
                    embed.add_field(name="Top Years", value=years_str, inline=False)
                
                await send_message(ctx, embed=embed)
                
                # Send all generated images
                for title, path in images_to_send:
                    try:
                        with open(path, 'rb') as f:
                            await ctx.channel.send(f"**{title}**", file=discord.File(f, filename=f"{title.lower().replace(' ', '_')}.png"))
                    except Exception as e:
                        print(f"Error sending {title} image: {e}")
                        
        except Exception as e:
            print(f"Error generating wrap: {e}")
            await send_message(ctx, f"Error generating wrap: {e}")

    @bot.command(name="ifuckedup")

    async def restart(ctx):
        """A command to restart the bot. Usage: ifuckedup"""
        import sys
        await send_message(ctx, "Yes, you definitely fucked up.")
        sys.exit(0)

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
            try:
                await message.delete()
            except Exception:
                pass
            # call the play command callback directly, passing the message content as the query
            await bot.get_command("p").callback(ctx, query=message.content)

        except Exception as e:
            print(f"Error handling autoplay message: {e}")

        # Also allow the normal command processing in case the message contained a command.
        await bot.process_commands(message)
