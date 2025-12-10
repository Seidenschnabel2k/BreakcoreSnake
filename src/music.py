import time
import asyncio
import discord
import yt_dlp as youtube_dl

from logger import Logger
from utils import is_duplicate


logger = Logger()


# ---------------------------------------
# YT-DLP OPTIONS (SoundCloud-safe)
# ---------------------------------------
ytdl_format_options = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",
    "prefer_ffmpeg": True,
    "geo_bypass": True,

    # SoundCloud stability
    "hls_prefer_native": False,
    "hls_use_mpegts": True,

    "retries": 10,
    "fragment_retries": 10,
    "extractor_retries": 3,
    "skip_unavailable_fragments": True,
}

playlist_ytdl_options = {
    **ytdl_format_options,
    "noplaylist": False,
    "ignoreerrors": True,
    "playlist_items": "1-50",
}


ytdl = youtube_dl.YoutubeDL(ytdl_format_options)
pl_ytdl = youtube_dl.YoutubeDL(playlist_ytdl_options)

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -bufsize 512k",
}
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("webpage_url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()

        # yt-dlp runs blocking, so offload to executor:
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream)
        )

        if "entries" in data:
            data = data["entries"][0]

        # streaming URL (SoundCloud-safe)
        filename = data["url"] if stream else ytdl.prepare_filename(data)

        source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
        return cls(source, data=data)


class MusicPlayer:
    def __init__(self, guild):
        self.guild = guild
        self.queue = []
        self.now_queue = []
        self.current = None
        self.start_time = None
        self.paused_offset = None

    async def add_track(self, query, requester, playlist=False, index=None, prio=False):
        skipped_tracks = []

        extractor = pl_ytdl if playlist else ytdl
        loop = asyncio.get_event_loop()

        data = await loop.run_in_executor(
            None, lambda: extractor.extract_info(query, download=False)
        )

        infos = data["entries"] if "entries" in data else [data]

        for info in infos:
            if is_duplicate(info, [self.queue, self.now_queue]):
                skipped_tracks.append(info)
                continue

            info["requester"] = requester

            if prio:
                self.now_queue.append(info)
            elif index is None:
                self.queue.append(info)
            else:
                self.queue.insert(index, info)

            logger.log_track(info, requester_id=requester.id)

        return infos, skipped_tracks

    async def play_next(self, interactor=None, bot=None):
        if not (self.queue or self.now_queue):
            await bot.change_presence(status=discord.Status.idle)
            return

        vc = self.guild.voice_client

        # Auto-connect if not in VC
        if not vc:
            if interactor and interactor.voice:
                vc = await interactor.voice.channel.connect()
            else:
                return

        # priority first
        if self.now_queue:
            self.current = self.now_queue.pop(0)
        else:
            self.current = self.queue.pop(0)

        self.start_time = time.time()
        self.paused_offset = None

        try:
            # SoundCloud-safe playback (refetch URL)
            source = await YTDLSource.from_url(
                self.current["webpage_url"], loop=bot.loop, stream=True
            )
        except Exception as e:
            print(f"Error preparing audio: {e}")
            return await self.play_next(interactor, bot)

        def after_play(err):
            if err:
                print(f"Playback error: {err}")

            asyncio.run_coroutine_threadsafe(
                self.play_next(interactor, bot), bot.loop
            )

        vc.play(source, after=after_play)
        vc.source = source

        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=source.title
            )
        )

    def clear(self):
        self.now_queue.clear()
        self.queue.clear()

players = {}


def get_player(guild):
    if guild.id not in players:
        players[guild.id] = MusicPlayer(guild)
    return players[guild.id]
