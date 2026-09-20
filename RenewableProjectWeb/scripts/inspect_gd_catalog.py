"""Read-only helper for inspecting Guangdong catalog selectors and network calls."""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


ROOT = Path(__file__).resolve().parents[1]
URL = "https://tzxm.gd.gov.cn/PublicityInformation/PublicityHandlingResults.html"


def main() -> None:
    options = webdriver.ChromeOptions()
    options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='gd-catalog-')}")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(service=Service(str(ROOT / "runtime" / "chromedriver.exe")), options=options)
    try:
        driver.get(URL)
        time.sleep(8)
        driver.execute_script("sessionStorage.setItem('moreflag', '1')")
        driver.get("https://tzxm.gd.gov.cn/PublicityInformation/PublicityHandlingResultsList.html")
        time.sleep(6)
        links = [
            {"text": item.text.strip(), "href": item.get_attribute("href"), "onclick": item.get_attribute("onclick")}
            for item in driver.find_elements("css selector", "a")
            if item.text.strip() in {"更多>", "详情"}
        ]
        source = driver.page_source
        network = []
        bodies = []
        for entry in driver.get_log("performance"):
            message = json.loads(entry["message"])["message"]
            if message["method"] == "Network.requestWillBeSent":
                request = message["params"]["request"]
                if "/api/publicityInformation/" in request["url"]:
                    network.append({"phase": "request", "url": request["url"], "method": request["method"],
                                    "postData": request.get("postData", "")})
                continue
            if message["method"] != "Network.responseReceived":
                continue
            response = message["params"]["response"]
            url = response["url"]
            mime = response.get("mimeType", "")
            if "tzxm.gd.gov.cn" in url and ("json" in mime or "/api/" in url):
                network.append({"phase": "response", "url": url, "status": response["status"], "mime": mime})
                if "/api/publicityInformation/" in url:
                    try:
                        body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": message["params"]["requestId"]})
                        bodies.append({"url": url, "body": body.get("body", "")[:3000]})
                    except Exception as exc:
                        bodies.append({"url": url, "error": str(exc)})
        marker = "selectByPageBA"
        marker_at = source.find(marker)
        keyword_snippets = []
        for term in ("projectName", "projectCode", "bamoreflag", "moreflag"):
            for found in list(re.finditer(term, source, re.I))[:6]:
                keyword_snippets.append({"term": term, "snippet": source[max(0, found.start() - 420):found.start() + 760]})
        print(json.dumps({
            "current_url": driver.current_url,
            "inputs": [{"id": item.get_attribute("id"), "name": item.get_attribute("name"),
                        "placeholder": item.get_attribute("placeholder"), "outer": item.get_attribute("outerHTML")[:600]}
                       for item in driver.find_elements("css selector", "input")],
            "selects": [{"id": item.get_attribute("id"), "outer": item.get_attribute("outerHTML")[:1200]}
                        for item in driver.find_elements("css selector", "select")],
            "buttons": [{"text": item.text.strip(), "outer": item.get_attribute("outerHTML")[:500]}
                        for item in driver.find_elements("css selector", "button,a") if item.text.strip()],
            "links": links,
            "api_literals": sorted(set(re.findall(r"[^\"' ]*/api/[^\"' <]+", source)))[:100],
            "network": network,
            "bodies": bodies,
            "source_snippet": source[max(0, marker_at - 1800):marker_at + 2500],
            "keyword_snippets": keyword_snippets,
        }, ensure_ascii=True, indent=2))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
