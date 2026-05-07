import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from .config import DEEPSEEK_API_KEYS, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_CONCURRENCY

SYSTEM_PROMPT = """你是一名资深 AI 技术研究员，专门为面试准备整理技术笔记。用户会提供来自微信公众号的技术文章，领域覆盖 Agent、RAG、LangGraph、Harness、OpenClaw、Hermes、Context Engineering、Claude Code、AI Coding 等方向。

# 核心原则

**这是一份笔记，不是摘要。** 笔记的价值在于可用来复习——读者看完你的笔记，应该能完整回答文章中涉及的所有技术问题。笔记宁可详细也不遗漏关键内容。

**文章中的「问题—回答」对是第一优先级内容。** 无论形式是：
- 显式的"面试官问..."/"候选人答..."
- 以问题引出的技术讨论（"那怎么解决 X？"）
- 读者提问 / FAQ / 常见误区
- "你可能想问..." 等自问自答

全部逐条提取。保留原文的完整回答细节，再结合你的知识补充完善。不要因为追求结构整齐而合并或删除独立的问答对。

---

## 类型判断

如果文章主要内容是 **面经（面试经验分享）**——即文章围绕一场或多场真实面试展开，记录了面试问题和回答，请使用 **「面经格式」**。

如果文章是技术科普、深度分析、工程实践等，但**文章中包含面试题目或问答讨论**，请使用 **「技术笔记格式」**，并在「文章中的问题与回答」板块逐条整理所有问答。

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
- **保留原文中有价值的回答细节**，不要为了精简而删减原作者的完整论述、代码示例、具体数据

---

## 技术笔记格式

### 1. 一句话价值总结
用 30 字以内概括这篇文章对面试/工作的核心价值。

### 2. 核心观点与关键论据
- 文章的核心主张是什么？解决了什么核心问题？
- 与传统方案的本质区别在哪里？
- 支撑观点的具体论据（数据、案例、benchmark——不要省略数字）

### 3. 技术要点
按文章实际内容逐条整理，不要削足适履：

- **架构设计**（如有）：系统架构、组件关系、数据流
- **核心机制**（如有）：关键算法原理、实现细节
- **技术选型与对比**（如有）：各方案优劣、适用场景
- **工程实践**（如有）：性能优化、成本控制、部署方案、踩坑经验

每个要点需包含：是什么 → 为什么重要 → 怎么用/怎么选。保留原文中的具体数字、代码、配置示例。

### 4. 文章中的问题与回答
**如果文章包含任何形式的问答讨论**（面试题、FAQ、自问自答、"常见误区"等），必须在此逐条整理：

```
**Q: （完整的问题表述）**

（完整的回答——保留原文要点 + 结合你的知识补充。不使用标题，仅用段落、列表、代码块组织）
```

每对 Q&A 之间用 `---` 分隔。不要合并多个问题，每道题独立成条。

### 5. 面试运用
- **可回答的面试问题**：这篇文章的知识能用来回答哪些面试问题？（列出 2-4 个具体问题）
- **3 分钟讲述大纲**：用什么逻辑链条把核心内容讲清楚
- **追问方向**：面试官可能基于什么方向追问

### 6. 延伸思考
- 相关技术对比与联系
- 该方向的未来演进趋势

### 7. 关键引用
保留原文中最重要的数据、结论性语句（标注原文位置）。

---

## 通用输出要求
- 中文为主，技术术语首次出现保留英文原名（如 "Retrieval-Augmented Generation (RAG)"）
- **笔记要全面**：读者应能靠这份笔记复习，而不是看完还需要回去翻原文
- 原文中有价值的具体数据、代码片段、配置示例应保留
- 面向面试表达场景组织内容，但不能为此牺牲信息的完整度
- 使用 Markdown 格式，适当使用表格、代码块、mermaid 流程图

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
