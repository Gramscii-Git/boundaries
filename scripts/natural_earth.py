"""Build reproducible country geometry from one pinned Natural Earth archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import shapefile
from pyproj import Transformer
from shapely.geometry import box
from shapely.geometry import shape as to_shape
from shapely.ops import transform, unary_union


def _load(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if value.get("schema_version") != 1:
        raise ValueError("Natural Earth build specification requires schema version 1")
    return value


def _verify_archive(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Natural Earth archive checksum differs: {actual}")


def _reader(archive: Path, member_base: str, directory: Path):
    required = [f"{member_base}.{suffix}" for suffix in ("shp", "shx", "dbf", "prj", "cpg")]
    with zipfile.ZipFile(archive) as source:
        names = set(source.namelist())
        missing = set(required) - names
        if missing:
            raise ValueError(f"Natural Earth archive omits members: {sorted(missing)}")
        for name in required:
            target = directory / name
            target.write_bytes(source.read(name))
    return shapefile.Reader(str(directory / f"{member_base}.shp"))


def _records(reader, identity: dict) -> list[tuple[str, str, str, object]]:
    grouped = {}
    aliases = identity["aliases"]
    missing = identity["missing_code"]
    for record, held in zip(reader.records(), reader.shapes(), strict=True):
        fields = record.as_dict()
        record_id = fields[identity["record_id_field"]]
        override = identity["overrides"].get(record_id, {})
        alpha2 = override.get("alpha2", fields[identity["alpha2_field"]])
        alpha3 = override.get("alpha3", fields[identity["alpha3_field"]])
        name = fields[identity["name_field"]]
        group_name = fields[identity["group_name_field"]]
        if alpha2 == missing or alpha3 == missing:
            continue
        if not isinstance(alpha2, str) or len(alpha2) != 2 or not alpha2.isupper():
            raise ValueError(f"Natural Earth alpha-2 identity is invalid: {alpha2!r}")
        if not isinstance(alpha3, str) or len(alpha3) != 3 or not alpha3.isupper():
            raise ValueError(f"Natural Earth alpha-3 identity is invalid: {alpha3!r}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Natural Earth {alpha3} has no English name")
        if not isinstance(group_name, str) or not group_name.strip():
            raise ValueError(f"Natural Earth {alpha3} has no group name")
        geometry = to_shape(held.__geo_interface__)
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Natural Earth {alpha3} geometry is invalid")
        entry = grouped.setdefault((alpha2, alpha3), {"names": set(), "group_names": set(), "geometries": []})
        entry["names"].add(name.strip())
        entry["group_names"].add(group_name.strip())
        entry["geometries"].append(geometry)
    rows = []
    for (alpha2, alpha3), entry in grouped.items():
        repeated = len(entry["geometries"]) > 1
        names = entry["group_names"] if repeated else entry["names"]
        configured_name = identity["group_names"].get(alpha2)
        if configured_name is not None:
            names = {configured_name}
        if len(names) != 1:
            raise ValueError(f"Natural Earth {alpha3} has ambiguous grouped names: {sorted(names)}")
        geometry = unary_union(entry["geometries"])
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Natural Earth {alpha3} grouped geometry is invalid")
        rows.append((alpha2, alpha3, next(iter(names)), geometry))
    unknown = set(aliases) - {alpha2 for alpha2, _, _, _ in rows}
    if unknown:
        raise ValueError(f"configured aliases reference absent countries: {sorted(unknown)}")
    return rows


def _path(geometry, tolerance: float, scale: float, left: float, top: float) -> str:
    simplified = geometry.simplify(tolerance, preserve_topology=True)
    polygons = getattr(simplified, "geoms", [simplified])
    parts = []
    for polygon in polygons:
        if polygon.is_empty or polygon.geom_type != "Polygon":
            continue
        for ring in [polygon.exterior, *polygon.interiors]:
            points = [f"{(x - left) * scale:.1f},{(top - y) * scale:.1f}" for x, y in ring.coords]
            if len(points) >= 4:
                parts.append("M" + "L".join(points) + "Z")
    if not parts:
        raise ValueError("projected country geometry produces no SVG path")
    return "".join(parts)


def _build(rows, source: dict, identity: dict, output: dict) -> dict:
    transformer = Transformer.from_crs("EPSG:4326", output["projection"], always_xy=True)
    projected = [
        (alpha2, alpha3, name, transform(transformer.transform, geometry))
        for alpha2, alpha3, name, geometry in rows
    ]
    frame = output["frame"]
    if frame is None:
        bounds = [geometry.bounds for _, _, _, geometry in projected]
        frame = [
            min(item[0] for item in bounds), min(item[1] for item in bounds),
            max(item[2] for item in bounds), max(item[3] for item in bounds),
        ]
    clip = box(*frame)
    selected = []
    for alpha2, alpha3, name, geometry in projected:
        clipped = geometry.intersection(clip)
        if clipped.is_empty:
            continue
        selected.append((alpha2, alpha3, name, clipped))
    left, bottom, right, top = frame
    width = output["canvas_width"]
    scale = width / (right - left)
    shapes = []
    seen = set()
    for alpha2, alpha3, name, geometry in selected:
        values = [alpha2, alpha3, *identity["aliases"].get(alpha2, [])]
        if seen.intersection(values):
            raise ValueError(f"country aliases are ambiguous: {values}")
        seen.update(values)
        shapes.append({
            "aliases": values,
            "name": name,
            "d": _path(geometry, output["simplification_tolerance"], scale, left, top),
        })
    shapes.sort(key=lambda item: item["aliases"][0])
    return {
        "viewBox": f"0 0 {width:.0f} {(top - bottom) * scale:.1f}",
        "source": (
            f"{source['name']}, {source['version']}, {source['scale']}, "
            f"{source['license']}"
        ),
        "source_archive_sha256": source["sha256"],
        "shapes": shapes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    spec = _load(args.spec)
    _verify_archive(args.archive, spec["source"]["sha256"])
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as held:
        reader = _reader(args.archive, spec["source"]["member_base"], Path(held))
        rows = _records(reader, spec["identity"])
        for output in spec["outputs"]:
            body = _build(rows, spec["source"], spec["identity"], output)
            target = args.output / output["file"]
            target.write_text(
                json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            print(f"{target.name}: {len(body['shapes'])} shapes")


if __name__ == "__main__":
    main()
