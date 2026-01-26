"""Tests for Confluence MCP"""

import pytest
from confluence_mcp.config import ConfluenceConfig, ConfluenceType


class TestConfiguration:
    """Test configuration loading"""
    
    def test_config_cloud(self, monkeypatch):
        """Test Cloud configuration"""
        monkeypatch.setenv("CONFLUENCE_URL", "https://test.atlassian.net")
        monkeypatch.setenv("CONFLUENCE_USERNAME", "user@test.com")
        monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token123")
        monkeypatch.setenv("CONFLUENCE_TYPE", "cloud")
        
        config = ConfluenceConfig.from_env()
        
        assert config.base_url == "https://test.atlassian.net"
        assert config.confluence_type == ConfluenceType.CLOUD
        assert config.api_base == "https://test.atlassian.net/wiki/rest/api"
    
    def test_config_server(self, monkeypatch):
        """Test Server configuration"""
        monkeypatch.setenv("CONFLUENCE_URL", "https://confluence.test.com")
        monkeypatch.setenv("CONFLUENCE_PAT", "pat123")
        monkeypatch.setenv("CONFLUENCE_TYPE", "server")
        
        config = ConfluenceConfig.from_env()
        
        assert config.base_url == "https://confluence.test.com"
        assert config.confluence_type == ConfluenceType.SERVER
        assert config.api_base == "https://confluence.test.com/rest/api"
    
    def test_auth_headers_basic(self, monkeypatch):
        """Test basic auth headers"""
        monkeypatch.setenv("CONFLUENCE_URL", "https://test.atlassian.net")
        monkeypatch.setenv("CONFLUENCE_USERNAME", "user@test.com")
        monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token123")
        
        config = ConfluenceConfig.from_env()
        headers = config.auth_headers
        
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")
    
    def test_auth_headers_pat(self, monkeypatch):
        """Test PAT auth headers"""
        monkeypatch.setenv("CONFLUENCE_URL", "https://test.atlassian.net")
        monkeypatch.setenv("CONFLUENCE_PAT", "pat123")
        
        config = ConfluenceConfig.from_env()
        headers = config.auth_headers
        
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer pat123"


if __name__ == "__main__":
    pytest.main([__file__])
