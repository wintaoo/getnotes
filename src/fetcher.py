import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .config import DEFAULT_USER_AGENT, WECHAT_USER_AGENT


def _is_wechat(url: str) -> bool:
    domain = urlparse(url).netloc
    return "mp.weixin.qq.com" in domain


def _clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _fetch_with_requests(url: str, user_agent: str = DEFAULT_USER_AGENT) -> str | None:
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        return resp.text
    except requests.RequestException:
        return None


def _extract_with_trafilatura(html: str, url: str) -> tuple[str, str] | None:
    import trafilatura
    doc = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        output_format="markdown",
        with_metadata=True,
    )
    if not doc:
        return None

    body = doc
    title = ""

    # Extract title from YAML frontmatter (trafilatura markdown with metadata)
    yaml_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", doc, re.DOTALL)
    if yaml_match:
        yaml_block = yaml_match.group(1)
        body = doc[yaml_match.end():]
        for line in yaml_block.splitlines():
            if line.startswith("title:"):
                title = line.split(":", 1)[1].strip().strip('"').strip("'")
                if " | " in title:
                    title = title.split(" | ")[0].strip()
                break

    # Fallback: extract from first H1 heading
    if not title:
        h1_match = re.search(r"^# (.+)", body, re.MULTILINE)
        if h1_match:
            title = h1_match.group(1).strip()
            body = re.sub(r"^# .+\n+", "", body, count=1, flags=re.MULTILINE).strip()

    return title, body.strip()


def _extract_with_bs4(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "untitled"

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    # Try to find the main content area
    for selector in ["article", '[role="main"]', "main", ".rich_media_content", "#js_content", ".content"]:
        main = soup.select_one(selector)
        if main:
            soup = main
            break

    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return title, "\n".join(lines)


def _fetch_with_selenium(url: str) -> str | None:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"user-agent={DEFAULT_USER_AGENT}")

        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            return driver.page_source
        finally:
            driver.quit()
    except Exception:
        return None


def fetch_content(url: str) -> tuple[str, str]:
    """
    Fetch and extract content from a URL.
    Returns (title, content) tuple.
    Uses multiple strategies with automatic fallback.
    """
    html = None

    # Tier 1: requests + browser UA
    html = _fetch_with_requests(url)

    # Tier 2: WeChat specific UA
    if html and _is_wechat(url):
        html2 = _fetch_with_requests(url, user_agent=WECHAT_USER_AGENT)
        if html2 and len(html2) > len(html):
            html = html2

    # Tier 3: Selenium for JS-rendered content
    if not html or len(html) < 500:
        html = _fetch_with_selenium(url)

    if not html:
        raise RuntimeError(f"无法获取 URL 内容: {url}")

    # Extract content with trafilatura first
    result = _extract_with_trafilatura(html, url)
    if result and result[1] and len(result[1]) > 200:
        return result

    # Fallback to BeautifulSoup extraction
    return _extract_with_bs4(html)
