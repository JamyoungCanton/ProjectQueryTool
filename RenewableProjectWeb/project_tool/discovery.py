from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


class SourceDiscovery:
    def __init__(self, config_path: Path):
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.client = httpx.Client(timeout=15, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

    def discover(self, criteria: dict, log) -> list[dict]:
        result: list[dict] = []
        combined = " ".join(str(value) for value in criteria.values() if value)
        for page in self.config.get("bootstrap_pages", []):
            if all(word.lower() in combined.lower() for word in page.get("match_all", [])):
                result.append(dict(page))
        location = " ".join(filter(None, [criteria.get("province"), criteria.get("city"), criteria.get("district")]))
        enabled_sources = [source for source in self.config.get("sources", []) if source.get("enabled", True)]
        overflow: list[dict] = []
        for source in enabled_sources:
            stage = source.get("stage", source.get("name", "公开信息"))
            domains = " OR ".join(f"site:{domain}" for domain in source.get("search_domains", []))
            query = " ".join(filter(None, [criteria["project_name"], location, stage, domains]))
            try:
                log(stage, "搜狗公开搜索", "running", query)
                response = self.client.get("https://www.sogou.com/web", params={"query": query})
                response.raise_for_status()
                if "验证码" in response.text[:5000]:
                    log(stage, "搜狗公开搜索", "manual", "该网站需要人工验证，请手动打开网站确认。")
                    continue
                soup = BeautifulSoup(response.text, "lxml")
                source_candidates = []
                for anchor in soup.select("h3 a")[:5]:
                    href = urljoin("https://www.sogou.com", anchor.get("href", ""))
                    final = self._resolve(href)
                    if final and urlparse(final).scheme in {"http", "https"}:
                        source_candidates.append({"name": source.get("name", anchor.get_text(" ", strip=True)),
                                                  "url": final, "stage": stage})
                if source_candidates:
                    result.append(source_candidates[0])
                    overflow.extend(source_candidates[1:])
                log(stage, "搜狗公开搜索", "success", f"发现 {len(soup.select('h3 a')[:5])} 条候选链接")
            except Exception as exc:
                log(stage, "搜狗公开搜索", "error", str(exc))
            time.sleep(float(self.config.get("request_interval_seconds", 1.2)))
        result.extend(overflow)
        unique = []
        seen = set()
        for page in result:
            normalized = page["url"].split("#", 1)[0]
            if normalized not in seen:
                seen.add(normalized)
                unique.append(page)
        return unique[: int(self.config.get("max_discovered_urls", 8))]

    def _resolve(self, url: str) -> str:
        if "sogou.com/link" not in url:
            return url
        response = self.client.get(url)
        match = re.search(r'window\.location\.replace\(["\']([^"\']+)', response.text)
        if not match:
            match = re.search(r'URL=["\']?([^"\'>]+)', response.text, re.I)
        return match.group(1).replace("&amp;", "&") if match else str(response.url)

    def close(self) -> None:
        self.client.close()
