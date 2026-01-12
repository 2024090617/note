# 基于对话的文件生成与推送 GitHub 系统设计文档

## 一、项目概述

本项目旨在开发一个**基于对话交互的文件生成系统**，通过自然语言多轮对话理解用户需求，自动生成对应文件，并推送至指定 GitHub 仓库。系统前端提供简洁聊天界面，后端采用 Flask 实现业务逻辑，深度集成 **DeepSeek 大模型** 用于自然语言处理和文件生成。

## 二、系统架构设计

### 1. 技术栈

| 层次    | 技术选型                   |
| ----- | ---------------------- |
| 前端    | HTML + JS + CSS        |
| 后端    | Flask + Flask-Session  |
| 大模型接口 | DeepSeek Chat API      |
| 持久化存储 | GitHub 仓库（通过 PyGithub） |

### 2. 模块划分

- **前端 UI**：对话输入输出，生成文件触发按钮
- **会话管理**：Flask-Session 实现多轮对话状态跟踪
- **指令解析模块**：大模型解析用户意图 → 结构化 JSON
- **内容生成模块**：大模型根据指令生成文件内容
- **GitHub 操作模块**：使用 PyGithub 创建或更新仓库文件

### 3. 流程图

```
用户输入需求 → 发送给后端 →
  → [调用大模型：结构化解析]
      → 文件名、路径、操作类型、内容（可选）
          → [若内容为空 → 调用大模型生成内容]
              → GitHub 推送 → 返回结果给前端
```

## 三、交互逻辑设计

### 1. 多轮对话逻辑

- Session 中存储 `history` 列表：[{role: "user", content: "..."}, ...]
- 每次请求携带 `history`，实现上下文理解
- 特殊 `/generate` 路径：对话之外，触发文件生成

### 2. Prompt 设计

#### （1）指令解析 Prompt

```
你是一个代码助手，请将用户的需求解析成结构化 JSON。
输出格式如下：
{
  "operation": "create | update | delete",
  "fileName": "string",
  "filePath": "string （默认 '/'）",
  "content": "string （如果为空，请设置为 null）"
}
```

#### （2）内容生成 Prompt

```
你是一个专业的开源项目文档撰写专家。
请为项目 {项目名称} 生成一份 README.md 文件，包含简介、安装方法、使用方法、许可证、联系方式。
```

### 3. DeepSeek API 调用示例

```python
headers = {"Authorization": "Bearer sk-xxxx", "Content-Type": "application/json"}
data = {"model": "deepseek-chat", "messages": messages}
response = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data)
```

## 四、核心代码结构

### 1. Flask 路由

```python
@app.route("/chat")  # 多轮对话（自然语言理解）
@app.route("/generate")  # 文件生成 + GitHub 推送
```

### 2. GitHub 文件推送逻辑

```python
def push_to_github(file_path, content, commit_message):
    repo = Github(GITHUB_TOKEN).get_repo(GITHUB_REPO)
    try:
        contents = repo.get_contents(file_path)
        repo.update_file(file_path, commit_message, content, sha=contents.sha)
    except Exception:
        repo.create_file(file_path, commit_message, content)
```

## 五、实战操作指南

### 1. 安装依赖

```
pip install Flask Flask-Session requests PyGithub
```

### 2. 启动项目

```
python main.py
```

访问：[http://localhost:5000](http://localhost:5000)

### 3. 配置项

- **DeepSeek API KEY**：`DEEPSEEK_API_KEY = "sk-xxxx"`
- **GitHub Token**：需具备 repo 权限
- **GITHUB\_REPO**：格式 "username/repo"

## 六、后续优化方向

1. 支持多用户并发会话（数据库存储会话）
2. 文件类型多样化（支持代码片段、配置文件等）
3. UI 优化（WebSocket、Loading 动画、消息气泡）
4. Docker 化部署 + Nginx 反向代理
5. 接入权限认证和 API 限流

## 七、总结

本项目完整展示了**自然语言对话生成 → 结构化需求 → 文件生成 → GitHub 推送**的完整链路，适用于自动化文档生成、项目初始化等场景。通过与大模型（DeepSeek）的结合，具备高度智能化和灵活性，未来可拓展性强。

