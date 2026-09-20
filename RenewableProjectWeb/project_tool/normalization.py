from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher
from urllib.parse import urlparse


FIELD_LABELS = {
    "project_name": "项目名称", "project_code": "项目代码", "construction_unit": "建设单位",
    "project_company": "项目公司", "actual_investor": "实际投资主体", "location": "建设地点",
    "construction_scale": "建设规模", "storage_scale": "储能规模", "total_investment": "总投资",
    "filing_status": "备案状态", "filing_time": "备案时间", "planned_start": "计划开工时间",
    "planned_grid_connection": "计划并网时间", "land_status": "土地落实情况",
    "land_preapproval": "用地预审", "site_opinion": "选址意见", "construction_land_approval": "建设用地批复",
    "land_transaction": "土地成交/划拨信息", "eia": "环评", "epc_tender": "EPC招标",
    "epc_winner": "EPC中标单位", "grid_access": "接入系统", "grid_support": "电网支持意见",
    "construction_status": "开工情况", "grid_connection_status": "并网情况",
}
EMPTY = "公开信息暂未查询到"


PATTERNS: dict[str, list[str]] = {
    "project_code": [r"(?:项目代码|备案项目编号|备案证号)[：:\s]*([A-Za-z0-9_-]{8,40})"],
    "construction_unit": [r"(?:建设单位|项目单位|建设单位名称|项目法人)[：:\s]*([^，。；;\n]{4,100}(?:公司|集团|委员会|中心))"],
    "project_company": [r"(?:项目公司|建设单位|项目单位)[：:\s]*([^，。；;\n]{4,100}(?:公司|集团))"],
    "actual_investor": [r"(?:实际投资主体|投资主体|投资方)[：:\s]*([^，。；;\n]{4,100}(?:公司|集团))"],
    "location": [r"((?:拟位于|拟建于|拟建在|建设地点[：:]?|项目位于|选址于)[^。；;\n]{4,160})"],
    "storage_scale": [r"(\d+(?:\.\d+)?\s*(?:MW|兆瓦|万千瓦)\s*[/／]\s*\d+(?:\.\d+)?\s*(?:MWh|兆瓦时|万千瓦时))"],
    "construction_scale": [r"(?:建设规模|建设内容|项目规模)[：:\s]*([^。；;\n]{8,260})"],
    "total_investment": [r"(?:计划)?总投资(?:总额|额)?[约为：:\s]*([0-9,.]+\s*(?:亿元|万元|元))"],
    "filing_status": [r"((?:已|完成|通过).{0,8}(?:项目)?备案|备案证已获批)"],
    "filing_time": [r"(?:备案时间|备案日期|办结日期)[：:\s]*(20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?)"],
    "planned_start": [r"(?:计划|拟|预计)(?:于)?[^。]{0,12}(20\d{2}年(?:\d{1,2}月)?)[^。]{0,8}(?:开工|动工)"],
    "planned_grid_connection": [r"(?:计划|预计)(?:于)?[^。]{0,12}(20\d{2}年(?:\d{1,2}月)?)[^。]{0,12}(?:并网|投产)"],
    "epc_winner": [r"(?:EPC(?:总承包)?中标单位|中标人|第一中标候选人)[：:\s]*([^，。；;\n]{4,120}(?:公司|集团|院))"],
}


