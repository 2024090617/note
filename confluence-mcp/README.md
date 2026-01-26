# Confluence MCP Server

A Model Context Protocol (MCP) server for seamless integration with Atlassian Confluence. Read, write, update Confluence pages with full support for **multi-tabs and tables**.

## Features

✅ **Multi-Tab Support** - Automatically parse and extract tab groups from Confluence pages
✅ **Table Parsing** - Convert complex tables to structured data (Markdown, JSON, HTML)
✅ **Cloud & Server** - Works with both Confluence Cloud and Server/Data Center
✅ **Full CRUD** - Create, read, update, delete pages
✅ **Search** - CQL (Confluence Query Language) and text search
✅ **Attachments** - List and manage page attachments
✅ **Comments** - Read and write page comments
✅ **Labels** - Manage page labels
✅ **MCP Compatible** - Works with any MCP client (Claude, VS Code, etc.)

## Installation

```bash
# Clone or navigate to the confluence-mcp directory
cd confluence-mcp

# Install in editable mode
pip install -e .
```

## Configuration

Set environment variables:

```bash
# Confluence Cloud
export CONFLUENCE_URL="https://your-company.atlassian.net"
export CONFLUENCE_USERNAME="your-email@company.com"
export CONFLUENCE_API_TOKEN="your-api-token"
export CONFLUENCE_TYPE="cloud"
export CONFLUENCE_DEFAULT_SPACE="DOCS"

# OR Confluence Server/Data Center
export CONFLUENCE_URL="https://confluence.company.com"
export CONFLUENCE_PAT="your-personal-access-token"
export CONFLUENCE_TYPE="server"
```

### Getting API Credentials

**Cloud:**
1. Go to https://id.atlassian.com/manage-profile/security
2. Create API token
3. Use token as `CONFLUENCE_API_TOKEN`

**Server/Data Center:**
1. Generate Personal Access Token in User Settings
2. Use as `CONFLUENCE_PAT`

## Usage

### As MCP Server (with Claude, VS Code, etc.)

```bash
# Run the server
confluence-mcp

# Or with custom config
CONFLUENCE_URL=... CONFLUENCE_API_TOKEN=... confluence-mcp
```

### Python Integration

```python
from confluence_mcp import ConfluenceClient, ConfluenceConfig

async with ConfluenceClient(ConfluenceConfig.from_env()) as client:
    # Get page by ID
    page = await client.get_page(page_id="123456")
    print(page.title, page.body_storage)
    
    # Get page by title
    page = await client.get_page(title="Release Notes", space_key="DOCS")
    
    # Create new page
    new_page = await client.create_page(
        title="New Feature",
        body="<p>Feature description</p>",
        space_key="DOCS",
        labels=["feature", "new"]
    )
    
    # Update page
    updated = await client.update_page(
        page_id="123456",
        body="<p>Updated content</p>",
        version_comment="Fixed typo"
    )
    
    # Search
    results = await client.search("implementation")
    
    # List spaces
    spaces = await client.get_spaces()
```

### Content Parsing

```python
from confluence_mcp import ContentParser

parser = ContentParser()

# Parse Confluence storage format
parsed = parser.parse(page.body_storage)

print(parsed["tables"])      # List of tables
print(parsed["tabs"])        # List of tab groups
print(parsed["code_blocks"]) # Code blocks
print(parsed["text"])        # Plain text

# Convert to Markdown
markdown = parser.extract_markdown()
```

## MCP Tools Reference

### confluence_get_page
Read a Confluence page with support for multi-tabs and tables.

```
confluence_get_page(
    space_key: str,              # Required
    page_id?: str,               # Optional, preferred method
    title?: str,                 # Optional, requires space_key
    format?: "json"|"markdown"|"html"  # Default: json
)
```

**Returns:**
```json
{
    "id": "123456",
    "title": "Page Title",
    "url": "https://...",
    "space": "DOCS",
    "version": 5,
    "labels": ["api", "documentation"],
    "content": {
        "tables": [...],         // Parsed tables with cells, colspan, rowspan
        "tabs": [...],           // Tab groups with tab contents
        "code_blocks": [...],    // Code blocks with language
        "text": "..."            // Plain text content
    },
    "format": "json"
}
```

### confluence_create_page
Create a new Confluence page.

