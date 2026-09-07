"""
西方文论 Wiki AI 问答后端
FastAPI + DeepSeek API，提供基于知识库的智能问答
用法: python server.py
依赖: pip install fastapi uvicorn httpx
"""
import json, math, re, sys, os
from pathlib import Path
from typing import Dict, List, Tuple
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn, httpx

# ── 配置 ──────────────────────────────────────────────
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

SCRIPT_DIR = Path(__file__).parent.resolve()
DOCS_DIR = SCRIPT_DIR / "wiki-site" / "docs"
QA_INDEX = DOCS_DIR / "qa-index.json"

# ── 加载知识库索引 ────────────────────────────────────
print("正在加载知识库索引...")
with open(QA_INDEX, "r", encoding="utf-8") as f:
    qa_data = json.load(f)

DOCS = qa_data["docs"]
AVG_LEN = qa_data["avg_len"]
TOTAL_DOCS = qa_data["total_docs"]
print(f"知识库已加载: {TOTAL_DOCS} 页面, {len(DOCS)} 文档")

# ── BM25 检索引擎（与前端 JS 逻辑一致）─────────────────
STOP_WORDS = set(
    "的 了 是 在 和 与 或 也 都 就 还 又 把 被 让 使 对 为 以 于 从 到 向 由 按 据 说 着 过 起 来 去 上 下 中 里 外 前 后 间 侧 们 这 那 些 某 其 此 该 它 他 她 你 我 什么 怎么 如何 为什么 哪些 哪个 请 帮 给 关于 对于 请问 一下".split()
)


def extract_terms(text: str) -> List[str]:
    """提取查询词: 中文 2-gram/3-gram + 英文单词"""
    terms = []
    en_words = re.findall(r"[a-zA-Z]{2,}", text)
    terms.extend(w.lower() for w in en_words)
    cn_chars = re.sub(r"[^一-龥]", "", text)
    for i in range(len(cn_chars) - 1):
        terms.append(cn_chars[i : i + 2])
        if i < len(cn_chars) - 2:
            terms.append(cn_chars[i : i + 3])
    return terms


def extract_query_terms(query: str) -> List[str]:
    """从问题中提取查询词（过滤停用词后做 n-gram）"""
    words = re.sub(r"[^一-龥a-zA-Z0-9？？]", " ", query).strip().split()
    filtered = [w for w in words if len(w) > 1 and w not in STOP_WORDS]
    text = "".join(filtered)
    return extract_terms(text)


def compute_df(query_terms: List[str]) -> Dict[str, int]:
    """计算文档频率"""
    df = {t: 0 for t in query_terms}
    for doc in DOCS:
        doc_lower = (doc["title"] + " " + " ".join(doc.get("sentences", []))).lower()
        for qt in query_terms:
            if qt in df and qt in doc_lower:
                df[qt] += 1
    return df


def bm25_score(query_terms, df, doc):
    """BM25 评分"""
    k1, b = 1.5, 0.75
    score = 0.0
    doc_text = doc["title"] + " " + " ".join(doc.get("sentences", []))
    doc_lower = doc_text.lower()
    title_lower = doc["title"].lower()
    tag_text = " ".join(doc.get("tags", [])).lower()
    dl = doc.get("len", 1)
    seen = set()
    for qt in query_terms:
        if qt in seen:
            continue
        seen.add(qt)
        df_val = df.get(qt, 0)
        if df_val == 0:
            continue
        f = doc_lower.count(qt)
        title_f = title_lower.count(qt)
        tag_f = tag_text.count(qt)
        if f == 0 and title_f == 0 and tag_f == 0:
            continue
        idf = math.log((TOTAL_DOCS - df_val + 0.5) / (df_val + 0.5) + 1)
        combined_f = f + 3 * title_f + 2 * tag_f
        tf_norm = (combined_f * (k1 + 1)) / (combined_f + k1 * (1 - b + b * dl / AVG_LEN))
        score += idf * tf_norm
    return score


def extract_relevant_sentences(query_terms, doc, max_n=3):
    """从文档中提取最相关句子"""
    sentences = doc.get("sentences", [])
    scored = []
    for idx, s in enumerate(sentences):
        s_lower = s.lower()
        s_score = sum(3 if len(qt) >= 3 else 1 for qt in query_terms if qt.lower() in s_lower)
        if s_score > 0:
            scored.append({"text": s, "score": s_score, "idx": idx})
    scored.sort(key=lambda x: -x["score"])
    return scored[:max_n]


