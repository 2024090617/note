# Thesis Writing Agent (学位论文写作助手)

AI-powered thesis writing assistant with academic paper search, RAG-based content generation, and automatic document formatting.

## Features

### 📚 Academic Paper Management
- **Multi-source search**: ArXiv, Semantic Scholar
- **Automatic metadata extraction**: DOI, authors, citations, abstracts
- **Knowledge base integration**: Store papers in Qdrant vector database
- **Bilingual support**: Chinese and English papers

### ✍️ AI-Powered Writing
- **RAG (Retrieval-Augmented Generation)**: Generate content based on collected papers
- **Chinese-first**: Professional academic Chinese writing
- **Citation management**: GB/T 7714-2015, APA, IEEE formats
- **Outline generation**: Structured thesis organization
- **Section refinement**: Iterative improvement based on feedback

### 📄 Document Export
- **LLM-based formatting interpretation**: Natural language format specs → concrete rules
- **.docx generation**: Microsoft Word compatible documents
- **Chinese typography**: Proper CJK fonts, spacing, punctuation
- **Automatic formatting**: Table of contents, references, page numbers

## Installation

```bash
# Install llm-service with thesis support
cd llm-service
pip install -e .
pip install python-docx

# Ensure knowledge-base is running
cd ../knowledge-base
docker compose up -d  # Start Qdrant
python -m notebook.api  # Start API server
```

## Quick Start

### 1. Search and Collect Papers

```bash
# Search papers (automatically added to knowledge base)
llm thesis search "深度学习在自然语言处理中的应用"

# Search from specific sources
llm thesis search "Transformer models" --sources arxiv --limit 20

# List papers in knowledge base
llm thesis list-papers --tags thesis --limit 20
```

### 2. Generate Outline

```bash
# Generate thesis outline
llm thesis outline "基于Transformer的文本分类研究" -o outline.json

# With additional requirements
llm thesis outline "Deep Learning for NLP" -r "包括实验分析章节"
```

### 3. Write Sections with RAG

```bash
# Write a section (uses knowledge base for context)
llm thesis write -s 1.1 -t "研究背景" -o sections/1.1.md

# Write with specific requirements
llm thesis write -s 2.1 -t "相关工作" -w 1200 -r "重点介绍Transformer架构"

# Write without RAG
llm thesis write -s 3.1 -t "方法设计" --no-rag
```

### 4. Export to .docx

```bash
# Export thesis to Word document
llm thesis export thesis.docx \
  --title "基于Transformer的中文文本分类研究" \
  --author "张三" \
  --institution "示例大学" \
  --advisor "李教授" \
  --format "标准中国高校硕士学位论文"

# Different formatting specification
llm thesis export output.docx \
  --title "My Thesis" \
  --author "Author Name" \
  --format "北京大学硕士学位论文格式要求"
```

### 5. Generate Bibliography

```bash
# Generate bibliography
llm thesis citations

# Different citation style
llm thesis citations -s APA -o references.txt

# GB/T 7714-2015 (Chinese standard)
llm thesis citations -s GB/T7714-2015
```

## Python API

### Complete Workflow Example

```python
from llm_service.thesis import ThesisAgent, CitationStyle

# Initialize agent
agent = ThesisAgent(citation_style=CitationStyle.GB_T_7714)

# 1. Search and collect papers
papers = agent.search_papers(
    query="Transformer模型在自然语言处理中的应用",
    sources=["arxiv", "semantic_scholar"],
    limit=20,
    auto_add=True  # Automatically add to knowledge base
)

# 2. Generate outline
outline = agent.generate_outline(
    topic="基于Transformer的中文文本分类方法研究",
    requirements="包括实验分析和对比研究"
)

# 3. Write sections with RAG
section = agent.write_section(
    section_id="1.1",
    section_title="研究背景",
    target_words=800,
    user_requirements="介绍Transformer模型的发展历程",
    use_rag=True  # Use knowledge base for context
)

# 4. Save section to markdown
agent.save_section("1.1", "sections/1.1_研究背景.md")

# 5. Refine section based on feedback
refined = agent.refine_section(
    section_id="1.1",
    feedback="添加更多关于BERT模型的内容"
)

# 6. Write more sections
agent.write_section("1.2", "研究意义", target_words=600)
agent.write_section("2.1", "相关工作", target_words=1200)

# 7. Export to .docx
agent.export_docx(
    output_path="thesis.docx",
    formatting_spec="标准中国高校硕士学位论文",
    include_cover=True,
    title=outline.title,
    author="张三",
    institution="示例大学",
    advisor="李教授",
    date="2026年1月"
)
```

### Paper Management

```python
# Get paper by ArXiv ID
from llm_service.thesis import PaperFetcher

fetcher = PaperFetcher()
paper = fetcher.get_paper_by_arxiv_id("2301.12345")

# Get paper by DOI
paper = fetcher.get_paper_by_doi("10.1234/example")

# Enrich paper metadata
enriched = fetcher.enrich_paper_metadata(paper)

# Add papers to knowledge base
agent.add_papers_to_kb([paper])
```

### Citation Formatting

```python
from llm_service.thesis import CitationManager, CitationStyle

# Initialize citation manager
citations = CitationManager(style=CitationStyle.GB_T_7714)

# Add papers
key1 = citations.add_paper(paper1)
key2 = citations.add_paper(paper2)

# Format inline citation
inline = citations.format_inline_citation([key1, key2])  # "[1,2]"

# Generate bibliography
references = citations.generate_bibliography()

# Export BibTeX
bibtex = citations.export_bibtex()
```

### Document Formatting

