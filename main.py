import threading
import queue
import time
import json
import os
import webbrowser
import logging
from nicegui import ui, app
import pystray
from PIL import Image, ImageDraw
import asyncio

# Core Modules
from core.downloader import Downloader
from core.transcriber import Transcriber
from core.summarizer import Summarizer
from core.monitor import Monitor
from utils.logger import setup_logger
from utils.file_handler import FileHandler

# Setup Logger
setup_logger()
logger = logging.getLogger("main")

# --- Pre-launch Update ---
from core.updater import update_ytdlp
update_ytdlp()

# Global State
task_queue = queue.Queue()
running_tasks = [] # List of task dicts
completed_tasks = [] # List of task dicts
system_stats = {"cpu": 0, "ram": 0, "vram": 0}

# Configuration
CONFIG_PATH = "config/settings.json"
PROMPTS_DIR = "config/prompts"

def load_settings():
    """Load settings from JSON file, merge with defaults."""
    default_settings = {
        "api_key": "",
        "model": "gemini-2.5-flash",
        "device": "cuda",
        "output_dir": os.path.join(os.getcwd(), "downloads"),
        "prompt_file": "default.txt",
        "transcription_profile": "fast",
        "transcription_profiles": {
            "fast": {
                "label": "Fast (Large-V3 + Float16 + Beam 3 + VAD)",
                "model_size": "large-v3",
                "compute_type": "float16",
                "beam_size": 3,
                "vad_filter": True
            },
            "balanced": {
                "label": "Balanced (Large-V3 + Float16 + VAD)",
                "model_size": "large-v3",
                "compute_type": "float16",
                "beam_size": 5,
                "vad_filter": True
            },
            "accurate": {
                "label": "Accurate (Large-V3 + Float16 + VAD)",
                "model_size": "large-v3",
                "compute_type": "float16",
                "beam_size": 5,
                "vad_filter": True
            }
        }
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                loaded = json.load(f)
                default_settings.update(loaded)
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    return default_settings

def save_settings(settings):
    with open(CONFIG_PATH, "w") as f:
        json.dump(settings, f, indent=4)

settings = load_settings()

# === Startup Diagnostics ===
logger.info("=" * 60)
logger.info("🚀 VidScribe-AI Starting Up")
logger.info("=" * 60)

# Check CUDA availability
import torch
if torch.cuda.is_available():
    logger.info(f"✅ CUDA Available: {torch.cuda.get_device_name(0)}")
    logger.info(f"   CUDA Version: {torch.version.cuda}")
    logger.info(f"   Total VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
else:
    logger.warning("⚠️ CUDA not available. CPU mode will be used.")

# Check GPU monitoring
from core.monitor import NVML_AVAILABLE
if NVML_AVAILABLE:
    logger.info("✅ GPU monitoring enabled (pynvml)")
else:
    logger.warning("⚠️ GPU monitoring disabled (pynvml not available)")

logger.info("=" * 60)

# --- Worker Thread ---
def worker():
    logger.info("Worker thread started.")
    while True:
        try:
            task = task_queue.get()
            if task is None:
                break
            
            # Timing
            workflow_start = time.time()
            task['start_time'] = workflow_start  # Store for elapsed time display
            
            def log(msg, emoji=""):
                try:
                    timestamp = time.strftime("%H:%M:%S")
                    entry = f"[{timestamp}] {emoji} {msg}" if emoji else f"[{timestamp}] {msg}"
                    task['logs'].append(entry)
                    logger.info(f"[{task['url']}] {msg}")
                except Exception as e:
                    # If logging fails, at least print to console
                    print(f"LOG ERROR: {e} - Message: {msg}")
            
            # Check if this is transcript-only mode
            is_transcript_only = task.get('transcript_only', False)
            
            # Determine total steps dynamically based on workflow
            # With subtitles: 1(Info) + 2(Subtitle) + [3(AI Summary)] + 4(Cleanup) = 3 or 4 steps
            # Without subtitles: 1(Info) + 2(Check) + 3(Audio) + 4(Transcribe) + 5(Save) + [6(AI Summary)] + 7(Cleanup) = 6 or 7 steps
            # We'll update this after checking subtitles
            total_steps = 7 if not is_transcript_only else 6  # Max possible, will adjust later
            current_step = 0
            
            task['status'] = 'Processing'
            task['total_steps'] = total_steps
            task['current_step'] = current_step
            
            def update_progress(step_num, step_name, step_progress=0.0):
                """Update progress in task dict (will be polled by UI timer)"""
                try:
                    task['current_step'] = step_num
                    task['current_step_name'] = step_name
                    task['current_step_progress'] = step_progress
                    
                    # Update overall progress
                    overall = (step_num - 1 + step_progress) / task['total_steps']
                    task['progress'] = overall
                    
                except Exception as e:
                    logger.error(f"Error updating progress: {e}")
            
            # === Step 1: Get Video Info ===
            current_step += 1
            current_step += 1
            log(f"Step {current_step}/?: Fetching Metadata...", "🎯")
            task['status'] = 'Fetching Info'
            update_progress(current_step, "🎯 Fetching Metadata...", 0.0)
            
            downloader = Downloader(settings['output_dir'])
            try:
                download_result = downloader.download(task['url'])
                task['title'] = download_result['title']
                audio_path = download_result['audio_path']
                subtitle_path = download_result['subtitle_path']
                
                log(f"Video Title: {task['title']}", "✅")
                log("High-Speed Mode: Multi-threaded Download + GPU Acceleration + Auto-Save", "🚀")
                update_progress(current_step, "✅ Metadata Fetched", 1.0)
                
            except Exception as e:
                task['status'] = 'Failed (Download)'
                task['error'] = str(e)
                log(f"Download Error: {e}", "❌")
                completed_tasks.append(task)
                running_tasks.remove(task)
                task_queue.task_done()
                continue
            
            # === Step 2: Check Subtitles ===
            current_step += 1
            step_start = time.time()
            log(f"Step {current_step}/?: Checking Subtitles...", "🔍")
            task['status'] = 'Checking Subtitles'
            
            transcript_text = ""
            transcript_source = None
            
            # Check if subtitle download had errors
            if download_result.get('subtitle_error'):
                log(f"Subtitle Failed ({download_result['subtitle_error']}), switching to audio transcription...", "⚠️")
                total_steps = 7  # Need audio + transcribe + save
            elif subtitle_path and os.path.exists(subtitle_path):
                log(f"Subtitle Found: {os.path.basename(subtitle_path)}", "✅")
                try:
                    with open(subtitle_path, 'r', encoding='utf-8') as f:
                        transcript_text = f.read()
                    transcript_source = "subtitle"
                    log(f"Subtitle Loaded ({time.time() - step_start:.1f}s)", "⚡")
                    # If we have subtitles, total steps = 5 (no audio/transcribe/save)
                    total_steps = 5
                    update_progress(current_step, "✅ Subtitle Loaded", 1.0)
                except Exception as e:
                    log(f"Subtitle Read Error: {e}", "⚠️")
                    total_steps = 7
            else:
                log("No subtitles available. Using speech-to-text.", "ℹ️")
                total_steps = 7  # Need audio + transcribe + save
            
            # === Step 3: Download Audio (if needed) ===
            if not transcript_text and audio_path and os.path.exists(audio_path):
                current_step += 1
                step_start = time.time()
                log(f"Step {current_step}/{total_steps}: Downloading Audio (Fallback)...", "🎵")
                task['status'] = 'Audio Ready'
                log("Audio Downloaded", "✅")
                log(f"Audio Time: {time.time() - step_start:.1f}s", "⚡")
                update_progress(current_step, "✅ Audio Ready", 1.0)
            
            # === Step 4: Transcribe (if needed) ===
            if not transcript_text and audio_path and os.path.exists(audio_path):
                current_step += 1
                step_start = time.time()
                log(f"Step {current_step}/{total_steps}: Transcribing (Whisper)...", "🔥")
                task['status'] = 'Transcribing'
                
                # Get Profile
                profile_key = settings.get('transcription_profile', 'fast')
                profiles = settings.get('transcription_profiles', {})
                profile = profiles.get(profile_key, profiles.get('fast'))
                
                # Get Device
                device = settings.get('device', 'cuda')
                
                log(f"Language: Auto-Detect", "🌍")
                log(f"Profile: {profile['label']} on {device}", "⚙️")
                
                transcriber = Transcriber(
                    model_size=profile['model_size'],
                    compute_type=profile['compute_type'],
                    beam_size=profile['beam_size'],
                    vad_filter=profile.get('vad_filter', False),
                    temperature=profile.get('temperature', [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]),
                    device=device
                )
                
                try:
                    temp_transcript_path = os.path.join(settings['output_dir'], "_temp_transcript.txt")
                    
                    # Detect language from title for better transcription accuracy
                    def detect_language_from_title(title):
                        """Simple language detection based on character sets in title"""
                        # Check for Chinese characters (both simplified and traditional)
                        if any('\u4e00' <= char <= '\u9fff' for char in title):
                            return 'zh'
                        # Check for Japanese characters
                        elif any('\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' for char in title):
                            return 'ja'
                        # Check for Korean characters
                        elif any('\uac00' <= char <= '\ud7af' for char in title):
                            return 'ko'
                        # Default to None (auto-detect)
                        return None
                    
                    detected_lang = detect_language_from_title(task['title'])
                    if detected_lang:
                        log(f"Detected Language: {detected_lang}", "🌍")
                    
                    # Define progress callback for transcription
                    def transcribe_progress_callback(progress, message):
                        """Handle transcription progress updates"""
                        try:
                            # Just update the step progress, let update_progress calculate overall
                            update_progress(current_step, message, progress)
                        except Exception as e:
                            logger.error(f"Error in transcribe callback: {e}")
                    
                    # Use detected language as hint, but Whisper will still verify
                    logger.info("DEBUG: About to call transcriber.transcribe()")
                    logger.info(f"DEBUG: audio_path = {audio_path}")
                    logger.info(f"DEBUG: temp_transcript_path = {temp_transcript_path}")
                    logger.info(f"DEBUG: detected_lang = {detected_lang}")
                    
                    try:
                        logger.info("DEBUG: ===== ENTERING INNER TRY BLOCK =====")
                        logger.info("DEBUG: About to call transcriber.transcribe()")
                        logger.info(f"DEBUG: Parameters - audio_path={audio_path}")
                        logger.info(f"DEBUG: Parameters - temp_transcript_path={temp_transcript_path}")
                        logger.info(f"DEBUG: Parameters - language={detected_lang}")
                        
                        # CRITICAL: Do NOT assign return value - causes thread crash
                        # Use subprocess to run transcription in a separate process
                        # This isolates potential crashes (CUDA/Memory/Threading) from the main app
                        import subprocess
                        import sys
                        
                        script_path = os.path.join(os.path.dirname(__file__), "core", "run_transcription.py")
                        
                        cmd = [
                            sys.executable, script_path,
                            '--audio_path', audio_path,
                            '--output_path', temp_transcript_path,
                            '--model', profile.get('model_size', 'large-v3'),
                            '--device', device,
                            '--compute_type', profile.get('compute_type', 'float16'),
                        ]
                        
                        if detected_lang:
                            cmd.extend(['--language', detected_lang])
                            
                        # Add VAD if enabled in settings (assuming true for now as in original code)
                        cmd.append('--vad')
                        
                        logger.info(f"DEBUG: Running transcription subprocess: {' '.join(cmd)}")
                        
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            encoding='utf-8',
                            errors='replace', # CRITICAL: Prevent crash on mixed encoding output
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                        
                        # Read output in real-time
                        while True:
                            output = process.stdout.readline()
                            if output == '' and process.poll() is not None:
                                break
                            if output:
                                line = output.strip()
                                logger.info(f"Subprocess: {line}")
                                
                                # Parse progress
                                if line.startswith("PROGRESS:"):
                                    try:
                                        _, progress_str, msg = line.split(":", 2)
                                        p = float(progress_str)
                                        transcribe_progress_callback(p, msg)
                                    except ValueError:
                                        pass
                                elif line.startswith("ERROR:"):
                                    logger.error(f"Subprocess Error: {line}")
                        
                        # Wait for completion
                        return_code = process.poll()
                        logger.info(f"DEBUG: Subprocess finished with code {return_code}")
                        
                        if return_code != 0:
                            # If file exists and valid, maybe it's fine (crash on exit)
                            if os.path.exists(temp_transcript_path) and os.path.getsize(temp_transcript_path) > 10:
                                logger.warning("Subprocess failed but transcript file exists. Assuming success.")
                            else:
                                raise RuntimeError(f"Transcription subprocess failed with code {return_code}")

                        logger.info("DEBUG: ===== TRANSCRIBER.TRANSCRIBE() RETURNED =====")
                        
                        # Read transcript from file instead of using return value (to avoid crash)
                        logger.info(f"DEBUG: About to read from file: {temp_transcript_path}")
                        logger.info(f"DEBUG: File exists: {os.path.exists(temp_transcript_path)}")
                        
                        if os.path.exists(temp_transcript_path):
                            logger.info("DEBUG: Opening file for reading...")
                            with open(temp_transcript_path, 'r', encoding='utf-8') as f:
                                logger.info("DEBUG: File opened successfully, reading content...")
                                transcript_text = f.read()
                                logger.info(f"DEBUG: Read {len(transcript_text)} characters from file")
                        else:
                            logger.error(f"DEBUG: File does not exist: {temp_transcript_path}")
                            raise FileNotFoundError(f"Transcript file not found: {temp_transcript_path}")
                        
                        logger.info("DEBUG: ===== FILE READ COMPLETED =====")
                        
                    except Exception as transcribe_error:
                        logger.error(f"DEBUG: ===== EXCEPTION CAUGHT IN INNER TRY BLOCK =====")
                        logger.error(f"DEBUG: Exception: {transcribe_error}")
                        logger.error(f"DEBUG: Exception type: {type(transcribe_error)}")
                        import traceback
                        logger.error(f"DEBUG: Traceback:\n{traceback.format_exc()}")
                        raise transcribe_error
                    
                    transcript_source = "whisper"
                    logger.info(f"DEBUG: transcript_text length = {len(transcript_text)} characters")
                    log(f"Transcript Saved: _temp_transcript.txt", "✅")
                    log(f"Transcription Complete ({time.time() - step_start:.1f}s)", "🔥")
                except Exception as e:
                    logger.error(f"Exception in transcription: {e}")
                    task['status'] = 'Failed (Transcribe)'
                    task['error'] = str(e)
                    log(f"Transcribe Error: {e}", "❌")
                    completed_tasks.append(task)
                    running_tasks.remove(task)
                    task_queue.task_done()
                    continue
            
            # === Step 5: Save Transcript Permanently (if from Whisper) ===
            logger.info(f"DEBUG: Entering Step 5 - transcript_source = {transcript_source}")
            if transcript_source == "whisper":
                current_step += 1
                log(f"Step {current_step}/{total_steps}: Saving Transcript...", "💾")
                task['status'] = 'Saving Transcript'
                
                # Create saved_transcripts directory
                saved_dir = os.path.join(settings['output_dir'], "saved_transcripts")
                os.makedirs(saved_dir, exist_ok=True)
                
                safe_title = FileHandler.sanitize_filename(task['title'])
                logger.info(f"DEBUG: Original title = {task['title']}")
                logger.info(f"DEBUG: Sanitized title = {safe_title}")
                saved_transcript_path = os.path.join(saved_dir, f"{safe_title}.txt")
                logger.info(f"DEBUG: Saving to path = {saved_transcript_path}")
                try:
                    with open(saved_transcript_path, 'w', encoding='utf-8') as f:
                        f.write(transcript_text)
                    log(f"Transcript Saved: saved_transcripts/{safe_title}.txt", "💾")
                    logger.info("DEBUG: Transcript save successful")
                except Exception as e:
                    logger.error(f"DEBUG: Transcript save failed - {e}")
                    log(f"Save Transcript Error: {e}", "⚠️")
            
            logger.info(f"DEBUG: Checking transcript_text - exists = {bool(transcript_text)}, length = {len(transcript_text) if transcript_text else 0}")
            if not transcript_text:
                task['status'] = 'Failed (No Media)'
                err_msg = "Could not get text from subtitle or audio."
                task['error'] = err_msg
                log(err_msg, "❌")
                completed_tasks.append(task)
                running_tasks.remove(task)
                task_queue.task_done()
                continue
            
            
            
            # === Step 6: AI Summarization (skip if transcript_only) ===
            logger.info(f"DEBUG: Entering Step 6 - transcript_only = {task.get('transcript_only', False)}")
            if not task.get('transcript_only', False):
                current_step += 1
                step_start = time.time()
                log(f"Step {current_step}/{total_steps}: AI Summarization (Gemini)...", "🤖")
                logger.info("DEBUG: Starting AI Summarization")
                task['status'] = 'Summarizing'
                
                summarizer = Summarizer(settings['api_key'])
                
                # Load Prompt
                prompt_content = ""
                prompt_path = os.path.join(PROMPTS_DIR, settings['prompt_file'])
                if os.path.exists(prompt_path):
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        prompt_content = f.read()
                
                log("Analyzing with Custom Prompt...", "🎯")
                
                # Simulated progress for AI summarization
                import threading
                # Logic Update: Start simulated progress at 70% immediately for better UX
                simulated_progress = {'active': True, 'progress': 0.70}
                api_started = {'value': False}
                
                def simulate_ai_progress():
                    """Simulate progress during AI summarization (70% → 95%)"""
                    iteration = 0
                    # Wait for API to start
                    while not api_started['value'] and iteration < 20:  # Max 10 seconds wait
                        time.sleep(0.5)
                        iteration += 1
                    
                    if not api_started['value']:
                        return
                    
                    iteration = 0
                    while simulated_progress['active'] and simulated_progress['progress'] < 0.95:
                        iteration += 1
                        # Non-linear growth: slower as it approaches 95%
                        current = simulated_progress['progress']
                        increment = (0.95 - current) * 0.01  # Slow increment
                        simulated_progress['progress'] = min(current + increment, 0.95)
                        update_progress(current_step, "🤖 Generating AI Summary...", simulated_progress['progress'])
                        time.sleep(1.0) # Slow update
                
                # Start simulated progress thread
                progress_thread = threading.Thread(target=simulate_ai_progress, daemon=True)
                progress_thread.start()
                
                try:
                    # Define progress callback for summarization
                    def summarize_progress_callback(progress, message):
                        """Handle summarization progress updates"""
                        try:
                            # Mark API as started
                            if not api_started['value']:
                                api_started['value'] = True
                            
                            # Stop simulated progress when real progress comes in at 90%
                            if progress >= 0.9:
                                simulated_progress['active'] = False
                            
                            # Only update progress for significant milestones (0%, 10%, 20%, 90%, 100%)
                            # Let simulated progress handle the middle part
                            if progress < 0.3 or progress >= 0.9:
                                update_progress(current_step, message, progress)
                        except Exception as e:
                            logger.error(f"Error in summarize callback: {e}")
                    
                    summary = summarizer.summarize(
                        transcript_text, 
                        model_name=settings['model'], 
                        prompt_template=prompt_content,
                        progress_callback=summarize_progress_callback
                    )
                    
                finally:
                    # Stop simulated progress
                    simulated_progress['active'] = False
                    if progress_thread.is_alive():
                        progress_thread.join(timeout=1.0)
                
                # Save Summary
                safe_title = FileHandler.sanitize_filename(task['title'])
                summary_path = os.path.join(settings['output_dir'], f"{safe_title}.md")
                summarizer.save_summary(summary, summary_path)
                
                task['summary'] = summary
                log(f"Report Generated: {safe_title}.md", "✅")
                log(f"AI Analysis Time: {time.time() - step_start:.1f}s", "⚡")
                update_progress(current_step, "✅ Analysis Complete", 1.0)
            else:
                log("Skipping AI Summary (Transcript Only)", "ℹ️")
                update_progress(current_step, "ℹ️ AI Summary Skipped", 1.0)
            
            # === Step 7: Cleanup ===
            current_step += 1
            log(f"Step {current_step}/{total_steps}: Cleaning up...", "🧹")
            task['status'] = 'Cleaning Up'
            update_progress(current_step, "🧹 Cleaning up...", 0.0)
            
            # Remove temp audio
            if audio_path and os.path.exists(audio_path) and "_temp" not in audio_path:
                # Only remove if it's the downloaded audio (not a temp file already)
                try:
                    os.remove(audio_path)
                    log(f"Removed: {os.path.basename(audio_path)}", "🗑️")
                except Exception as e:
                    log(f"Cleanup Audio Error: {e}", "⚠️")
            
            # Remove temp transcript
            temp_transcript = os.path.join(settings['output_dir'], "_temp_transcript.txt")
            if os.path.exists(temp_transcript):
                try:
                    os.remove(temp_transcript)
                    log("Removed: _temp_transcript.txt", "🗑️")
                except Exception as e:
                    log(f"Cleanup Transcript Error: {e}", "⚠️")
            
            # Final
            update_progress(current_step, "🧹 Cleanup Complete", 1.0)
            
            # Show 100% completion for 1.5 seconds
            task['status'] = 'Completed'
            task['progress'] = 1.0
            task['current_step_name'] = "✅ Completed"
            time.sleep(1.5)
            
            total_time = time.time() - workflow_start
            log(f"Task Completed! Total Time: {total_time:.1f}s", "✅")
            log("", "")
            
            completed_tasks.append(task)
            running_tasks.remove(task)
            task_queue.task_done()
            
        except Exception as e:
            logger.error(f"Worker error: {e}")
            if 'task' in locals() and task in running_tasks:
                 task['status'] = 'Error'
                 task['error'] = str(e)
                 if 'logs' in task:
                     task['logs'].append(f"❌ Critical Error: {e}")
                 completed_tasks.append(task)
                 running_tasks.remove(task)

# Start Worker
threading.Thread(target=worker, daemon=True).start()

# --- System Tray ---
def create_image():
    """Load the application icon from icon.png"""
    try:
        return Image.open('icon.png')
    except:
        # Fallback to simple generated icon if file not found
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color=(55, 55, 55))
        dc = ImageDraw.Draw(image)
        dc.rectangle([16, 16, 48, 48], fill=(255, 255, 255))
        return image

def on_open_ui(icon, item):
    webbrowser.open('http://localhost:8080')

def on_exit(icon, item):
    icon.stop()
    app.shutdown()

def setup_tray():
    icon = pystray.Icon("VidScribe-AI", create_image(), "VidScribe AI", menu=pystray.Menu(
        pystray.MenuItem("Open Web UI", on_open_ui),
        pystray.MenuItem("Exit", on_exit)
    ))
    icon.run()

# Start Tray in separate thread
threading.Thread(target=setup_tray, daemon=True).start()

# --- UI ---
@ui.page('/')
def index():
    # --- Theme & Styling Setup (Scheme A+C Mix) ---
    # Global CSS for Glassmorphism + Soft Focus
    ui.add_head_html('''
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --glass-border-light: 1px solid rgba(255, 255, 255, 0.5);
                --glass-border-dark: 1px solid rgba(255, 255, 255, 0.08);
            }
            
            body {
                font-family: 'Outfit', sans-serif;
                background-color: #f8fafc; /* Slate 50 */
                transition: background-color 0.3s ease;
            }
            
            body.body--dark {
                background-color: #0f172a; /* Slate 900 */
            }

            /* Ambient Background Glow */
            .ambient-glow {
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                z-index: -1;
                background: 
                    radial-gradient(circle at 15% 50%, rgba(99, 102, 241, 0.08) 0%, transparent 25%),
                    radial-gradient(circle at 85% 30%, rgba(168, 85, 247, 0.08) 0%, transparent 25%);
                pointer-events: none;
            }
            
            /* Glass Component Class */
            .glass-panel {
                background: rgba(255, 255, 255, 0.7);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                border: var(--glass-border-light);
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            }
            
            body.body--dark .glass-panel {
                background: rgba(30, 41, 59, 0.6); /* Slate 800 with opacity */
                border: var(--glass-border-dark);
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            }
            
            /* Smooth Inputs */
            .q-field__native {
                color: inherit !important;
            }
            .body--dark .q-field__label {
                color: #94a3b8 !important; /* Slate 400 */
            }
        </style>
    ''')
    
    # Ambient Background
    ui.element('div').classes('ambient-glow')

    # Dark Mode Control
    dark_mode = ui.dark_mode()
    dark_mode.enable() # Load system preference or saved state

    # State bindings
    url_input = ui.input('Video URL').classes('w-full')
    
    # Load Prompts
    prompts = [f for f in os.listdir(PROMPTS_DIR) if f.endswith('.txt')]
    
    # --- Left Sidebar (Settings) ---
    with ui.left_drawer(value=True).classes('bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-r border-slate-200 dark:border-slate-800 q-pa-md').props('width=320'):
        with ui.row().classes('items-center justify-between w-full q-mb-lg'):
            ui.label('Settings').classes('text-h6 font-bold text-slate-800 dark:text-slate-100')
            # Theme Toggle
            with ui.button(icon='dark_mode', on_click=lambda: dark_mode.toggle()).props('flat round dense').classes('text-slate-600 dark:text-yellow-400'):
                ui.tooltip('Toggle Dark Mode')
        
        # Settings Content
        with ui.column().classes('w-full gap-4'):
            
            # Model Selection
            with ui.column().classes('w-full gap-1'):
                ui.label('Gemini Model').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
                model_options = ['gemini-3.1-pro-preview', 'gemini-3-flash-preview', 'gemini-3-pro-preview']
                if settings['model'] not in model_options:
                    model_options.append(settings['model'])
                
                ui.select(
                    model_options, 
                    value=settings['model'], 
                    label='Select Model',
                    new_value_mode='add-unique'
                ).bind_value(settings, 'model').classes('w-full').props('outlined dense')

            # Profile Selection
            with ui.column().classes('w-full gap-1'):
                ui.label('Transcription Profile').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
                profile_options = {k: v['label'] for k, v in settings['transcription_profiles'].items()}
                ui.select(profile_options, value=settings['transcription_profile'], label='Performance').bind_value(settings, 'transcription_profile').classes('w-full').props('outlined dense')

            # Prompt Template
            with ui.column().classes('w-full gap-1'):
                ui.label('Prompt Template').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
                ui.select(prompts, value=settings['prompt_file'], label='Template').bind_value(settings, 'prompt_file').classes('w-full').props('outlined dense')
            
            # API Key
            with ui.column().classes('w-full gap-1'):
                ui.label('API Key').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
                ui.input('Enter Key', password=True).bind_value(settings, 'api_key').classes('w-full').props('outlined dense rounded')

            # Output Dir
            with ui.column().classes('w-full gap-1'):
                ui.label('Output Directory').classes('text-xs font-bold text-slate-500 uppercase tracking-wider')
                ui.input('Path').bind_value(settings, 'output_dir').classes('w-full').props('outlined dense')

        ui.separator().classes('q-my-lg opacity-50')
        
        # App Control
        with ui.column().classes('w-full mt-auto'):
             def shutdown_app():
                ui.notify('Shutting down...', type='warning')
                app.shutdown()
             ui.button('Exit Application', on_click=shutdown_app, icon='power_settings_new').classes('w-full bg-rose-500/10 text-rose-600 dark:text-rose-400 hover:bg-rose-500/20 shadow-none border border-rose-500/20')

    # --- Right Sidebar (Resources) ---
    with ui.right_drawer(value=True).classes('bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-l border-slate-200 dark:border-slate-800 q-pa-md').props('width=280'):
        ui.label('System Monitor').classes('text-h6 font-bold text-slate-800 dark:text-slate-100 q-mb-lg')
        
        # Monitor Card Style
        def monitor_row(label, value_label, sub_label=None, color_class='text-slate-800 dark:text-slate-200'):
            with ui.row().classes('w-full justify-between items-baseline mb-1'):
                ui.label(label).classes('text-sm text-slate-500 font-medium')
                ui.label(value_label).classes(f'text-base font-bold {color_class}')
            if sub_label:
                ui.label(sub_label).classes('text-xs text-slate-400 text-right w-full mb-3')
            else:
                 ui.element('div').classes('h-2') # spacer

        # CPU
        ui.label('CPU Usage').classes('text-xs font-bold text-slate-500 uppercase tracking-wider mb-2')
        with ui.card().classes('w-full bg-slate-50 dark:bg-slate-800/50 shadow-none border border-slate-200 dark:border-slate-700 p-3 mb-4'):
             sys_cpu_label = ui.label('System: 0%').classes('text-sm font-bold text-slate-700 dark:text-slate-300')
             app_cpu_label = ui.label('App: 0%').classes('text-sm text-blue-500')

        # RAM
        ui.label('Memory (RAM)').classes('text-xs font-bold text-slate-500 uppercase tracking-wider mb-2')
        with ui.card().classes('w-full bg-slate-50 dark:bg-slate-800/50 shadow-none border border-slate-200 dark:border-slate-700 p-3 mb-4'):
            sys_ram_label = ui.label('System: 0%').classes('text-sm font-bold text-slate-700 dark:text-slate-300')
            sys_ram_detail = ui.label('0GB / 0GB').classes('text-xs text-slate-400')
            ui.separator().classes('my-2 opacity-20')
            app_ram_label = ui.label('App: 0GB').classes('text-sm text-purple-500')

        # GPU
        ui.label('GPU Acceleration').classes('text-xs font-bold text-slate-500 uppercase tracking-wider mb-2')
        with ui.card().classes('w-full bg-slate-50 dark:bg-slate-800/50 shadow-none border border-slate-200 dark:border-slate-700 p-3 mb-4'):
             gpu_name_label = ui.label('Checking...').classes('text-xs font-mono text-slate-500 break-all mb-1')
             gpu_load_label = ui.label('Load: 0%').classes('text-sm font-bold text-emerald-500')
             vram_label = ui.label('VRAM: 0GB / 0GB').classes('text-xs text-slate-400 mt-1')

        ui.separator().classes('q-my-lg opacity-50')
        
        # Quick Actions
        ui.label('Quick Actions').classes('text-xs font-bold text-slate-500 uppercase tracking-wider mb-2')
        def open_downloads_folder():
            import subprocess
            output_dir = settings.get('output_dir', 'downloads')
            if os.path.exists(output_dir):
                subprocess.Popen(f'explorer "{output_dir}"')
                ui.notify('Opening downloads folder...', type='info')
            else:
                ui.notify('Downloads folder not found!', type='negative')
        
        ui.button('Open Folders', on_click=open_downloads_folder, icon='folder_open').classes('w-full bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 shadow-none border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700')

    # Initialize monitor
    monitor = Monitor()
    
    def update_stats():
        stats = monitor.get_stats()
        
        # Update CPU
        sys_cpu_label.set_text(f"System: {stats['sys_cpu']:.1f}%")
        app_cpu_label.set_text(f"App: {stats['app_cpu']:.1f}%")
        
        # Update RAM
        sys_ram_label.set_text(f"System: {stats['sys_ram_percent']:.1f}%")
        sys_ram_detail.set_text(f"{stats['sys_ram_used_gb']:.1f}GB / {stats['sys_ram_total_gb']:.1f}GB")
        app_ram_label.set_text(f"App: {stats['app_ram_gb']:.2f}GB")
        
        # Update GPU
        gpu_name_label.set_text(f"{stats['gpu_name']}")
        gpu_load_label.set_text(f"Load: {stats['gpu_load']:.1f}%")
        
        # Update VRAM
        vram_label.set_text(f"{stats['vram_used']:.1f}GB / {stats['vram_total']:.1f}GB")
        
    ui.timer(1.0, update_stats)
    
    # Progress update timer (polls from running tasks)
    last_task_info = {'title': 'No active task', 'status': 'Idle', 'elapsed': '0s', 'progress': 0.0, 'step_name': 'Waiting...', 'step_progress': 0.0}
    
    def update_progress_ui():
        """Update progress UI from running tasks"""
        try:
            if running_tasks:
                # Get the first running task
                task = running_tasks[0]
                
                # Update task info
                title = task.get('title', 'Processing...')
                status = task.get('status', 'Idle')
                current_step = task.get('current_step', 0)
                total_steps = task.get('total_steps', 0)
                step_name = task.get('current_step_name', 'Waiting...')
                step_progress = task.get('current_step_progress', 0.0)
                overall_progress = task.get('progress', 0.0)
                
                # Calculate elapsed time
                start_time = task.get('start_time', time.time())
                elapsed = time.time() - start_time
                if elapsed < 60:
                    elapsed_str = f"{int(elapsed)}s"
                elif elapsed < 3600:
                    elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                else:
                    hours = int(elapsed // 3600)
                    minutes = int((elapsed % 3600) // 60)
                    elapsed_str = f"{hours}h {minutes}m"
                
                # Store for later use
                last_task_info['title'] = title
                last_task_info['status'] = status
                last_task_info['elapsed'] = elapsed_str
                last_task_info['progress'] = overall_progress
                last_task_info['step_name'] = step_name
                last_task_info['step_progress'] = step_progress
                
                # Update UI
                task_title_label.set_text(title)
                task_status_label.set_text(f"Status: {status}")
                elapsed_time_label.set_text(elapsed_str)
                overall_progress_label.set_text(f"{int(overall_progress * 100)}%")
                overall_progress_bar.set_value(overall_progress)
                current_step_label.set_text(step_name)
                current_step_progress.set_value(step_progress)
            else:
                # No active tasks - keep showing last completed task info
                task_title_label.set_text(last_task_info['title'])
                task_status_label.set_text(f"Status: {last_task_info['status']}")
                elapsed_time_label.set_text(last_task_info['elapsed'])
                overall_progress_label.set_text(f"{int(last_task_info['progress'] * 100)}%")
                overall_progress_bar.set_value(last_task_info['progress'])
                current_step_label.set_text(last_task_info['step_name'])
                current_step_progress.set_value(last_task_info['step_progress'])
        except Exception as e:
            logger.error(f"Error updating progress UI: {e}")
    
    ui.timer(0.5, update_progress_ui)  # Update progress twice per second

    # --- Main Content ---
    with ui.column().classes('w-full min-h-screen q-pa-lg items-center gap-8'):
        
        # Title Header
        with ui.column().classes('items-center q-pt-lg'):
            ui.label('VidScribe AI').classes('text-6xl font-black text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500 dark:from-indigo-400 dark:via-purple-400 dark:to-pink-400 tracking-tight drop-shadow-sm')
            ui.label('Professional Video Analysis & Summarization').classes('text-lg text-slate-500 dark:text-slate-400 font-medium tracking-wide mt-2')

        # Input Area Card
        with ui.card().classes('w-full max-w-4xl glass-panel p-8 rounded-2xl'):
            ui.label('New Analysis').classes('text-lg font-bold text-slate-700 dark:text-slate-200 mb-4')
            url_input.props('outlined rounded standout dense placeholder="Paste YouTube/Bilibili URL here"').classes('w-full text-lg')
            
            def add_task():
                url = url_input.value
                if not url:
                    ui.notify('Please enter a URL', type='warning')
                    return
                if not settings['api_key']:
                    ui.notify('Please enter API Key in Settings', type='negative')
                    return
                    
                save_settings(settings) # Save settings on start
                
                new_task = {
                    'url': url,
                    'status': 'Waiting',
                    'title': 'Fetching...',
                    'summary': '',
                    'logs': [],
                    'progress': 0.0,
                    'log_expanded': True,
                    'transcript_only': False  # Full analysis mode
                }
                running_tasks.append(new_task)
                task_queue.put(new_task)
                url_input.value = ''
                ui.notify('Task added to queue', type='positive')

            def add_transcript_only_task():
                """Add task for transcript only (no AI summary)"""
                url = url_input.value
                if not url:
                    ui.notify('Please enter a URL', type='warning')
                    return
                    
                save_settings(settings)
                
                new_task = {
                    'url': url,
                    'status': 'Waiting',
                    'title': 'Fetching...',
                    'summary': '',
                    'logs': [],
                    'progress': 0.0,
                    'log_expanded': True,
                    'transcript_only': True  # Skip AI summary
                }
                
                running_tasks.append(new_task)
                task_queue.put(new_task)
                url_input.value = ''
                ui.notify('Transcript-only task added', type='info')

            with ui.row().classes('w-full gap-4 q-mt-lg'):
                ui.button('Transcript Only', on_click=add_transcript_only_task, icon='description').classes('flex-1 h-12 text-base font-semibold shadow-md bg-gradient-to-r from-teal-500 to-emerald-500 text-white border-0 hover:shadow-lg transition-all rounded-xl')
                ui.button('Full Analysis', on_click=add_task, icon='auto_awesome').classes('flex-1 h-12 text-base font-semibold shadow-md bg-gradient-to-r from-indigo-600 to-violet-600 text-white border-0 hover:shadow-lg transition-all rounded-xl')

        
        # System Logs (Collapsible with scroll)
        with ui.expansion('System Logs', icon='terminal', value=False).classes('w-full max-w-4xl glass-panel rounded-xl overflow-hidden'):
            with ui.scroll_area().classes('w-full h-64 bg-slate-900/90 p-4'):  # Dark terminal feel
                log_container = ui.column().classes('w-full font-mono text-xs')
        
        # Progress Tracking
        with ui.card().classes('w-full max-w-4xl glass-panel p-6 rounded-2xl q-mt-xl'):
            # --- Header Row ---
            with ui.row().classes('w-full justify-between items-center mb-2'):
                # Title
                ui.label('CURRENT TASK').classes('text-sm font-bold text-gray-500 dark:text-gray-400 tracking-wider')
                
                # Timer (Monospace, Top-Right)
                elapsed_time_label = ui.label('00:00').classes('text-xl font-mono font-bold text-gray-400 select-none')

            ui.separator().classes('mb-6 opacity-20')

            # --- Content ---
            with ui.row().classes('w-full justify-between items-start'):
                with ui.column().classes('gap-1'):
                    task_title_label = ui.label('No active task').classes('text-xl font-bold text-slate-800 dark:text-slate-100 leading-tight mb-1')
                    with ui.row().classes('items-center gap-2'):
                        spinner = ui.spinner('dots', size='sm')
                        task_status_label = ui.label('Idle').classes('text-sm font-medium text-slate-500 dark:text-slate-400')
                        spinner.bind_visibility_from(task_status_label, 'text', lambda t: not any(keyword in t for keyword in ['Idle', 'Completed', 'Error']))
            
            # Overall progress
            with ui.row().classes('w-full justify-between mb-2 mt-4'):
                ui.label('OVERALL PROGRESS').classes('text-xs font-bold uppercase tracking-wider text-slate-500')
                overall_progress_label = ui.label('0%').classes('text-sm font-bold text-indigo-500')
            overall_progress_bar = ui.linear_progress(value=0, show_value=False).props('color=indigo track-color=grey-3 size=10px rounded instantly-updates')
            
            # Current step progress
            ui.label('STEP DETAIL').classes('text-xs font-bold uppercase tracking-wider text-slate-500 mt-6 mb-2')
            with ui.row().classes('w-full justify-between items-baseline mb-2'):
                 current_step_label = ui.label('Waiting...').classes('text-lg font-medium text-slate-700 dark:text-slate-200')
                 
            current_step_progress = ui.linear_progress(value=0, show_value=False).props('color=cyan track-color=grey-3 size=6px rounded instantly-updates')
        
        # Add handler if not already added
        class LogHandler(logging.Handler):
            def emit(self, record):
                # CRITICAL: Disable all logging during emit to prevent infinite recursion
                # When client is deleted, ui.label() triggers warnings that call this handler again
                logging.disable(logging.CRITICAL)
                try:
                    msg = self.format(record)
                    # Add to collapsible log container
                    try:
                        with log_container:
                            ui.label(msg).classes('text-xs text-green-400 font-mono')
                    except (RuntimeError, Exception):
                        # Client deleted (browser closed/refreshed) or other UI errors
                        # Silently ignore - don't log anything here to avoid recursion
                        pass
                except Exception:
                    # Ignore any other errors - don't log to avoid recursion
                    pass
                finally:
                    # Re-enable logging
                    logging.disable(logging.NOTSET)
        
        # Add handler if not already added (check to avoid duplicates on reload)
        root_logger = logging.getLogger()
        if not any(isinstance(h, LogHandler) for h in root_logger.handlers):
            handler = LogHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            root_logger.addHandler(handler)

        # Summary Display
        with ui.card().classes('w-full max-w-4xl glass-panel p-6 rounded-2xl q-mt-xl'):
            # --- Header Row ---
            with ui.row().classes('w-full justify-between items-center mb-2'):
                ui.label('ANALYSIS REPORT').classes('text-sm font-bold text-gray-500 dark:text-gray-400 tracking-wider')
                
                # History button (embedded in header)
                async def load_history():
                    import glob
                    output_dir = settings.get('output_dir', 'downloads')
                    md_files = glob.glob(os.path.join(output_dir, '*.md'))
                    
                    if not md_files:
                        ui.notify('No summary files found!', type='warning')
                        return
                    
                    # Create file list with basenames
                    file_options = {f: os.path.basename(f) for f in md_files}
                    
                    # Show dialog
                    with ui.dialog() as dialog, ui.card().classes('w-96 glass-panel rounded-xl'):
                        ui.label('Select Summary File').classes('text-h6 font-bold q-mb-md text-slate-800 dark:text-slate-100')
                        
                        selected_file = {'path': None}
                        
                        def on_select(file_path):
                            selected_file['path'] = file_path
                            dialog.close()
                            
                            # Load the file
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                
                                current_summary['title'] = os.path.basename(file_path)
                                current_summary['content'] = content
                                
                                summary_title.set_text(current_summary['title'])
                                summary_content.set_content(content)
                                
                                # Switch view: Hide empty state, Show content
                                empty_state_container.set_visibility(False)
                                content_container.set_visibility(True)
                                
                                ui.notify(f'Loaded: {current_summary["title"]}', type='positive')
                            except Exception as e:
                                ui.notify(f'Error loading file: {e}', type='negative')
                        
                        with ui.column().classes('w-full gap-2'):
                            for file_path, file_name in file_options.items():
                                ui.button(file_name, on_click=lambda fp=file_path: on_select(fp)).classes('w-full text-left align-left bg-slate-50 hover:bg-slate-100 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 shadow-none border border-slate-200 dark:border-slate-700 rounded-lg')
                        
                        ui.button('Cancel', on_click=dialog.close).classes('w-full bg-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 shadow-none q-mt-md')
                    
                    dialog.open()
                
                ui.button('Histroy', on_click=load_history, icon='history').props('flat dense').classes('text-gray-400 hover:text-indigo-500')

            ui.separator().classes('mb-6 opacity-20')
            
            # Current summary state
            current_summary = {'title': '', 'content': ''}

            # --- Empty State Container ---
            with ui.column().classes('w-full items-center justify-center py-12') as empty_state_container:
                ui.icon('assignment', size='4em').classes('text-slate-200 dark:text-slate-700 mb-4 opacity-50')
                ui.label('No report loaded').classes('text-slate-400 font-medium italic')

            # --- Content Container (Initially Hidden) ---
            with ui.column().classes('w-full') as content_container:
                content_container.set_visibility(False) # Default hidden
                summary_title = ui.label('').classes('text-xl font-bold text-indigo-600 dark:text-indigo-400 mb-4')
                summary_content = ui.markdown('').classes('w-full nicegui-markdown')
            
            
            # Add custom CSS for better markdown readability (Scheme A+C)
            ui.add_head_html('''
                <style>
                    .nicegui-markdown {
                        color: inherit;
                        font-family: 'Outfit', sans-serif;
                    }
                    .nicegui-markdown h1 { font-size: 1.8rem; font-weight: 800; margin-top: 1.5em; margin-bottom: 0.8em; line-height: 1.2; letter-spacing: -0.02em; }
                    .nicegui-markdown h2 { font-size: 1.4rem; font-weight: 700; margin-top: 1.5em; margin-bottom: 0.6em; padding-bottom: 0.3em; border-bottom: 1px solid rgba(128,128,128,0.1); }
                    .nicegui-markdown p { font-size: 1.05rem; line-height: 1.8; margin-bottom: 1.25em; color: inherit; opacity: 0.9; }
                    .nicegui-markdown li { font-size: 1.05rem; line-height: 1.7; margin-bottom: 0.5em; opacity: 0.9; }
                    .nicegui-markdown strong { font-weight: 700; color: #6366f1; } /* Indigo highlight */
                    .body--dark .nicegui-markdown strong { color: #a5b4fc; }
                    .nicegui-markdown blockquote { border-left: 4px solid #6366f1; padding-left: 1rem; font-style: italic; opacity: 0.8; background: rgba(99, 102, 241, 0.05); padding: 1rem; border-radius: 0 8px 8px 0; margin-bottom: 1.5rem; }
                    .nicegui-markdown code { background: rgba(128, 128, 128, 0.15); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
                </style>
            ''')
        
        # Auto-update summary when task completes
        last_completed_count = {'count': 0}
        
        def check_for_new_summary():
            current_count = len(completed_tasks)
            # Only update if there's a NEW completion (count increased)
            if current_count > last_completed_count['count']:
                last_completed_count['count'] = current_count
                if completed_tasks:
                    latest_task = completed_tasks[-1]
                    if latest_task.get('summary') and latest_task.get('title'):
                        current_summary['title'] = latest_task['title']
                        current_summary['content'] = latest_task['summary']
                        
                        summary_title.set_text(current_summary['title'])
                        summary_content.set_content(current_summary['content'])
                        
                        # Switch to content view
                        empty_state_container.set_visibility(False)
                        content_container.set_visibility(True)
                        current_summary['content'] = latest_task['summary']
                        summary_title.set_text(f"{latest_task['title']}.md")
                        summary_content.set_content(latest_task['summary'])
        
        ui.timer(2.0, check_for_new_summary)



ui.run(title='VidScribe AI', reload=False, port=8080, favicon='icon.png')
