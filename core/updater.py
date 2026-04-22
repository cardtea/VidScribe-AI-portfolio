import sys
import subprocess
import logging

logger = logging.getLogger(__name__)

def update_ytdlp():
    logger.info("Checking for yt-dlp updates...")
    print("Checking for yt-dlp updates...") # Fallback print
    try:
        # Use the current python executable to ensure we use the venv's pip
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT
        )
        logger.info("yt-dlp update check complete.")
        print("yt-dlp update check complete.")
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to update yt-dlp: {e}")
        print(f"Warning: Failed to update yt-dlp: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error updating yt-dlp: {e}")
        print(f"Warning: Unexpected error updating yt-dlp: {e}")
