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
        
        # Remove common unwanted patterns and artifacts (including year markers)
        clean_name = re.sub(
            r'(?:\.|\(|\[|\-)?(\d{3,4}p|WEBRip|BluRay|WEB-DL|WEBDL|HDRip|DVDRip|'
            r'x264|x265|H265|H256|HEVC|AAC5\.1|DTS-HD|Atmos|DDP5|Remux|MeGusta|d3g|'
            r'(?:PPV\.)?[HP]DTV|(?:HD)?CAM|B[LR]\.Rip|WEB|h264|YTS|Copy|10Bit|'
            r'\d{1,2}\.\d{1,2}|\d{1,2}bit|1080p|2160p)(?:\.|\)|\]|\-)?',
            '', clean_name, flags=re.IGNORECASE
        )
        
        # Remove all content between brackets/parentheses including the brackets
        clean_name = re.sub(r'[\[\(].*?[\]\)]', '', clean_name)
        
        # Replace remaining special characters and normalize spaces
        clean_name = re.sub(r'[^\w\s]', ' ', clean_name)  # Replace non-alphanum with space
        clean_name = re.sub(r'[\-.]+', ' ', clean_name)    # Replace dashes/dots with space
        clean_name = re.sub(r'\s+', ' ', clean_name)       # Collapse multiple spaces
        clean_name = clean_name.strip()
        
        # Extract year if present (look for years in filename before cleaning)
        year_match = re.search(r'\b(19|20)\d{2}\b', filename)  # Search original filename
        year = year_match.group(1) if year_match else None
        
        # Extract season/episode (for TV shows) - handles S01E01, S1E2, etc formats
        episode_match = re.search(r'(?:^|\b)[Ss](\d{1,3})[Ee](\d{1,3})\b', filename)
        
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
        
        total_files = 0
        has_subtitles = 0
        downloaded = 0
        failed = 0
        
        print(f"\nScanning media folder: {media_path}")
        
        for root, _, files in os.walk(media_path):
            for file in files:
                if file.lower().endswith(video_extensions):
                    total_files += 1
                    base_name = os.path.splitext(file)[0]
                    sub_found = False
                    file_path = os.path.join(root, file)
                    
                    print(f"\nFound video file: {file_path}")
                    
                    # Check for existing subtitles
                    for sub_file in files:
                        if (sub_file.startswith(base_name) and 
                            (sub_file.endswith('.srt') or 
                             sub_file.endswith('.english.srt'))):
                            sub_found = True
                            has_subtitles += 1
                            print(f"✓ Subtitle already exists: {sub_file}")
                            break
                    
                    if not sub_found:
                        print("× No matching subtitle found - searching...")
                        cleaned = self.clean_filename(file)
                        # Print cleaned results without searching
                        print(f"  Cleaned title: {cleaned['title']}")
                        if cleaned.get('year'):
                            print(f"  Detected year: {cleaned['year']}")
                        if cleaned['type'] == 'tv':
                            print(f"  Season: {cleaned['season']}, Episode: {cleaned['episode']}")
                        print("  Skipping search (demo mode)\n")
                        failed += 1
        
        # Print summary
        print("\n" + "="*50)
        print("Subtitle Search Summary:")
        print(f"Total video files found: {total_files}")
        print(f"Files with existing subtitles: {has_subtitles}")
        print(f"Subtitles downloaded: {downloaded}")
        print(f"Files still missing subtitles: {failed}")
        print("="*50 + "\n")

    def search_subtitles(self, media_info):
        """Search for subtitles on subdl.com"""
        # Build search query with appropriate metadata
        if media_info['type'] == 'movie':
            base_query = f"{media_info['title']} {media_info.get('year', '')}"
        else:  # TV show
            base_query = f"{media_info['title']} S{media_info['season']}E{media_info['episode']}"
        
        # Clean and format the query for URL
        query = base_query.strip().replace(' ', '-').lower()
        query = re.sub(r'-+', '-', query)  # Remove duplicate dashes
        query = quote(query)
        search_url = f"{self.base_url}/search/{query}"
        
        print(f"Searching subtitles for: {media_info['title']}")
        
        try:
            response = self.session.get(search_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find subtitle results
            results = soup.find_all('a', href=re.compile(r'/subtitle/'))
            if results:
                print(f"Found {len(results)} potential subtitle(s)")
                best_match = results[0]  # First result is usually best
                subtitle_url = f"{self.base_url}{best_match['href']}"
                return self.download_subtitle(subtitle_url, media_info)
            else:
                print("No subtitles found for this title")
                return False
                
        except Exception as e:
            print(f"Error searching for {media_info['title']}: {e}")
            return False

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
                print(f"✓ Successfully downloaded subtitle: {filename}")
                return True
            else:
                print("× No English subtitle download link found")
                return False
                
        except Exception as e:
            print(f"× Error downloading subtitle: {e}")
            return False

if __name__ == "__main__":
    finder = SubtitleFinder()
    finder.find_missing_subtitles()
