from project_tool.catalog import catalog_source, city_code, public_candidate
from project_tool.normalization import merge_project


def test_catalog_record_becomes_a_grade_evidence_and_strict_land_status():
    candidate = public_candidate({
        "baId": "1", "projectName": "远景肇庆广宁200MW/400MWh共享储能电站项目",
        "projectCode": "2504-441223-04-01-343550", "projectDept": "蔚能（广宁）储能科技有限公司",
        "projectAddress": "肇庆市广宁县横山镇荔洞村委会高新产业园二期",
        "areaDetailName": "肇庆市广宁县横山镇", "stateFlagName": "办结（通过）",
        "finishDate": "2025-04-30", "totalMoney": 38000,
        "scaleContent": "本项目建设200MW/400MWh电化学储能系统，采用磷酸铁锂电池。",
        "projectStarttimeS": "2026-01",
    })
    source = catalog_source(candidate)
    criteria = {"project_name": candidate["project_name"], "project_code": candidate["project_code"],
                "project_company": candidate["project_company"], "province": "广东省", "city": "肇庆市",
                "district": "广宁县", "keywords": "储能"}
    project = merge_project(criteria, [source])
    assert city_code("肇庆市") == "4412"
    assert source["grade"] == "A"
    assert project["storage_scale"] == "200MW/400MWh"
    assert project["total_investment"] == "38000万元"
    assert project["land_status"] == "已初步选址，土地落实情况待核实"
