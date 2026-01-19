#!/usr/bin/env python3
"""
Extract GitHub Copilot OAuth token from VS Code storage.

Copilot Chat uses OAuth tokens (not PATs) which provide access to premium models
like GPT-5, GPT-5.2, Claude Opus 4.5, etc.
"""

import os
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any


def find_vscode_storage_paths() -> list[Path]:
    """Find VS Code storage directories."""
    home = Path.home()
    
    possible_paths = [
        # macOS
        home / "Library/Application Support/Code/User/globalStorage/github.copilot",
        home / "Library/Application Support/Code - Insiders/User/globalStorage/github.copilot",
        # Linux
        home / ".config/Code/User/globalStorage/github.copilot",
        home / ".config/Code - Insiders/User/globalStorage/github.copilot",
        # Windows
        home / "AppData/Roaming/Code/User/globalStorage/github.copilot",
        home / "AppData/Roaming/Code - Insiders/User/globalStorage/github.copilot",
    ]
    
    return [p for p in possible_paths if p.exists()]


def extract_token_from_storage(storage_path: Path) -> Optional[str]:
    """Extract Copilot OAuth token from storage."""
    
    # Try different storage file locations
    token_files = [
        storage_path / "user.json",
        storage_path / "versions" / "user.json",
        storage_path / "hosts.json",
    ]
    
    for token_file in token_files:
        if token_file.exists():
            try:
                with open(token_file, 'r') as f:
                    data = json.load(f)
                    
                # Try different token field names
                token = (
                    data.get('token') or 
                    data.get('oauth_token') or
                    data.get('access_token') or
                    (data.get('github.com', {}).get('oauth_token'))
                )
                
                if token:
                    return token
                    
            except (json.JSONDecodeError, IOError) as e:
                continue
    
    return None


def get_copilot_token_via_api(github_token: str) -> Optional[Dict[str, Any]]:
    """Get Copilot token using GitHub PAT."""
    import requests
    
    endpoints = [
        "https://api.github.com/copilot_internal/v2/token",
        "https://api.githubcopilot.com/token",
    ]
    
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/json",
        "Editor-Version": "vscode/1.85.0",
        "Editor-Plugin-Version": "copilot/1.150.0",
    }
    
    for url in endpoints:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except:
            continue
    
    return None


def main():
    print("=" * 80)
    print("GitHub Copilot OAuth Token Extractor")
    print("=" * 80)
    print()
    
    # Method 1: Extract from VS Code storage
    print("Method 1: Extracting from VS Code storage...")
    storage_paths = find_vscode_storage_paths()
    
    if storage_paths:
        print(f"Found {len(storage_paths)} VS Code Copilot storage location(s)")
        for path in storage_paths:
            print(f"  • {path}")
            token = extract_token_from_storage(path)
            if token:
                print()
                print("✓ Found Copilot OAuth token!")
                print()
                print("Token (first 20 chars):", token[:20] + "...")
                print()
                print("To use this token, set:")
                print(f'  export COPILOT_TOKEN="{token}"')
                print()
                
                # Test the token
                print("Testing token with Copilot API...")
                import requests
                
                test_models = ["gpt-4o", "o1", "claude-opus-4.5"]
                working = []
                
                for model in test_models:
                    try:
                        headers = {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            "Editor-Version": "vscode/1.85.0",
                            "Editor-Plugin-Version": "copilot/1.150.0",
                            "OpenAI-Organization": "github-copilot",
                        }
                        
                        payload = {
                            "model": model,
                            "messages": [{"role": "user", "content": "Hi"}],
                            "max_tokens": 10,
                        }
                        
                        response = requests.post(
                            "https://api.githubcopilot.com/chat/completions",
                            headers=headers,
                            json=payload,
                            timeout=10,
                        )
                        
                        if response.status_code == 200:
                            working.append(model)
                            print(f"  ✓ {model} works!")
                        else:
                            print(f"  ✗ {model} failed: {response.status_code}")
                            
                    except Exception as e:
                        print(f"  ✗ {model} error: {str(e)[:50]}")
                
                if working:
                    print()
                    print(f"✓ Token works with {len(working)} model(s): {', '.join(working)}")
                    print()
                
                return
    else:
        print("  ✗ No VS Code Copilot storage found")
    
    print()
    
    # Method 2: Try to get token via API
    print("Method 2: Requesting token via GitHub API...")
    github_token = os.getenv("GITHUB_TOKEN")
    
    if github_token:
        print(f"  Using GITHUB_TOKEN: {github_token[:10]}...")
        result = get_copilot_token_via_api(github_token)
        
        if result:
            token = result.get("token")
            expires_at = result.get("expires_at")
            
            if token:
                print()
                print("✓ Got Copilot token via API!")
                print()
                print("Token (first 20 chars):", token[:20] + "...")
                print(f"Expires at: {expires_at}")
                print()
                print("To use this token, set:")
                print(f'  export COPILOT_TOKEN="{token}"')
                print()
                return
        
        print("  ✗ Could not get token via API")
    else:
        print("  ✗ GITHUB_TOKEN not set")
    
    print()
    print("=" * 80)
    print("INSTRUCTIONS")
    print("=" * 80)
    print()
    print("To access premium Copilot models (GPT-5, Claude Opus 4.5, etc.):")
    print()
    print("1. Make sure you're signed into GitHub Copilot in VS Code")
    print("2. Open VS Code and use Copilot Chat once")
    print("3. Run this script again to extract the OAuth token")
    print()
    print("Alternatively, you can manually extract the token from:")
    print("  ~/Library/Application Support/Code/User/globalStorage/github.copilot/")
    print()


if __name__ == "__main__":
    main()
