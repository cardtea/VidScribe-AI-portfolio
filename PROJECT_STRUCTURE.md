# VidScribe-AI Project Structure

## Overview
VidScribe-AI is a YouTube video transcription and AI summarization tool with GPU acceleration support. It uses Whisper for speech-to-text and Gemini AI for intelligent summarization.

## Project Directory Structure

```
VidScribe-AI/
├── main.py                          # Main application entry point (NiceGUI web interface)
│
├── config/                          # Configuration files
│   ├── settings.example.json        # Safe committed example settings
│   ├── settings.json                # Local application settings (gitignored)
│   └── prompts/
│       └── default.txt              # Default AI summarization prompt
│
├── core/                            # Core functionality modules
│   ├── downloader.py                # YouTube video/audio/subtitle downloader (yt-dlp)
│   ├── transcriber.py               # Whisper-based speech-to-text transcription
│   ├── summarizer.py                # Gemini AI summarization
│   └── monitor.py                   # System resource monitoring (CPU/GPU/RAM/VRAM)
│
├── utils/                           # Utility modules
│   ├── logger.py                    # Logging configuration
│   ├── file_handler.py              # File operations
│   └── text_cleaner.py              # Text cleaning utilities
│
├── downloads/                       # Output directory
│   ├── *.md                         # Generated summary files
│   ├── *.vtt                        # Downloaded subtitle files
│   └── saved_transcripts/           # Permanently saved transcripts
│       └── *.txt
│
└── .venv/                           # Python virtual environment
    └── (dependencies)
```

## Key Files Description

### Main Application
- **main.py**: NiceGUI-based web interface with worker thread for async processing
  - URL input and processing queue
  - Real-time system monitoring (CPU, GPU, RAM, VRAM)
  - Summary display and history management
  - Transcription profile selection (Fast/Balanced/Accurate)

### Core Modules

#### downloader.py
- Downloads YouTube videos using yt-dlp
- Supports subtitle extraction (multiple languages)
- Audio extraction for transcription fallback
- Graceful error handling for subtitle failures

#### transcriber.py
- Whisper-based speech-to-text using faster-whisper
- GPU acceleration (CUDA support)
- Advanced features:
  - VAD (Voice Activity Detection) filter
  - Language detection from video title
  - Chinese initial prompt for better accuracy
  - Temperature fallback for robust decoding
- Three quality profiles:
  - **Fast**: Turbo model, beam=3, ~90% accuracy
  - **Balanced**: Large-v3 + int8, beam=5, ~95% accuracy
  - **Accurate**: Large-v3 + float16, beam=5, 98%+ accuracy

#### summarizer.py
- Gemini AI integration for intelligent summarization
- Custom prompt support
- Markdown output generation

#### monitor.py
- Real-time system resource monitoring
- Dual GPU monitoring approach:
  1. Primary: pynvml (NVML library)
  2. Fallback: nvidia-smi subprocess (Windows compatibility)
- Metrics: CPU%, GPU%, RAM (used/total), VRAM (used/total)

### Configuration

#### settings.example.json
```json
{
  "api_key": "",
  "model": "gemini-2.5-flash",
  "device": "cuda",
  "output_dir": "downloads",
  "prompt_file": "default.txt",
  "transcription_profile": "balanced",
  "transcription_profiles": {
    "fast": {
      "label": "Fast (Turbo + Beam 3 + VAD)",
      "model_size": "turbo",
      "compute_type": "int8_float16",
      "beam_size": 3,
      "vad_filter": true,
      "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    },
    "balanced": {
      "label": "Balanced (Large-V3 + Int8 + VAD)",
      "model_size": "large-v3",
      "compute_type": "int8",
      "beam_size": 5,
      "vad_filter": true,
      "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    },
    "accurate": {
      "label": "Accurate (Large-V3 + Float16 + VAD)",
      "model_size": "large-v3",
      "compute_type": "float16",
      "beam_size": 5,
      "vad_filter": true,
      "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    }
  }
}
```

`config/settings.json` is intended for local use only and should stay out of version control.

