import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import NOTES_DIR, DEEPSEEK_CONCURRENCY, DEEPSEEK_API_KEYS
from src.fetcher import fetch_content
from src.generator import generate_notes_batch


def sanitize_filename(title: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", title)
    return name.strip()[:80]


def process_url(url: str, output_dir: str) -> str:
    print(f"  抓取: {url}")
    title, content = fetch_content(url)
    print(f"  标题: {title} ({len(content)} 字符)")

    notes = generate_notes_batch([{"content": content, "title": title}])[0]
    if notes["error"]:
        raise RuntimeError(notes["error"])

    filename = sanitize_filename(title) + ".md"
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(notes["content"])

    print(f"  已保存: {filepath}")
    return filepath


def parse_urls(args) -> list[str]:
    urls = []
    if args.url:
        urls.append(args.url)
    if args.list:
        urls.extend(u.strip() for u in args.list.split(",") if u.strip())
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    if not urls:
        print("错误: 请提供至少一个 URL (-u/-l/-f)")
        sys.exit(1)
    return urls


def main():
    default_concurrency = min(len(DEEPSEEK_API_KEYS) * 3, DEEPSEEK_CONCURRENCY)
    parser = argparse.ArgumentParser(description="GetNotes - 将 URL 内容转化为专业笔记")
    parser.add_argument("-u", "--url", help="单个 URL")
    parser.add_argument("-l", "--list", help="逗号分隔的 URL 列表")
    parser.add_argument("-f", "--file", help="包含 URL 列表的文件 (每行一个)")
    parser.add_argument("-o", "--output", default=NOTES_DIR, help="笔记输出目录 (默认: ./notes)")
    parser.add_argument("-c", "--concurrency", type=int, default=default_concurrency,
                        help=f"并发数 (默认: {default_concurrency})")
    args = parser.parse_args()

    urls = parse_urls(args)
    print(f"共 {len(urls)} 个 URL，并发度 {args.concurrency}\n")

    # Step 1: Concurrent fetch
    print("--- 抓取内容 ---")
    fetch_tasks = {}
    with ThreadPoolExecutor(max_workers=min(len(urls), args.concurrency)) as executor:
        for url in urls:
            future = executor.submit(fetch_content, url)
            fetch_tasks[future] = url

        fetch_results = {}
        for future in as_completed(fetch_tasks):
            url = fetch_tasks[future]
            try:
                title, content = future.result()
                fetch_results[url] = (title, content)
                print(f"  [OK] {url} -> {title} ({len(content)} 字符)")
            except Exception as e:
                fetch_results[url] = ("", "")
                print(f"  [FAIL] {url} -> {e}")

    # Step 2: Concurrent generate
    print("\n--- 生成笔记 ---")
    gen_tasks = []
    gen_urls = []
    for url in urls:
        title, content = fetch_results[url]
        if content:
            gen_tasks.append({"content": content, "title": title})
            gen_urls.append(url)

    if gen_tasks:
        gen_results = generate_notes_batch(gen_tasks)
        for url, result in zip(gen_urls, gen_results):
            if result["error"]:
                print(f"  [FAIL] {url} -> {result['error']}")
                continue
            title = result["title"]
            filename = sanitize_filename(title) + ".md"
            os.makedirs(args.output, exist_ok=True)
            filepath = os.path.join(args.output, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(result["content"])
            print(f"  [OK] {url} -> {filepath}")

    print(f"\n完成!")


if __name__ == "__main__":
    main()
