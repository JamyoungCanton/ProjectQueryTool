from __future__ import annotations

import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


MANIFEST_URL = (
    "https://googlechromelabs.github.io/chrome-for-testing/"
    "known-good-versions-with-downloads.json"
)


def find_chrome() -> tuple[Path, str]:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application"),
    ]
    for application_dir in candidates:
        binary = application_dir / "chrome.exe"
        if not binary.exists():
            continue
        versions = sorted(
            (path.name for path in application_dir.iterdir() if path.is_dir() and path.name[:1].isdigit()),
            key=lambda value: tuple(int(part) for part in value.split(".")),
            reverse=True,
        )
        if versions:
            return binary, versions[0]
    raise RuntimeError("未找到 Google Chrome，请先在服务器电脑安装 Chrome。")


def select_download(manifest: dict, chrome_version: str) -> tuple[str, str]:
    build = ".".join(chrome_version.split(".")[:3])
    matches = [item for item in manifest["versions"] if item["version"].startswith(build + ".")]
    if not matches:
        major = chrome_version.split(".")[0]
        matches = [item for item in manifest["versions"] if item["version"].startswith(major + ".")]
    if not matches:
        raise RuntimeError(f"官方清单中未找到 Chrome {chrome_version} 对应的 ChromeDriver。")
    matches.sort(key=lambda item: tuple(int(part) for part in item["version"].split(".")), reverse=True)
    for item in matches:
        for download in item.get("downloads", {}).get("chromedriver", []):
            if download.get("platform") == "win64":
                return item["version"], download["url"]
    raise RuntimeError("官方清单中未找到 Windows 64 位 ChromeDriver。")


def main() -> int:
    app_root = Path(__file__).resolve().parents[1]
    runtime_dir = app_root / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    chrome_binary, chrome_version = find_chrome()
    with urllib.request.urlopen(MANIFEST_URL, timeout=30) as response:
        manifest = json.load(response)
    driver_version, download_url = select_download(manifest, chrome_version)

    with tempfile.TemporaryDirectory(prefix="project-query-driver-") as temp_name:
        temp_dir = Path(temp_name)
        archive = temp_dir / "chromedriver.zip"
        urllib.request.urlretrieve(download_url, archive)
        with zipfile.ZipFile(archive) as package:
            member = next(name for name in package.namelist() if name.endswith("/chromedriver.exe"))
            package.extract(member, temp_dir)
            shutil.copy2(temp_dir / member, runtime_dir / "chromedriver.exe")

    stealth_source = app_root.parent / "ElectronJS" / "stealth.min.js"
    if not stealth_source.exists():
        raise RuntimeError("EasySpider 的 stealth.min.js 不存在，仓库文件可能不完整。")
    shutil.copy2(stealth_source, runtime_dir / "stealth.min.js")

    (runtime_dir / "browser_runtime.json").write_text(
        json.dumps(
            {
                "chrome_binary": str(chrome_binary),
                "chrome_version": chrome_version,
                "chromedriver_version": driver_version,
                "download_url": download_url,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Chrome {chrome_version} / ChromeDriver {driver_version} 已就绪。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ChromeDriver 配置失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
