from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import re


def extract_text_from_file(file_path: Path, content_type: str | None = None) -> str:
    """Extract text content from various file formats"""
    
    suffix = file_path.suffix.lower()
    
    # Plain text files
    if suffix in ['.txt', '.md', '.py', '.js', '.java', '.cpp', '.c', '.h']:
        return file_path.read_text(encoding='utf-8', errors='ignore')
    
    # HTML files
    if suffix in ['.html', '.htm']:
        return extract_from_html(file_path.read_text(encoding='utf-8', errors='ignore'))
    
    # PDF files
    if suffix == '.pdf':
        return extract_from_pdf(file_path)
    
    # Fallback: try to read as text
    try:
        return file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return f"[Binary file: {file_path.name}]"


def extract_from_html(html_content: str) -> str:
    """Extract text from HTML, removing tags"""
    # Remove script and style tags
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html_content)
    
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def extract_from_pdf(file_path: Path) -> str:
    """Extract text from PDF file"""
    try:
        import pypdf
        
        with open(file_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            text_parts = []
            
            for page in reader.pages:
                text_parts.append(page.extract_text())
            
            return '\n\n'.join(text_parts)
    except ImportError:
        return "[PDF parsing requires pypdf: pip install pypdf]"
    except Exception as e:
        return f"[PDF parsing error: {str(e)}]"


def generate_title_from_content(content: str, filename: str) -> str:
    """Generate a title from content or filename"""
    lines = content.strip().split('\n')
    
    # Try to find a good title from first few lines
    for line in lines[:10]:
        line = line.strip()
        if len(line) > 10 and len(line) < 200:
            # Remove common markdown headers
            line = re.sub(r'^#+\s*', '', line)
            if line:
                return line
    
    # Fallback to filename
    return Path(filename).stem.replace('_', ' ').replace('-', ' ').title()


def extract_metadata(file_path: Path, content: str) -> Dict[str, Any]:
    """Extract metadata from file"""
    metadata = {
        'filename': file_path.name,
        'file_size': file_path.stat().st_size,
        'file_type': file_path.suffix.lower(),
    }
    
    # Try to detect tags from content
    tags = []
    
    # Check file extension for basic categorization
    ext = file_path.suffix.lower()
    if ext in ['.py', '.js', '.java', '.cpp', '.c']:
        tags.append('code')
    elif ext in ['.md', '.txt']:
        tags.append('document')
    elif ext in ['.html', '.htm']:
        tags.append('web')
    elif ext == '.pdf':
        tags.append('paper')
    
    # Simple keyword detection for academic papers
    lower_content = content.lower()
    if any(word in lower_content for word in ['abstract', 'introduction', 'conclusion', 'references']):
        tags.append('research')
    
    if any(word in lower_content for word in ['algorithm', 'complexity', 'theorem', 'proof']):
        tags.append('computer-science')
    
    if any(word in lower_content for word in ['neural', 'model', 'training', 'learning']):
        tags.append('ai')
    
    metadata['suggested_tags'] = tags
    
    return metadata
