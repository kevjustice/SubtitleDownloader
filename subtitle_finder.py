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
        
        # Extract year if present (look for years in filename before cleaning)
        year_match = re.search(r'\b(19|20)\d{2}\b', filename)  # Find 4-digit years
        year = year_match.group(0) if year_match else None  # Get actual matched text
        if year:
            clean_name = re.sub(r'\b(19|20)\d{2}\b', '', clean_name)  # Remove year from name
        
        
        # Extract season/episode (for TV shows) - handles S01E01, S1E2, etc formats
        episode_match = re.search(r'(?:^|\b)[Ss](\d{1,3})[Ee](\d{1,3})\b', filename)
        season, episode = episode_match.groups() if episode_match else (None, None)
        
        if episode:
            clean_name = re.sub(r'(?:^|\b)[Ss](\d{1,3})[Ee](\d{1,3})\b', '', clean_name)
        
        
        # Remove common unwanted patterns and artifacts (including year markers)
        clean_name = re.sub(
            r'(?:\.|\(|\[|\-)?(\d{3,4}p|WEBRip|BluRay|WEB-DL|WEBDL|HDRip|DVDRip|'
            r'x264|x265|H265|H256|HEVC|AAC5\.1|DTS-HD|Atmos|DDP5|Remux|MeGusta|d3g|'
            r'(?:PPV\.)?[HP]DTV|(?:HD)?CAM|B[LR]\.Rip|WEB|h264|YTS|Copy|10Bit|mkv|avi|mp4|m4v|'
            r'AC3|DTS|DD5\.1|AC3\.5\.1|AC3\.2\.0|AAC|DTS-HD|TrueHD|BluRay\.Rip|'
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
        

        if episode_match:
            season, episode = episode_match.groups()
            return {
                'type': 'tv',
                'title': clean_name.strip('. -'),
                'title': f"{clean_name.strip('. -')} S{season}E{episode}" if episode else clean_name.strip('. -'),
                'season': season,
                'episode': episode
            }
        else:
            if year:
                return {
                    'type': 'movie',
                    'title': f"{clean_name.strip('. -')} {year}" if year else clean_name.strip('. -'),
                    'year': year
                }
            else:
                return {
                    'type': 'unknown',
                    'title': clean_name.strip('. -')
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
                        # Print cleaned results and search
                        print(f"  Cleaned title: {cleaned['title']}")
                        if cleaned.get('year'):
                            print(f"  Detected year: {cleaned['year']}")
                        if cleaned['type'] == 'tv':
                            print(f"  Season: {cleaned['season']}, Episode: {cleaned['episode']}")
                        
                        if self.search_subtitles(cleaned):
                            downloaded += 1
                        else:
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
        #if media_info['type'] == 'movie':
        #    base_query = f"{media_info['title']} {media_info.get('year', '')}"
        #else:  # TV show
        #    base_query = f"{media_info['title']} S{media_info['season']}E{media_info['episode']}"
        base_query = media_info['title']
        
        # Clean and format the query for URL
        query = base_query.strip().replace(' ', '%20').lower()
        query = re.sub(r'-+', '-', query)  # Remove duplicate dashes
        query = quote(query)
        search_url = f"{self.base_url}/search/{query}"
        print(f"Searching URL: {search_url}")
        
        print(f"Searching subtitles for: {media_info['title']}")
        
        try:
            response = self.session.get(search_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find subtitle results in the list
            subtitle_divs = soup.find_all('div', class_='subtitle')
            if not subtitle_divs:
                print("No subtitles found for this title")
                return False

            subtitles = []
            for div in subtitle_divs:
                # Extract subtitle details
                title = div.find('h3').get_text(strip=True)
                language = div.find('img', alt='English')
                if not language:
                    continue  # Skip non-English subtitles
                
                release = div.find('span', class_='release').get_text(strip=True) if div.find('span', class_='release') else ''
                downloads = div.find('div', class_='downloads').get_text(strip=True) if div.find('div', class_='downloads') else '0'
                
                subtitles.append({
                    'title': title,
                    'url': f"{self.base_url}{div.find('a')['href']}",
                    'release': release,
                    'downloads': int(''.join(filter(str.isdigit, downloads)))
                })

            if not subtitles:
                print("No English subtitles found")
                return False

            # Sort by best match (download count + release type match)
            media_type = media_info['type']
            subtitles.sort(key=lambda x: (
                -x['downloads'],
                x['release'].lower() in media_info.get('title', '').lower()
            ), reverse=True)

            print(f"Found {len(subtitles)} English subtitle(s)")
            print(f"Best match: {subtitles[0]['title']} (Downloads: {subtitles[0]['downloads']})")
            return self.download_subtitle(subtitles[0]['url'], media_info)
                
        except Exception as e:
            print(f"Error searching for {media_info['title']}: {e}")
            return False

    def download_subtitle(self, subtitle_url, media_info):
        """Download the subtitle file"""
        try:
            response = self.session.get(subtitle_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find download link in the download button
            download_form = soup.find('form', {'action': lambda x: x and '/download/' in x})
            if not download_form:
                return False
                
            download_url = f"{self.base_url}{download_form['action']}"
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
            
                
        except Exception as e:
            print(f"× Error downloading subtitle: {e}")
            return False

if __name__ == "__main__":
    finder = SubtitleFinder()
    finder.find_missing_subtitles()
