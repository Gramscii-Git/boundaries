"""Hugging Face publication contains every verified boundary exactly once."""

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from scripts.hugging_face import build


class HuggingFaceTests(unittest.TestCase):
    def test_build_has_deterministic_complete_licence_separated_rows(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            release = build(root, Path(first))
            repeated = build(root, Path(second))
            self.assertEqual(release, repeated)
            self.assertEqual(
                sum(item["rows"] for item in release["data_files"].values()),
                33852,
            )
            for group, metadata in release["data_files"].items():
                with gzip.open(Path(first) / metadata["file"], "rt", encoding="utf-8") as source:
                    rows = [json.loads(line) for line in source]
                self.assertEqual(len(rows), metadata["rows"])
                self.assertEqual(
                    {row["commercial_use"] for row in rows},
                    {group == "open"},
                )
                identities = {
                    (row["boundary_set_id"], alias)
                    for row in rows
                    for alias in row["aliases"]
                }
                self.assertEqual(
                    len(identities),
                    sum(len(row["aliases"]) for row in rows),
                )


if __name__ == "__main__":
    unittest.main()
