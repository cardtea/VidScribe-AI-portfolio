
import sys
import os
import argparse
import logging

# Configure logging to output to stdout for parent process parsing
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Force stdout to use UTF-8 to avoid UnicodeEncodeError on Windows (cp950)
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

# Add current directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from core.transcriber import Transcriber
except ImportError as e:
    print(f"ERROR: Could not import Transcriber: {e}")
    sys.exit(1)

def progress_callback(progress: float, message: str):
    """Output progress in a format easy for main.py to parse"""
    # Format: PROGRESS:<percent>:<message>
    # Flush stdout to ensure real-time updates
    print(f"PROGRESS:{progress:.2f}:{message}", flush=True)

def main():
    parser = argparse.ArgumentParser(description='Run VidScribe-AI Transcription')
    parser.add_argument('--audio_path', required=True, help='Path to input audio file')
    parser.add_argument('--output_path', required=True, help='Path to save transcript')
    parser.add_argument('--model', default='large-v3', help='Whisper model size')
    parser.add_argument('--device', default='cuda', help='Device (cuda/cpu)')
    parser.add_argument('--language', default=None, help='Language code')
    parser.add_argument('--compute_type', default='int8', help='Compute type')
    parser.add_argument('--beam_size', type=int, default=5, help='Beam size')
    parser.add_argument('--vad', action='store_true', help='Enable VAD filter')

    args = parser.parse_args()

    try:
        print(f"LOG: Initializing Transcriber (Model: {args.model}, Device: {args.device})", flush=True)
        
        transcriber = Transcriber(
            model_size=args.model,
            device=args.device,
            compute_type=args.compute_type,
            beam_size=args.beam_size,
            vad_filter=args.vad
        )

        print(f"LOG: Starting transcription for {os.path.basename(args.audio_path)}", flush=True)
        
        transcriber.transcribe(
            audio_path=args.audio_path,
            output_path=args.output_path,
            language=args.language,
            progress_callback=progress_callback
        )

        print("SUCCESS: Transcription completed successfully", flush=True)
        sys.exit(0)

    except Exception as e:
        print(f"ERROR: Transcription failed: {str(e)}", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
