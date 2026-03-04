import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import glob

# Configure matplotlib for better looking output
sns.set_style("whitegrid")
sns.set_context("talk")  # Larger fonts for better readability
plt.rcParams['figure.facecolor'] = 'white'
plt.rcParams['axes.facecolor'] = 'white'
plt.rcParams['font.size'] = 12
plt.rcParams['axes.labelsize'] = 14
plt.rcParams['axes.titlesize'] = 16
plt.rcParams['xtick.labelsize'] = 11
plt.rcParams['ytick.labelsize'] = 11
plt.rcParams['legend.fontsize'] = 11
plt.rcParams['figure.titlesize'] = 18
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3


class Analytics:
    def __init__(
        self,
        log_file: str = "log/music_log.parquet",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_name_map: Optional[Dict[int, str]] = None,
    ):
        self.log_file = log_file
        self.df = None
        self.start_date = start_date
        self.end_date = end_date
        self.user_name_map = user_name_map or {}
        self.load_data()

    def load_data(self):
        """Load the parquet file into a DataFrame and apply time filters."""
        if os.path.exists(self.log_file):
            self.df = pd.read_parquet(self.log_file)
            # Ensure played_at is datetime
            self.df['played_at'] = pd.to_datetime(self.df['played_at'])
            
            # Apply time filters if specified
            if self.start_date:
                self.df = self.df[self.df['played_at'] >= self.start_date]
            if self.end_date:
                self.df = self.df[self.df['played_at'] <= self.end_date]
        else:
            self.df = pd.DataFrame()

    def is_empty(self) -> bool:
        """Check if there's any data to analyze."""
        return self.df.empty or len(self.df) == 0

    def _get_user_display_name(self, user_id: int, fallback: Optional[str] = None) -> str:
        """Resolve a readable display name for a requester ID."""
        if fallback:
            return fallback
        if user_id in self.user_name_map and self.user_name_map[user_id]:
            return self.user_name_map[user_id]
        return f"User {user_id}"
    
    @staticmethod
    def cleanup_old_images(output_dir: str = "visualizations"):
        """Delete all existing images in the visualizations directory."""
        if os.path.exists(output_dir):
            image_files = glob.glob(os.path.join(output_dir, "*.png"))
            for img_file in image_files:
                try:
                    os.remove(img_file)
                except Exception as e:
                    print(f"Error deleting {img_file}: {e}")

    # ============================================================
    # METRICS CALCULATION
    # ============================================================

    def get_most_active_hour(self) -> Tuple[int, int]:
        """Get the hour when most songs were posted."""
        if self.is_empty():
            return (0, 0)
        hour_counts = self.df['played_at'].dt.hour.value_counts()
        if hour_counts.empty:
            return (0, 0)
        top_hour = hour_counts.idxmax()
        return (top_hour, hour_counts.max())

    def get_top_posters(self, limit: int = 10) -> List[Dict]:
        """Get users who posted the most songs."""
        if self.is_empty():
            return []
        top = self.df['requester_id'].value_counts().head(limit)
        return [{"user_id": uid, "count": count} for uid, count in top.items()]

    def get_longest_posters(self, limit: int = 10) -> List[Dict]:
        """Get users who posted the longest total duration."""
        if self.is_empty():
            return []
        user_durations = self.df.groupby('requester_id')['duration'].sum().sort_values(ascending=False).head(limit)
        return [{"user_id": uid, "duration": dur} for uid, dur in user_durations.items()]

    def get_top_genres(self, limit: int = 10) -> List[Dict]:
        """Get the most posted genres."""
        if self.is_empty():
            return []
        genres = self.df[self.df['genre'].notna()]['genre'].value_counts().head(limit)
        return [{"genre": g, "count": c} for g, c in genres.items()]

    def get_top_years(self, limit: int = 10) -> List[Dict]:
        """Get the years from which most songs were posted."""
        if self.is_empty():
            return []
        self.df['upload_year'] = pd.to_datetime(self.df['upload_date'], errors='coerce').dt.year
        years = self.df[self.df['upload_year'].notna()]['upload_year'].value_counts().head(limit).sort_index(ascending=False)
        return [{"year": int(y), "count": c} for y, c in years.items()]

    def get_most_played_songs(self, limit: int = 10) -> List[Dict]:
        """Get the songs that got played the most."""
        if self.is_empty():
            return []
        songs = self.df['title'].value_counts().head(limit)
        return [{"title": title, "count": count} for title, count in songs.items()]

    def get_user_stats(self, user_id: int) -> Dict:
        """Get detailed stats for a specific user."""
        user_df = self.df[self.df['requester_id'] == user_id]
        if user_df.empty:
            return {}
        
        total_duration = user_df['duration'].sum() or 0
        return {
            "user_id": user_id,
            "total_songs": len(user_df),
            "total_duration": total_duration,
            "top_genres": self.df[self.df['requester_id'] == user_id]['genre'].value_counts().head(5).to_dict(),
            "top_songs": user_df['title'].value_counts().head(5).to_dict(),
        }

    # ============================================================
    # VISUALIZATION FUNCTIONS
    # ============================================================

    def create_activity_heatmap(self, output_path: str = "visualizations/heatmap.png") -> str:
        """Create a heatmap of when most songs were posted (hour of day x day of week)."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if self.is_empty():
            fig, ax = plt.subplots(figsize=(14, 7))
            ax.text(0.5, 0.5, "No data available", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path

        # Create pivot table for heatmap
        self.df['hour'] = self.df['played_at'].dt.hour
        self.df['day_of_week'] = self.df['played_at'].dt.dayofweek
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        heatmap_data = self.df.pivot_table(
            index='day_of_week',
            columns='hour',
            values='title',
            aggfunc='count',
            fill_value=0
        )
        
        fig, ax = plt.subplots(figsize=(18, 8))
        sns.heatmap(
            heatmap_data, 
            cmap='RdYlGn_r', 
            annot=True, 
            fmt='g', 
            cbar_kws={'label': 'Songs Posted'},
            ax=ax,
            linewidths=0.5,
            linecolor='gray',
            annot_kws={'fontsize': 10, 'fontweight': 'bold'}
        )
        ax.set_yticklabels([days[int(i.get_text())] if i.get_text() else '' for i in ax.get_yticklabels()], rotation=0, fontsize=13)
        ax.set_xticklabels(ax.get_xticklabels(), fontsize=11)
        ax.set_xlabel('Hour of Day', fontsize=15, fontweight='bold')
        ax.set_ylabel('Day of Week', fontsize=15, fontweight='bold')
        ax.set_title('Activity Heatmap: When Are Songs Posted?', fontsize=18, fontweight='bold', pad=20)
        
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return output_path

    def create_top_posters_chart(self, output_path: str = "visualizations/top_posters.png", limit: int = 10) -> str:
        """Create a bar chart of top posters."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if self.is_empty():
            fig, ax = plt.subplots(figsize=(14, 7))
            ax.text(0.5, 0.5, "No data available", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path

        top_posters = self.df['requester_id'].value_counts().head(limit)
        
        fig, ax = plt.subplots(figsize=(14, 8))
        colors = plt.cm.viridis(range(len(top_posters)))
        bars = ax.barh(range(len(top_posters)), top_posters.values, color=colors, edgecolor='black', linewidth=1.2)
        ax.set_yticks(range(len(top_posters)))
        ax.set_yticklabels([self._get_user_display_name(uid) for uid in top_posters.index], fontsize=13)
        ax.set_xlabel('Number of Songs', fontsize=15, fontweight='bold')
        ax.set_title('Top Song Requesters', fontsize=18, fontweight='bold', pad=20)
        ax.invert_yaxis()
        ax.grid(axis='x', alpha=0.3)
        
        # Add value labels on bars
        for i, (bar, value) in enumerate(zip(bars, top_posters.values)):
            ax.text(value + max(top_posters.values) * 0.01, i, f' {int(value)}', 
                   va='center', fontsize=12, fontweight='bold')
        
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return output_path

    def create_longest_posters_chart(self, output_path: str = "visualizations/longest_posters.png", limit: int = 10) -> str:
        """Create a bar chart of users who posted the longest total duration."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if self.is_empty():
            fig, ax = plt.subplots(figsize=(14, 7))
            ax.text(0.5, 0.5, "No data available", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path

        user_durations = self.df.groupby('requester_id')['duration'].sum().sort_values(ascending=False).head(limit)
        
        # Convert to hours for better readability
        hours = user_durations / 3600
        
        fig, ax = plt.subplots(figsize=(14, 8))
        colors = plt.cm.plasma(range(len(hours)))
        bars = ax.barh(range(len(hours)), hours.values, color=colors, edgecolor='black', linewidth=1.2)
        ax.set_yticks(range(len(hours)))
        ax.set_yticklabels([self._get_user_display_name(uid) for uid in hours.index], fontsize=13)
        ax.set_xlabel('Total Hours', fontsize=15, fontweight='bold')
        ax.set_title('Users with Longest Total Duration', fontsize=18, fontweight='bold', pad=20)
        ax.invert_yaxis()
        ax.grid(axis='x', alpha=0.3)
        
        # Add value labels on bars
        for i, (bar, value) in enumerate(zip(bars, hours.values)):
            ax.text(value + max(hours.values) * 0.01, i, f' {value:.1f}h', 
                   va='center', fontsize=12, fontweight='bold')
        
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return output_path

    def create_genres_chart(self, output_path: str = "visualizations/genres.png", limit: int = 15) -> str:
        """Create a pie chart of top genres."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if self.is_empty():
            fig, ax = plt.subplots(figsize=(14, 9))
            ax.text(0.5, 0.5, "No data available", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path

        genres = self.df[self.df['genre'].notna()]['genre'].value_counts().head(limit)
        
        if genres.empty:
            fig, ax = plt.subplots(figsize=(14, 9))
            ax.text(0.5, 0.5, "No genre data available", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path
        
        fig, ax = plt.subplots(figsize=(14, 9))
        colors = plt.cm.tab20(range(len(genres)))
        wedges, texts, autotexts = ax.pie(
            genres.values, 
            labels=genres.index, 
            autopct='%1.1f%%', 
            colors=colors, 
            startangle=90,
            textprops={'fontsize': 12},
            wedgeprops={'edgecolor': 'white', 'linewidth': 2}
        )
        ax.set_title('Top Genres', fontsize=18, fontweight='bold', pad=20)
        
        # Make percentage text more readable
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(11)
        
        # Adjust label font
        for text in texts:
            text.set_fontsize(12)
            text.set_fontweight('bold')
        
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return output_path

    def create_years_chart(self, output_path: str = "visualizations/years.png") -> str:
        """Create a bar chart of songs by upload year."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if self.is_empty():
            fig, ax = plt.subplots(figsize=(16, 7))
            ax.text(0.5, 0.5, "No data available", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path

        self.df['upload_year'] = pd.to_datetime(self.df['upload_date'], errors='coerce').dt.year
        years = self.df[self.df['upload_year'].notna()]['upload_year'].value_counts().sort_index(ascending=False).head(20)
        
        if years.empty:
            fig, ax = plt.subplots(figsize=(16, 7))
            ax.text(0.5, 0.5, "No year data available", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path
        
        fig, ax = plt.subplots(figsize=(16, 8))
        colors = plt.cm.coolwarm(range(len(years)))
        bars = ax.bar(range(len(years)), years.values, color=colors, edgecolor='black', linewidth=1.2)
        ax.set_xticks(range(len(years)))
        ax.set_xticklabels([int(y) for y in years.index], rotation=45, fontsize=12)
        ax.set_ylabel('Number of Songs', fontsize=15, fontweight='bold')
        ax.set_xlabel('Release Year', fontsize=15, fontweight='bold')
        ax.set_title('Songs by Release Year', fontsize=18, fontweight='bold', pad=20)
        ax.grid(axis='y', alpha=0.3)
        
        # Add value labels on bars
        for bar, value in zip(bars, years.values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + max(years.values) * 0.01,
                   f'{int(value)}', ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return output_path

    def create_most_played_chart(self, output_path: str = "visualizations/most_played.png", limit: int = 15) -> str:
        """Create a bar chart of most played songs."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        if self.is_empty():
            fig, ax = plt.subplots(figsize=(16, 9))
            ax.text(0.5, 0.5, "No data available", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path

        songs = self.df['title'].value_counts().head(limit)
        
        fig, ax = plt.subplots(figsize=(16, 10))
        colors = plt.cm.Spectral(range(len(songs)))
        bars = ax.barh(range(len(songs)), songs.values, color=colors, edgecolor='black', linewidth=1.2)
        ax.set_yticks(range(len(songs)))
        # Truncate long titles
        labels = [title[:60] + "..." if len(title) > 60 else title for title in songs.index]
        ax.set_yticklabels(labels, fontsize=12)
        ax.set_xlabel('Times Played', fontsize=15, fontweight='bold')
        ax.set_title('Most Played Songs', fontsize=18, fontweight='bold', pad=20)
        ax.invert_yaxis()
        ax.grid(axis='x', alpha=0.3)
        
        # Add value labels on bars
        for i, (bar, value) in enumerate(zip(bars, songs.values)):
            ax.text(value + max(songs.values) * 0.01, i, f' {int(value)}', 
                   va='center', fontsize=12, fontweight='bold')
        
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return output_path

    def create_user_summary(self, user_id: int, output_path: str = None, user_name: str = None) -> str:
        """Create a comprehensive summary image for a specific user."""
        if output_path is None:
            output_path = f"visualizations/user_{user_id}_summary.png"
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        display_name = self._get_user_display_name(user_id, fallback=user_name)
        
        user_df = self.df[self.df['requester_id'] == user_id]
        if user_df.empty:
            fig, ax = plt.subplots(figsize=(14, 8), facecolor='white')
            ax.text(0.5, 0.5, f"No data for {display_name}", ha='center', va='center', fontsize=20, color='#666')
            ax.axis('off')
            fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            return output_path

        total_songs = len(user_df)
        total_duration = user_df['duration'].sum() or 0
        top_genre = user_df[user_df['genre'].notna()]['genre'].value_counts().index[0] if not user_df[user_df['genre'].notna()].empty else "Unknown"
        
        fig = plt.figure(figsize=(16, 11), facecolor='white')
        gs = fig.add_gridspec(3, 2, hspace=0.35, wspace=0.3)
        
        # Title
        fig.suptitle(f'{display_name} - Music Wrap Summary', fontsize=20, fontweight='bold')
        
        # Stats boxes
        ax_stats = fig.add_subplot(gs[0, :])
        ax_stats.axis('off')
        
        hours = total_duration / 3600
        stats_text = f"Total Songs: {total_songs} | Total Duration: {hours:.1f}h | Top Genre: {top_genre}"
        ax_stats.text(0.5, 0.5, stats_text, ha='center', va='center', fontsize=14, fontweight='bold',
                 bbox=dict(boxstyle='round', facecolor='#87CEEB', alpha=0.8, edgecolor='black', linewidth=2))
        
        # Top genres
        ax_genres = fig.add_subplot(gs[1, 0])
        genres = user_df[user_df['genre'].notna()]['genre'].value_counts().head(8)
        if not genres.empty:
            colors = plt.cm.Set3(range(len(genres)))
            bars = ax_genres.barh(range(len(genres)), genres.values, color=colors, edgecolor='black', linewidth=1)
            ax_genres.set_yticks(range(len(genres)))
            ax_genres.set_yticklabels(genres.index, fontsize=11, fontweight='bold')
            ax_genres.set_xlabel('Count', fontsize=12, fontweight='bold')
            ax_genres.set_title('Top Genres', fontweight='bold', fontsize=14)
            ax_genres.invert_yaxis()
            ax_genres.grid(axis='x', alpha=0.3)
        
        # Top songs
        ax_songs = fig.add_subplot(gs[1, 1])
        songs = user_df['title'].value_counts().head(8)
        if not songs.empty:
            colors = plt.cm.Paired(range(len(songs)))
            bars = ax_songs.barh(range(len(songs)), songs.values, color=colors, edgecolor='black', linewidth=1)
            ax_songs.set_yticks(range(len(songs)))
            labels = [title[:35] + "..." if len(title) > 35 else title for title in songs.index]
            ax_songs.set_yticklabels(labels, fontsize=10, fontweight='bold')
            ax_songs.set_xlabel('Times Queued', fontsize=12, fontweight='bold')
            ax_songs.set_title('Top Songs', fontweight='bold', fontsize=14)
            ax_songs.invert_yaxis()
            ax_songs.grid(axis='x', alpha=0.3)
        
        # Activity by day of week
        ax_dow = fig.add_subplot(gs[2, 0])
        dow = user_df['played_at'].dt.dayofweek.value_counts().sort_index()
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        colors = plt.cm.rainbow(range(len(dow)))
        bars = ax_dow.bar([days[int(d)] for d in dow.index], dow.values, color=colors, edgecolor='black', linewidth=1.2)
        ax_dow.set_ylabel('Songs', fontsize=12, fontweight='bold')
        ax_dow.set_title('Activity by Day', fontweight='bold', fontsize=14)
        ax_dow.grid(axis='y', alpha=0.3)
        # Add value labels on top of bars
        for i, (bar, val) in enumerate(zip(bars, [dow.get(i, 0) for i in range(7)])):
            if val > 0:
                ax_dow.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{int(val)}',
                           ha='center', va='bottom', fontweight='bold', fontsize=10)
        
        # Activity by hour
        ax_hour = fig.add_subplot(gs[2, 1])
        hour = user_df['played_at'].dt.hour.value_counts().sort_index()
        ax_hour.plot(hour.index, hour.values, marker='o', linewidth=3, markersize=8, color='#E74C3C')
        ax_hour.fill_between(hour.index, hour.values, alpha=0.4, color='#E74C3C')
        ax_hour.set_xlabel('Hour of Day', fontsize=12, fontweight='bold')
        ax_hour.set_ylabel('Songs', fontsize=12, fontweight='bold')
        ax_hour.set_title('Activity by Hour', fontweight='bold', fontsize=14)
        ax_hour.set_xlim(0, 23)
        ax_hour.grid(alpha=0.3)
        
        fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return output_path


if __name__ == "__main__":
    analytics = Analytics()
    print(f"Top posters: {analytics.get_top_posters(5)}")
    print(f"Top genres: {analytics.get_top_genres(5)}")
    print(f"Most played songs: {analytics.get_most_played_songs(5)}")
