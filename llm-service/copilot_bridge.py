#!/usr/bin/env python3
"""
Access Copilot models by leveraging VS Code's Language Model API.

This creates a bridge between the dual-worker framework and VS Code's Copilot.
"""

import sys
import os
import json
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def create_vscode_extension_for_copilot():
    """
    Create a minimal VS Code extension that exposes Copilot models via HTTP.
    
    This extension will run inside VS Code and provide an HTTP endpoint
    that our dual-worker framework can call.
    """
    
    extension_dir = Path.home() / ".vscode/extensions/copilot-bridge-1.0.0"
    extension_dir.mkdir(parents=True, exist_ok=True)
    
    # package.json
    package_json = {
        "name": "copilot-bridge",
        "displayName": "Copilot Bridge",
        "description": "Bridge to access Copilot models from external tools",
        "version": "1.0.0",
        "engines": {"vscode": "^1.85.0"},
        "activationEvents": ["onStartupFinished"],
        "main": "./extension.js",
        "contributes": {
            "commands": [{
                "command": "copilotBridge.startServer",
                "title": "Start Copilot Bridge Server"
            }]
        },
        "extensionDependencies": ["github.copilot-chat"]
    }
    
    with open(extension_dir / "package.json", "w") as f:
        json.dump(package_json, f, indent=2)
    
    # extension.js
    extension_js = '''
const vscode = require('vscode');
const http = require('http');

let server = null;

function activate(context) {
    console.log('Copilot Bridge activated');
    
    // Start HTTP server to bridge Copilot API
    const port = 19823;
    
    server = http.createServer(async (req, res) => {
        if (req.method === 'POST' && req.url === '/chat') {
            let body = '';
            req.on('data', chunk => body += chunk);
            req.on('end', async () => {
                try {
                    const data = JSON.parse(body);
                    const model = data.model || 'gpt-5';
                    const messages = data.messages || [];
                    
                    // Get Copilot language model
                    const models = await vscode.lm.selectChatModels({
                        vendor: 'copilot',
                        family: model
                    });
                    
                    if (models.length === 0) {
                        res.writeHead(404);
                        res.end(JSON.stringify({error: `Model ${model} not found`}));
                        return;
                    }
                    
                    const lm = models[0];
                    
                    // Create chat messages
                    const chatMessages = messages.map(m => {
                        if (m.role === 'system') {
                            return vscode.LanguageModelChatMessage.User(m.content);
                        } else if (m.role === 'user') {
                            return vscode.LanguageModelChatMessage.User(m.content);
                        } else {
                            return vscode.LanguageModelChatMessage.Assistant(m.content);
                        }
                    });
                    
                    // Send request
                    const response = await lm.sendRequest(
                        chatMessages,
                        {},
                        new vscode.CancellationTokenSource().token
                    );
                    
                    // Collect response
                    let content = '';
                    for await (const part of response.text) {
                        content += part;
                    }
                    
                    res.writeHead(200, {'Content-Type': 'application/json'});
                    res.end(JSON.stringify({
                        choices: [{
                            message: {role: 'assistant', content: content},
                            finish_reason: 'stop'
                        }],
                        model: model
                    }));
                    
                } catch (error) {
                    res.writeHead(500);
                    res.end(JSON.stringify({error: error.message}));
                }
            });
        } else if (req.method === 'GET' && req.url === '/models') {
            try {
                const models = await vscode.lm.selectChatModels({vendor: 'copilot'});
                const modelList = models.map(m => ({
                    id: m.id,
                    name: m.name,
                    vendor: m.vendor,
                    family: m.family,
                    version: m.version,
                    maxInputTokens: m.maxInputTokens
                }));
                
                res.writeHead(200, {'Content-Type': 'application/json'});
                res.end(JSON.stringify(modelList));
            } catch (error) {
                res.writeHead(500);
                res.end(JSON.stringify({error: error.message}));
            }
        } else {
            res.writeHead(404);
            res.end('Not found');
        }
    });
    
    server.listen(port, '127.0.0.1', () => {
        console.log(`Copilot Bridge server running on http://127.0.0.1:${port}`);
        vscode.window.showInformationMessage(`Copilot Bridge running on port ${port}`);
    });
    
    context.subscriptions.push({
        dispose: () => {
            if (server) server.close();
        }
    });
}

function deactivate() {
    if (server) server.close();
}

module.exports = { activate, deactivate };
'''
    
    with open(extension_dir / "extension.js", "w") as f:
        f.write(extension_js)
    
    print(f"✓ Created VS Code extension at: {extension_dir}")
    print()
    print("To use Copilot models:")
    print("1. Restart VS Code")
    print("2. Run command: 'Start Copilot Bridge Server'")
    print("3. The bridge will be available at http://127.0.0.1:19823")
    print()
    print("Endpoints:")
    print("  GET  /models  - List available models")
    print("  POST /chat    - Send chat completion request")
    print()
    
    return extension_dir


def test_copilot_bridge():
    """Test if the Copilot bridge is running."""
    import requests
    
    try:
        response = requests.get("http://127.0.0.1:19823/models", timeout=2)
        if response.status_code == 200:
            models = response.json()
            print(f"✓ Copilot Bridge is running with {len(models)} models")
            for m in models:
                print(f"  • {m.get('family', m.get('id'))}")
            return True
    except:
        pass
    
    print("✗ Copilot Bridge not running")
    print("  Start VS Code and run the 'Start Copilot Bridge Server' command")
    return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Copilot Bridge for dual-worker framework")
    parser.add_argument("--install", action="store_true", help="Install VS Code extension")
    parser.add_argument("--test", action="store_true", help="Test bridge connection")
    args = parser.parse_args()
    
    if args.install:
        create_vscode_extension_for_copilot()
    elif args.test:
        test_copilot_bridge()
    else:
        print("GitHub Copilot Bridge")
        print()
        print("This tool helps access Copilot models (GPT-5, Claude Opus 4.5, etc.)")
        print("from the dual-worker framework by bridging through VS Code.")
        print()
        print("Usage:")
        print("  python copilot_bridge.py --install  # Install VS Code extension")
        print("  python copilot_bridge.py --test     # Test bridge connection")
        print()
        print("After installation:")
        print("1. Restart VS Code")
        print("2. Run: Ctrl+Shift+P -> 'Start Copilot Bridge Server'")
        print("3. The dual-worker framework will automatically use Copilot models")
