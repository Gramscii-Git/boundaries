"""Native shapefile builds require exact inventory and qualified geometry inputs."""

import copy
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import shapefile

from scripts.municipalities import build, specification


class MunicipalityBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.output = self.root / "output"
        self.spec = json.loads((Path(__file__).parents[1] / "municipalities.build.json").read_bytes())
        projection = b"qualified test projection"
        self.spec["sources"] = {}
        self.spec["geometries"] = {}
        for name, codes in (("base", ["001001", "001002"]), ("addition", ["001003"])):
            stem = self.root / name
            with shapefile.Writer(str(stem), shapeType=shapefile.POLYGON, encoding="utf-8") as writer:
                writer.field("code", "C", size=6)
                for code in codes:
                    writer.poly([[[0, 0], [0, 10000], [10000, 10000], [10000, 0], [0, 0]]])
                    writer.record(code)
            stem.with_suffix(".prj").write_bytes(projection)
            archive = self.inputs / f"{name}.zip"
            with zipfile.ZipFile(archive, "w") as held:
                for suffix in (".shp", ".shx", ".dbf", ".prj"):
                    held.write(stem.with_suffix(suffix), name + suffix)
            self.source(name, archive)
            self.spec["geometries"][name] = {
                "source": name, "member": name, "code_field": "code", "encoding": "utf-8",
                "projection_sha256": hashlib.sha256(projection).hexdigest(), "reference_date": "2018-01-01",
            }
        inventory = self.inputs / "inventory.json"
        inventory.write_text(json.dumps({"rows": [
            {"code": "001001", "name": "Inventory name"}, {"code": "001003", "name": "New municipality"},
        ]}))
        self.source("inventory", inventory)
        self.spec["inventories"] = {"active": {
            "source": "inventory", "rows_field": "rows", "code_field": "code", "name_field": "name",
            "reference_date": "2018-12-31", "rows": 2,
        }}
        self.spec["frame"] = {key: self.spec["geometries"]["base"][key]
                              for key in ("source", "member", "projection_sha256")}
        self.spec["outputs"] = [{
            "file": "municipalities.geo.json", "inventory": "active", "base": "base",
            "additions": [{"geometry": "addition", "codes": ["001003"]}], "attribution": "Test source",
        }]

    def source(self, name, path):
        self.spec["sources"][name] = {
            "file": path.name, "url": "https://example.org/" + path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def run_build(self):
        path = self.root / "spec.json"
        path.write_text(json.dumps(self.spec))
        return build(specification(path), self.inputs, self.output)

    def test_official_inventory_excludes_retired_codes_and_names_every_shape(self):
        report = self.run_build()
        body = json.loads((self.output / "municipalities.geo.json").read_bytes())
        self.assertEqual([row["aliases"] for row in body["shapes"]], [["001001"], ["001003"]])
        self.assertEqual(body["shapes"][0]["name"], "Inventory name")
        self.assertEqual(body["reference_date"], "2018-12-31")
        self.assertEqual(report["municipalities.geo.json"]["shapes"], 2)
        self.assertTrue(all(row["d"].startswith("M") for row in body["shapes"]))

    def test_a_new_code_requires_an_explicit_geometry_assignment(self):
        self.spec["outputs"][0]["additions"] = []
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.run_build()
        self.assertFalse(self.output.exists())

    def test_changed_input_is_refused_before_rendering(self):
        (self.inputs / "inventory.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.run_build()
        self.assertFalse(self.output.exists())

    def test_unknown_projection_is_refused(self):
        self.spec["geometries"]["addition"]["projection_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "projection differs"):
            self.run_build()
        self.assertFalse(self.output.exists())

    def test_ambiguous_additions_or_output_names_are_refused(self):
        baseline = copy.deepcopy(self.spec)
        for codes in (["001001"], ["001999"], ["001003", "001003"]):
            with self.subTest(codes=codes):
                self.spec = copy.deepcopy(baseline)
                self.spec["outputs"][0]["additions"][0]["codes"] = codes
                with self.assertRaises(ValueError):
                    self.run_build()
                self.assertFalse(self.output.exists())
        self.spec = baseline
        self.spec["outputs"].append(copy.deepcopy(self.spec["outputs"][0]))
        with self.assertRaisesRegex(ValueError, "distinct filenames"):
            self.run_build()


if __name__ == "__main__":
    unittest.main()
