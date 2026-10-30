from pathlib import Path

from project_tool.easyspider_adapter import EasySpiderAdapter


def make_adapter(tmp_path: Path) -> EasySpiderAdapter:
    repo_root = tmp_path / "EasySpider"
    (repo_root / "ExecuteStage" / "execution_instances").mkdir(parents=True)
    runtime = tmp_path / "RenewableProjectWeb" / "runtime"
    runtime.mkdir(parents=True)
    return EasySpiderAdapter(repo_root, runtime)


def test_matching_browser_runtime_does_not_refresh(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path)
    monkeypatch.setattr(adapter, "_installed_chrome_version", lambda path: "156.0.8078.73")
    monkeypatch.setattr(adapter, "_installed_driver_version", lambda path: "156.0.8078.73")
    refreshed = []
    monkeypatch.setattr(adapter, "_refresh_browser_runtime", lambda *versions: refreshed.append(versions))

    adapter._ensure_browser_runtime()

    assert refreshed == []


def test_mismatched_browser_runtime_refreshes_driver(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path)
    monkeypatch.delenv("EASYSPIDER_CHROME_BINARY", raising=False)
    monkeypatch.delenv("EASYSPIDER_DRIVER_PATH", raising=False)
    monkeypatch.setattr(adapter, "_installed_chrome_version", lambda path: "156.0.8078.73")
    driver_versions = iter(["154.0.8037.92", "156.0.8078.73"])
    monkeypatch.setattr(adapter, "_installed_driver_version", lambda path: next(driver_versions))
    refreshed = []
    monkeypatch.setattr(adapter, "_refresh_browser_runtime", lambda *versions: refreshed.append(versions))

    adapter._ensure_browser_runtime()

    assert refreshed == [("156.0.8078.73", "154.0.8037.92")]


def test_missing_driver_also_triggers_refresh(tmp_path, monkeypatch):
    adapter = make_adapter(tmp_path)
    monkeypatch.delenv("EASYSPIDER_CHROME_BINARY", raising=False)
    monkeypatch.delenv("EASYSPIDER_DRIVER_PATH", raising=False)
    monkeypatch.setattr(adapter, "_installed_chrome_version", lambda path: "156.0.8078.73")
    driver_versions = iter(["", "156.0.8078.73"])
    monkeypatch.setattr(adapter, "_installed_driver_version", lambda path: next(driver_versions))
    refreshed = []
    monkeypatch.setattr(adapter, "_refresh_browser_runtime", lambda *versions: refreshed.append(versions))

    adapter._ensure_browser_runtime()

    assert refreshed == [("156.0.8078.73", "")]
