import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, jsonify

from src.config import NOTES_DIR, DEEPSEEK_CONCURRENCY
from src.fetcher import fetch_content
from src.generator import generate_notes_batch
from main import sanitize_filename

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


def _process_one_url(url: str) -> dict:
    """Fetch + generate for a single URL. Runs in a thread."""
    try:
        title, content = fetch_content(url)
        return {"url": url, "title": title, "content": content, "error": None}
    except Exception as e:
        return {"url": url, "title": "", "content": "", "error": str(e)}


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    urls = [u.strip() for u in data.get("urls", []) if u.strip()]
    if not urls:
        return jsonify({"error": "请提供至少一个 URL"}), 400

    # Step 1: Concurrent fetch for all URLs
    fetch_workers = min(len(urls), DEEPSEEK_CONCURRENCY)
    fetch_results = []
    with ThreadPoolExecutor(max_workers=fetch_workers) as executor:
        futures = {executor.submit(_process_one_url, url): url for url in urls}
        for future in as_completed(futures):
            fetch_results.append(future.result())

    # Restore original order
    url_order = {url: i for i, url in enumerate(urls)}
    fetch_results.sort(key=lambda r: url_order.get(r["url"], 999))

    # Separate successful fetches from errors
    gen_tasks = []
    results = []
    for fr in fetch_results:
        if fr["error"]:
            results.append({
                "url": fr["url"],
                "title": "",
                "filename": "",
                "content": "",
                "error": fr["error"],
            })
        else:
            gen_tasks.append(fr)

    # Step 2: Concurrent generate via batch API
    if gen_tasks:
        batch_input = [{"content": t["content"], "title": t["title"]} for t in gen_tasks]
        gen_results = generate_notes_batch(batch_input)

        for task, gen in zip(gen_tasks, gen_results):
            if gen["error"]:
                results.append({
                    "url": task["url"],
                    "title": task["title"],
                    "filename": "",
                    "content": "",
                    "error": gen["error"],
                })
            else:
                filename = sanitize_filename(task["title"]) + ".md"
                os.makedirs(NOTES_DIR, exist_ok=True)
                filepath = os.path.join(NOTES_DIR, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(gen["content"])
                results.append({
                    "url": task["url"],
                    "title": task["title"],
                    "filename": filename,
                    "content": gen["content"],
                    "error": None,
                })

    # Sort results back to original URL order
    results.sort(key=lambda r: url_order.get(r["url"], 999))
    return jsonify({"results": results})


@app.route("/api/notes", methods=["GET"])
def api_notes():
    files = []
    if os.path.isdir(NOTES_DIR):
        for f in sorted(os.listdir(NOTES_DIR), reverse=True):
            if f.endswith(".md"):
                fpath = os.path.join(NOTES_DIR, f)
                files.append({
                    "filename": f,
                    "size": os.path.getsize(fpath),
                    "mtime": os.path.getmtime(fpath),
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


@app.route("/api/notes/<path:filename>", methods=["DELETE"])
def api_note_delete(filename):
    filepath = os.path.join(NOTES_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "文件不存在"}), 404
    os.remove(filepath)
    return jsonify({"deleted": filename})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
