import os
import pandas as pd
from datetime import datetime


class Logger:
    def __init__(self, log_dir="log", filename="music_log.parquet"):
        self.log_dir = log_dir
        self.log_file = os.path.join(self.log_dir, filename)
        os.makedirs(self.log_dir, exist_ok=True)
        self.columns = [
            "title",
            "url",
            "requester_id",
            "genre",
            "upload_date",
            "duration",
            "played_at",
        ]
        if not os.path.exists(self.log_file):
            pd.DataFrame(columns=self.columns).to_parquet(
                self.log_file, index=False)

    def _normalize_info(self, info_dict: dict, requester_id: int) -> dict:
        """
        Normalize info from YouTube or SoundCloud to a common schema.
        """
        # Genre: SoundCloud has genre, YouTube may have tags
        genre = info_dict.get("genre")
        if not genre:
            tags = info_dict.get("tags") or []
            genre = tags[0] if tags else None

        # Upload date: YouTube: upload_date (YYYYMMDD), SoundCloud: release_date
        upload_date = info_dict.get(
            "upload_date") or info_dict.get("release_date")
        if upload_date:
            if len(str(upload_date)) == 8:  # YouTube YYYYMMDD
                upload_date = f"{
                    str(upload_date)[:4]}-{str(upload_date)[4:6]}-{str(upload_date)[6:]}"
        else:
            upload_date = None

        title = info_dict.get("title") or "Unknown Title"
        url = info_dict.get("webpage_url") or info_dict.get(
            "url") or "Unknown URL"
        duration = info_dict.get("duration")  # in seconds

        return {
            "title": title,
            "url": url,
            "requester_id": requester_id,
            "genre": genre,
            "upload_date": upload_date,
            "duration": duration,
            "played_at": datetime.now(),
        }

    def log_track(self, info_dict: dict, requester_id: int):
        """
        Append a track to the Parquet log.
        """
        row = self._normalize_info(info_dict, requester_id)
        df = pd.read_parquet(self.log_file)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df.to_parquet(self.log_file, index=False)


if __name__ == "__main__":
    # Path to your log file
    log_file = "log/music_log.parquet"

    # Load the Parquet file into a DataFrame
    df = pd.read_parquet(log_file)

    # Display the first few rows
    print(df.tail())
