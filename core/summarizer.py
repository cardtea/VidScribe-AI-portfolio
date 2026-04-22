import google.generativeai as genai
import logging
import os

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("API Key is required for Summarizer")
        genai.configure(api_key=api_key)
        logger.info("Summarizer initialized with API Key.")

    def summarize(self, text_content: str, model_name: str = "gemini-1.5-pro", prompt_template: str = "", progress_callback=None) -> str:
        """
        Summarizes the given text using Google Gemini API.
        
        Args:
            text_content: The text to summarize
            model_name: Gemini model name
            prompt_template: Custom prompt template
            progress_callback: Optional callback(progress, message) for progress updates
        """
        try:
            if progress_callback:
                progress_callback(0.0, "🤖 初始化 AI 模型...")
            
            logger.info(f"Summarizing content with model: {model_name}")
            model = genai.GenerativeModel(model_name)
            
            if progress_callback:
                progress_callback(0.1, "🤖 準備分析內容...")
            
            full_prompt = f"{prompt_template}\n\n---\n\nTranscript:\n{text_content}"
            
            if progress_callback:
                progress_callback(0.2, "🤖 發送請求到 Gemini API...")
            
            # Safety settings can be adjusted if needed, using defaults for now
            response = model.generate_content(full_prompt)
            
            if progress_callback:
                progress_callback(0.9, "🤖 處理 AI 回應...")
            
            if response.text:
                logger.info("Summarization completed successfully.")
                if progress_callback:
                    progress_callback(1.0, "✅ AI 分析完成")
                return response.text
            else:
                logger.warning("Summarization returned empty response.")
                return "Error: Empty response from Gemini API."

        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            if progress_callback:
                progress_callback(0.0, f"❌ AI 分析失敗: {e}")
            return f"Error during summarization: {e}"

    def save_summary(self, summary_text: str, output_path: str):
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(summary_text)
            logger.info(f"Summary saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save summary: {e}")
            raise e