def retrieve(query: str, top_k: int = 5) -> Tuple[List[dict], List[dict]]:
    """BM25 检索: 返回 (top_docs, passages)"""
    query_terms = extract_query_terms(query)
    if not query_terms:
        return [], []
    df = compute_df(query_terms)
    scored = []
    for doc in DOCS:
        s = bm25_score(query_terms, df, doc)
        if s > 0:
            scored.append({"doc": doc, "score": s})
    scored.sort(key=lambda x: -x["score"])
    top = scored[:top_k]
    # 收集段落
    passages = []
    for item in top:
        sents = extract_relevant_sentences(query_terms, item["doc"], 3)
        for s in sents:
            passages.append({
                "text": s["text"],
                "title": item["doc"]["title"],
                "slug": item["doc"]["slug"],
                "type": item["doc"]["type"],
                "score": item["score"],
            })
    return top, passages


# ── DeepSeek API 调用 ──────────────────────────────────
SYSTEM_PROMPT = """你是西方文论知识库的学术问答助手。请根据用户提问和检索到的知识库段落，生成准确、学术、连贯的整合回答。

要求：
1. 回答必须基于检索到的段落内容，不要编造未提供的知识
2. 在关键论点后用 [序号] 标注引用来源
3. 组织逻辑：先定义核心概念，再展开主要观点，最后补充具体例证
4. 使用学术但易懂的中文，避免口语化
5. 如果检索段落不足以回答问题，如实说明并建议查阅相关页面
6. 回答控制在 300-500 字以内"""


def build_context(passages: List[dict]) -> str:
    """构建发送给 LLM 的上下文"""
    parts = []
    for i, p in enumerate(passages, 1):
        parts.append(f"[{i}] 来源：{p['title']}\n{p['text']}")
    return "\n\n".join(parts)


async def stream_deepseek(query: str, context: str, sources: List[dict]):
    """调用 DeepSeek API 并流式返回"""
    # 先发送来源信息
    yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"

    user_msg = f"用户提问：{query}\n\n检索到的知识库段落：\n{context}\n\n请基于以上段落生成整合回答。"

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "stream": True,
        "max_tokens": 1024,
        "temperature": 0.3,
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST", DEEPSEEK_API_URL, json=payload, headers=headers
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                try:
                    err = json.loads(body)
                    msg = err.get("error", {}).get("message", f"HTTP {resp.status_code}")
                except Exception:
                    msg = f"DeepSeek API 返回 HTTP {resp.status_code}"
                yield f"data: {json.dumps({'error': msg}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        continue
    yield "data: [DONE]\n\n"


# ── FastAPI 应用 ───────────────────────────────────────
app = FastAPI(title="西方文论 Wiki AI")


@app.get("/api/health")
async def health():
    return {"status": "ok", "docs": TOTAL_DOCS}


@app.post("/api/ask")
async def ask(request: Request):
    """AI 问答接口: 接收问题, 流式返回整合回答"""
    body = await request.json()
    query = body.get("query", "").strip()
    if not query:
        return JSONResponse({"error": "问题不能为空"}, status_code=400)

    # BM25 检索
    top_docs, passages = retrieve(query, top_k=5)
    if not passages:
        return JSONResponse({"error": "未检索到相关内容"}, status_code=404)

    # 构建上下文
    context = build_context(passages)
    sources = [
        {"title": p["title"], "slug": p["slug"], "type": p["type"], "score": p["score"]}
        for p in passages
    ]

    # 流式返回
    return StreamingResponse(
        stream_deepseek(query, context, sources),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/search")
async def search(q: str):
    """纯检索接口（不调用 LLM）"""
    top_docs, passages = retrieve(q, top_k=5)
    return {
        "query": q,
        "total_hits": len(top_docs),
        "passages": passages,
        "docs": [
            {"title": d["doc"]["title"], "slug": d["doc"]["slug"], "score": d["score"]}
            for d in top_docs
        ],
    }


# 静态文件服务（wiki-site/docs 下的 HTML）
app.mount("/", StaticFiles(directory=str(DOCS_DIR), html=True), name="static")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n西方文论 Wiki AI 问答服务")
    print(f"知识库: {TOTAL_DOCS} 页面")
    print(f"静态文件: {DOCS_DIR}")
    print(f"启动: http://localhost:{port}")
    print(f"问答页: http://localhost:{port}/qa.html")
    print()
    uvicorn.run(app, host="0.0.0.0", port=port)
