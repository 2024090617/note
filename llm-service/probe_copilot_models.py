#!/usr/bin/env python3
"""
Probe script to discover available models via GitHub Copilot API.

Tests various model names to see which ones work with Copilot API.
"""

import sys
import os
import requests
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from llm_service.auth import GitHubAuthenticator


# List of potential model names to test
POTENTIAL_MODELS = [
    # GPT models
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-5",
    "gpt-5-mini",
    
    # O1 models (reasoning)
    "o1",
    "o1-preview",
    "o1-mini",
    
    # Claude models
    "claude-3-opus",
    "claude-3.5-sonnet",
    "claude-opus-4",
    "claude-opus-4.5",
    "claude-sonnet-4.5",
    
    # Grok models
    "grok",
    "grok-beta",
    "grok-code",
    "grok-code-fast",
    "grok-code-fast-1",
    
    # Gemini models
    "gemini-pro",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    
    # Llama models
    "llama-3.1-70b",
    "llama-3.1-405b",
    
    # Mistral models
    "mistral-large",
    "mistral-large-2407",
    "mistral-large-2411",
]


def test_model(model_name: str, auth: GitHubAuthenticator, copilot_endpoint: str) -> Dict[str, Any]:
    """
    Test if a model works with Copilot API.
    
    Args:
        model_name: Name of model to test
        auth: GitHub authenticator
        copilot_endpoint: Copilot API endpoint
        
    Returns:
        Dict with test results
    """
    headers = auth.get_headers()
    headers.update({
        "Editor-Version": "vscode/1.85.0",
        "Editor-Plugin-Version": "copilot/1.150.0",
        "OpenAI-Organization": "github-copilot",
    })
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 10,
        "temperature": 0.7,
    }
    
    try:
        response = requests.post(
            copilot_endpoint,
            headers=headers,
            json=payload,
            timeout=30,
        )
        
        result = {
            "model": model_name,
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "error": None,
            "response_model": None,
        }
        
        if response.status_code == 200:
            data = response.json()
            result["response_model"] = data.get("model", "unknown")
            result["content"] = data.get("choices", [{}])[0].get("message", {}).get("content", "")[:50]
        else:
            try:
                error_data = response.json()
                result["error"] = error_data.get("error", {}).get("message") or str(error_data)
            except:
                result["error"] = response.text[:100]
        
        return result
        
    except Exception as e:
        return {
            "model": model_name,
            "status_code": None,
            "success": False,
            "error": str(e)[:100],
            "response_model": None,
        }


def main():
    """Main probe function."""
    print("=" * 80)
    print("GitHub Copilot API Model Probe")
    print("=" * 80)
    print()
    
    # Get GitHub token
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        print("❌ Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)
    
    print(f"✓ GitHub token found: {github_token[:10]}...")
    print()
    
    # Initialize authenticator
    auth = GitHubAuthenticator(github_token)
    copilot_endpoint = "https://api.githubcopilot.com/chat/completions"
    
    print(f"Testing {len(POTENTIAL_MODELS)} potential models...")
    print()
    
    # Test all models
    results = []
    working_models = []
    
    for i, model_name in enumerate(POTENTIAL_MODELS, 1):
        print(f"[{i:2d}/{len(POTENTIAL_MODELS)}] Testing {model_name:30s} ", end="", flush=True)
        
        result = test_model(model_name, auth, copilot_endpoint)
        results.append(result)
        
        if result["success"]:
            print(f"✓ WORKS (responds as: {result['response_model']})")
            working_models.append(model_name)
        else:
            error_msg = result["error"] or f"HTTP {result['status_code']}"
            print(f"✗ FAILED ({error_msg[:40]}...)")
    
    # Print summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    
    if working_models:
        print(f"✓ {len(working_models)} models work with Copilot API:")
        print()
        for model in working_models:
            matching_result = next(r for r in results if r["model"] == model)
            response_model = matching_result.get("response_model", "unknown")
            print(f"  • {model:30s} (responds as: {response_model})")
        print()
        
        # Categorize models
        print("Recommended configuration:")
        print()
        
        # Find best workers
        worker_fast = next((m for m in working_models if "mini" in m or "turbo" in m), working_models[0] if working_models else None)
        worker_reasoning = next((m for m in working_models if "4o" in m or "opus" in m), working_models[0] if working_models else None)
        judge_standard = next((m for m in working_models if "o1-mini" in m or "mistral" in m), working_models[0] if working_models else None)
        judge_premium = next((m for m in working_models if "o1" in m and "mini" not in m or "405b" in m or "opus" in m), working_models[0] if working_models else None)
        
        print(f"  WORKER_PRAGMATIC:  {worker_fast}")
        print(f"  WORKER_REASONING:  {worker_reasoning}")
        print(f"  JUDGE_STANDARD:    {judge_standard}")
        print(f"  JUDGE_PREMIUM:     {judge_premium}")
        print()
    else:
        print("❌ No models work with Copilot API")
        print()
        print("This could mean:")
        print("  1. Your GitHub token doesn't have Copilot access")
        print("  2. The Copilot API endpoint has changed")
        print("  3. Authentication method needs updating")
        print()
    
    # Print detailed failure analysis
    failed_models = [r for r in results if not r["success"]]
    if failed_models:
        print()
        print("Failed models breakdown:")
        error_counts = {}
        for r in failed_models:
            error_msg = (r["error"] or f"HTTP {r['status_code']}")[:50]
            error_counts[error_msg] = error_counts.get(error_msg, 0) + 1
        
        for error, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            print(f"  • {count:2d} models: {error}")
        print()


if __name__ == "__main__":
    main()
