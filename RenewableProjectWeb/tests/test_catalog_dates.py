import pytest
from fastapi import HTTPException

from app import CatalogSearchInput, jobs, search_catalog


def test_catalog_search_passes_date_range_to_engine(monkeypatch):
    seen = {}

    def fake_search(keyword, city, page, page_size, **options):
        seen.update(keyword=keyword, city=city, page=page, page_size=page_size, **options)
        return {"items": [], "page": page, "page_size": 15, "total": 0,
                "total_pages": 0, "next_page": 2, "has_more": False,
                "scanned_to": 1, "date_filtered": True}

    monkeypatch.setattr(jobs.adapter, "search_guangdong_catalog", fake_search)
    result = search_catalog(CatalogSearchInput(keyword="储能", city="肇庆市",
                                               start_date="2026-01-01", end_date="2026-09-16"))
    assert seen == {"keyword": "储能", "city": "4412", "page": 1, "page_size": 15,
                    "start_date": "2026-01-01", "end_date": "2026-09-16"}
    assert result["date_filtered"] is True


@pytest.mark.parametrize("start_date,end_date", [
    ("2026-09-17", "2026-09-16"), ("2026-02-30", ""),
])
def test_catalog_search_rejects_invalid_date_range(start_date, end_date):
    with pytest.raises(HTTPException) as error:
        search_catalog(CatalogSearchInput(keyword="储能", start_date=start_date, end_date=end_date))
    assert error.value.status_code == 422
