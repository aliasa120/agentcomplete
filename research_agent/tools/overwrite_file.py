import os
from langchain_core.tools import tool

@tool
def overwrite_file(file_path: str, content: str) -> str:
    """Write content to a file, completely overwriting it if it already exists.
    
    Use this instead of write_file when you know the file might exist (e.g. /news_input.md, /social_posts.md).
    Only supports paths in the project root directory.
    
    Args:
        file_path: The path to write to (e.g. "/news_input.md" or "news_input.md")
        content: The full content to write to the file
    """
    # Clean up path to just the filename to prevent directory traversal
    filename = os.path.basename(file_path)
    
    # We only allow writing to the project root for safety
    if filename not in ["news_input.md", "social_posts.md"]:
        return f"Error: You are only allowed to overwrite 'news_input.md' and 'social_posts.md'. Cannot write to {filename}."
        
    try:
        # Get absolute path relative to current working directory (project root)
        abs_path = os.path.join(os.getcwd(), filename)
        
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return f"Successfully overwrote {filename}"
        
    except Exception as e:
        return f"Error writing file: {str(e)}"
