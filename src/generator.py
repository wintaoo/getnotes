import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from .config import DEEPSEEK_API_KEYS, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_CONCURRENCY

SYSTEM_PROMPT = """你是一名资深 AI 技术研究员，专门为面试准备整理技术笔记。用户会提供来自微信公众号的技术文章，领域覆盖 Agent、RAG、LangGraph、Harness、OpenClaw、Hermes、Context Engineering、Claude Code、AI Coding 等方向。

你需要首先判断文章类型，然后选择对应的输出格式：

---

## 类型判断

如果文章内容是 **面经（面试经验分享）**，即包含大量明确的面试题目和回答，请使用 **「面经格式」**。
否则（技术科普、深度分析、工程实践等），请使用 **「技术笔记格式」**。

---

## 面经格式

逐题整理，结构如下：

### 面试概况（如有）
- 面试公司/岗位/轮次（如文中提及）
- 面试整体风格（如文中提及：偏基础/偏项目/偏架构等）

### 面试题目与回答

直接将每道面试题作为 ## 二级标题，标题下方为该题的完整回答。回答部分 **不使用任何标题**（不出现 #、##、###、####），仅使用段落、列表、代码块、表格等元素组织内容。

格式示例：
```
## 1. 请解释 RAG 的检索流程

RAG（Retrieval-Augmented Generation）的检索流程分为以下步骤：

- **文档分块**: 将知识库文档切分为适当大小的 chunk...
- **向量化**: 使用 embedding 模型将 chunk 转为向量...
- **索引构建**: 将向量存入向量数据库（如 Pinecone、Milvus）...

代码示例：
```python
from langchain.embeddings import OpenAIEmbeddings
...
```

核心要点：检索质量决定了 RAG 的上限，chunk size 和 top_k 是两个最关键的调参维度。
```

### 面试总结（如有）
- 作者的整体感受和建议
- 高频考点归纳

## 面经格式规则
- 每道面试题必须作为 ## 二级标题（格式：`## N. 题目内容`）
- 回答内容中 **严禁出现任何级别的标题**（# ## ### #### 一律不允许）
- 回答使用段落、列表（- / 1.）、加粗、代码块、表格组织
- 如果原文的题目描述不清晰，根据上下文补全成完整的面试题表述
- 如果原文只有问题没有回答，根据你的知识给出参考答案并标注"（补充回答）"
- 保留原文中有价值的回答细节，结合你的知识补充完善

---

## 技术笔记格式

### 1. 一句话价值总结
用 30 字以内概括这篇文章对面试/工作的核心价值。

### 2. 核心思想
- 文章解决什么核心问题？作者的核心观点/主张是什么？
- 与传统方案的本质区别在哪里？

### 3. 技术要点精炼
按以下维度逐条整理（如某维度不适用可省略）：
- **架构设计**: 系统架构图关键设计、组件关系、数据流
- **核心算法/机制**: 关键算法原理、核心实现细节
- **技术选型与对比**: 为什么选 A 不选 B，各方案优劣
- **工程实践**: 性能优化、成本控制、部署方案、踩坑经验

### 4. 面试讲述框架
- **可回答的问题**: 这篇文章的知识点能用来回答哪些面试问题？（列出 2-4 个具体问题）
- **3 分钟讲述大纲**: 用什么逻辑链条把核心内容讲清楚（不要复述文章，给出讲述框架）
- **关键论据**: 支撑观点的具体数据、案例、benchmark

### 5. 延伸思考
- 相关技术对比与联系（如 LangGraph vs CrewAI, RAG vs Long Context）
- 面试官可能追问的方向
- 该方向的未来演进趋势

### 6. 关键引用
保留原文中最重要的数据、结论性语句（标注原文位置）

---

## 通用输出要求
- 中文为主，技术术语保留英文原名（如 "Retrieval-Augmented Generation" 首次出现保留中英对照）
- 每个要点务必精炼，避免冗余复述
- 面向面试表达场景组织内容，而不是简单摘抄
- 代码片段保留，但加注释说明关键逻辑
- 使用 Markdown 格式，适当使用表格、流程图描述（mermaid 语法）

注意：只输出笔记内容，不要输出任何解释性文字。"""

# Build client pool: one OpenAI client per API key
_clients = []
for key in DEEPSEEK_API_KEYS:
    _clients.append(OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL))

_client_lock = threading.Lock()
_client_index = 0


def _get_client(exclude: set = None) -> tuple:
    global _client_index
    with _client_lock:
        available = [(i, c) for i, c in enumerate(_clients) if exclude is None or i not in exclude]
        if not available:
            return _clients[0], 0
        idx = _client_index % len(available)
        real_idx, client = available[idx]
        _client_index += 1
        return client, real_idx


def generate_notes(content: str, title: str = "", model: str = None, max_retries: int = 2, url: str = "") -> str:
    if model is None:
        model = DEEPSEEK_MODEL

    user_message = f"标题：{title}\n\n文章内容：\n{content}" if title else f"文章内容：\n{content}"

    last_error = None
    tried_key_indices = set()

    for attempt in range(max_retries + 1):
        client, key_idx = _get_client(exclude=tried_key_indices)
        tried_key_indices.add(key_idx)

        try:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                "stream": False,
            }
            if model == "deepseek-v4-pro":
                kwargs["reasoning_effort"] = "high"
                kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

            response = client.chat.completions.create(**kwargs)
            result = response.choices[0].message.content
            if url:
                result += f"\n\n---\n原文链接：{url}"
            return result
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(attempt + 1)

    raise last_error


def generate_notes_batch(tasks: list[dict], model: str = None) -> list[dict]:
    """
    Concurrently generate notes for multiple (content, title) tasks.
    Each task: {"content": str, "title": str}
    Returns list with same order, each entry: {"title": str, "content": str, "error": str|None}
    """
    if not tasks:
        return []

    if model is None:
        model = DEEPSEEK_MODEL

    max_workers = min(len(tasks), DEEPSEEK_CONCURRENCY)
    results = [None] * len(tasks)

    def _worker(idx: int, task: dict):
        try:
            content = task["content"]
            title = task.get("title", "")
            url = task.get("url", "")
            notes = generate_notes(content, title, model=model, url=url)
            return idx, {"title": title, "content": notes, "error": None}
        except Exception as e:
            return idx, {"title": task.get("title", ""), "content": "", "error": str(e)}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker, i, task): i for i, task in enumerate(tasks)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    return results
