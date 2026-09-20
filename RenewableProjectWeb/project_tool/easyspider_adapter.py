from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


class EasySpiderAdapter:
    """Creates hidden preconfigured EasySpider instances and runs its executor."""

    def __init__(self, repo_root: Path, runtime_dir: Path):
        self.repo_root = repo_root
        self.execute_dir = repo_root / "ExecuteStage"
        self.runtime_dir = runtime_dir
        self.instance_dir = self.execute_dir / "execution_instances"
        self.instance_dir.mkdir(parents=True, exist_ok=True)
        self._processes: dict[int, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def capture(self, query_id: int, sequence: int, url: str, timeout: int = 50) -> dict:
        instance_id = 900000 + query_id * 100 + sequence
        save_name = f"project_{query_id}_{sequence}"
        task = self._build_task(instance_id, url, save_name)
        (self.instance_dir / f"{instance_id}.json").write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        chrome = os.environ.get("EASYSPIDER_CHROME_BINARY", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        driver = os.environ.get("EASYSPIDER_DRIVER_PATH", str(self.runtime_dir / "chromedriver.exe"))
        env["EASYSPIDER_CHROME_BINARY"] = chrome
        env["EASYSPIDER_DRIVER_PATH"] = driver
        output_file = self.execute_dir / "Data" / f"Task_{instance_id}" / f"{save_name}.json"
        command = [
            sys.executable, "-u", str(self.execute_dir / "easyspider_executestage.py"),
            "--ids", f"[{instance_id}]", "--read_type", "local", "--headless", "1",
            "--keyboard", "0", "--saved_file_name", save_name,
        ]
        process = subprocess.Popen(
            command,
            cwd=self.execute_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        with self._lock:
            self._processes[query_id] = process
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._terminate_process_tree(process)
            try:
                output, _ = process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
            if not output_file.exists():
                raise TimeoutError(f"EasySpider 页面任务超时：{url}\n{output[-1200:]}")
        finally:
            with self._lock:
                self._processes.pop(query_id, None)
        if process.returncode != 0 and not output_file.exists():
            raise RuntimeError(f"EasySpider 执行失败（退出码 {process.returncode}）：{output[-1600:]}")
        if not output_file.exists():
            raise RuntimeError(f"EasySpider 未生成预期结果：{output[-1600:]}")
        rows = json.loads(output_file.read_text(encoding="utf-8-sig"))
        if not rows:
            raise RuntimeError("EasySpider 返回空数据")
        row = rows[-1]
        return {
            "page_title": str(row.get("page_title", "")).strip(),
            "url": str(row.get("page_url", url)).strip() or url,
            "raw_text": str(row.get("raw_text", "")).strip(),
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "engine_log": output[-3000:],
        }

    def search_guangdong_catalog(self, keyword: str, city_code: str = "", page: int = 1,
                                 page_size: int = 15, timeout: int = 70,
                                 start_date: str = "", end_date: str = "") -> dict:
        """Run a hidden EasySpider task against the official Guangdong filing catalog."""
        instance_id = 800000000 + int(time.time() * 1000) % 100000000
        save_name = f"gd_catalog_{instance_id}"
        page_size = min(max(int(page_size), 1), 15)
        page = max(int(page), 1)
        payload = {"flag": "1", "nameOrCode": keyword.strip(), "pageSize": page_size,
                   "city": city_code[:4], "pageNumber": page}
        task = self._build_catalog_task(instance_id, save_name, payload, start_date, end_date)
        (self.instance_dir / f"{instance_id}.json").write_text(
            json.dumps(task, ensure_ascii=False), encoding="utf-8"
        )
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["EASYSPIDER_CHROME_BINARY"] = os.environ.get(
            "EASYSPIDER_CHROME_BINARY", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        env["EASYSPIDER_DRIVER_PATH"] = os.environ.get(
            "EASYSPIDER_DRIVER_PATH", str((self.runtime_dir / "chromedriver.exe").resolve())
        )
        output_file = self.execute_dir / "Data" / f"Task_{instance_id}" / f"{save_name}.json"
        command = [sys.executable, "-u", str(self.execute_dir / "easyspider_executestage.py"),
                   "--ids", f"[{instance_id}]", "--read_type", "local", "--headless", "1",
                   "--keyboard", "0", "--saved_file_name", save_name]
        process = subprocess.Popen(command, cwd=self.execute_dir, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._terminate_process_tree(process)
            raise TimeoutError("广东省备案项目目录检索超时")
        if process.returncode != 0 or not output_file.exists():
            raise RuntimeError(f"EasySpider 备案目录任务失败：{output[-1000:]}")
        rows = json.loads(output_file.read_text(encoding="utf-8-sig"))
        raw = str(rows[-1].get("catalog_json", "")) if rows else ""
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("广东省备案平台返回内容无法解析") from exc
        data = response.get("data") or {}
        filtered = bool(start_date or end_date)
        total_pages = int(data.get("totalPage") or 0)
        scanned_to = int(response.get("scanned_to") or data.get("pageNumber") or page)
        next_page = scanned_to + 1
        return {"items": data.get("list") or [], "page": page,
                "page_size": data.get("pageSize", page_size), "total": data.get("totalRow", 0),
                "total_pages": total_pages, "next_page": next_page,
                "has_more": next_page <= total_pages, "scanned_to": scanned_to,
                "date_filtered": filtered, "engine_log": output[-1600:]}

    def stop(self, query_id: int) -> None:
        with self._lock:
            process = self._processes.get(query_id)
        if process and process.poll() is None:
            self._terminate_process_tree(process)

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            process.terminate()

    def _build_task(self, instance_id: int, url: str, save_name: str) -> dict:
        task = json.loads((self.repo_root / "ElectronJS" / "tasks" / "30.json").read_text(encoding="utf-8"))
        task.update({
            "id": instance_id, "version": "0.6.5", "name": "新能源项目公开页面采集", "url": url, "links": url,
            "desc": "内部预配置任务：采集页面标题、URL和正文", "outputFormat": "json",
            "saveName": save_name, "quitWaitTime": 0, "recordLog": True,
        })
        task["inputParameters"] = [{"id": 0, "name": "urlList_0", "nodeId": 1, "nodeName": "打开公开页面",
                                     "value": url, "desc": "公开页面URL", "type": "string", "exampleValue": url}]
        task["outputParameters"] = [
            {"id": 0, "name": "page_title", "desc": "页面标题", "type": "text", "recordASField": True},
            {"id": 1, "name": "page_url", "desc": "页面URL", "type": "text", "recordASField": True},
            {"id": 2, "name": "raw_text", "desc": "页面原始文本", "type": "text", "recordASField": True},
        ]
        task["graph"] = [
            {"index": 0, "id": 0, "parentId": 0, "type": -1, "option": 0, "title": "root", "sequence": [1, 2],
             "parameters": {"history": 1, "tabIndex": 0, "useLoop": False, "xpath": "", "wait": 0}, "isInLoop": False},
            {"id": 1, "index": 1, "parentId": 0, "type": 0, "option": 1, "title": "打开公开页面", "sequence": [],
             "isInLoop": False, "position": 0, "parameters": {"useLoop": False, "xpath": "", "wait": 3,
             "url": url, "links": url, "scrollType": 0, "scrollCount": 1}},
            {"id": 2, "index": 2, "parentId": 0, "type": 0, "option": 3, "title": "提取页面证据", "sequence": [],
             "isInLoop": False, "position": 1, "parameters": {"history": 1, "tabIndex": -1, "useLoop": False,
             "xpath": "", "wait": 1, "params": [
                 self._extract_param("page_title", 6, ""), self._extract_param("page_url", 5, ""),
                 self._extract_param("raw_text", 0, "/html/body"),
             ]}},
        ]
        return task

    def _build_catalog_task(self, instance_id: int, save_name: str, payload: dict,
                            start_date: str = "", end_date: str = "") -> dict:
        url = "https://tzxm.gd.gov.cn/PublicityInformation/PublicityHandlingResults.html"
        task = json.loads((self.repo_root / "ElectronJS" / "tasks" / "30.json").read_text(encoding="utf-8"))
        task.update({"id": instance_id, "version": "0.6.5", "name": "广东省备案项目关键词检索",
                     "url": url, "links": url, "desc": "内部预配置任务：检索广东省备案项目公开目录",
                     "outputFormat": "json", "saveName": save_name, "quitWaitTime": 0, "recordLog": True})
        task["inputParameters"] = []
        task["outputParameters"] = [
            {"id": 0, "name": "catalog_json", "desc": "官网检索结果", "type": "text", "recordASField": True}
        ]
        encoded = json.dumps(payload, ensure_ascii=False)
        request_js = (
            "var xhr=new XMLHttpRequest();"
            "xhr.open('POST','/tzxmspweb/api/publicityInformation/selectByPageBA',false);"
            "xhr.setRequestHeader('Content-Type','application/json;charset=UTF-8');"
            "xhr.setRequestHeader('X-Requested-With','XMLHttpRequest');"
            "xhr.send(JSON.stringify(query));"
            "if(xhr.status<200||xhr.status>=300){throw new Error('HTTP '+xhr.status);};"
        )
        if start_date or end_date:
            js = (
                f"var query={encoded};"
                f"var startDate={json.dumps(start_date)},endDate={json.dumps(end_date)};"
                "var matched=[],last=null,firstPage=query.pageNumber,scannedTo=firstPage;"
                "for(var scan=0;scan<12;scan++){"
                "query.pageNumber=firstPage+scan;scannedTo=query.pageNumber;"
                + request_js +
                "last=JSON.parse(xhr.responseText);"
                "var data=last.data||{},rows=data.list||[];"
                "for(var i=0;i<rows.length;i++){"
                "var date=String(rows[i].finishDate||'').slice(0,10);"
                "if(date&&(!startDate||date>=startDate)&&(!endDate||date<=endDate))matched.push(rows[i]);"
                "}"
                "if(matched.length>=15||!rows.length||scannedTo>=Number(data.totalPage||0))break;"
                "}"
                "last.data.list=matched;"
                "return JSON.stringify({data:last.data,scanned_to:scannedTo});"
            )
        else:
            js = f"var query={encoded};" + request_js + "return xhr.responseText;"
        task["graph"] = [
            {"index": 0, "id": 0, "parentId": 0, "type": -1, "option": 0, "title": "root", "sequence": [1, 2],
             "parameters": {"history": 1, "tabIndex": 0, "useLoop": False, "xpath": "", "wait": 0}, "isInLoop": False},
            {"id": 1, "index": 1, "parentId": 0, "type": 0, "option": 1, "title": "打开广东省备案公开页",
             "sequence": [], "isInLoop": False, "position": 0,
             "parameters": {"useLoop": False, "xpath": "", "wait": 4, "beforeJS": "", "beforeJSWaitTime": 0,
                            "afterJS": "", "afterJSWaitTime": 0, "url": url, "links": url, "maxWaitTime": 20,
                            "scrollType": 0, "scrollCount": 1, "scrollWaitTime": 1}},
            {"id": 2, "index": 2, "parentId": 0, "type": 0, "option": 5, "title": "catalog_json",
             "sequence": [], "isInLoop": False, "position": 1,
             "parameters": {"history": 1, "tabIndex": -1, "useLoop": False, "xpath": "", "wait": 0,
                            "beforeJS": "", "beforeJSWaitTime": 0, "afterJS": "", "afterJSWaitTime": 0,
                            "codeMode": 0, "code": js, "waitTime": 20, "recordASField": 1,
                            "newLine": 1, "clear": 0, "iframe": False}},
        ]
        return task

    @staticmethod
    def _extract_param(name: str, content_type: int, xpath: str) -> dict:
        return {"nodeType": 0, "contentType": content_type, "relative": False, "name": name, "desc": "",
                "extractType": 0, "relativeXPath": xpath, "allXPaths": [xpath] if xpath else [],
                "exampleValues": [], "default": "", "beforeJS": "", "beforeJSWaitTime": 0, "JS": "",
                "JSWaitTime": 0, "afterJS": "", "afterJSWaitTime": 0, "downloadPic": 0}