```python
from llm_service.thesis import FormattingInterpreter, create_thesis_document

# Interpret natural language formatting spec
interpreter = FormattingInterpreter()
formatting = interpreter.interpret("标准中国高校硕士学位论文")

# Create document
create_thesis_document(
    sections=[section1, section2, section3],
    references=references,
    formatting_spec="标准中国高校硕士学位论文",
    title="论文标题",
    author="作者",
    output_path="thesis.docx",
    institution="学校名称",
    advisor="导师姓名"
)
```

## Formatting Specifications

The agent can interpret natural language formatting requirements and apply them to .docx documents.

### Supported Specifications

- **"标准中国高校硕士学位论文"** - Standard Chinese university master's thesis
- **"北京大学硕士学位论文格式"** - Peking University format
- **"清华大学博士学位论文格式"** - Tsinghua University PhD format
- **Custom specifications** - Describe your requirements in Chinese or English

### Example Interpreted Rules

Input: `"标准中国高校硕士学位论文"`

Output formatting rules:
- **Page margins**: 上下2.54cm, 左右3.17cm
- **Body font**: 中文宋体, English Times New Roman, 小四号(12pt)
- **Line spacing**: 1.5倍行距
- **First line indent**: 2字符
- **Headings**: 
  - Level 1: 黑体三号 (16pt)
  - Level 2: 黑体四号 (14pt)
  - Level 3: 黑体小四 (12pt)
- **Citation style**: GB/T 7714-2015

## Architecture

```
ThesisAgent
├── PaperFetcher          # Search ArXiv, Semantic Scholar
├── CitationManager       # GB/T 7714-2015, APA, IEEE
├── FormattingInterpreter # LLM-based format parsing
├── ThesisDocxGenerator   # python-docx with CJK support
└── KnowledgeBase (Qdrant) # Vector storage for papers
```

## File Structure

```
llm-service/src/llm_service/thesis/
├── __init__.py
├── agent.py              # ThesisAgent (main class)
├── paper_fetcher.py      # ArXiv, Semantic Scholar APIs
├── citation_manager.py   # Citation formatting
├── docx_generator.py     # Document generation
├── prompts.py            # Chinese prompts
└── models.py             # Data models
```

## Citation Formats

### GB/T 7714-2015 (Chinese National Standard)

```
[1] Zhang L, Wang H, Li M, et al. Deep Learning for Natural Language Processing[J]. 
    Journal of AI Research, 2023, 15(3): 123-145. DOI: 10.1234/example.
```

### APA

```
[1] Zhang, L., Wang, H., Li, M., et al. (2023). Deep Learning for Natural 
    Language Processing. *Journal of AI Research*, 15(3), 123-145. 
    https://doi.org/10.1234/example
```

### IEEE

```
[1] L. Zhang, H. Wang, M. Li et al., "Deep Learning for Natural Language Processing," 
    *Journal of AI Research*, vol. 15, no. 3, pp. 123-145, 2023. doi: 10.1234/example
```

## Demo

Run the included demo to see the complete workflow:

```bash
cd llm-service/examples
python thesis_writer_demo.py
```

The demo will:
1. Search 5 papers on "Transformer模型在自然语言处理中的应用"
2. Generate a thesis outline
3. Write two sections using RAG
4. Generate bibliography in GB/T 7714-2015 format
5. Export to .docx with Chinese formatting

## Troubleshooting

### Knowledge Base Connection Failed

Ensure Qdrant is running:
```bash
cd knowledge-base
docker compose up -d
```

### python-docx Not Found

Install the dependency:
```bash
pip install python-docx
```

### Formatting Issues in .docx

1. Open the document in Microsoft Word
2. Right-click on "目录" (Table of Contents)
3. Select "Update Field" → "Update Entire Table"
4. Check that Chinese fonts (宋体, 黑体) are installed on your system

### ArXiv/Semantic Scholar API Errors

- **Rate limiting**: Add delays between requests
- **Network issues**: Check internet connection
- **API changes**: Update paper_fetcher.py if needed

## Advanced Features

### Custom System Prompts

```python
from llm_service.thesis.prompts import THESIS_WRITER_SYSTEM_PROMPT

custom_prompt = """
你是一位计算机科学领域的学术论文写作专家。
重点关注深度学习和自然语言处理方向。
"""

# Use in agent initialization (modify agent.py)
```

### Custom Formatting Rules

```python
from llm_service.thesis import FormattingRules, ThesisDocxGenerator

# Define custom formatting
custom_format = FormattingRules(
    page_margins={"top": "3cm", "bottom": "3cm", "left": "4cm", "right": "2cm"},
    body_font={"chinese": "仿宋", "english": "Arial"},
    body_font_size="14pt",
    line_spacing=2.0,
    citation_style="APA"
)

# Use in document generation
generator = ThesisDocxGenerator(custom_format)
```

### Batch Paper Processing

```python
# Search multiple topics
topics = [
    "Transformer architecture",
    "BERT pretraining",
    "Attention mechanisms",
    "Transfer learning NLP"
]

all_papers = []
for topic in topics:
    papers = agent.search_papers(topic, limit=10)
    all_papers.extend(papers)

print(f"Collected {len(all_papers)} papers")
```

## Contributing

The thesis module is part of the llm-service project. Contributions welcome!

### Extending Paper Sources

Add new academic databases in `paper_fetcher.py`:

```python
def search_pubmed(self, query: str, limit: int = 10) -> List[PaperMetadata]:
    """Search PubMed for biomedical papers."""
    # Implement PubMed API integration
    pass
```

### Adding Citation Styles

Extend `citation_manager.py`:

```python
def _format_chicago(self, citation_key: str, paper: PaperMetadata) -> str:
    """Format citation in Chicago style."""
    # Implement Chicago Manual of Style formatting
    pass
```

## License

MIT License - See llm-service/LICENSE for details.