```
confluence_create_page(
    title: str,
    content: str,
    space_key: str,
    parent_id?: str,
    labels?: string[]
)
```

### confluence_update_page
Update an existing page.

```
confluence_update_page(
    page_id: str,
    content: str,
    title?: str,
    version_comment?: str
)
```

### confluence_delete_page
Delete a page.

```
confluence_delete_page(page_id: str)
```

### confluence_search
Search using text or CQL.

```
confluence_search(
    query: str,
    space_key?: str,
    limit?: number,
    content_type?: "page"|"blogpost"
)
```

**CQL Examples:**
```
space = "DOCS" AND type = page AND text ~ "API"
lastModified >= -1w AND creator = currentUser()
label = "bug" AND priority = "High"
```

### confluence_get_children
Get child pages.

```
confluence_get_children(
    page_id: str,
    limit?: number
)
```

### confluence_get_attachments
List page attachments.

```
confluence_get_attachments(page_id: str)
```

### confluence_add_comment
Add comment to page.

```
confluence_add_comment(
    page_id: str,
    comment: str
)
```

### confluence_get_comments
Get page comments.

```
confluence_get_comments(page_id: str)
```

### confluence_add_labels
Add labels to page.

```
confluence_add_labels(
    page_id: str,
    labels: string[]
)
```

### confluence_get_spaces
List all spaces.

```
confluence_get_spaces(limit?: number)
```

## Multi-Tab Support

The parser automatically detects and extracts Confluence tab groups:

```json
{
    "type": "tabs",
    "tabs": [
        {
            "title": "Installation",
            "content": "Step 1: Install...",
            "identifier": "tab-1"
        },
        {
            "title": "Configuration",
            "content": "Configure...",
            "identifier": "tab-2"
        }
    ]
}
```

## Table Support

Complex tables are fully parsed with cell properties:

```json
{
    "type": "table",
    "rows": [
        {
            "is_header": true,
            "cells": [
                {"content": "Name", "header": true, "colspan": 1, "rowspan": 1},
                {"content": "Type", "header": true, "colspan": 1, "rowspan": 1}
            ]
        },
        {
            "is_header": false,
            "cells": [
                {"content": "User ID", "header": false, "colspan": 1, "rowspan": 1},
                {"content": "String", "header": false, "colspan": 1, "rowspan": 1}
            ]
        }
    ]
}
```

## Integration with Developer Agent

Use the Confluence MCP server with the Developer Agent:

```bash
# In Developer Agent config, add Confluence server:
export MCP_SERVERS='[
    {
        "name": "confluence",
        "command": "confluence-mcp",
        "env": {
            "CONFLUENCE_URL": "https://...",
            "CONFLUENCE_API_TOKEN": "..."
        }
    }
]'
```

Then in the agent:

```
/task Read the API documentation from Confluence and create a Python SDK
```

The agent can:
- Search for relevant documentation
- Parse pages with multi-tabs and tables
- Extract code examples
- Create new pages with implementation notes

## Troubleshooting

### "Invalid configuration" error

Check that all required environment variables are set:

```bash
echo $CONFLUENCE_URL
echo $CONFLUENCE_API_TOKEN
```

### "Unauthorized" error

- Verify API token is valid
- For Cloud, check CONFLUENCE_USERNAME is correct
- For Server/DC, verify PAT has appropriate permissions

### Tables/Tabs not parsing

Some Confluence instances may use different macro formats. Enable debug logging:

```bash
DEBUG=1 confluence-mcp
```

Check the `raw_html` field in response to see the exact format.

## Architecture

```
confluence-mcp/
├── config.py          # Configuration management
├── client.py          # Confluence REST API client (async)
├── parser.py          # Content parser (tabs, tables, etc.)
├── tools.py           # MCP tool definitions
├── server.py          # MCP server implementation
└── __init__.py        # Package exports
```

## Dependencies

- **mcp** - Model Context Protocol SDK
- **httpx** - Async HTTP client
- **pydantic** - Data validation
- **beautifulsoup4** - HTML/XML parsing
- **lxml** - XML processing
- **markdownify** - HTML to Markdown conversion

## License

MIT

## Support

For issues or questions:
1. Check the [Confluence API docs](https://developer.atlassian.com/cloud/confluence/rest/v2/)
2. Open an issue on GitHub
3. Enable debug logging for more details
