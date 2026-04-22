import gc
import os
import logging
from faster_whisper import WhisperModel
import torch

# Configure logging
logger = logging.getLogger(__name__)

class Transcriber:
    def __init__(self, model_size="base", device=None, compute_type="int8", beam_size=5, 
                 vad_filter=False, temperature=None):
        self.model_size = model_size
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.temperature = temperature if temperature else [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        
        # If device is explicitly provided, use it. Otherwise auto-detect.
        if device:
            self.device = device
        else:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Auto-adjust compute_type for CPU ONLY if we are actually on CPU
        if self.device == "cpu" and compute_type == "int8_float16":
            logger.warning("int8_float16 is not supported on CPU. Falling back to int8.")
            self.compute_type = "int8"
        else:
            self.compute_type = compute_type
            
        logger.info(f"Transcriber initialized: model={self.model_size}, device={self.device}, "
                   f"compute={self.compute_type}, beam={self.beam_size}, vad={self.vad_filter}")

    def transcribe(self, audio_path: str, output_path: str = None, language: str = None, progress_callback=None) -> str:
        """
        Transcribes audio file using faster-whisper.
        Loads the model, processes the audio, and immediately unloads the model to free memory.
        
        Args:
            audio_path: Path to audio file
            output_path: REQUIRED path to save transcript (to avoid crash when returning large strings)
            language: Optional language code (e.g., 'zh', 'en'). If None, auto-detect.
            progress_callback: Optional callback(progress, message) for progress updates
        
        Returns:
            Empty string (actual content is in output_path file)
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        if not output_path:
            raise ValueError("output_path is required to avoid crashes")

        model = None
        result_text = ""  # Initialize outside try block
        
        try:
            if progress_callback:
                progress_callback(0.0, "🔥 載入 Whisper 模型...")
            
            logger.info(f"Loading Whisper model: {self.model_size} on {self.device}...")
            # Load model only when needed
            model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)

            if progress_callback:
                progress_callback(0.2, "🔥 開始轉錄音訊...")
            
            logger.info(f"Transcribing {audio_path}...")
            # Build transcribe options
            transcribe_options = {
                'beam_size': self.beam_size,
                'temperature': self.temperature
            }
            
            # Add VAD filter if enabled
            if self.vad_filter:
                transcribe_options['vad_filter'] = True
                transcribe_options['vad_parameters'] = {
                    'min_silence_duration_ms': 500
                }
                logger.info("VAD filter enabled for noise reduction")
            
            # Add language and initial prompt if provided
            if language:
                transcribe_options['language'] = language
                # Add Chinese-specific initial prompt
                if language == 'zh':
                    transcribe_options['initial_prompt'] = "以下是繁體中文或簡體中文的影片內容。"
                    logger.info("Using Chinese initial prompt for better accuracy")
                logger.info(f"Using specified language: {language}")
            
            if progress_callback:
                progress_callback(0.4, "🔥 處理音訊中...")
            
            segments, info = model.transcribe(audio_path, **transcribe_options)

            if progress_callback:
                progress_callback(0.6, "🔥 組合轉錄文本...")
            
            # Collect segments immediately to free up generator and allow model cleanup
            for segment in segments:
                result_text += segment.text + " "
            
            result_text = result_text.strip()
            logger.info("Transcription completed.")

            if progress_callback:
                progress_callback(0.8, "🔥 儲存轉錄結果...")
            
            # Always save to file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result_text)
            logger.info(f"Transcription saved to {output_path}")

            if progress_callback:
                progress_callback(1.0, "✅ 轉錄完成")

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            if progress_callback:
                progress_callback(0.0, f"❌ 轉錄失敗: {e}")
            raise e
        finally:
            # CRITICAL: NO cleanup operations in finally block
            # Any cleanup here causes thread crash - let Python GC handle it
            pass
        
        # Return empty string to avoid crash - caller should read from output_path
        logger.info("DEBUG: About to return from transcribe()")
        return ""
