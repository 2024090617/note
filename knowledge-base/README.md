# 个人知识库系统

这是一个基于 DeepSeek 大模型的个人知识库系统，可以自动从指定来源抓取内容并生成摘要。

## 功能特点

- 自动从指定网站、博客、公众号等来源抓取内容
- 使用 DeepSeek 模型生成内容摘要
- 支持定时任务，自动执行内容抓取和摘要生成
- 将摘要保存为结构化的 JSON 文件

## 安装

1. 克隆项目并安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量：
创建 `.env` 文件并添加你的 DeepSeek API 密钥：
```
DEEPSEEK_API_KEY=your_api_key_here
```

## 配置

在 `config/config.py` 中配置你的内容源：

```python
DEFAULT_CONFIG = Config(
    sources=[
        SourceConfig(
            url="https://example.com/blog",
            type="blog",
            name="Example Blog",
            selector="article.content"
        ),
        # 添加更多源...
    ],
    output_dir="data/summaries",
    schedule_time="00:00"
)
```

## 运行

启动系统：
```bash
python src/main.py
```

系统将按照配置的时间自动运行，抓取内容并生成摘要。摘要文件将保存在 `data/summaries` 目录下。

## 在线 Notebook（Qdrant + API）

本项目内置一个最小可用的“在线笔记本”服务：

- 使用 Qdrant 存储向量 + 笔记 payload（note_id、version、title、content、tags、status 等）
- 每次更新都会写入一个新版本（不可变），支持版本列表与语义检索

### 1) 启动 Qdrant

```bash
docker compose up -d
```

### 2) 启动 API

安装依赖：

```bash
pip install -r requirements.txt
```

启动：

```bash
uvicorn src.notebook.api:app --reload --port 8000
```

健康检查：

```bash
curl http://localhost:8000/health
```

### 3) 写入/搜索示例

创建笔记：

```bash
curl -X POST http://localhost:8000/notes \
    -H 'Content-Type: application/json' \
    -d '{"title":"Qdrant basics","content":"Vector DB + payload.","tags":["qdrant","rag"]}'
```

语义搜索：

```bash
curl -X POST http://localhost:8000/search \

For portable deployment (works offline, no internet required):

1. **Bundle the model with your project:**
```bash
mkdir -p models
cp -r ~/.cache/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2 models/
```

2. **Update `.env` to use local path:**
```dotenv
LOCAL_EMBEDDING_MODEL=./models/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/86741b4e3f5cb7765a600d3a3d55a0f6a6cb443d
```

This approach is ideal for:
- Air-gapped environments
- Migrating to Windows/other systems
- Avoiding first-time download delays

### Option 3: Use DeepSeek API

```dotenv
EMBEDDING_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-api-key
```

## Import Existing Summaries

Import summaries from `data/summaries/` into Qdrant:

```bash
python src/ingest_summaries.py
```

This will process all `summary_*.json` files and create searchable notes.

## Integration with LLM Service

This knowledge base integrates with the `llm-service` for RAG (Retrieval-Augmented Generation):

```python
from notebook.storage import get_store
from llm_service import LLMClient, Message, MessageRole

# Initialize knowledge base
kb_store = get_store()
kb_store.ensure_collection()

# Search for context
results = kb_store.search("Python best practices", limit=3)

# Use with LLM
client = LLMClient()
context = "\n".join([r['content'] for r in results])
response = client.simple_query(
    f"Context: {context}\n\nQuestion: How to write clean Python code?"
)
```

See `llm-service/examples/knowledge_base_agent.py` for a complete RAG agent example.

## Project Structure

```
knowledge-base/
├── config/
│   ├── __init__.py
│   └── config.py              # Configuration settings
├── src/
│   ├── notebook/
│   │   ├── __init__.py
│   │   ├── api.py             # FastAPI REST endpoints
│   │   ├── embedder.py        # Embedding generation
│   │   ├── models.py          # Data models
│   │   ├── parsers.py         # Content parsers
│   │   ├── settings.py        # Settings management
│   │   └── storage.py         # Qdrant storage layer
│   ├── crawler.py             # Web scraping
│   ├── summarizer.py          # Content summarization
│   └── ingest_summaries.py    # Import existing data
├── data/
│   └── summaries/             # Saved summaries (JSON)
├── qdrant_data/               # Qdrant database files
├── models/                    # Bundled embedding models (optional)
├── static/
│   └── index.html             # Web UI
├── docker-compose.yml         # Qdrant setup
├── requirements.txt
├── .env                       # Environment configuration
└── README.md
```

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `QDRANT_URL` | Qdrant server URL | `http://localhost:6333` |
| `QDRANT_COLLECTION` | Collection name | `notebook` |
| `EMBEDDING_PROVIDER` | Embedding provider (`local` or `deepseek`) | `local` |
| `LOCAL_EMBEDDING_MODEL` | Model name or path | `paraphrase-multilingual-MiniLM-L12-v2` |
| `DEEPSEEK_API_KEY` | DeepSeek API key (for embeddings) | - |
| `GITHUB_TOKEN` | GitHub token (for LLM integration) | - |

## Migration to Windows

To migrate this project to Windows:

1. **Copy the entire project folder**
2. **Bundle the embedding model** (see Option 2 above)
3. **On Windows:**
   - Install Python 3.8+
   - Install Docker Desktop
   - Run `pip install -r requirements.txt`
   - Start Qdrant: `docker compose up -d`
   - Start API: `uvicorn src.notebook.api:app --reload --port 8000`

The bundled model path (`./models/...`) works on both macOS and Windows!

## Best Practices

1. ✅ **Use local embedding models** for offline capability and faster performance
2. ✅ **Version your notes** using the built-in versioning system
3. ✅ **Tag your content** properly for better organization
4. ✅ **Backup Qdrant data** regularly (the `qdrant_data/` directory)
5. ⚠️ **Respect website ToS** when scraping content
6. ⚠️ **Secure your API keys** - never commit `.env` to version control

## Troubleshooting

### Qdrant Connection Error
```bash
# Check if Qdrant is running
docker ps | grep qdrant

# Restart Qdrant
docker compose restart
```

### Model Download Issues
```bash
# Pre-download the model manually
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### Import Errors
```bash
# Ensure you're in the correct conda environment
conda activate py312

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## License

MIT

## Contributing

Contributions welcome! Please open an issue or submit a pull request. 