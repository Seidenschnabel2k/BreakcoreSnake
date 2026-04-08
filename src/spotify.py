import asyncio
import base64
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class SpotifyTrack:
    title: str
    artists: list[str]

    def to_ytmusic_query(self) -> str:
        artist_text = self.artists[0]
        return f"ytsearch1:{self.title} - {artist_text}"


class SpotifyResolver:
    SPOTIFY_URL_RE = re.compile(
        r"(?:https?://)?open\.spotify\.com/(?P<kind>track|album|playlist)/(?P<id>[A-Za-z0-9]+)",
        re.IGNORECASE,
    )

    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def is_spotify_url(self, value: str) -> bool:
        return bool(self.SPOTIFY_URL_RE.search(value or ""))

    def get_url_type(self, value: str) -> str | None:
        match = self.SPOTIFY_URL_RE.search(value or "")
        return match.group("kind").lower() if match else None

    def _extract_kind_and_id(self, value: str) -> tuple[str, str]:
        match = self.SPOTIFY_URL_RE.search(value or "")
        if not match:
            raise ValueError("Not a valid Spotify track/album/playlist URL.")
        return match.group("kind").lower(), match.group("id")

    async def to_youtube_music_query(self, spotify_url: str) -> str:
        kind, item_id = self._extract_kind_and_id(spotify_url)
        if kind != "track":
            raise ValueError("This Spotify URL is not a track. Use playlist command for albums/playlists.")
        track = await self._get_track(item_id)
        return track.to_ytmusic_query()

    async def to_youtube_music_queries(self, spotify_url: str) -> list[str]:
        kind, item_id = self._extract_kind_and_id(spotify_url)
        if kind == "track":
            track = await self._get_track(item_id)
            return [track.to_ytmusic_query()]
        if kind == "album":
            tracks = await self._get_album_tracks(item_id)
            return [track.to_ytmusic_query() for track in tracks]
        if kind == "playlist":
            tracks = await self._get_playlist_tracks(item_id)
            return [track.to_ytmusic_query() for track in tracks]
        raise ValueError("Unsupported Spotify URL type.")

    async def _get_access_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Spotify credentials are missing. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env."
            )

        now = time.time()
        if self._access_token and now < self._token_expires_at:
            return self._access_token

        loop = asyncio.get_event_loop()
        token_data = await loop.run_in_executor(None, self._fetch_access_token_sync)
        self._access_token = token_data["access_token"]
        expires_in = int(token_data.get("expires_in", 3600))
        self._token_expires_at = now + max(60, expires_in - 30)
        return self._access_token

    def _fetch_access_token_sync(self) -> dict[str, Any]:
        credentials = f"{self.client_id}:{self.client_secret}".encode("utf-8")
        auth_header = base64.b64encode(credentials).decode("utf-8")
        data = urlencode({"grant_type": "client_credentials"}).encode("utf-8")

        request = Request(
            "https://accounts.spotify.com/api/token",
            data=data,
            headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    async def _api_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._get_access_token()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._api_get_sync, token, path, params)

    def _api_get_sync(self, token: str, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"https://api.spotify.com/v1/{path}{query}"
        request = Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)

    @staticmethod
    def _to_track(item: dict[str, Any]) -> SpotifyTrack:
        artists = [artist.get("name", "") for artist in item.get("artists", []) if artist.get("name")]
        return SpotifyTrack(title=item.get("name", "Unknown Title"), artists=artists or ["Unknown Artist"])

    async def _get_track(self, track_id: str) -> SpotifyTrack:
        payload = await self._api_get(f"tracks/{track_id}")
        return self._to_track(payload)

    async def _get_album_tracks(self, album_id: str) -> list[SpotifyTrack]:
        tracks: list[SpotifyTrack] = []
        offset = 0

        while True:
            payload = await self._api_get(f"albums/{album_id}/tracks", {"limit": 50, "offset": offset})
            items = payload.get("items", [])
            tracks.extend(self._to_track(item) for item in items)
            if not payload.get("next"):
                break
            offset += len(items)

        return tracks

    async def _get_playlist_tracks(self, playlist_id: str) -> list[SpotifyTrack]:
        tracks: list[SpotifyTrack] = []
        offset = 0

        while True:
            payload = await self._api_get(
                f"playlists/{playlist_id}/tracks",
                {"limit": 100, "offset": offset, "additional_types": "track"},
            )
            items = payload.get("items", [])

            for item in items:
                track = item.get("track")
                if not isinstance(track, dict):
                    continue
                if track.get("is_local"):
                    continue
                tracks.append(self._to_track(track))

            if not payload.get("next"):
                break
            offset += len(items)

        return tracks
