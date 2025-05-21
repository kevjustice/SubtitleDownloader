import os
import re
import configparser
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

class SubtitleFinder:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read('config.ini')
        self.base_url = "https://subdl.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def clean_filename(self, filename):
        """Clean filename to extract title and year/episode info"""
        # Remove file extension
        clean_name = os.path.splitext(filename)[0]
        
        # Common patterns to remove
        patterns = [
            r'\.\d{3,4}p',  # Resolution
            r'\.WEBRip', r'\.BluRay', r'\.x264', r'\.x265',  # Quality
            r'\.\w{2,3}\-?\w{2,3}',  # Audio/video codecs
            r'\[.*?\]', r'\(.*?\)',  # Bracketed text
            r'\.\d{4}\.',  # Year in middle
            r'\.S\d{2}E\d{2}',  # TV episode format
        ]
        
        for pattern in patterns:
            clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
        
        # Extract year if present (for movies)
        year_match = re.search(r'\.(\d{4})\.?$', clean_name)
        year = year_match.group(1) if year_match else None
        
        # Extract season/episode (for TV shows)
        episode_match = re.search(r'S(\d{2})E(\d{2})', filename, re.IGNORECASE)
        
        if episode_match:
            season, episode = episode_match.groups()
            return {
                'type': 'tv',
                'title': clean_name.strip('. -'),
                'season': season,
                'episode': episode
            }
        else:
            return {
                'type': 'movie',
                'title': clean_name.strip('. -'),
                'year': year
            }

    def find_missing_subtitles(self):
        """Find video files missing subtitles"""
        media_path = self.config.get('Settings', 'media_path')
        video_extensions = ('.mp4', '.mkv', '.avi', '.mov')
        
        for root, _, files in os.walk(media_path):
            for file in files:
                if file.lower().endswith(video_extensions):
                    base_name = os.path.splitext(file)[0]
                    sub_found = False
                    
                    # Check for existing subtitles
                    for sub_file in files:
                        if (sub_file.startswith(base_name) and 
                            (sub_file.endswith('.srt') or 
                             sub_file.endswith('.english.srt'))):
                            sub_found = True
                            break
                    
                    if not sub_found:
                        cleaned = self.clean_filename(file)
                        self.search_subtitles(cleaned)

    def search_subtitles(self, media_info):
        """Search for subtitles on subdl.com"""
        query = quote(media_info['title'].replace(' ', '-').lower())
        search_url = f"{self.base_url}/search/{query}"
        
        try:
            response = self.session.get(search_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find subtitle results
            results = soup.find_all('a', href=re.compile(r'/subtitle/'))
            if results:
                best_match = results[0]  # First result is usually best
                subtitle_url = f"{self.base_url}{best_match['href']}"
                self.download_subtitle(subtitle_url, media_info)
                
        except Exception as e:
            print(f"Error searching for {media_info['title']}: {e}")

    def download_subtitle(self, subtitle_url, media_info):
        """Download the subtitle file"""
        try:
            response = self.session.get(subtitle_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find English subtitle download link
            download_link = soup.find('a', href=re.compile(r'/download/'))
            if download_link:
                download_url = f"{self.base_url}{download_link['href']}"
                response = self.session.get(download_url)
                
                # Save subtitle file
                filename = f"{media_info['title']}"
                if media_info['type'] == 'tv':
                    filename += f"_S{media_info['season']}E{media_info['episode']}"
                else:
                    if media_info.get('year'):
                        filename += f"_{media_info['year']}"
                filename += ".english.srt"
                
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"Downloaded subtitle: {filename}")
                
        except Exception as e:
            print(f"Error downloading subtitle: {e}")

if __name__ == "__main__":
    finder = SubtitleFinder()
    finder.find_missing_subtitles()
