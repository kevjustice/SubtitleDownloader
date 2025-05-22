import os
import re
import configparser
import requests
import zipfile
import tempfile
import shutil
from bs4 import BeautifulSoup
from urllib.parse import quote

class SubtitleFinder:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read('config.ini')
        self.base_url = "https://subdl.com"
        self.session = requests.Session()
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        self.current_ua = 0
        self.update_headers()
        self.last_request_time = 0

    def update_headers(self):
        """Rotate user agent and update session headers"""
        headers = {
            'User-Agent': self.user_agents[self.current_ua],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': self.base_url,
            'DNT': '1'
        }
        self.session.headers.update(headers)
        self.current_ua = (self.current_ua + 1) % len(self.user_agents)

    def throttled_get(self, url):
        """Make request with rate limiting and header rotation"""
        import time
        # Add delay between requests (2-5 seconds)
        elapsed = time.time() - self.last_request_time
        if elapsed < 3:
            time.sleep(3 - elapsed)
        
        self.update_headers()
        response = self.session.get(url)
        self.last_request_time = time.time()
        
        # Random delay after request (1-3 seconds)
        time.sleep(1 + (time.time() % 2))
        return response

    def clean_filename(self, filename):
        """Clean filename to extract title and year/episode info"""
        # Remove file extension
        clean_name = os.path.splitext(filename)[0]
        
        # First check if this is a TV show by looking for S##E## pattern
        episode_match = re.search(r'(?:^|\b)[Ss](\d{1,3})[Ee](\d{1,3})\b', clean_name)
        
        if episode_match:
            # This is a TV show - split into show title and episode title
            season, episode = episode_match.groups()
            parts = re.split(r'[Ss]\d{1,3}[Ee]\d{1,3}', clean_name)
            show_title = parts[0].strip()
            episode_title = parts[1] if len(parts) > 1 else ""
            
            # Clean show title
            show_title = self._clean_common_patterns(show_title)
            
            # Clean episode title
            episode_title = self._clean_common_patterns(episode_title)
            
            return {
                'type': 'tv',
                'show_title': show_title,
                'episode_title': episode_title,
                'season': season,
                'episode': episode,
                'title': f"{show_title} S{season}E{episode}"  # Full title for display
            }
        else:
            # This is a movie - handle normally
            year_match = re.search(r'\b(19|20)\d{2}\b', clean_name)
            year = year_match.group(0) if year_match else None
            
            clean_name = self._clean_common_patterns(clean_name)
            
            if year:
                return {
                    'type': 'movie',
                    'title': f"{clean_name} {year}",
                    'year': year
                }
            else:
                return {
                    'type': 'movie',
                    'title': clean_name,
                    'year': None
                }

    def _clean_common_patterns(self, text):
        """Helper to clean common patterns from text"""
        if not text:
            return ""
            
        # Remove common unwanted patterns
        text = re.sub(
            r'(?:\.|\(|\[|\-)?(\d{3,4}p|WEBRip|BluRay|WEB-DL|WEBDL|HDRip|DVDRip|'
            r'x264|x265|H265|H256|HEVC|AAC5\.1|DTS-HD|Atmos|DDP5|Remux|MeGusta|d3g|'
            r'(?:PPV\.)?[HP]DTV|(?:HD)?CAM|B[LR]\.Rip|WEB|h264|YTS|Copy|10Bit|mkv|avi|mp4|m4v|'
            r'AC3|DTS|DD5\.1|AC3\.5\.1|AC3\.2\.0|AAC|DTS-HD|TrueHD|BluRay\.Rip|'
            r'\d{1,2}\.\d{1,2}|\d{1,2}bit|1080p|2160p)(?:\.|\)|\]|\-)?',
            '', text, flags=re.IGNORECASE
        )
        
        # Remove content in brackets/parentheses
        text = re.sub(r'[\[\(].*?[\]\)]', '', text)
        
        # Normalize special characters and spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'[\-.]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
            

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
                    
                    print(f"\nFound video file: {file_path}", flush=True)
                    
                    # Check for existing subtitles
                    for sub_file in files:
                        if (sub_file.startswith(base_name) and 
                            (sub_file.endswith('.srt') or 
                             sub_file.endswith('.english.srt'))):
                            sub_found = True
                            has_subtitles += 1
                            print(f"Subtitle already exists: {sub_file}", flush=True)
                            break
                    
                    if not sub_found:
                        print("No matching subtitle found - searching...", flush=True)
                        cleaned = self.clean_filename(file)
                        # Print cleaned results and search
                        print(f"  Cleaned title: {cleaned['title']}", flush=True)
                        if cleaned.get('year'):
                            print(f"  Detected year: {cleaned['year']}", flush=True)
                        if cleaned['type'] == 'tv':
                            print(f"  Season: {cleaned['season']}, Episode: {cleaned['episode']}", flush=True)
                        
                        if cleaned['type'] == 'movie':
                            if self.search_movie_subtitles(cleaned, root, file):
                                downloaded += 1
                            else:
                                failed += 1
                        elif cleaned['type'] == 'tv':
                            if self.search_tv_subtitles(cleaned, root, file):
                                downloaded += 1
                            else:
                                failed += 1
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

    def search_movie_subtitles(self, media_info, root, file, retry_count=0):
        """Search for movie subtitles on subdl.com"""
        base_query = f"{media_info['title']} {media_info.get('year', '')}"
        
        # Clean and format the query for URL
        query = base_query.strip().replace(' ', '%20').lower()
        query = re.sub(r'-+', '-', query)  # Remove duplicate dashes
        query = quote(query)
        search_url = f"{self.base_url}/search/{query}"
        print(f"Searching URL: {search_url}", flush=True)
        
        print(f"Searching subtitles for: {media_info['title']}", flush=True)
        
        try:
            response = self.throttled_get(search_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Step 1: Find the <h3> tag containing "Matches"
            matches_h3 = soup.find("h3", string=lambda text: text and text.strip().startswith("Matches"))

            # Step 2: Find the first <a> tag after this <h3>
            if matches_h3:
                first_a  = matches_h3.find_next("a", href=True)
                media_url = f"{self.base_url}{first_a["href"]}" if first_a else None
                if media_url:
                    print(f"Fetching subtitle list from: {media_url}", flush=True)
                    
                    # Check for ad redirect (indicates no subtitles available)
                    if "subdl.com/ads" in media_url:
                        print("No subtitles found for this title (ad redirect page detected)", flush=True)
                        return False
                    
                    # Now get subtitles list from the media-specific page
                    return self.get_movie_subtitle_link(media_url, media_info, root, file)    
                else:
                    print("No media matches found", flush=True)
            else:
                print("No media matches found", flush=True)
                return False               
        except Exception as e:
            print(f"Error searching for {media_info['title']}: {e}")
            return False

    def get_movie_subtitle_link(self, media_url, media_info, root, file):
        """Get movie subtitle link from a specific media url"""
        try:
            response = self.throttled_get(media_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            zip_link = ""
                   
            title = soup.find('h3').get_text(strip=True)
            subtitle_url = f"{self.base_url}{soup.find('a')['href']}"
            
        except Exception as e:
            print(f"Error getting subtitle list: {e}")
            return False
        
        if subtitle_url:
            print(f"Fetching subtitle page: {subtitle_url}", flush=True)
            try:
                response = self.throttled_get(subtitle_url)
                soup= BeautifulSoup(response.text, 'html.parser')
                
                # Find all language sections
                sections = soup.find_all("div", class_="flex flex-col mt-4 select-none")

                # Loop through each section to find the one containing "English"
                for section in sections:
                    header = section.find("h2")
                    if header and "English" in header.text:
                        print("Found English section")
                        # Found the English section
                        # Now find first link inside it that ends with ".zip"
                        zip_link = section.find("a", href=True, string=None)
                        if not zip_link:
                            zip_link = section.find("a", href=True)
                        while zip_link and ".zip" not in zip_link["href"]:
                            zip_link = zip_link.find_next("a", href=True)
                        
                        if zip_link:
                            print("First English subtitle download link:", zip_link["href"])
                            return self.download_and_extract_subtitle(zip_link, media_info, root, file)
                        else:
                            print("No download link found in English section.")
                        break
                    
            except Exception as e:
                print(f"Error finding subtitle page for {media_info['title']}: {e}")
                return False        
        else:
            print("No subtitle URL found.")
            return False   

    def download_movie_subtitle(self, subtitle_url, media_info, output_folder, file):
        """Download and extract movie subtitle"""
        # Ensure output folder exists
        os.makedirs(output_folder, exist_ok=True)

        # Create zip file path matching video filename
        zip_name = os.path.splitext(file)[0] + ".subtitle.zip"
        zip_path = os.path.join(output_folder, zip_name)

        try:
            # Download the zip file
            print("Downloading:", subtitle_url["href"])
            response = requests.get(subtitle_url["href"], stream=True)
            response.raise_for_status()  # Raise error if download fails
            with open(zip_path, "wb") as f:
                f.write(response.content)
            print(f"Saved subtitle zip: {zip_path}")

            # Extract the zip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_contents = zip_ref.namelist()
                srt_files = [f for f in zip_contents if f.lower().endswith('.srt')]

                # Find largest .srt file by size
                largest_srt = None
                max_size = 0
                for file_info in zip_ref.infolist():
                    if file_info.filename.lower().endswith('.srt'):
                        if file_info.file_size > max_size:
                            max_size = file_info.file_size
                            largest_srt = file_info.filename
                
                if largest_srt:
                    # Extract the largest .srt file
                    temp_extract_folder = tempfile.mkdtemp()
                    zip_ref.extract(largest_srt, temp_extract_folder)
                    
                    original_file_path = os.path.join(temp_extract_folder, largest_srt)
                    base_name = os.path.splitext(file)[0] + ".english.srt"
                    new_file_path = os.path.join(output_folder, base_name)
                    shutil.move(original_file_path, new_file_path)
                    
                    print(f"Successfully downloaded subtitle: {new_file_path}")
                    print(f"Selected largest .srt file: {largest_srt} ({max_size} bytes)")
                    shutil.rmtree(temp_extract_folder)
                else:
                    print("No .srt files found in the zip archive")

            return True
        
        except Exception as e:
            print(f"Error downloading subtitle: {e}")
            return False


    def search_tv_subtitles(self, media_info, root, file):
        """Search for TV show subtitles on subdl.com"""
        # Search using just the show name (without season/episode)
        base_query = media_info['title'].replace(f" S{media_info['season']}E{media_info['episode']}", "")
        query = base_query.strip().replace(' ', '%20').lower()
        query = quote(query)
        search_url = f"{self.base_url}/search/{query}"
        print(f"Searching TV show: {search_url}", flush=True)

        try:
            response = self.throttled_get(search_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the TV show match
            matches_h3 = soup.find("h3", string=lambda text: text and text.strip().startswith("Matches"))
            if matches_h3:
                first_a = matches_h3.find_next("a", href=True)
                if first_a:
                    show_url = f"{self.base_url}{first_a['href']}"
                    print(f"Found TV show page: {show_url}", flush=True)
                    return self.get_tv_season_subtitles(show_url, media_info, root, file)
            
            print("No matching TV show found", flush=True)
            return False
            
        except Exception as e:
            print(f"Error searching for TV show: {e}")
            return False

    def get_tv_season_subtitles(self, show_url, media_info, root, file):
        """Get subtitles for a specific TV season"""
        try:
            response = self.throttled_get(show_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the season we need - try both padded and unpadded season numbers
            season_num = str(int(media_info['season']))  # Remove leading zeros
            season_strs = [
                f"Season {season_num}",  # "Season 2"
                f"Season {media_info['season']}"  # "Season 02"
            ]
            
            season_heading = None
            for season_str in season_strs:
                season_heading = soup.find("h3", string=lambda text: text and season_str in text)
                if season_heading:
                    break
            
            if not season_heading:
                print(f"No subtitles found for {season_str}", flush=True)
                return False
                
            # Find English section
            english_section = None
            for section in season_heading.find_all_next("div", class_="flex flex-col mt-4 select-none"):
                if section.find("h2") and "English" in section.find("h2").text:
                    english_section = section
                    break
                    
            if not english_section:
                print("No English subtitles found for this season", flush=True)
                return False
                
            # Look for episode-specific or full season subtitles
            episode_str = f"S{media_info['season']}E{media_info['episode']}"
            episode_link = None
            season_link = None
            
            for link in english_section.find_all("a", href=True):
                if episode_str in link.text:
                    episode_link = link
                    break
                elif "Season" in link.text:
                    season_link = link
                    
            if episode_link:
                print(f"Found episode-specific subtitle: {episode_link['href']}", flush=True)
                return self.download_tv_subtitle(episode_link, media_info, root, file)
            elif season_link:
                print(f"Found full season subtitle package: {season_link['href']}", flush=True)
                return self.download_tv_subtitle(season_link, media_info, root, file)
            else:
                print("No matching subtitles found for this episode", flush=True)
                return False
                
        except Exception as e:
            print(f"Error getting season subtitles: {e}")
            return False

    def download_tv_subtitle(self, subtitle_url, media_info, output_folder, file):
        """Download and extract TV subtitle (either episode or full season)"""
        try:
            # Create zip file path matching video filename
            zip_name = os.path.splitext(file)[0] + ".subtitle.zip"
            zip_path = os.path.join(output_folder, zip_name)

            # Download the zip file
            print("Downloading:", subtitle_url["href"])
            response = requests.get(subtitle_url["href"], stream=True)
            response.raise_for_status()
            with open(zip_path, "wb") as f:
                f.write(response.content)
            print(f"Saved subtitle zip: {zip_path}")

            # Extract the zip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Look for our specific episode file first
                target_episode = f"S{media_info['season']}E{media_info['episode']}"
                matching_files = [f for f in zip_ref.namelist() 
                                if target_episode.lower() in f.lower() and f.lower().endswith('.srt')]
                
                if matching_files:
                    # Found episode-specific file
                    srt_file = matching_files[0]
                    temp_extract_folder = tempfile.mkdtemp()
                    zip_ref.extract(srt_file, temp_extract_folder)
                    
                    original_path = os.path.join(temp_extract_folder, srt_file)
                    new_path = os.path.join(output_folder, os.path.splitext(file)[0] + ".english.srt")
                    shutil.move(original_path, new_path)
                    
                    print(f"Successfully extracted episode subtitle: {new_path}")
                    shutil.rmtree(temp_extract_folder)
                    return True
                else:
                    # No episode-specific file, check if this was a full season package
                    print("No episode-specific subtitle found in package", flush=True)
                    return False
                    
        except Exception as e:
            print(f"Error downloading TV subtitle: {e}")
            return False
if __name__ == "__main__":
    finder = SubtitleFinder()
    finder.find_missing_subtitles()
