from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from project_tool.catalog import city_code, public_candidate
from project_tool.database import Database
from project_tool.jobs import JobManager


APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT.parent
(APP_ROOT / "logs").mkdir(exist_ok=True)
handler = logging.FileHandler(APP_ROOT / "logs" / f"{datetime.now():%Y-%m-%d}.log", encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

db = Database(APP_ROOT / "data" / "project_queries.db")
jobs = JobManager(db, REPO_ROOT, APP_ROOT)
app = FastAPI(title="新能源项目公开信息查询工具", docs_url=None, redoc_url=None)
catalog_cache: dict[str, dict] = {}
catalog_cache_lock = threading.RLock()


class QueryInput(BaseModel):
    project_name: str = Field(min_length=2, max_length=200)
    project_code: str = Field(default="", max_length=80)
    project_company: str = Field(default="", max_length=200)
    province: str = Field(default="", max_length=40)
    city: str = Field(default="", max_length=40)
    district: str = Field(default="", max_length=40)
    keywords: str = Field(default="", max_length=300)


class CatalogSearchInput(BaseModel):
    keyword: str = Field(min_length=1, max_length=120)
    city: str = Field(default="", max_length=40)
    page: int = Field(default=1, ge=1, le=10000)
    start_date: str = Field(default="", max_length=10)
    end_date: str = Field(default="", max_length=10)


class SelectedProject(BaseModel):
    catalog_id: str = Field(default="", max_length=100)
    project_name: str = Field(min_length=1, max_length=300)
    project_code: str = Field(default="", max_length=80)
    project_company: str = Field(default="", max_length=300)
    construction_unit: str = Field(default="", max_length=300)
    location: str = Field(default="", max_length=500)
    construction_scale: str = Field(default="", max_length=5000)
    storage_scale: str = Field(default="", max_length=100)
    total_investment: str = Field(default="", max_length=100)
    filing_status: str = Field(default="", max_length=100)
    filing_time: str = Field(default="", max_length=60)
    planned_start: str = Field(default="", max_length=60)
    planned_completion: str = Field(default="", max_length=60)
    area: str = Field(default="", max_length=100)
    approval_unit: str = Field(default="", max_length=300)
    source_site: str = Field(default="广东省投资项目在线审批监管平台", max_length=100)
    url: str = Field(default="", max_length=1000)


class BatchQueryInput(BaseModel):
    projects: list[SelectedProject] = Field(min_length=1, max_length=10)
    keyword: str = Field(default="", max_length=120)
    city: str = Field(default="", max_length=40)
    district: str = Field(default="", max_length=40)
    keywords: str = Field(default="", max_length=300)


@app.post("/api/catalog/search")
def search_catalog(payload: CatalogSearchInput):
    try:
        start_date = date.fromisoformat(payload.start_date) if payload.start_date else None
        end_date = date.fromisoformat(payload.end_date) if payload.end_date else None
    except ValueError as exc:
        raise HTTPException(422, "请输入有效的备案通过日期。") from exc
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "开始日期不能晚于结束日期。")
    try:
        result = jobs.adapter.search_guangdong_catalog(
            payload.keyword.strip(), city_code(payload.city), payload.page, 15,
            start_date=payload.start_date, end_date=payload.end_date
        )
    except Exception as exc:
        logging.getLogger("renewable_project_tool").exception("catalog search failed")
        raise HTTPException(502, f"广东省备案平台检索失败：{str(exc).splitlines()[0][:180]}") from exc
    items = [public_candidate(item) for item in result["items"]]
    with catalog_cache_lock:
        for item in items:
            if item["catalog_id"]:
                catalog_cache[item["catalog_id"]] = item
    return {"items": items, "page": result["page"], "page_size": result["page_size"],
            "total": result["total"], "total_pages": result["total_pages"],
            "next_page": result["next_page"], "has_more": result["has_more"],
            "scanned_to": result["scanned_to"], "date_filtered": result["date_filtered"]}


@app.post("/api/queries/batch")
def create_batch_query(payload: BatchQueryInput):
    criteria = payload.model_dump()
    with catalog_cache_lock:
        verified = [catalog_cache.get(project.catalog_id) for project in payload.projects]
    if any(project is None for project in verified):
        raise HTTPException(409, "候选项目已失效，请重新搜索后再选择。")
    criteria["projects"] = verified
    criteria["province"] = "广东省"
    query_id = db.create_query(criteria)
    jobs.start_batch(query_id, criteria)
    return {"id": query_id, "status": "queued", "project_count": len(payload.projects)}


@app.post("/api/queries")
def create_query(payload: QueryInput):
    criteria = {key: value.strip() for key, value in payload.model_dump().items()}
    query_id = db.create_query(criteria)
    jobs.start(query_id, criteria)
    return {"id": query_id, "status": "queued"}


@app.get("/api/queries/{query_id}")
def query_detail(query_id: int):
    detail = db.query_detail(query_id)
    if not detail:
        raise HTTPException(404, "查询记录不存在")
    for source in detail["sources"]:
        source["raw_text_preview"] = source["raw_text"][:1200]
        source.pop("raw_text", None)
    return detail


@app.post("/api/queries/{query_id}/stop")
def stop_query(query_id: int):
    if not db.query_detail(query_id):
        raise HTTPException(404, "查询记录不存在")
    jobs.stop(query_id)
    return {"status": "stopping"}


@app.get("/api/history")
def history():
    return db.history(100)


@app.get("/api/queries/{query_id}/export")
def download_export(query_id: int):
    detail = db.query_detail(query_id)
    if not detail or not detail.get("export_path"):
        raise HTTPException(404, "导出文件尚未生成")
    path = Path(detail["export_path"])
    if not path.exists():
        raise HTTPException(404, "导出文件不存在")
    return FileResponse(path, filename=path.name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


app.mount("/", StaticFiles(directory=APP_ROOT / "static", html=True), name="static")
