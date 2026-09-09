"""Distributed maps match their recorded identities and configured inventories."""

import hashlib
import json
import unittest
from pathlib import Path


class DistributionTests(unittest.TestCase):
    def test_checksums_cover_exactly_the_distributed_geometry_files(self):
        root = Path(__file__).parents[1]
        digests = {}
        for line in (root / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split()
            self.assertNotIn(name, digests)
            digests[name] = digest
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)
        self.assertEqual(set(digests), {path.name for path in root.glob("*.geo.json")})

    def test_historical_files_match_their_declared_inventory_and_geometry_dates(self):
        root = Path(__file__).parents[1]
        spec = json.loads((root / "municipalities.build.json").read_bytes())
        current = json.loads((root / "italy-municipalities.geo.json").read_bytes())
        for output in spec["outputs"]:
            with self.subTest(file=output["file"]):
                inventory = spec["inventories"][output["inventory"]]
                held = json.loads((root / output["file"]).read_bytes())
                self.assertEqual(held["viewBox"], current["viewBox"])
                self.assertEqual(held["reference_date"], inventory["reference_date"])
                self.assertEqual(len(held["shapes"]), inventory["rows"])
                expected_dates = {code: spec["geometries"][item["geometry"]]["reference_date"]
                                  for item in output["additions"] for code in item["codes"]}
                codes = set()
                for shape in held["shapes"]:
                    self.assertEqual(len(shape["aliases"]), 1)
                    code = shape["aliases"][0]
                    self.assertNotIn(code, codes)
                    codes.add(code)
                    self.assertRegex(code, "^" + spec["code_pattern"] + "$")
                    self.assertTrue(shape["name"].strip())
                    self.assertTrue(shape["d"].startswith("M"))
                    expected = (expected_dates[code] if code in expected_dates
                                else spec["geometries"][output["base"]]["reference_date"])
                    self.assertEqual(shape["boundary_date"], expected)
                self.assertLessEqual(set(expected_dates), codes)


if __name__ == "__main__":
    unittest.main()