def normalize_page(criteria: dict, page: dict) -> dict | None:
    text = re.sub(r"[ \t\u3000]+", " ", page.get("raw_text", ""))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 40 or not is_relevant(criteria, text):
        return None
    relevant_text = project_context(criteria, text)
    grade, category = source_grade(page["url"])
    evidence: list[dict] = []
    name = best_project_name(criteria["project_name"], relevant_text)
    if name:
        evidence.append(item("project_name", name, excerpt(relevant_text, name), grade))
    for field, patterns in PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, relevant_text, re.I)
            if match:
                evidence.append(item(field, clean(match.group(1)), excerpt(relevant_text, match.group(0)), grade))
                break
    flags = {
        "land_preapproval": (r"建设项目用地预审(?:与|及)选址意见书|用地预审.{0,20}(?:批复|通过|取得)", "已取得"),
        "site_opinion": (r"选址意见书.{0,20}(?:核发|取得|批复)|建设项目用地预审与选址意见书", "已取得"),
        "construction_land_approval": (r"建设用地(?:批复|批准文件|审批同意)|农用地转用.{0,20}批复", "已取得"),
        "land_transaction": (r"(?:国有建设用地|土地)(?:使用权)?(?:成交公告|出让合同)|划拨决定书", "已查询到"),
        "eia": (r"(?:环境影响报告(?:书|表)|环评)(?:批复|审批意见|获批|通过)", "已取得"),
        "epc_tender": (r"EPC(?:总承包)?(?:招标公告|中标公告|中标候选人公示)|工程总承包.{0,20}(?:招标|中标)", "已招标"),
        "grid_access": (r"接入系统.{0,20}(?:批复|审查意见|方案批复|通过|同意)", "已取得"),
        "grid_support": (r"电网(?:支持意见|消纳意见).{0,20}(?:取得|通过|同意)", "已取得"),
        "construction_status": (r"(?:正式|已经|已)(?:开工|动工)", "已开工"),
        "grid_connection_status": (r"(?:正式|已经|已)(?:全容量)?并网", "已并网"),
    }
    for field, (pattern, value) in flags.items():
        match = re.search(pattern, relevant_text, re.I)
        if match:
            evidence.append(item(field, value, excerpt(relevant_text, match.group(0)), grade))
    page.update({"raw_text": text[:1_500_000], "relevant_text": relevant_text,
                 "grade": grade, "category": category, "evidence": evidence})
    return page


def merge_project(criteria: dict, pages: list[dict]) -> dict:
    merged = {key: EMPTY for key in FIELD_LABELS}
    merged["project_name"] = criteria["project_name"]
    if criteria.get("project_code"):
        merged["project_code"] = criteria["project_code"]
    if criteria.get("project_company"):
        merged["project_company"] = criteria["project_company"]
    choices: dict[str, list[tuple[int, str, str]]] = {}
    for page in pages:
        for evidence in page.get("evidence", []):
            choices.setdefault(evidence["field_name"], []).append(("ABCD".index(evidence["grade"]), page.get("published_at", ""), evidence["value"]))
    for field, values in choices.items():
        if field == "project_name" and criteria.get("project_name"):
            continue
        values.sort(key=lambda row: (row[0], _reverse_date(row[1])))
        merged[field] = values[0][2]
    merged["land_status"] = assess_land(pages)
    merged["source_count"] = len(pages)
    merged["query_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return merged


def assess_land(pages: list[dict]) -> str:
    text = " ".join(page.get("relevant_text", page.get("raw_text", "")) for page in pages)
    if re.search(r"不动产权证|不动产权证明|土地使用权证", text):
        return "土地权属已落实"
    if re.search(r"国有建设用地(?:使用权)?成交公告|土地成交公告|划拨决定书|土地出让合同", text):
        return "项目用地已落实"
    if re.search(r"建设用地(?:批复|批准文件)|农用地转用.{0,20}批复", text):
        return "建设用地已获批"
    if re.search(r"建设项目用地预审(?:与|及)选址意见书", text):
        return "已取得用地预审及选址意见"
    if re.search(r"拟选址|拟建于|拟建在|拟位于|项目地址|拟用地\s*\d|总(?:用地|占地)(?:约)?\s*\d", text):
        return "已初步选址，土地落实情况待核实"
    return EMPTY


def is_relevant(criteria: dict, text: str) -> bool:
    name = criteria["project_name"]
    if name in text or criteria.get("project_code") and criteria["project_code"] in text:
        return True
    locations = [criteria.get("district", ""), criteria.get("city", "")]
    locations = [value.removesuffix("市").removesuffix("县").removesuffix("区") for value in locations if value]
    if locations and not any(value and value in text for value in locations):
        return False
    identity_hits = sum(token in text for token in identity_tokens(name))
    candidates = re.findall(r"[^。；\n]{4,100}(?:储能电站|数据中心|算力中心)(?:建设)?项目?", text)
    return identity_hits >= 2 and any(
        SequenceMatcher(None, clean(name), clean(candidate)).ratio() >= 0.55 for candidate in candidates
    )


def identity_tokens(project_name: str) -> set[str]:
    prefix = re.split(r"\d+(?:\.\d+)?\s*(?:MW|兆瓦|万千瓦)", project_name, maxsplit=1, flags=re.I)[0]
    prefix = re.sub(r"项目|新能源|共享|独立|储能|电站|建设", "", prefix)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", prefix))
    ignored = {"项目", "储能", "电站", "共享", "独立", "建设", "新能源"}
    return {chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))
            if chinese[index:index + 2] not in ignored}


