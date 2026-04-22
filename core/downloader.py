import yt_dlp
import os
import logging

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def download(self, url: str) -> dict:
        """
        Downloads video/audio from the given URL.
        Prioritizes manual subtitles over automatic ones, with language preference.
        Gracefully handles subtitle download failures (HTTP 429, 403, etc.) by falling back to audio.
        Returns a dictionary with paths to the downloaded files.
        """
        logger.info(f"Starting download for URL: {url}")
        
        # Common options
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'restrictfilenames': True,
        }

        result = {
            'audio_path': None,
            'subtitle_path': None,
            'title': None,
            'id': None,
            'subtitle_error': None  # Track subtitle errors
        }

        try:
            # 1. Extract Info first to get title and sanitize it
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                raw_title = info_dict.get('title', 'Unknown Title')
                video_id = info_dict.get('id', 'Unknown ID')
                
                # SANITIZE TITLE HERE
                from utils.file_handler import FileHandler
                safe_title = FileHandler.sanitize_filename(raw_title)
                result['title'] = safe_title
                result['id'] = video_id
                logger.info(f"Video found: {safe_title}")

            # Define output template with sanitized title
            out_tmpl = os.path.join(self.output_dir, f"{safe_title}.%(ext)s")
            
            # 2. Try to download subtitles ONLY (no audio yet)
            # This allows us to catch subtitle errors without failing the entire download
            subtitle_opts = ydl_opts.copy()
            subtitle_opts.update({
                'outtmpl': out_tmpl,
                'skip_download': True,  # Don't download video/audio yet
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['zh-TW', 'zh-Hant', 'zh.*', 'en.*', 'ja.*', 'orig'],
                'subtitlesformat': 'vtt',
                'ignoreerrors': True,  # Don't crash on subtitle errors
            })
            
            subtitle_success = False
            try:
                with yt_dlp.YoutubeDL(subtitle_opts) as ydl:
                    ydl.download([url])
                    subtitle_success = True
            except Exception as e:
                # Catch subtitle-specific errors (429, 403, etc.)
                error_msg = str(e)
                if '429' in error_msg or 'Too Many Requests' in error_msg:
                    result['subtitle_error'] = 'HTTP 429 (Too Many Requests)'
                    logger.warning(f"Subtitle download blocked (HTTP 429). Will fallback to audio.")
                elif '403' in error_msg or 'Forbidden' in error_msg:
                    result['subtitle_error'] = 'HTTP 403 (Forbidden)'
                    logger.warning(f"Subtitle download forbidden (HTTP 403). Will fallback to audio.")
                else:
                    result['subtitle_error'] = 'Unknown error'
                    logger.warning(f"Subtitle download failed: {e}. Will fallback to audio.")
            
            # 3. Check if subtitles were actually downloaded
            priority_langs = ['zh-TW', 'zh-Hant', 'zh', 'en', 'ja']
            vtt_path = None
            
            if subtitle_success:
                for lang in priority_langs:
                    candidate = os.path.join(self.output_dir, f"{safe_title}.{lang}.vtt")
                    if os.path.exists(candidate):
                        vtt_path = candidate
                        logger.info(f"Found subtitle: {lang}")
                        break
                
                # If no priority lang found, try to find any VTT
                if not vtt_path:
                    import glob
                    all_vtts = glob.glob(os.path.join(self.output_dir, f"{safe_title}.*.vtt"))
                    if all_vtts:
                        vtt_path = all_vtts[0]
                        logger.info(f"Found subtitle: {os.path.basename(vtt_path)}")
            
            # 4. Convert VTT to clean TXT if found
            if vtt_path:
                from utils.text_cleaner import vtt_to_clean_txt
                txt_path = os.path.join(self.output_dir, f"{safe_title}_subtitle.txt")
                vtt_to_clean_txt(vtt_path, txt_path)
                result['subtitle_path'] = txt_path
                logger.info(f"Converted subtitle to clean TXT: {txt_path}")
            else:
                # No subtitles found - we'll need audio
                logger.info("No subtitles available. Proceeding to audio download.")
            
            # 5. Download Audio (always, as fallback or for archival)
            audio_opts = ydl_opts.copy()
            audio_opts.update({
                'outtmpl': out_tmpl,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
            
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                ydl.download([url])
            
            # Find the audio file
            audio_filename = os.path.join(self.output_dir, f"{safe_title}.mp3")
            if os.path.exists(audio_filename):
                result['audio_path'] = audio_filename
                logger.info(f"Audio downloaded: {audio_filename}")

            return result

        except Exception as e:
            logger.error(f"Critical download error: {e}")
            raise e
