---
title: 西方文论 Wiki AI
emoji: 📚
colorFrom: indigo
colorTo: violet
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: 西方文论知识库智能问答后端（FastAPI + DeepSeek）
---

# 西方文论 Wiki AI

基于西方文论知识库（1381 页面）的智能问答后端。FastAPI + BM25 检索 + DeepSeek LLM 流式整合回答。

## 本地运行

```bash
export DEEPSEEK_API_KEY=sk-xxxx
pip install -r requirements.txt
python server.py
# 问答页: http://localhost:8000/qa.html
```

## 端口

容器默认监听 `7860`（Hugging Face Spaces 默认），可用 `PORT` 环境变量覆盖。
