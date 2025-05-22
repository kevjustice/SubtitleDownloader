# Subtitle Downloader

This was a fun little project that saves me a few click in Kodi.  It goes through a library of video files recursively and searches subdl.com for any subtitles.  It downloads them, extracts them, renames them to the same name as the video file, and cleans up after itself.

Why did I do this?  Yes, it's a timesaver...but...  I wanted to see how well I could use Aider and other AI tools to help me do this.  Some of the code it came up with was much more robust than I would have.  It was a neat experiment!

## 🔧 Installation

```bash
# Clone the repository
git clone https://github.com/kevjustice/SubtitleDownloader

# Go into the folder
cd SubtitleDownloader

# (Optional) Set up a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# edit the config.ini to put the path to your video files.
<your-editor> config.ini

# Run!
python subtitle_finder.py
```

## 📄 License
This project is licensed under Beerware [https://en.wikipedia.org/wiki/Beerware](https://en.wikipedia.org/wiki/Beerware)

## 🙋‍♂️ Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss.

## 📬 Contact
Kevin Justice - kevin@matice.com
GitHub: @kevjustice

## LLMS USED:
Deepseek Coder (in Aider)
OpenAI ChatGPT4.o (through Chatbox)
Claude 3.7 (through Chatbox)
