from project_tool.normalization import merge_project, normalize_page


CRITERIA = {
    "project_name": "远景肇庆广宁200MW/400MWh共享储能电站项目", "project_code": "",
    "project_company": "", "province": "广东省", "city": "肇庆市", "district": "广宁县", "keywords": "储能",
}


def test_realistic_text_extracts_scale_location_investment_and_strict_land():
    page = normalize_page(CRITERIA, {
        "source_site": "广宁公开报道", "page_title": "广宁高质量发展瞄准新能源赛道",
        "url": "https://example.gov.cn/a", "published_at": "2024-04-02", "fetched_at": "2026-09-08 12:00:00",
        "raw_text": "肇庆广宁200MW/400MWh共享储能电站项目拟位于广宁县南街街道220kV翠竹变电站旁，计划总投资6.4亿元，总用地约50亩，目前正在开展前期准备工作。",
    })
    assert page is not None
    project = merge_project(CRITERIA, [page])
    assert project["storage_scale"] == "200MW/400MWh"
    assert project["total_investment"] == "6.4亿元"
    assert "翠竹变电站" in project["location"]
    assert project["land_status"] == "已初步选址，土地落实情况待核实"


def test_other_projects_land_evidence_does_not_contaminate_target():
    text = (
        "相邻光伏项目已完成400多亩土地协议签署并已并网。"
        "广宁县引进肇庆广宁200MW/400MWh共享储能电站项目，"
        "拟建在广宁县南街街道220kV翠竹变电站旁，计划总投资总额6.4亿元，"
        "总占地约50亩。建设内容包括储能电池、管理系统和配电室。"
        "目前正在开展项目前期准备工作。"
    )
    page = normalize_page(CRITERIA, {
        "source_site": "政府官网", "page_title": "项目进展",
        "url": "https://example.gov.cn/a", "published_at": "2024-04-02",
        "fetched_at": "2026-09-08 12:00:00", "raw_text": text,
    })
    project = merge_project(CRITERIA, [page])
    assert project["project_name"] == CRITERIA["project_name"]
    assert project["storage_scale"] == "200MW/400MWh"
    assert project["total_investment"] == "6.4亿元"
    assert "220kV翠竹变电站旁" in project["location"]
    assert project["land_status"] == "已初步选址，土地落实情况待核实"


def test_same_scale_projects_in_other_regions_are_rejected():
    unrelated = [
        "中核罗甸200MW/400MWh共享储能电站项目已备案。",
        "湛江市生态环境局批准清烽能源东海岛200MW/400MWh储能电站项目环评文件。",
    ]
    no_location = {**CRITERIA, "province": "", "city": "", "district": ""}
    for text in unrelated:
        assert normalize_page(no_location, {
            "source_site": "政府官网", "page_title": "公开信息",
            "url": "https://example.gov.cn/unrelated", "published_at": "2025-01-01",
            "fetched_at": "2026-09-08 12:00:00", "raw_text": text,
        }) is None
