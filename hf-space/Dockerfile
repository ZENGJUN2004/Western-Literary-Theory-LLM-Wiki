# 西方文论 Wiki AI —— Hugging Face Spaces Docker
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码与知识库静态资源
COPY server.py .
COPY README.md .
COPY wiki-site/docs ./wiki-site/docs

# 数据文件（QA 索引）应存在
RUN test -f wiki-site/docs/qa-index.json && echo "QA index OK"

EXPOSE 7860

ENV PORT=7860

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
