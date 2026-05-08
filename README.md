# GetNotes

将任意 URL 内容通过 DeepSeek API 转化为**面试级结构化技术笔记**。

专为 AI 领域技术文章优化（Agent、RAG、LangGraph、Context Engineering、Claude Code、AI Coding 等），支持面经自动识别和逐题整理。

## 特性

- **智能笔记生成** — 自动提炼技术要点、架构设计、面试讲述框架
- **面经模式** — 自动识别面经文章，逐题整理为面试题+回答
- **URL 去重** — SQLite 缓存已处理 URL，避免重复消耗 API 额度
- **失败重试** — 自动切换 Key 重试（最多 2 次），指数退避
- **模型切换** — 支持 V4 Pro / V4 Flash / V3 / R1，CLI 和 Web 均可切换
- **多 Key 并发** — 支持多个 API Key 轮询路由，并发生成，提速 3-6 倍
- **黑白主题** — 暗色/亮色一键切换，偏好持久化
- **历史管理** — 侧边栏预览、搜索、删除、重新生成、标签标记（优/良/中/差）
- **题库积累** — 自动从笔记中提取面试题和 Q&A，汇入 `notes/questions.md` 表格
- **在线编辑** — 预览区一键切换编辑模式，选中文字自动复制
- **三层反反爬** — requests → 微信 UA 伪装 → Selenium headless Chrome 自动降级
- **Web UI + CLI** — 浏览器操作或命令行批处理，二选一

## 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/wintaoo/getnotes.git
cd getnotes
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 DeepSeek API Key（支持多个，逗号分隔）：

```
DEEPSEEK_API_KEYS=sk-xxx,sk-yyy
```

### 3. 启动

**Web 界面：**

```bash
python app.py
# 浏览器打开 http://127.0.0.1:5000
```

**命令行：**

```bash
# 单个 URL
python main.py -u "https://mp.weixin.qq.com/s/xxxx"

# 多个 URL
python main.py -l "url1,url2,url3"

# 从文件批量处理
python main.py -f urls.txt

# 指定模型和并发数
python main.py -f urls.txt -m deepseek-chat -c 6
```
  
可选模型：`deepseek-v4-pro`（默认）、`deepseek-v4-flash`、`deepseek-chat`（V3）、`deepseek-reasoner`（R1）

## 笔记输出结构

### 技术文章 → 技术笔记格式

1. **一句话价值总结** — 对面试/工作的核心价值
2. **核心思想** — 解决的核心问题 + 与传统方案区别
3. **技术要点精炼** — 架构设计 / 核心算法 / 技术选型 / 工程实践
4. **面试讲述框架** — 可回答的问题 + 3 分钟讲述大纲 + 关键论据
5. **延伸思考** — 技术对比 + 追问方向 + 趋势
6. **关键引用** — 原文重要数据和结论

### 面经文章 → 面经格式

- 逐题整理，每题作为二级标题
- 回答部分纯内容组织，无嵌套标题
- 原文缺失的回答自动补充

## 项目结构

```
getnotes/
├── app.py                # Flask Web 应用
├── main.py               # CLI 入口
├── src/
│   ├── config.py         # 配置管理
│   ├── fetcher.py        # URL 抓取（三层反反爬）
│   ├── generator.py      # DeepSeek API 并发生成
│   └── dedup.py          # URL 去重缓存（SQLite）
├── templates/
│   └── index.html        # Web 前端
├── static/
│   └── style.css         # 样式（暗色/亮色主题）
├── notes/                # 笔记输出目录
│   ├── *.md              # 生成的笔记
│   ├── tags.json         # 标签数据（优/良/中/差）
│   └── questions.md      # 题库汇总表（题目 + 来源 URL）
```

## 技术栈

- Python 3.11+
- Flask (Web)
- OpenAI SDK (DeepSeek API)
- trafilatura + BeautifulSoup (内容提取)
- Selenium (JS 渲染降级)
- ThreadPoolExecutor (并发)

## License

MIT
