from flask import Flask, render_template, request, jsonify, send_file, abort
import yt_dlp
import os
import uuid
import threading
import time
import re
import shutil
import atexit
from datetime import datetime, timedelta
import logging
from logging.handlers import RotatingFileHandler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import subprocess
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set backend environment
ENV = os.environ.get('BACKEND_ENV', '').upper()
if ENV not in ['PRODUCTION', 'DEVELOPMENT']:
    ENV = 'DEVELOPMENT'

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Set Flask debug mode and config based on environment
if ENV == 'PRODUCTION':
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(days=1)
    )
    debug_mode = False
else:
    debug_mode = True

# FFmpeg startup check
def check_ffmpeg():
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.splitlines()[0]
            print(f"[FFmpeg Check] FFmpeg is available: {version_line}")
        else:
            print("[FFmpeg Check] FFmpeg is not available or returned an error.")
            print(result.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("[FFmpeg Check] FFmpeg executable not found in PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"[FFmpeg Check] Error checking FFmpeg: {e}")
        sys.exit(1)

check_ffmpeg()

# Configure logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('YouTube Downloader startup')

# CORS: allow only frontend origin in production
if os.environ.get('FLASK_ENV') == 'production':
    CORS(app, origins=["https://youtubevideodownloader7751.onrender.com"])  # Set your domain
else:
    CORS(app)

# Rate limiting: 3 downloads per minute per IP (adjust as needed)
limiter = Limiter(get_remote_address, app=app)  # No default_limits
DOWNLOAD_LIMIT = "3 per minute"

# Production settings
if os.environ.get('FLASK_ENV') == 'production':
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(days=1)
    )

progress_data = {}

# Create a temporary directory for downloads
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_downloads')
os.makedirs(TEMP_DIR, exist_ok=True)

# --- Utility Functions ---
def cleanup_old_files():
    """Clean up temp files older than 1 hour or large files sooner"""
    try:
        current_time = datetime.now()
        for filename in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, filename)
            if os.path.exists(file_path):
                file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                file_size = os.path.getsize(file_path)
                # Remove if older than 1 hour or >500MB and older than 10 min
                if (current_time - file_time > timedelta(hours=1)) or \
                   (file_size > 500*1024*1024 and current_time - file_time > timedelta(minutes=10)):
                    try:
                        os.remove(file_path)
                        app.logger.info(f'Cleaned up old file: {filename}')
                    except Exception as e:
                        app.logger.error(f'Error cleaning up file {filename}: {str(e)}')
    except Exception as e:
        app.logger.error(f'Error in cleanup_old_files: {str(e)}')

def cleanup_temp_dir():
    try:
        shutil.rmtree(TEMP_DIR)
        app.logger.info('Cleaned up temp directory on shutdown')
    except Exception as e:
        app.logger.error(f'Error cleaning up temp directory: {str(e)}')

atexit.register(cleanup_temp_dir)