def project_context(criteria: dict, text: str) -> str:
    """Select target-project sentences so nearby projects cannot contaminate fields."""
    sentences = [part.strip() for part in re.split(r"(?<=[。！？])\s*", text) if part.strip()]
    if not sentences:
        return text
    expected = criteria.get("project_name", "")
    scale_match = re.search(r"\d+(?:\.\d+)?\s*MW\s*[/／]\s*\d+(?:\.\d+)?\s*MWh", expected, re.I)
    scale = re.sub(r"\s+", "", scale_match.group(0)).lower() if scale_match else ""
    terms = [criteria.get("project_code", ""), criteria.get("district", ""), "共享储能", "独立储能"]

    def score(sentence: str) -> int:
        compact = re.sub(r"\s+", "", sentence).lower()
        value = 100 if expected and expected in sentence else 0
        if scale and scale in compact:
            value += 45
        for term in terms:
            if term and term in sentence:
                value += 12
        for token in re.findall(r"[\u4e00-\u9fff]{2,6}", expected):
            if token in sentence:
                value += min(len(token), 6)
        return value

    best_index = max(range(len(sentences)), key=lambda index: score(sentences[index]))
    if score(sentences[best_index]) <= 0:
        return text
    return " ".join(sentences[best_index:min(len(sentences), best_index + 3)])


def best_project_name(expected: str, text: str) -> str:
    if expected in text:
        return expected
    candidates = re.findall(r"[^。；\n]{4,100}(?:储能电站|数据中心|算力中心)(?:建设)?项目?", text)
    return max(candidates, key=lambda value: SequenceMatcher(None, expected, value).ratio(), default="").strip("，,：: ")


def source_grade(url: str) -> tuple[str, str]:
    host = urlparse(url).netloc.lower()
    if host.endswith("gov.cn") or host in {"csg.cn", "www.csg.cn"}:
        return "A", "政府部门/电网公司"
    if any(key in host for key in ("ggzy", "cebpubservice", "cncec")):
        return "B", "正式招投标/企业官网"
    if any(key in host for key in ("nfnews.com", "southcn.com", "people.com.cn", "xinhuanet.com")):
        return "C", "权威新闻媒体"
    return "D", "其他公开来源"


def extract_published_date(text: str) -> str:
    match = re.search(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})", text[:3000])
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}" if match else ""


def item(field: str, value: str, quote: str, grade: str) -> dict:
    return {"field_name": field, "value": value, "excerpt": quote[:1000], "grade": grade}


def excerpt(text: str, needle: str, radius: int = 180) -> str:
    pos = text.find(needle)
    return text[max(0, pos - radius):pos + len(needle) + radius].strip() if pos >= 0 else text[: radius * 2]


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ：:，,。；;")


def _reverse_date(value: str) -> int:
    digits = re.sub(r"\D", "", value)[:8]
    return -int(digits or 0)
