import os
import re
import configparser
import requests
import zipfile
import tempfile
import shutil
import json
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
        
        # List to track shows that need better names
        self.shows_to_lookup = set()
        
        # Load show name mappings from file
        self.show_name_mappings = self.load_show_name_mappings()

    def load_show_name_mappings(self):
        """Load show name mappings from file"""
        mappings_file = 'show_name_mappings.json'
        if os.path.exists(mappings_file):
            try:
                with open(mappings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading show name mappings: {e}")
                return {}
        return {}

    def save_show_name_mappings(self):
        """Save show name mappings to file"""
        mappings_file = 'show_name_mappings.json'
        try:
            with open(mappings_file, 'w', encoding='utf-8') as f:
                json.dump(self.show_name_mappings, f, indent=2, ensure_ascii=False)
            print(f"Saved {len(self.show_name_mappings)} show name mappings to {mappings_file}")
        except Exception as e:
            print(f"Error saving show name mappings: {e}")

    def get_official_show_name(self, show_title):
        """Get the official show name from TVmaze API"""
        try:
            query = quote(show_title)
            url = f"https://api.tvmaze.com/search/shows?q={query}"
            
            # Use a regular request to avoid throttling our main session
            response = requests.get(url, timeout=10)
            results = response.json()
            
            if results and len(results) > 0:
                show = results[0]['show']
                print(f"TVmaze API: '{show_title}' → '{show['name']}'")
                return {
                    'name': show['name'],
                    'original_name': show.get('original_name', show['name']),
                    'id': show['id'],
                    'url': show['url']
                }
            return None
        except Exception as e:
            print(f"Error getting official show name: {e}")
            return None

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
                    'title': f"{clean_name}",
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
            r'(?:\.|\(|$$|\-)?(\d{3,4}p|WEBRip|BluRay|WEB-DL|WEBDL|HDRip|DVDRip|'
            r'x264|x265|H265|H256|HEVC|AAC5\.1|DTS-HD|Atmos|DDP5|Remux|MeGusta|d3g|'
            r'(?:PPV\.)?[HP]DTV|(?:HD)?CAM|B[LR]\.Rip|WEB|h264|YTS|Copy|10Bit|mkv|mp4|m4v|'
            r'AC3|DTS|DD5\.1|AC3\.5\.1|AC3\.2\.0|AAC|DTS-HD|TrueHD|BluRay\.Rip|'
            r'\d{1,2}\.\d{1,2}|\d{1,2}bit|1080p|2160p)(?:\.|\)|$$|\-)?',
            '', text, flags=re.IGNORECASE
        )
        
        # Remove content in brackets/parentheses
        text = re.sub(r'[$$\(].*?[$$\)]', '', text)
        
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
                            # Check if we have a better name for this show
                            original_title = cleaned['show_title']
                            if original_title.lower() in self.show_name_mappings:
                                better_name = self.show_name_mappings[original_title.lower()]['name']
                                print(f"  Using mapped show name: '{better_name}' (was: '{original_title}')")
                                cleaned['show_title'] = better_name
                                cleaned['title'] = f"{better_name} S{cleaned['season']}E{cleaned['episode']}"
                            
                            if self.search_tv_subtitles(cleaned, root, file):
                                downloaded += 1
                            else:
                                failed += 1
                        else:
                            failed += 1
        
        # After processing all files, look up any shows that need better names
        if self.shows_to_lookup:
            print("\nLooking up official names for TV shows...")
            for show_title in self.shows_to_lookup:
                # Skip if we already have this mapping
                if show_title.lower() in self.show_name_mappings:
                    continue
                    
                # Query TVmaze API
                show_info = self.get_official_show_name(show_title)
                if show_info:
                    self.show_name_mappings[show_title.lower()] = show_info
                    print(f"Added mapping: '{show_title}' → '{show_info['name']}'")
            
            # Save updated mappings
            self.save_show_name_mappings()
        
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
            print(f"Error searching for {media_info['title']}: {e}", flush=True)
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
            print(f"Error getting subtitle list: {e}", flush=True)
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
                            print("First English subtitle download link:", zip_link["href"], flush=True)
                            return self.download_movie_subtitle(zip_link, media_info, root, file)
                        else:
                            print("No download link found in English section.", flush=True)
                        break
                    
            except Exception as e:
                print(f"Error finding subtitle page for {media_info['title']}: {e}", flush=True)
                return False        
        else:
            print("No subtitle URL found.", flush=True)
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
            print("Downloading:", subtitle_url["href"], flush=True)
            response = requests.get(subtitle_url["href"], stream=True)
            response.raise_for_status()  # Raise error if download fails
            with open(zip_path, "wb") as f:
                f.write(response.content)
            print(f"Saved subtitle zip: {zip_path}", flush=True)

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
                    
                    print(f"Successfully downloaded subtitle: {new_file_path}", flush=True)
                    print(f"Selected largest .srt file: {largest_srt} ({max_size} bytes)", flush=True)
                    shutil.rmtree(temp_extract_folder)
                else:
                    print("No .srt files found in the zip archive", flush=True)

            # Clean up zip file after successful extraction
            if os.path.exists(zip_path):
                os.remove(zip_path)
                print(f"Removed zip file: {zip_path}", flush=True)
            return True
        
        except Exception as e:
            print(f"Error downloading subtitle: {e}", flush=True)
            # Clean up zip file if it exists
            if os.path.exists(zip_path):
                os.remove(zip_path)
                print(f"Removed zip file: {zip_path}", flush=True)
            return False


    def search_tv_subtitles(self, media_info, root, file):
        """Search for TV show subtitles on subdl.com"""
        # Search using just the show name (without season/episode)
        base_query = media_info['show_title']
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
                    
                    # Check if this is an ad redirect page
                    if "subdl.com/ads" in show_url:
                        print("No subtitles found for this show (ad redirect page detected)", flush=True)
                        # Add this show to our lookup list
                        self.shows_to_lookup.add(media_info['show_title'])
                        print(f"Added '{media_info['show_title']}' to shows that need better names")
                        return False
                    
                    return self.get_tv_season_subtitles(show_url, media_info, root, file)
            
            print("No matching TV show found", flush=True)
            # Add this show to our lookup list
            self.shows_to_lookup.add(media_info['show_title'])
            print(f"Added '{media_info['show_title']}' to shows that need better names")
            return False
            
        except Exception as e:
            print(f"Error searching for TV show: {e}", flush=True)
            return False

    def get_tv_season_subtitles(self, show_url, media_info, root, file):
        """Get subtitles for a specific TV season"""
        try:
            response = self.throttled_get(show_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the season we need
            season_number = int(media_info['season'])  # Converts "02" to 2
            season_str = f"Season {season_number}"
            
            for a_tag in soup.find_all('a', href=True):
                if season_str.lower() in a_tag.get_text(separator=" ", strip=True).lower():
                    episode_page = f"{self.base_url}{a_tag['href']}"
                    print(f"Found {season_str}:", episode_page, flush=True)
                    return self.get_tv_episode_subtitles(episode_page, media_info, root, file)
            
            print(f"No subtitles found for {season_str}", flush=True)
            return False
                        
        except Exception as e:
            print(f"Error getting season subtitles: {e}", flush=True)
            return False   
            
    def get_tv_episode_subtitles(self, show_url, media_info, root, file):
        """Get subtitles for a specific TV season"""
        try:
            response = self.throttled_get(show_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Step 1: Find the English section
            english_section = None
            language_headers = soup.find_all("div", class_="flex items-center gap-2")

            for header in language_headers:
                if "English" in header.get_text():
                    english_section = header.find_parent("div", class_="flex flex-col mt-4 select-none")
                    break

            if not english_section:
                print("English section not found.")
                return False

            # Step 2: Look for episode-specific links
            # Create multiple search patterns for the episode
            season = media_info['season'].zfill(2)  # Ensure 2 digits (e.g., "01" instead of "1")
            episode = media_info['episode'].zfill(2)  # Ensure 2 digits

            # Different episode format patterns to search for
            search_patterns = [
                f"S{season}E{episode}",       # S01E01
                f"S{season}xE{episode}",      # S01xE01
                f"S{season}x{episode}",       # S01x01
                f"{season}x{episode}",        # 01x01
                f"S{season}{episode}",        # S0101
                f"Season {season} Episode {episode}",  # Season 01 Episode 01
                f"Season{season}Episode{episode}",     # Season01Episode01
                f"E{episode}",                # E01 (if we're already in the right season section)
                f"Ep{episode}",               # Ep01
                f"Ep {episode}",              # Ep 01
                f"Episode {episode}",         # Episode 01
                f"Episode{episode}"           # Episode01
            ]

            episode_link = None
            season_link = None

            # Look for links containing any of our episode patterns
            for a in english_section.find_all("a", href=True):
                text = a.get_text().strip()
                
                # Check if any of our patterns match
                if any(pattern.lower() in text.lower() for pattern in search_patterns):
                    # Found a link with our episode number
                    print(f"Found matching episode text: '{text}'")
                    parent_li = a.find_parent('li')
                    if parent_li:
                        # Look for zip download link in this list item
                        for download_a in parent_li.find_all('a', href=True):
                            if download_a['href'].endswith('.zip'):
                                episode_link = download_a['href']
                                break
                    if episode_link:
                        break
            
            # If no episode-specific link, look for season links
            if not episode_link:
                season_number = media_info['season']
                season_number_no_pad = str(int(season_number))  # Converts "02" to "2"

                season_keywords = [
                    f"S{season_number}",
                    f"Season.{season_number}",
                    f"Season {season_number}",
                    f"Season{season_number}",
                    f"Season.{season_number_no_pad}",
                    f"Season {season_number_no_pad}",
                    f"Season{season_number_no_pad}"
                ]
                
                for a in english_section.find_all("a", href=True):
                    text = a.get_text()
                    if any(keyword in text for keyword in season_keywords):
                        parent_li = a.find_parent('li')
                        if parent_li:
                            for download_a in parent_li.find_all('a', href=True):
                                if download_a['href'].endswith('.zip'):
                                    season_link = download_a['href']
                                    break
                        if season_link:
                            break

            # Result
            if episode_link:
                episode_link = f"{episode_link}"
                print(f"Found episode-specific subtitle: {episode_link}", flush=True)
                return self.download_tv_subtitle({'href': episode_link}, media_info, root, file)
            elif season_link:
                season_link = f"{season_link}"
                print(f"Found full season subtitle package: {season_link}", flush=True)
                return self.download_tv_subtitle({'href': season_link}, media_info, root, file)
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

            # Get the download URL, ensuring it's properly formatted
            download_url = subtitle_url["href"]
            print(f"Download URL: {download_url}", flush=True)

            
            # Download the zip file
            print(f"Downloading: {download_url}", flush=True)
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            with open(zip_path, "wb") as f:
                f.write(response.content)
            print(f"Saved subtitle zip: {zip_path}", flush=True)
            
            # Create multiple search patterns for the episode
            season = media_info['season'].zfill(2)  # Ensure 2 digits
            episode = media_info['episode'].zfill(2)  # Ensure 2 digits

            # Different episode format patterns to search for
            episode_patterns = [
                f"S{season}E{episode}",       # S01E01
                f"S{season}xE{episode}",      # S01xE01
                f"S{season}x{episode}",       # S01x01
                f"{season}x{episode}",        # 01x01
                f"S{season}{episode}",        # S0101
                f"Season {season} Episode {episode}",  # Season 01 Episode 01
                f"Season{season}Episode{episode}",     # Season01Episode01
                f"E{episode}",                # E01
                f"Ep{episode}",               # Ep01
                f"Ep {episode}",              # Ep 01
                f"Episode {episode}",         # Episode 01
                f"Episode{episode}"           # Episode01
            ]

            # Extract the zip file
            temp_extract_folder = tempfile.mkdtemp()
            success = False
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:

                # Find files matching any of our patterns
                matching_files = []
                for filename in zip_ref.namelist():
                    if filename.lower().endswith('.srt'):
                        # Check if any pattern matches this filename
                        if any(pattern.lower() in filename.lower() for pattern in episode_patterns):
                            matching_files.append(filename)
                            print(f"Found matching subtitle file: {filename}")

                if matching_files:
                    # Sort by file size (largest first) if there are multiple matches
                    matching_files.sort(key=lambda f: zip_ref.getinfo(f).file_size, reverse=True)
                    srt_file = matching_files[0]
                    
                    # Extract the file to temp folder
                    zip_ref.extract(srt_file, temp_extract_folder)
                    
                    # Move the file to final destination
                    original_path = os.path.join(temp_extract_folder, srt_file)
                    new_path = os.path.join(output_folder, os.path.splitext(file)[0] + ".english.srt")
                    shutil.move(original_path, new_path)
                    
                    print(f"Successfully extracted episode subtitle: {new_path}", flush=True)
                    success = True
                else:
                    print("No episode-specific subtitle found in package", flush=True)
            
            # Close the zipfile before trying to remove it
            # Clean up temp folder
            try:
                shutil.rmtree(temp_extract_folder)
            except Exception as e:
                print(f"Warning: Could not remove temp folder: {e}")
                
            # Now try to remove the zip file
            try:
                os.remove(zip_path)
                print(f"Removed zip file: {zip_path}")
            except Exception as e:
                print(f"Warning: Could not remove zip file: {e}")
                
            return success
                    
        except Exception as e:
            print(f"Error downloading TV subtitle: {e}")
            # Try to clean up even if there was an error
            try:
                if 'temp_extract_folder' in locals() and os.path.exists(temp_extract_folder):
                    shutil.rmtree(temp_extract_folder)
            except:
                pass
            return False

if __name__ == "__main__":
    finder = SubtitleFinder()
    finder.find_missing_subtitles()
