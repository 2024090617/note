"""
Debug logger for recording LLM request/response conversations.

Creates detailed markdown files with all API interactions when debug mode is enabled.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from llm_service.client import Message


class DebugMarkdownLogger:
    """
    Logger that writes LLM conversations to markdown files.
    
    Creates human-readable markdown files with:
    - Timestamps
    - Model information
    - Full request payloads
    - Complete responses
    - Token usage statistics
    """
    
    def __init__(self, session_id: str, output_dir: Optional[Path] = None):
        """
        Initialize debug logger.
        
        Args:
            session_id: Unique session identifier
            output_dir: Directory to write logs (defaults to ~/.dual_worker_state/debug_logs)
        """
        self.session_id = session_id
        
        if output_dir is None:
            output_dir = Path.home() / ".dual_worker_state" / "debug_logs"
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create session log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.output_dir / f"session_{session_id}_{timestamp}.md"
        
        # Initialize file with header
        self._write_header()
        
        self.request_count = 0
    
    def _write_header(self):
        """Write markdown header to log file"""
        with open(self.log_file, 'w') as f:
            f.write(f"# Dual-Worker Debug Log\n\n")
            f.write(f"**Session ID:** `{self.session_id}`\n\n")
            f.write(f"**Started:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
    
    def log_request(
        self,
        model_name: str,
        messages: List[Message],
        temperature: float,
        max_tokens: int,
        request_metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log an LLM request.
        
        Args:
            model_name: Model being called
            messages: Request messages
            temperature: Temperature parameter
            max_tokens: Max tokens parameter
            request_metadata: Additional metadata (worker_id, task_id, etc.)
        """
        self.request_count += 1
        
        with open(self.log_file, 'a') as f:
            f.write(f"## Request #{self.request_count}\n\n")
            f.write(f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Model:** `{model_name}`\n\n")
            
            if request_metadata:
                f.write("**Metadata:**\n")
                for key, value in request_metadata.items():
                    f.write(f"- {key}: `{value}`\n")
                f.write("\n")
            
            f.write("**Parameters:**\n")
            f.write(f"- Temperature: `{temperature}`\n")
            f.write(f"- Max Tokens: `{max_tokens}`\n\n")
            
            f.write("**Messages:**\n\n")
            for i, msg in enumerate(messages, 1):
                f.write(f"### Message {i} - {msg.role.value}\n\n")
                f.write(f"```\n{msg.content}\n```\n\n")
    
    def log_response(
        self,
        model_name: str,
        response_content: str,
        execution_time: float,
        token_usage: Optional[Dict[str, int]] = None,
        response_metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log an LLM response.
        
        Args:
            model_name: Model that responded
            response_content: Response text
            execution_time: Time taken (seconds)
            token_usage: Token usage stats
            response_metadata: Additional metadata
        """
        with open(self.log_file, 'a') as f:
            f.write(f"### Response from `{model_name}`\n\n")
            f.write(f"**Execution Time:** {execution_time:.2f}s\n\n")
            
            if token_usage:
                f.write("**Token Usage:**\n")
                for key, value in token_usage.items():
                    f.write(f"- {key}: `{value}`\n")
                f.write("\n")
            
            if response_metadata:
                f.write("**Metadata:**\n")
                for key, value in response_metadata.items():
                    f.write(f"- {key}: `{value}`\n")
                f.write("\n")
            
            f.write("**Response Content:**\n\n")
            f.write(f"```\n{response_content}\n```\n\n")
            f.write("---\n\n")
    
    def log_error(
        self,
        model_name: str,
        error_message: str,
        error_details: Optional[str] = None
    ):
        """
        Log an API error.
        
        Args:
            model_name: Model that failed
            error_message: Error message
            error_details: Additional error details
        """
        with open(self.log_file, 'a') as f:
            f.write(f"### ❌ Error from `{model_name}`\n\n")
            f.write(f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Error:** {error_message}\n\n")
            
            if error_details:
                f.write("**Details:**\n\n")
                f.write(f"```\n{error_details}\n```\n\n")
            
            f.write("---\n\n")
    
    def log_section(self, title: str, content: str):
        """
        Log a custom section.
        
        Args:
            title: Section title
            content: Section content
        """
        with open(self.log_file, 'a') as f:
            f.write(f"## {title}\n\n")
            f.write(f"{content}\n\n")
            f.write("---\n\n")
    
    def finalize(self, summary: Optional[str] = None):
        """
        Finalize the log file.
        
        Args:
            summary: Optional summary to append
        """
        with open(self.log_file, 'a') as f:
            f.write("\n---\n\n")
            f.write(f"## Session Summary\n\n")
            f.write(f"**Ended:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Total Requests:** {self.request_count}\n\n")
            
            if summary:
                f.write(f"{summary}\n\n")
    
    def get_log_path(self) -> Path:
        """Get the path to the log file"""
        return self.log_file


# Global debug logger instance (set by CLI when --debug is used)
_debug_logger: Optional[DebugMarkdownLogger] = None


def set_debug_logger(logger: Optional[DebugMarkdownLogger]):
    """Set the global debug logger instance"""
    global _debug_logger
    _debug_logger = logger


def get_debug_logger() -> Optional[DebugMarkdownLogger]:
    """Get the global debug logger instance"""
    return _debug_logger


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled"""
    return _debug_logger is not None
