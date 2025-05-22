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
                        
                        if self.search_subtitles(cleaned,root,file):
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

    def search_subtitles(self, media_info, root, file, retry_count=0):
        """Search for subtitles on subdl.com"""
        MAX_RETRIES = 4
        base_query = media_info['title']
        
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
                    return self.get_subtitle_link(media_url, media_info, root, file)    
                else:
                    print("No media matches found", flush=True)
            else:
                print("No media matches found", flush=True)
                return False               
        except Exception as e:
            print(f"Error searching for {media_info['title']}: {e}")
            return False

    def get_subtitle_link(self, media_url, media_info, root, file):
        """Get subtitle link from a specific media url"""
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

    def download_and_extract_subtitle(self, subtitle_url, media_info, output_folder, file):
        """
        Downloads a .zip file from the URL and extracts all files.
        If zip contains exactly one .srt file, saves it with the video filename.
        If zip contains multiple files, extracts all to a 'temp' subfolder.
        """
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


if __name__ == "__main__":
    finder = SubtitleFinder()
    finder.find_missing_subtitles()
