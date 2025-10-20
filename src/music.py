import time
import asyncio
import discord
import yt_dlp as youtube_dl
from src.logger import Logger
from src.utils import is_duplicate

logger = Logger()

ffmpeg_options = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
ytdl_format_options = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",
    "prefer_ffmpeg": True,
    "geo_bypass": True,
}
playlist_ytdl_options = {**ytdl_format_options, "noplaylist": False, "ignoreerrors": True}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
pl_ytdl = youtube_dl.YoutubeDL(playlist_ytdl_options)


class MusicPlayer:
    def __init__(self, guild):
        self.guild = guild
        self.queue = []
        self.current = None
        self.start_time = None

    async def add_track(self, query, requester, playlist=False):
        skipped_tracks = []
        
        loop = asyncio.get_event_loop()
        extractor = pl_ytdl if playlist else ytdl
        data = await loop.run_in_executor(None, lambda: extractor.extract_info(query, download=False))
        infos = data["entries"] if "entries" in data else [data]
        for info in infos:
            if is_duplicate(info, self.queue):
                skipped_tracks.append(info)
                continue
            info["requester"] = requester
            self.queue.append(info)
            logger.log_track(info, requester_id=requester.id)
        return infos, skipped_tracks

    async def play_next(self, interactor=None, bot=None):
        if not self.queue:
            await bot.change_presence(activity=None)
            return
        vc = self.guild.voice_client
        if not vc:
            if interactor and interactor.voice:
                vc = await interactor.voice.channel.connect()
            else:
                return
        self.current = self.queue.pop(0)
        self.start_time = time.time()
        source = discord.FFmpegPCMAudio(self.current["url"], **ffmpeg_options)
        wrapped = discord.PCMVolumeTransformer(source, volume=0.5)
        wrapped.data = self.current
        wrapped.start_time = self.start_time

        def after_play(err):
            if err:
                print(f"Playback error: {err}")
            asyncio.run_coroutine_threadsafe(self.play_next(interactor, bot), bot.loop)

        vc.play(wrapped, after=after_play)
        vc.source = wrapped
        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name=self.current['title'])
        )

    def clear(self):
        self.queue.clear()


players = {}
def get_player(guild):
    if guild.id not in players:
        players[guild.id] = MusicPlayer(guild)
    return players[guild.id]
