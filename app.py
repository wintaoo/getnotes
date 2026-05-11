import os
import sys
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify, Response

from src.config import NOTES_DIR, DEEPSEEK_CONCURRENCY, DEEPSEEK_MODEL, AVAILABLE_MODELS

TAGS_FILE = os.path.join(NOTES_DIR, "tags.json")


def _load_tags() -> dict:
    if os.path.isfile(TAGS_FILE):
        with open(TAGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_tags(tags: dict):
    os.makedirs(NOTES_DIR, exist_ok=True)
    with open(TAGS_FILE, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False)


TAG_LABELS = ["", "优", "良", "中", "差"]

INDEX_FILE = os.path.join(NOTES_DIR, "index.md")

import sqlite3

def _rebuild_index():
    """Rebuild notes/index.md — a table of all notes with their source URLs."""
    db = os.path.join(NOTES_DIR, ".cache.db")
    rows = []
    if os.path.isfile(db):
        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT filename, title, url FROM processed ORDER BY created_at DESC"
        ).fetchall()
        conn.close()

    os.makedirs(NOTES_DIR, exist_ok=True)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write("# 笔记索引\n\n")
        f.write("| 笔记 | 原文链接 |\n|------|----------|\n")
        for filename, title, url in rows:
            safe_title = title.replace("|", "\\|") if title else filename.replace(".md", "")
            f.write(f"| {safe_title} | [{filename}]({url}) |\n")
        f.write(f"\n共 {len(rows)} 篇笔记\n")

    logger.info(f"  [索引] 已重建, {len(rows)} 篇")
from src.fetcher import fetch_content
from src.generator import generate_notes_batch
from src.dedup import is_processed, mark_processed, get_url_by_filename
from main import sanitize_filename

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("app")


@app.route("/")
def index():
    return render_template("index.html", models=AVAILABLE_MODELS, default_model=DEEPSEEK_MODEL)


def _process_one_url(url: str) -> dict:
    """Fetch + generate for a single URL. Runs in a thread."""
    try:
        title, content = fetch_content(url)
        return {"url": url, "title": title, "content": content, "error": None}
    except Exception as e:
        return {"url": url, "title": "", "content": "", "error": str(e)}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    urls = [u.strip() for u in data.get("urls", []) if u.strip()]
    model = data.get("model", DEEPSEEK_MODEL)
    if model not in AVAILABLE_MODELS:
        model = DEEPSEEK_MODEL

    if not urls:
        return jsonify({"error": "请提供至少一个 URL"}), 400

    def generate():
        logger.info(f"收到请求: {len(urls)} 个 URL, 模型={model}")

        # Dedup check
        results = []
        new_urls = []
        for url in urls:
            existing = is_processed(url)
            if existing:
                logger.info(f"  [跳过] 已处理: {existing}")
                results.append({
                    "url": url, "title": "", "filename": existing,
                    "content": "", "error": None, "skipped": True,
                })
            else:
                new_urls.append(url)

        yield _sse({"type": "progress", "step": "dedup",
                     "message": f"检查重复: {len(urls) - len(new_urls)} 跳过, {len(new_urls)} 新",
                     "current": len(urls) - len(new_urls), "total": len(urls)})

        if not new_urls:
            logger.info("全部已处理过")
            results.sort(key=lambda r: urls.index(r["url"]))
            yield _sse({"type": "complete", "results": results})
            return

        # Step 1: Concurrent fetch
        logger.info(f"开始抓取 {len(new_urls)} 个 URL")
        fetch_workers = min(len(new_urls), DEEPSEEK_CONCURRENCY)
        fetch_results = []
        with ThreadPoolExecutor(max_workers=fetch_workers) as executor:
            futures = {executor.submit(_process_one_url, url): url for url in new_urls}
            for future in as_completed(futures):
                fr = future.result()
                fetch_results.append(fr)
                if fr["error"]:
                    logger.warning(f"  [失败] 抓取: {fr['error']}")
                else:
                    logger.info(f"  [抓取] {fr['title']} ({len(fr['content'])} 字符)")
                yield _sse({"type": "progress", "step": "fetch",
                             "message": f"抓取内容 ({len(fetch_results)}/{len(new_urls)})",
                             "current": len(fetch_results), "total": len(new_urls)})

        url_order = {url: i for i, url in enumerate(new_urls)}
        fetch_results.sort(key=lambda r: url_order.get(r["url"], 999))

        gen_tasks = []
        for fr in fetch_results:
            if fr["error"]:
                results.append({
                    "url": fr["url"], "title": "", "filename": "",
                    "content": "", "error": fr["error"], "skipped": False,
                })
            else:
                gen_tasks.append(fr)

        # Step 2: Concurrent generate
        if gen_tasks:
            logger.info(f"开始生成 {len(gen_tasks)} 篇笔记")
            batch_input = [{"content": t["content"], "title": t["title"], "url": t["url"]} for t in gen_tasks]
            gen_results = generate_notes_batch(batch_input, model=model)

            for task, gen in zip(gen_tasks, gen_results):
                if gen["error"]:
                    logger.warning(f"  [失败] 生成: {task['title']} -> {gen['error']}")
                    results.append({
                        "url": task["url"], "title": task["title"],
                        "filename": "", "content": "",
                        "error": gen["error"], "skipped": False,
                    })
                else:
                    filename = sanitize_filename(task["title"]) + ".md"
                    os.makedirs(NOTES_DIR, exist_ok=True)
                    filepath = os.path.join(NOTES_DIR, filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(gen["content"])
                    mark_processed(task["url"], task["title"], filename)
                    logger.info(f"  [保存] {filename}")
                    _rebuild_index()
                    note_info = {
                        "url": task["url"], "title": task["title"],
                        "filename": filename, "content": gen["content"],
                        "error": None, "skipped": False,
                    }
                    results.append(note_info)
                    yield _sse({"type": "note_saved",
                                "filename": filename,
                                "title": task["title"],
                                "size": os.path.getsize(filepath),
                                "mtime": os.path.getmtime(filepath)})
                yield _sse({"type": "progress", "step": "generate",
                             "message": f"生成笔记 ({len(results)}/{len(urls)})",
                             "current": len(results), "total": len(urls)})

        results.sort(key=lambda r: urls.index(r["url"]))
        logger.info(f"完成: {len(urls)} 个 URL 处理完毕")
        yield _sse({"type": "complete", "results": results})

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/regenerate/<path:filename>", methods=["POST"])
def api_regenerate(filename):
    url = get_url_by_filename(filename)
    if not url:
        return jsonify({"error": "未找到该笔记的原始 URL"}), 404

    data = request.get_json() or {}
    model = data.get("model", DEEPSEEK_MODEL)
    if model not in AVAILABLE_MODELS:
        model = DEEPSEEK_MODEL

    try:
        title, content = fetch_content(url)
        notes = generate_notes_batch(
            [{"content": content, "title": title, "url": url}],
            model=model,
        )
        gen = notes[0]
        if gen["error"]:
            return jsonify({"error": gen["error"]}), 500

        filepath = os.path.join(NOTES_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(gen["content"])
        _rebuild_index()

        return jsonify({
            "filename": filename,
            "title": title,
            "content": gen["content"],
            "url": url,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes", methods=["GET"])
def api_notes():
    tags = _load_tags()
    files = []
    if os.path.isdir(NOTES_DIR):
        md_files = [f for f in os.listdir(NOTES_DIR) if f.endswith(".md")]
        md_files.sort(key=lambda f: os.path.getmtime(os.path.join(NOTES_DIR, f)), reverse=True)
        for f in md_files:
            fpath = os.path.join(NOTES_DIR, f)
            files.append({
                "filename": f,
                "size": os.path.getsize(fpath),
                "mtime": os.path.getmtime(fpath),
                "tag": tags.get(f, ""),
            })
    return jsonify({"notes": files})


@app.route("/api/notes/<path:filename>", methods=["GET"])
def api_note_content(filename):
    filepath = os.path.join(NOTES_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "文件不存在"}), 404
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify({"filename": filename, "content": content})


@app.route("/api/notes/<path:filename>", methods=["PUT"])
def api_note_update(filename):
    filepath = os.path.join(NOTES_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "文件不存在"}), 404
    data = request.get_json()
    content = data.get("content", "")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"filename": filename, "saved": True})


