import csv
from dataclasses import dataclass
from datetime import datetime, timezone

from research_scout.config import Settings
from research_scout.models import RESULT_FIELDS, Item, title_key


@dataclass
class Known:
    ids: set[str]
    titles: set[str]


class Writer:
    def __init__(self, settings: Settings):
        self.directory = settings.results_dir

    def ensure_file(self, username: str):
        path = self.directory / f"{username}.csv"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as handle:
                csv.DictWriter(handle, RESULT_FIELDS).writeheader()
        return path

    def known(self, username: str) -> Known:
        path = self.directory / f"{username}.csv"
        ids: set[str] = set()
        titles: set[str] = set()
        if not path.exists():
            return Known(ids, titles)
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("canonical_id"):
                    ids.add(row["canonical_id"])
                if row.get("kind") == "paper" and row.get("title"):
                    titles.add(title_key(row["title"]))
        return Known(ids, titles)

    def append(self, username: str, items: list[Item]) -> None:
        path = self.ensure_file(username)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, RESULT_FIELDS)
            for item in items:
                item.retrieved_at = stamp
                writer.writerow(item.row())
