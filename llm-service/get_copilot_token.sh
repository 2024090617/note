#!/bin/bash
# Extract GitHub Copilot OAuth token from macOS Keychain

echo "Searching for GitHub Copilot tokens in macOS Keychain..."
echo

# Search for Copilot-related tokens
security find-generic-password -s "github.copilot" -w 2>/dev/null && echo "✓ Found github.copilot token" && exit 0
security find-generic-password -s "vscode.github-authentication" -w 2>/dev/null && echo "✓ Found GitHub auth token" && exit 0
security find-generic-password -a "github.copilot" -w 2>/dev/null && echo "✓ Found Copilot account token" && exit 0

echo "❌ No Copilot tokens found in Keychain"
echo
echo "Available Copilot-related keychain entries:"
security dump-keychain | grep -i copilot | head -5

echo
echo "To manually extract, try:"
echo '  security find-generic-password -l "copilot" -w'
