import re
import logging

logger = logging.getLogger(__name__)

def vtt_to_clean_txt(vtt_path: str, output_txt_path: str) -> str:
    """
    Converts VTT subtitle file to clean plain text.
    Removes timestamps, HTML tags, and duplicate lines.
    """
    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        clean_lines = []
        seen_lines = set()  # Remove duplicate sentences (common in auto-subs)

        # Regex to detect timestamps (e.g., 00:00:01.000 --> 00:00:04.000)
        timestamp_pattern = re.compile(r'\d{2}:\d{2}:\d{2}\.\d{3}\s-->\s\d{2}:\d{2}:\d{2}\.\d{3}')

        for line in lines:
            line = line.strip()
            
            # 1. Filter out "WEBVTT", empty lines, numeric indices
            if not line or line == 'WEBVTT' or line.isdigit():
                continue
                
            # 2. Filter out timestamps
            if timestamp_pattern.match(line):
                continue
                
            # 3. Filter out HTML tags (e.g., <c.colorE5E5E5>)
            line = re.sub(r'<[^>]+>', '', line)

            # 4. Deduplicate and save
            if line and line not in seen_lines:
                clean_lines.append(line)
                seen_lines.add(line)

        # Write clean text
        full_text = "\n".join(clean_lines)
        with open(output_txt_path, 'w', encoding='utf-8') as f:
            f.write(full_text)
        
        logger.info(f"Converted VTT to clean TXT: {output_txt_path}")
        return full_text
        
    except Exception as e:
        logger.error(f"Error converting VTT to TXT: {e}")
        raise e
