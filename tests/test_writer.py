import csv

from research_scout.config import Settings
from research_scout.models import RESULT_FIELDS, Item
from research_scout.workers.writer import Writer


def _settings(tmp_path, **overrides) -> Settings:
    values = dict(
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        logs_dir=tmp_path / "logs",
        metrics_dir=tmp_path / "metrics",
    )
    values.update(overrides)
    settings = Settings(**values, _env_file=None)
    settings.ensure_dirs()
    return settings


def _paper(canonical_id: str, title: str) -> Item:
    return Item(
        kind="paper",
        canonical_id=canonical_id,
        title=title,
        authors="Ada Lovelace",
        source="openalex",
        venue_or_site="NeurIPS",
        published_date="2024-01-01",
        url="https://example.com/paper",
        excerpt="An abstract.",
        query="agents",
        band="direct",
        relevancy_score=80,
        reason="matches the topic",
    )


def test_first_append_creates_file_and_keeps_header(tmp_path):
    writer = Writer(_settings(tmp_path))
    path = writer.ensure_file("ada_1")
    writer.append("ada_1", [_paper("doi:10.1/a", "First Paper")])
    writer.append("ada_1", [_paper("doi:10.1/b", "Second Paper")])

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert path == tmp_path / "results" / "ada_1.csv"
    assert list(rows[0]) == RESULT_FIELDS
    assert [row["canonical_id"] for row in rows] == ["doi:10.1/a", "doi:10.1/b"]
    assert rows[0]["authors"] == "Ada Lovelace"
    assert rows[0]["relevancy_score"] == "80"


def test_blog_venue_is_empty_and_known_ids_include_title(tmp_path):
    writer = Writer(_settings(tmp_path, results_dir=tmp_path / "custom-results"))
    blog = Item(
        kind="blog",
        canonical_id="url:https://example.com/post",
        title="Useful notes",
        authors="Grace",
        source="example.com",
        venue_or_site="should be cleared",
        published_date="2024-02-01",
        url="https://example.com/post",
        excerpt="A short note.",
        query="agents",
        band="direct",
        relevancy_score=75,
        reason="practical match",
    )
    writer.append("ada_1", [_paper("doi:10.1/a", "Same Title"), blog])
    known = writer.known("ada_1")

    with (tmp_path / "custom-results" / "ada_1.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[1]["venue_or_site"] == ""
    assert "doi:10.1/a" in known.ids
    assert "url:https://example.com/post" in known.ids
    assert "same title" in known.titles
