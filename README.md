# Hexxal's YouTube Downloader

A modern, privacy-respecting web app to download YouTube videos and audio in various formats and qualities. Features a beautiful UI, progress tracking, download history (local only), and mobile optimization.

---

## Features
- 🎬 Download videos in multiple resolutions (up to 8K, if available)
- 🎵 Download audio-only with bitrate selection
- ⏳ Real-time progress bar with speed and ETA
- 🕑 Download history (stored only in your browser)
- 📱 Mobile-optimized, responsive design
- 🌓 Dark/Light mode with persistent theme
- 💬 Friendly, user-focused error messages
- 🔒 No server-side tracking or analytics
- 🧹 Automatic cleanup of temporary files

---

## Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/Hexxal7751/Web-Youtube-Video-Downloader.git
cd Web-Youtube-Video-Downloader
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. FFmpeg
- **Windows:** FFmpeg is included and auto-checked on startup.
- **macOS/Linux:** Install FFmpeg via your package manager (e.g., `brew install ffmpeg` or `sudo apt install ffmpeg`).

### 4. Environment Configuration
Create a `.env` file in the project root:
```
BACKEND_ENV=DEVELOPMENT
```
Set to `PRODUCTION` for production mode.

---

## Usage

### Development
```bash
python app.py
```
- Runs in development mode (debug enabled, user-friendly errors).

### Production
```bash
# In your .env, set:
# BACKEND_ENV=PRODUCTION
python app.py
```
- Runs in production mode (secure cookies, no stack traces, user-friendly errors).

---

## API Endpoints
- `POST /api/info` — Get available video/audio formats for a YouTube URL.
- `POST /api/download` — Start a download/merge job, returns `task_id` (rate-limited per minute).
- `GET /api/progress/<task_id>` — Get progress for a job.
- `GET /api/file/<task_id>` — Download the finished file.

---

## Privacy & Data Policy
- **No personal data is collected or stored.**
- **Download history is stored only in your browser (localStorage), never sent to the server.**
- **No analytics or tracking.**
- **Temporary video/audio files are deleted after download or after 1 hour.**

See `/terms` for full Terms of Service and Privacy Policy.

---

## Credits
- Made by Hexxal7751
- Discord: Hexxal#7751 / hexxal.7751
- Email: hexxal.7751@gmail.com

---

## License
This project is for educational and personal use. Please respect YouTube's Terms of Service and copyright laws. 