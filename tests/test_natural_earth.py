"""Natural Earth outputs retain the exact reproducible source contract."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import natural_earth


class NaturalEarthTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parents[1]
        self.spec = json.loads((self.root / "natural-earth.build.json").read_bytes())

    def test_build_spec_identifies_one_exact_map_units_archive(self):
        source = self.spec["source"]
        self.assertEqual(source["name"], "Natural Earth Admin 0 - Map Units")
        self.assertEqual(source["version"], "5.1.1")
        self.assertTrue(source["url"].endswith("/ne_50m_admin_0_map_units.zip"))
        self.assertEqual(source["member_base"], "ne_50m_admin_0_map_units")
        self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")

    def test_distributed_outputs_record_the_pinned_archive_and_unique_aliases(self):
        expected = self.spec["source"]["sha256"]
        for output in self.spec["outputs"]:
            with self.subTest(file=output["file"]):
                body = json.loads((self.root / output["file"]).read_bytes())
                self.assertEqual(body["source_archive_sha256"], expected)
                self.assertIn(self.spec["source"]["name"], body["source"])
                self.assertIn(self.spec["source"]["version"], body["source"])
                aliases = [alias for shape in body["shapes"] for alias in shape["aliases"]]
                self.assertEqual(len(aliases), len(set(aliases)))

    def test_archive_verification_rejects_a_different_input(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "source.zip"
            archive.write_bytes(b"different source")
            actual = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, actual):
                natural_earth._verify_archive(archive, self.spec["source"]["sha256"])


if __name__ == "__main__":
    unittest.main()
