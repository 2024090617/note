from pydantic import BaseModel
from typing import List, Dict
import os
from dotenv import load_dotenv

load_dotenv()

class SourceConfig(BaseModel):
    url: str
    type: str  # 'blog', 'wechat', 'website'
    name: str
    selector: str  # CSS selector for content

class Config(BaseModel):
    sources: List[SourceConfig]
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    output_dir: str = "data/summaries"
    schedule_time: str = "00:00"  # Daily schedule time

# 示例配置
DEFAULT_CONFIG = Config(
    sources=[
        SourceConfig(
            url="https://www.qbitai.com/",
            type="website",
            name="量子位",
            selector="div.article_list"
        ),
    ],
    output_dir="data/summaries",
    schedule_time="00:00"
) 