def allowed_youtube_url(url):
    # Basic validation for YouTube URLs
    yt_regex = re.compile(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$")
    return bool(yt_regex.match(url))

threading.Thread(target=lambda: (cleanup_old_files(), time.sleep(3600)), daemon=True).start()

# --- Error Handling ---
@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        code = e.code
        description = e.description
    else:
        code = 500
        description = str(e)
    if app.debug:
        # Show stack trace in development
        import traceback
        return jsonify({"error": description, "trace": traceback.format_exc()}), code
    else:
        # User-friendly error in production
        return jsonify({"error": "An error occurred. Please try again later."}), code

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

# --- Frontend Pages (untouched) ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

# --- API Endpoints ---
@app.route('/api/info', methods=['POST'])
def api_info():
    url = request.json.get('url')
    if not url or not allowed_youtube_url(url):
        return jsonify({'error': 'Invalid or missing YouTube URL.'}), 400
    try:
        ydl_opts = {
            'quiet': True,
            'format': 'bestvideo+bestaudio/best'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            title = info.get('title', 'video')
            thumbnail = info.get('thumbnail', '')
            views = info.get('view_count', 0)
            likes = info.get('like_count', 0)
            comments = info.get('comment_count', 0)

        video_options = []
        audio_options = []
        seen_video_res = set()
        seen_audio_bitrate = set()
        for fmt in formats:
            # File size estimation
            size_bytes = fmt.get('filesize') or fmt.get('filesize_approx')
            if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                # Progressive (video+audio)
                height = fmt.get('height', 0)
                width = fmt.get('width', 0)
                if height and width and height not in seen_video_res:
                    seen_video_res.add(height)
                    entry = {
                        'id': fmt.get('format_id'),
                        'res': f"{width}x{height}",
                        'shorthand': f"{height}p",
                        'height': height,
                        'type': 'progressive'
                    }
                    if size_bytes:
                        entry['size'] = size_bytes
                    video_options.append(entry)
            elif fmt.get('vcodec') != 'none':
                # Video only
                height = fmt.get('height', 0)
                width = fmt.get('width', 0)
                if height and width and height not in seen_video_res:
                    seen_video_res.add(height)
                    entry = {
                        'id': fmt.get('format_id'),
                        'res': f"{width}x{height}",
                        'shorthand': f"{height}p",
                        'height': height,
                        'type': 'video'
                    }
                    if size_bytes:
                        entry['size'] = size_bytes
                    video_options.append(entry)
            elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                # Audio only
                abr = fmt.get('abr', 0)
                if abr and abr not in seen_audio_bitrate:
                    seen_audio_bitrate.add(abr)
                    entry = {
                        'id': fmt.get('format_id'),
                        'abr': abr,
                        'ext': fmt.get('ext', 'm4a'),
                        'type': 'audio'
                    }
                    if size_bytes:
                        entry['size'] = size_bytes
                    audio_options.append(entry)
        video_options.sort(key=lambda x: x['height'], reverse=True)
        audio_options.sort(key=lambda x: x['abr'], reverse=True)
        return jsonify({
            'video_formats': video_options,
            'audio_formats': audio_options,
            'title': title,
            'thumbnail': thumbnail,
            'stats': {
                'views': views,
                'likes': likes,
                'comments': comments
            },
            'url': url
        })
    except Exception as e:
        app.logger.error(f'Failed to fetch formats: {str(e)}')
        return jsonify({'error': 'Failed to fetch video info.'}), 500

@app.route('/api/download', methods=['POST'])
@limiter.limit(DOWNLOAD_LIMIT)
def api_download():
    data = request.json
    url = data.get('url')
    fmt_id = data.get('format_id')
    download_type = data.get('type', 'video')  # 'video' or 'audio'
    title = data.get('title', 'video')
    if not url or not fmt_id or not allowed_youtube_url(url):
        return jsonify({'error': 'Invalid request.'}), 400
    task_id = str(uuid.uuid4())[:8]
    progress_data[task_id] = {
        'progress': 0,
        'status': 'downloading',
        'type': download_type,
        'title': title
    }
    def download_job():
        try:
            temp_video = os.path.join(TEMP_DIR, f'{task_id}_video')
            temp_audio = os.path.join(TEMP_DIR, f'{task_id}_audio')
            output_file = os.path.join(TEMP_DIR, f'{task_id}_output.mp4')
            ydl_opts = {
                'quiet': True,
                'outtmpl': temp_video,
                'format': fmt_id,
                'progress_hooks': [lambda d: update_progress(task_id, d)]
            }
            if download_type == 'audio':
                ydl_opts['outtmpl'] = temp_audio
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if download_type == 'video':
                # Download best audio
                with yt_dlp.YoutubeDL({'quiet': True, 'outtmpl': temp_audio, 'format': 'bestaudio'}) as ydl:
                    ydl.download([url])
                # Merge with ffmpeg
                ffmpeg_cmd = [
                    'ffmpeg', '-y',
                    '-i', temp_video,
                    '-i', temp_audio,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-strict', 'experimental',
                    output_file
                ]
                subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                progress_data[task_id]['file'] = output_file
                # Cleanup temp video/audio
                try:
                    os.remove(temp_video)
                    os.remove(temp_audio)
                except Exception:
                    pass
            else:
                # Audio only
                progress_data[task_id]['file'] = temp_audio
            progress_data[task_id]['progress'] = 100
            progress_data[task_id]['status'] = 'completed'
        except Exception as e:
            progress_data[task_id]['error'] = str(e)
            progress_data[task_id]['status'] = 'error'
            app.logger.error(f'Error in download job: {str(e)}')
    def update_progress(task_id, d):
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            if total > 0:
                progress = (downloaded / total) * 80  # 80% for download, 20% for merge
                progress_data[task_id]['progress'] = round(progress, 1)
        elif d['status'] == 'finished':
            progress_data[task_id]['progress'] = 80
    threading.Thread(target=download_job).start()
    return jsonify({'task_id': task_id})

@app.route('/api/progress/<task_id>')
def api_progress(task_id):
    if task_id not in progress_data:
        return jsonify({'error': 'Invalid task ID'}), 404
    data = progress_data[task_id]
    if 'error' in data:
        return jsonify({'error': data['error'], 'status': 'error'})
    return jsonify({
        'progress': data['progress'],
        'status': data.get('status', 'downloading')
    })

@app.route('/api/file/<task_id>')
def api_file(task_id):
    if task_id not in progress_data:
        return jsonify({'error': 'Invalid task ID'}), 404
    data = progress_data[task_id]
    if 'error' in data:
        return jsonify({'error': data['error']}), 400
    if 'file' not in data or not os.path.exists(data['file']):
        return jsonify({'error': 'File not ready yet.'}), 400
    try:
        filename = f"{data['title']}" + (".mp4" if data['type'] == 'video' else ".m4a")
        response = send_file(
            data['file'],
            as_attachment=True,
            download_name=filename
        )
        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(data['file']):
                    os.remove(data['file'])
                del progress_data[task_id]
                app.logger.info(f'Cleaned up file for task: {task_id}')
            except Exception as e:
                app.logger.error(f'Error cleaning up file: {str(e)}')
        return response
    except Exception as e:
        app.logger.error(f'Error serving file: {str(e)}')
        return jsonify({'error': 'Failed to serve file.'}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    host = "0.0.0.0"
    print(f"Starting server on {host}:{port} in {ENV} mode")
    app.logger.info(f"Starting server on {host}:{port} in {ENV} mode")
    app.run(debug=debug_mode, host=host, port=port)
