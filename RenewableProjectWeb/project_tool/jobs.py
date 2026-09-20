from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .catalog import catalog_source
from .database import Database, now
from .discovery import SourceDiscovery
from .easyspider_adapter import EasySpiderAdapter
from .exporter import export_query
from .normalization import extract_published_date, merge_project, normalize_page


class JobManager:
    def __init__(self, database: Database, repo_root: Path, app_root: Path):
        self.db = database
        self.adapter = EasySpiderAdapter(repo_root, app_root / "runtime")
        self.app_root = app_root
        self._stops: dict[int, threading.Event] = {}
        self.logger = logging.getLogger("renewable_project_tool")

    def start(self, query_id: int, criteria: dict) -> None:
        event = threading.Event()
        self._stops[query_id] = event
        threading.Thread(target=self._run, args=(query_id, criteria, event), daemon=True).start()

    def start_batch(self, query_id: int, criteria: dict) -> None:
        event = threading.Event()
        self._stops[query_id] = event
        threading.Thread(target=self._run_batch, args=(query_id, criteria, event), daemon=True).start()

    def stop(self, query_id: int) -> None:
        event = self._stops.get(query_id)
        if event:
            event.set()
        self.adapter.stop(query_id)
        self.db.update_query(query_id, status="stopping", stage="正在停止")

    def _run(self, query_id: int, criteria: dict, stop: threading.Event) -> None:
        discovery = SourceDiscovery(self.app_root / "config" / "sources.json")
        try:
            self._progress(query_id, "running", "正在查询备案信息……", 5)
            candidates = discovery.discover(criteria, lambda stage, target, status, message: self.db.add_log(query_id, stage, target, status, message))
            page_timeout = int(discovery.config.get("page_timeout_seconds", 35))
            retry_count = max(0, int(discovery.config.get("retry_count", 1)))
            request_interval = max(0.2, float(discovery.config.get("request_interval_seconds", 1.2)))
            pages = []
            count = max(1, len(candidates))
            for index, candidate in enumerate(candidates, 1):
                if stop.is_set():
                    self.db.update_query(query_id, status="stopped", stage="查询已停止", completed_at=now())
                    self.db.add_log(query_id, "任务", "用户操作", "stopped", "用户停止查询")
                    return
                stage = display_stage(candidate.get("stage", "项目基本信息"))
                self._progress(query_id, "running", stage, 18 + int(index / count * 62))
                try:
                    captured = self._capture_with_retry(
                        query_id, index, candidate, page_timeout, retry_count, request_interval
                    )
                    captured.update({"source_site": candidate.get("name", "公开网站"),
                                     "published_at": extract_published_date(captured["raw_text"])})
                    normalized = normalize_page(criteria, captured)
                    if normalized:
                        pages.append(normalized)
                        self.db.add_log(query_id, candidate.get("stage", "采集"), candidate["url"], "success",
                                        f"EasySpider 已抓取正文，提取 {len(normalized['evidence'])} 条字段证据")
                    else:
                        self.db.add_log(query_id, candidate.get("stage", "采集"), candidate["url"], "empty", "正文与目标项目不匹配")
                except Exception as exc:
                    self.db.add_log(query_id, candidate.get("stage", "采集"), candidate["url"], "error",
                                    friendly_error(exc))
                    self.logger.exception("query=%s url=%s failed", query_id, candidate["url"])
                time.sleep(request_interval)
            self._progress(query_id, "running", "正在整理结果……", 86)
            project = merge_project(criteria, pages)
            self.db.save_project(query_id, project, pages)
            detail = self.db.query_detail(query_id)
            export_path = export_query(detail, self.app_root / "output")
            self.db.update_query(query_id, status="completed", stage="查询完成", progress=100,
                                 completed_at=now(), export_path=str(export_path))
            self.db.add_log(query_id, "结果整理", "Excel", "success", str(export_path))
        except Exception as exc:
            self.db.update_query(query_id, status="failed", stage="查询失败", completed_at=now(), error=str(exc))
            self.db.add_log(query_id, "任务", "系统", "error", str(exc))
            self.logger.exception("query=%s failed", query_id)
        finally:
            discovery.close()
            self._stops.pop(query_id, None)

    def _run_batch(self, query_id: int, batch: dict, stop: threading.Event) -> None:
        discovery = SourceDiscovery(self.app_root / "config" / "sources.json")
        selected = batch.get("projects") or []
        sequence = 1
        try:
            self._progress(query_id, "running", f"正在准备 {len(selected)} 个已选项目……", 2)
            page_timeout = int(discovery.config.get("page_timeout_seconds", 35))
            retry_count = max(0, int(discovery.config.get("retry_count", 1)))
            request_interval = max(0.2, float(discovery.config.get("request_interval_seconds", 1.2)))
            for project_index, selected_project in enumerate(selected):
                if stop.is_set():
                    self.db.update_query(query_id, status="stopped", stage="查询已停止", completed_at=now())
                    self.db.add_log(query_id, "任务", "用户操作", "stopped", "用户停止查询")
                    return
                criteria = {
                    "project_name": selected_project.get("project_name", ""),
                    "project_code": selected_project.get("project_code", ""),
                    "project_company": selected_project.get("project_company", ""),
                    "province": "广东省", "city": batch.get("city", ""),
                    "district": batch.get("district", ""), "keywords": batch.get("keywords", ""),
                }
                pages = [catalog_source(selected_project)]
                self.db.add_log(query_id, "备案信息", selected_project.get("url", ""), "success",
                                "已保存广东省投资项目在线审批监管平台公开备案记录")
                candidates = discovery.discover(
                    criteria,
                    lambda stage, target, status, message: self.db.add_log(query_id, stage, target, status, message),
                )
                count = max(1, len(candidates))
                for index, candidate in enumerate(candidates, 1):
                    if stop.is_set():
                        self.db.update_query(query_id, status="stopped", stage="查询已停止", completed_at=now())
                        return
                    within = (project_index + index / count) / max(1, len(selected))
                    self._progress(query_id, "running", display_stage(candidate.get("stage", "项目基本信息")),
                                   5 + int(within * 78))
                    try:
                        captured = self._capture_with_retry(
                            query_id, sequence, candidate, page_timeout, retry_count, request_interval
                        )
                        sequence += 1
                        captured.update({"source_site": candidate.get("name", "公开网站"),
                                         "published_at": extract_published_date(captured["raw_text"])})
                        normalized = normalize_page(criteria, captured)
                        if normalized:
                            pages.append(normalized)
                            self.db.add_log(query_id, candidate.get("stage", "采集"), candidate["url"], "success",
                                            f"EasySpider 已抓取正文，提取 {len(normalized['evidence'])} 条字段证据")
                        else:
                            self.db.add_log(query_id, candidate.get("stage", "采集"), candidate["url"], "empty",
                                            "正文与目标项目不匹配")
                    except Exception as exc:
                        sequence += 1
                        self.db.add_log(query_id, candidate.get("stage", "采集"), candidate["url"], "error",
                                        friendly_error(exc))
                    time.sleep(request_interval)
                project = merge_project(criteria, pages)
                self.db.save_project(query_id, project, pages)
            self._progress(query_id, "running", "正在整理结果……", 88)
            detail = self.db.query_detail(query_id)
            export_path = export_query(detail, self.app_root / "output")
            self.db.update_query(query_id, status="completed", stage="查询完成", progress=100,
                                 completed_at=now(), export_path=str(export_path))
            self.db.add_log(query_id, "结果整理", "Excel", "success", str(export_path))
        except Exception as exc:
            self.db.update_query(query_id, status="failed", stage="查询失败", completed_at=now(), error=str(exc))
            self.db.add_log(query_id, "任务", "系统", "error", str(exc))
            self.logger.exception("batch query=%s failed", query_id)
        finally:
            discovery.close()
            self._stops.pop(query_id, None)

    def _progress(self, query_id: int, status: str, stage: str, progress: int) -> None:
        self.db.update_query(query_id, status=status, stage=stage, progress=progress)

    def _capture_with_retry(self, query_id: int, sequence: int, candidate: dict,
                            timeout: int, retry_count: int, delay: float) -> dict:
        for attempt in range(retry_count + 1):
            try:
                return self.adapter.capture(query_id, sequence, candidate["url"], timeout=timeout)
            except Exception:
                if attempt >= retry_count:
                    raise
                self.db.add_log(query_id, candidate.get("stage", "采集"), candidate["url"], "retry",
                                f"第 {attempt + 1} 次访问失败，等待后重试。")
                time.sleep(delay)
        raise RuntimeError("页面采集未执行")


def display_stage(stage: str) -> str:
    if any(word in stage for word in ("自然", "选址")):
        return "正在查询自然资源信息……"
    if any(word in stage for word in ("土地", "用地")):
        return "正在查询土地信息……"
    if "环评" in stage:
        return "正在查询环评……"
    if any(word in stage for word in ("招标", "EPC")):
        return "正在查询招投标……"
    if any(word in stage for word in ("接入", "电网")):
        return "正在查询电网公开信息……"
    return "正在查询备案信息……"


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "页面访问超时，已跳过并继续查询其他来源。"
    first_line = str(exc).splitlines()[0].strip()
    if not first_line:
        first_line = exc.__class__.__name__
    return f"页面采集失败，已跳过并继续查询其他来源：{first_line[:240]}"
