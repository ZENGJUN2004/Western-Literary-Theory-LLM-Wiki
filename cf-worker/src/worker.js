/**
 * 西方文论 Wiki AI —— Cloudflare Worker
 * 职责：接收前端 BM25 检索到的语境（context + question），调用 DeepSeek 流式整合回答(SSE)，
 * 并附加 CORS。检索仍由前端完成，本 Worker 保持轻量、免费档可用。
 *
 * 部署：wrangler deploy（见仓库根 README 或 cf-worker/wrangler.toml）
 * 环境变量(SECRET)：DEEPSEEK_API_KEY
 */

const DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions";
const MODEL = "deepseek-chat";

const SYSTEM_PROMPT = `你是西方文论知识库的学术问答助手。请根据用户提问和检索到的知识库段落，生成准确、学术、连贯的整合回答。
要求：
1. 回答必须基于检索到的段落内容，不要编造未提供的知识
2. 在关键论点后用 [序号] 标注引用来源
3. 组织逻辑：先定义核心概念，再展开主要观点，最后补充具体例证
4. 使用学术但易懂的中文，避免口语化
5. 如果检索段落不足以回答问题，如实说明并建议查阅相关页面
6. 回答控制在 300-500 字以内`;

const AUTH = {
  allow: { origin: "*" },
  methods: "GET, POST, OPTIONS",
  headers: {
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "text/event-stream; charset=utf-8",
  },
};

async function corsOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": AUTH.allow.origin,
      "Access-Control-Allow-Methods": AUTH.methods,
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Max-Age": "86400",
    },
  });
}

/**
 * 构造 SSE 响应。通过 TransformStream 把 DeepSeek 流式 chunk 转发给浏览器。
 * 首行先发 sources，然后逐 chunk 发 content，最后 [DONE]。
 */
async function sseResponse(question, context, sources, env) {
  const encoder = new TextEncoder();

  // 1) 先构造一个可读序列（含 sources 首事件）
  const parts = []; // {type:'sources'|'content'|'done', data}
  parts.push({ type: "sources", data: { sources } });

  const userMsg = `用户提问：${question}\n\n检索到的知识库段落：\n${context}\n\n请基于以上段落生成整合回答。`;

  const payload = {
    model: MODEL,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: userMsg },
    ],
    stream: true,
    max_tokens: 1024,
    temperature: 0.3,
  };

  const resp = await fetch(DEEPSEEK_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.DEEPSEEK_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(60_000),
  });

  let downError = null;
  if (!resp.ok || !resp.body) {
    let msg = `DeepSeek API HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      msg = (err.error && err.error.message) || msg;
    } catch (_) {}
    downError = msg;
  }

  const stream = new ReadableStream({
    async start(controller) {
      const push = (obj) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
      };
      // 先发来源
      push(parts[0].data);

      if (downError) {
        push({ error: downError });
        push({ done: true });
        controller.close();
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";
      const reader = resp.body.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) continue;
            const data = trimmed.slice(6);
            if (data === "[DONE]") continue;
            try {
              const chunk = JSON.parse(data);
              const delta = chunk.choices?.[0]?.delta;
              const text = delta?.content;
              if (text) push({ content: text });
            } catch (_) {}
          }
        }
      } finally {
        push({ done: true });
        controller.close();
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: AUTH.headers,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const method = request.method;

    if (method === "OPTIONS") return corsOptions();

    // GET: 健康检查
    if (method === "GET" && url.pathname === "/api/health") {
      return new Response(JSON.stringify({ status: "ok", docs: "unknown" }), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }

    // POST: 问答
    if (method === "POST" && url.pathname === "/api/ask") {
      let body;
      try {
        body = await request.json();
      } catch (_) {
        return new Response(JSON.stringify({ error: "Bad JSON" }), {
          status: 400,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
        });
      }
      const question = (body.query || "").trim();
      const context = (body.context || "").trim();
      const sources = body.sources || [];
      if (!question) {
        return new Response(JSON.stringify({ error: "问题不能为空" }), {
          status: 400,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
        });
      }
      if (!context) {
        return new Response(JSON.stringify({ error: "未检索到相关内容" }), {
          status: 404,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
        });
      }
      return sseResponse(question, context, sources, env);
    }

    return new Response("Not Found", {
      status: 404,
      headers: { "Access-Control-Allow-Origin": "*" },
    });
  },
};
