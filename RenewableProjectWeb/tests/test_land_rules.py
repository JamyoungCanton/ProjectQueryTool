from project_tool.normalization import EMPTY, assess_land


def pages(text: str):
    return [{"raw_text": text}]


def test_planned_site_is_not_land_implemented():
    result = assess_land(pages("项目拟位于广宁县南街街道220kV翠竹变电站旁，总用地约50亩。"))
    assert result == "已初步选址，土地落实情况待核实"
    assert "项目用地已落实" != result


def test_preapproval_level():
    assert assess_land(pages("已取得《建设项目用地预审与选址意见书》。")) == "已取得用地预审及选址意见"


def test_construction_land_approval_level():
    assert assess_land(pages("省政府印发建设用地批复。")) == "建设用地已获批"


def test_transaction_level():
    assert assess_land(pages("国有建设用地使用权成交公告已发布。")) == "项目用地已落实"


def test_ownership_level():
    assert assess_land(pages("项目公司已取得不动产权证。")) == "土地权属已落实"


def test_no_evidence_is_unknown():
    assert assess_land(pages("项目开展前期工作。")) == EMPTY

