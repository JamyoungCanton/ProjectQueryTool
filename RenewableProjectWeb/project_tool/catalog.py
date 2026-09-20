from __future__ import annotations

import re
from datetime import datetime


CATALOG_URL = "https://tzxm.gd.gov.cn/PublicityInformation/PublicityHandlingResultsList.html"
CITY_CODES = {
    "广州": "4401", "韶关": "4402", "深圳": "4403", "珠海": "4404", "汕头": "4405",
    "佛山": "4406", "江门": "4407", "湛江": "4408", "茂名": "4409", "肇庆": "4412",
    "惠州": "4413", "梅州": "4414", "汕尾": "4415", "河源": "4416", "阳江": "4417",
    "清远": "4418", "东莞": "4419", "中山": "4420", "潮州": "4451", "揭阳": "4452",
    "云浮": "4453",
}


def city_code(value: str) -> str:
    compact = (value or "").replace("广东省", "").replace("市", "").strip()
    return CITY_CODES.get(compact, "")


def public_candidate(row: dict) -> dict:
    money = row.get("totalMoney")
    total_investment = f"{money:g}万元" if isinstance(money, (int, float)) else ""
    scale = clean(row.get("scaleContent"))
    return {
        "catalog_id": str(row.get("baId") or row.get("id") or ""),
        "project_name": clean(row.get("projectName")),
        "project_code": clean(row.get("projectCode")),
        "project_company": clean(row.get("projectDept") or row.get("legalDeptName")),
        "construction_unit": clean(row.get("projectDept") or row.get("legalDeptName")),
        "location": clean(row.get("projectAddress") or row.get("areaDetailName")),
        "construction_scale": scale,
        "storage_scale": storage_scale(scale or clean(row.get("projectName"))),
        "total_investment": total_investment,
        "filing_status": clean(row.get("stateFlagName") or row.get("auditTypeName")),
        "filing_time": clean(row.get("finishDate") or row.get("operateDate")),
        "planned_start": clean(row.get("projectStarttimeS")),
        "planned_completion": clean(row.get("projectEndtimeS")),
        "area": clean(row.get("areaDetailName")),
        "approval_unit": clean(row.get("approveUnitName")),
        "source_site": "广东省投资项目在线审批监管平台",
        "url": CATALOG_URL,
    }


def catalog_source(project: dict) -> dict:
    lines = [
        f"项目名称：{project.get('project_name', '')}", f"项目代码：{project.get('project_code', '')}",
        f"建设单位：{project.get('construction_unit') or project.get('project_company', '')}",
        f"项目地址：{project.get('location', '')}", f"建设规模：{project.get('construction_scale', '')}",
        f"储能规模：{project.get('storage_scale', '')}", f"总投资：{project.get('total_investment', '')}",
        f"备案状态：{project.get('filing_status', '')}", f"备案时间：{project.get('filing_time', '')}",
        f"计划开工时间：{project.get('planned_start', '')}", f"计划竣工时间：{project.get('planned_completion', '')}",
        f"备案机关：{project.get('approval_unit', '')}",
    ]
    raw = "\n".join(line for line in lines if not line.endswith("："))
    evidence = []
    mapping = {
        "project_name": "project_name", "project_code": "project_code", "construction_unit": "construction_unit",
        "project_company": "project_company", "location": "location", "construction_scale": "construction_scale",
        "storage_scale": "storage_scale", "total_investment": "total_investment",
        "filing_status": "filing_status", "filing_time": "filing_time", "planned_start": "planned_start",
    }
    for source_key, field_name in mapping.items():
        value = clean(project.get(source_key))
        if value:
            evidence.append({"field_name": field_name, "value": value, "excerpt": raw, "grade": "A"})
    return {"source_site": "广东省投资项目在线审批监管平台",
            "page_title": "备案项目公开检索结果", "url": CATALOG_URL,
            "published_at": project.get("filing_time", "")[:10],
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "raw_text": raw,
            "relevant_text": raw, "category": "政府部门/官方备案信息", "grade": "A", "evidence": evidence}


def storage_scale(value: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?\s*(?:MW|兆瓦|万千瓦)\s*[/／]\s*\d+(?:\.\d+)?\s*(?:MWh|兆瓦时|万千瓦时)", value, re.I)
    return re.sub(r"\s+", "", match.group(0)) if match else ""


def clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