@app.route("/api/notes/<path:filename>/rename", methods=["PUT"])
def api_note_rename(filename):
    filepath = os.path.join(NOTES_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "文件不存在"}), 404

    data = request.get_json()
    new_name = data.get("new_name", "").strip()
    if not new_name:
        return jsonify({"error": "新名称不能为空"}), 400

    new_filename = sanitize_filename(new_name) + ".md"
    new_filepath = os.path.join(NOTES_DIR, new_filename)

    if new_filename == filename:
        return jsonify({"error": "新名称与旧名称相同"}), 400

    if os.path.exists(new_filepath):
        return jsonify({"error": "该名称已存在"}), 409

    os.rename(filepath, new_filepath)

    db = os.path.join(NOTES_DIR, ".cache.db")
    if os.path.isfile(db):
        conn = sqlite3.connect(db)
        conn.execute("UPDATE processed SET filename = ? WHERE filename = ?", (new_filename, filename))
        conn.commit()
        conn.close()

    tags = _load_tags()
    if filename in tags:
        tags[new_filename] = tags.pop(filename)
        _save_tags(tags)

    _rebuild_index()

    logger.info(f"  [重命名] {filename} -> {new_filename}")
    return jsonify({
        "old_filename": filename,
        "new_filename": new_filename,
        "renamed": True,
    })


@app.route("/api/tags", methods=["GET"])
def api_tags():
    return jsonify({"tags": _load_tags()})


@app.route("/api/tags/<path:filename>", methods=["PUT"])
def api_set_tag(filename):
    tag = request.get_json().get("tag", "")
    if tag not in TAG_LABELS:
        return jsonify({"error": f"无效标签: {tag}"}), 400
    tags = _load_tags()
    if tag:
        tags[filename] = tag
    else:
        tags.pop(filename, None)
    _save_tags(tags)
    return jsonify({"filename": filename, "tag": tag})


@app.route("/api/notes/<path:filename>", methods=["DELETE"])
def api_note_delete(filename):
    filepath = os.path.join(NOTES_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "文件不存在"}), 404
    os.remove(filepath)
    tags = _load_tags()
    tags.pop(filename, None)
    _save_tags(tags)
    _rebuild_index()
    return jsonify({"deleted": filename})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
