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
    -H 'Content-Type: application/json' \
    -d '{"query":"how to store notes in qdrant?","limit":5}'
```

### 4) 导入已有 summaries

将 `data/summaries/summary_*.json` 导入 Qdrant：

```bash
python src/ingest_summaries.py
```

### 环境变量

- `QDRANT_URL`（默认 `http://localhost:6333`）
- `QDRANT_COLLECTION`（默认 `notebook`）
- `EMBEDDING_PROVIDER`（默认 `local`，可选 `deepseek`）
- `LOCAL_EMBEDDING_MODEL`（默认 `sentence-transformers/all-MiniLM-L6-v2`）
- `DEEPSEEK_API_KEY`（当 `EMBEDDING_PROVIDER=deepseek` 时必填）

## 目录结构

```
knowledge-base/
├── config/
│   └── config.py
├── src/
│   ├── main.py
│   ├── crawler.py
│   └── summarizer.py
├── data/
│   └── summaries/
├── requirements.txt
└── README.md
```

## 注意事项

1. 确保你有有效的 DeepSeek API 密钥
2. 根据目标网站的具体情况调整 CSS 选择器
3. 遵守目标网站的爬虫政策和使用条款 