## Workflow

### High-Speed Hybrid Workflow
1. **Step 1**: Download video info and check for subtitles
2. **Step 2**: 
   - If subtitles available: Download and parse
   - If no subtitles: Download audio
3. **Step 3**: Audio transcription (if needed)
   - Language detection from title
   - VAD filter for noise reduction
   - Chinese initial prompt (if applicable)
4. **Step 4**: Save transcript permanently
5. **Step 5**: AI summarization with Gemini
6. **Step 6**: Save summary as markdown
7. **Step 7**: Cleanup temporary files

## Key Features

### Whisper Optimization
- **VAD Filter**: Removes silence and background noise (saves ~2-3 seconds per 6-min video)
- **Language Detection**: Automatic detection from video title
  - Chinese (zh): 中文字符 (U+4E00 to U+9FFF)
  - Japanese (ja): 平假名/片假名
  - Korean (ko): 한글
  - Default: Auto-detect
- **Initial Prompt**: "以下是繁體中文或簡體中文的影片內容。" for Chinese videos
- **Temperature Fallback**: [0.0, 0.2, 0.4, 0.6, 0.8, 1.0] for robust decoding

### UI Features
- Real-time system monitoring (CPU, GPU, RAM, VRAM)
- Summary display with markdown rendering
- History management (load previous summaries)
- Open downloads folder button
- Transcription profile selector
- Custom font sizing for readability

### Error Handling
- Graceful subtitle download failure handling
- Automatic fallback to audio transcription
- Client deletion protection (NiceGUI)
- GPU monitoring fallback (pynvml → nvidia-smi)

## Dependencies

### Core
- **Python 3.11**
- **PyTorch** (with CUDA 12.1 support)
- **faster-whisper** (Whisper model inference)
- **google-generativeai** (Gemini AI)
- **yt-dlp** (YouTube downloader)
- **NiceGUI** (Web UI framework)

### Monitoring
- **psutil** (CPU/RAM monitoring)
- **nvidia-ml-py3** (GPU/VRAM monitoring via pynvml)

### Utilities
- **markdown2** (Markdown processing)
- **coloredlogs** (Enhanced logging)

## System Requirements

### Minimum
- NVIDIA GPU with CUDA support
- 8GB VRAM (for Turbo model)
- 16GB RAM
- Windows 10/11 with NVIDIA drivers

### Recommended
- NVIDIA RTX 3060 or better
- 10GB+ VRAM
- 32GB RAM
- CUDA 12.1+

## Startup Diagnostics

The application performs comprehensive startup checks:
```
============================================================
🚀 VidScribe-AI Starting Up
============================================================
✅ CUDA Available: NVIDIA GeForce RTX 3080
   CUDA Version: 12.1
   Total VRAM: 10.00 GB
✅ GPU monitoring enabled (pynvml)
   OR
⚠️ GPU monitoring disabled (pynvml not available)
   Falling back to nvidia-smi...
============================================================
```

## Performance Metrics

### Transcription Speed (5:55 video)
- **Fast** (Turbo + Beam 3): ~13 seconds
- **Balanced** (Large-v3 + Int8): ~45 seconds
- **Accurate** (Large-v3 + Float16): ~41 seconds

### Accuracy
- **Fast**: ~90%
- **Balanced**: ~95%
- **Accurate**: 98%+

### AI Summarization
- Average time: ~28 seconds (Gemini 2.5 Flash)

## Known Issues

### NVML on Windows
- pynvml may fail to find NVML shared library on Windows
- Automatic fallback to nvidia-smi subprocess
- Does not affect CUDA functionality for Whisper

### Subtitle Download
- Some videos may block subtitle downloads (HTTP 429/403)
- Automatic fallback to audio transcription

## Future Enhancements

- [ ] Batch processing support
- [ ] Multiple language output
- [ ] Custom Whisper model support
- [ ] Export to different formats (PDF, DOCX)
- [ ] Video timestamp integration
- [ ] Speaker diarization

## License
(To be determined)

## Author
Built with Antigravity AI Assistant
