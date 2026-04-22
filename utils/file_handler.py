import os
import re

class FileHandler:
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitizes a string to be safe for use as a filename.
        Removes all Windows illegal characters and control characters.
        """
        # Windows illegal characters: < > : " / \ | ? * and control characters
        illegal_chars = '<>:"/\\|?*#'
        for char in illegal_chars:
            filename = filename.replace(char, '')
        # Also remove control characters
        filename = ''.join(char for char in filename if ord(char) >= 32)
        # Trim whitespace and dots from ends
        filename = filename.strip().strip('.')
        # Limit length to avoid path too long errors
        if len(filename) > 200:
            filename = filename[:200]
        return filename if filename else "untitled"

    @staticmethod
    def get_unique_filename(directory: str, filename: str) -> str:
        """
        Returns a unique filename if the file already exists in the directory.
        Appends (1), (2), etc.
        """
        name, ext = os.path.splitext(filename)
        counter = 1
        unique_filename = filename
        
        while os.path.exists(os.path.join(directory, unique_filename)):
            unique_filename = f"{name} ({counter}){ext}"
            counter += 1
            
        return unique_filename
