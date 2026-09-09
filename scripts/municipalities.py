"""Build municipality maps from pinned ISTAT inventories and geometry releases."""

import argparse
import hashlib
import json
import math
import re
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import shapefile
from shapely.geometry import shape


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError(f"configuration requires exactly these fields: {names}")


def specification(path):
    spec = json.loads(path.read_bytes())
    fields(spec, "schema_version sources geometries inventories frame canvas_width tolerance_metres precision code_pattern outputs")
    if spec["schema_version"] != 1:
        raise ValueError("municipality build schema_version must be 1")
    re.compile(spec["code_pattern"])
    for key in ("canvas_width", "tolerance_metres"):
        if type(spec[key]) not in (int, float) or not math.isfinite(spec[key]) or spec[key] <= 0:
            raise ValueError(f"{key} must be a finite positive number")
    if type(spec["precision"]) is not int or spec["precision"] < 0:
        raise ValueError("coordinate precision must be a non-negative integer")
    for key in ("sources", "geometries", "inventories"):
        if not isinstance(spec[key], dict) or not spec[key]:
            raise ValueError(f"{key} must declare at least one entry")
    for source in spec["sources"].values():
        fields(source, "file url sha256")
        url = urlsplit(source["url"])
        if (Path(source["file"]).name != source["file"] or url.scheme != "https" or not url.hostname
                or url.username is not None or url.password is not None or url.fragment
                or re.fullmatch(r"[a-f0-9]{64}", source["sha256"]) is None):
            raise ValueError("source requires a local filename, HTTPS URL and SHA-256")
    for geometry in spec["geometries"].values():
        fields(geometry, "source member code_field encoding projection_sha256 reference_date")
        if geometry["source"] not in spec["sources"]:
            raise ValueError("geometry names an undeclared source")
        date.fromisoformat(geometry["reference_date"])
    for inventory in spec["inventories"].values():
        fields(inventory, "source rows_field code_field name_field reference_date rows")
        if inventory["source"] not in spec["sources"] or type(inventory["rows"]) is not int or inventory["rows"] <= 0:
            raise ValueError("inventory requires a declared source and positive row count")
        date.fromisoformat(inventory["reference_date"])
    fields(spec["frame"], "source member projection_sha256")
    if spec["frame"]["source"] not in spec["sources"]:
        raise ValueError("reference frame names an undeclared source")
    if not isinstance(spec["outputs"], list) or not spec["outputs"]:
        raise ValueError("build must declare at least one output")
    filenames = set()
    for output in spec["outputs"]:
        fields(output, "file inventory base additions attribution")
        if re.fullmatch(r"[a-z][a-z0-9-]*\.geo\.json", output["file"]) is None:
            raise ValueError("output must name one geometry file")
        if output["inventory"] not in spec["inventories"] or output["base"] not in spec["geometries"]:
            raise ValueError("output requires declared inventory and base geometry")
        if output["file"] in filenames or not isinstance(output["attribution"], str) or not output["attribution"].strip():
            raise ValueError("outputs require distinct filenames and source attribution")
        filenames.add(output["file"])
        for addition in output["additions"]:
            fields(addition, "geometry codes")
            if addition["geometry"] not in spec["geometries"] or not addition["codes"]:
                raise ValueError("geometry addition requires a declared source and explicit codes")
            if (not isinstance(addition["codes"], list) or len(set(addition["codes"])) != len(addition["codes"])
                    or any(not isinstance(code, str) or re.fullmatch(spec["code_pattern"], code) is None
                           for code in addition["codes"])):
                raise ValueError("geometry additions require distinct valid municipality codes")
    return spec


def verified_sources(spec, inputs):
    sources = {}
    for name, source in spec["sources"].items():
        path = inputs / source["file"]
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != source["sha256"]:
            raise ValueError(f"source digest mismatch: {path}")
        sources[name] = path
    return sources


def svg_path(geometry, spec, transform):
    geometry = geometry.simplify(spec["tolerance_metres"], preserve_topology=True)
    polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    scale, left, top = transform
    precision = spec["precision"]
    rings = []
    for polygon in polygons:
        if polygon.geom_type != "Polygon" or polygon.is_empty:
            raise ValueError("municipality requires a non-empty polygon geometry")
        for ring in (polygon.exterior, *polygon.interiors):
            coordinates = [((x - left) * scale, (top - y) * scale) for x, y in ring.coords]
            if any(not math.isfinite(value) for point in coordinates for value in point):
                raise ValueError("municipality contains a non-finite coordinate")
            rings.append("M" + "L".join(f"{x:.{precision}f},{y:.{precision}f}" for x, y in coordinates) + "Z")
    return "".join(rings)


def geometry_rows(definition, sources, spec, transform):
    stem = definition["member"]
    with zipfile.ZipFile(sources[definition["source"]]) as archive:
        if hashlib.sha256(archive.read(stem + ".prj")).hexdigest() != definition["projection_sha256"]:
            raise ValueError("geometry projection differs from the qualified source")
        with (
            archive.open(stem + ".shp") as shp, archive.open(stem + ".dbf") as dbf,
            archive.open(stem + ".shx") as shx,
            shapefile.Reader(shp=shp, dbf=dbf, shx=shx, encoding=definition["encoding"]) as reader,
        ):
            result = {}
            for item in reader.iterShapeRecords():
                code = item.record[definition["code_field"]]
                if not isinstance(code, str) or re.fullmatch(spec["code_pattern"], code) is None or code in result:
                    raise ValueError("geometry requires distinct codes matching its source schema")
                result[code] = {"aliases": [code],
                                "d": svg_path(shape(item.shape.__geo_interface__), spec, transform),
                                "boundary_date": definition["reference_date"]}
            return result


def build(spec, inputs, output):
    sources = verified_sources(spec, inputs)
    frame = spec["frame"]
    with zipfile.ZipFile(sources[frame["source"]]) as archive:
        if hashlib.sha256(archive.read(frame["member"] + ".prj")).hexdigest() != frame["projection_sha256"]:
            raise ValueError("reference frame projection differs from its qualified source")
        with archive.open(frame["member"] + ".shp") as stream, shapefile.Reader(shp=stream) as reader:
            left, bottom, right, top = reader.bbox
    if any(not math.isfinite(value) for value in (left, bottom, right, top)) or right <= left or top <= bottom:
        raise ValueError("reference frame must have finite positive dimensions")
    scale = spec["canvas_width"] / (right - left)
    geometries = {name: geometry_rows(definition, sources, spec, (scale, left, top))
                  for name, definition in spec["geometries"].items()}
    rendered = {}
    for target in spec["outputs"]:
        inventory = spec["inventories"][target["inventory"]]
        rows = json.loads(sources[inventory["source"]].read_bytes())[inventory["rows_field"]]
        codes = [row[inventory["code_field"]] for row in rows]
        if (len(codes) != inventory["rows"] or len(set(codes)) != len(codes)
                or any(not isinstance(code, str) or re.fullmatch(spec["code_pattern"], code) is None for code in codes)):
            raise ValueError("inventory row count or municipality identity differs from its qualified scope")
        names = {row[inventory["code_field"]]: row[inventory["name_field"]] for row in rows}
        if any(not isinstance(name, str) or not name.strip() for name in names.values()):
            raise ValueError("official inventory requires a name for every municipality")
        selected = {code: geometries[target["base"]][code] for code in codes if code in geometries[target["base"]]}
        for addition in target["additions"]:
            for code in addition["codes"]:
                if code in selected or code not in codes:
                    raise ValueError("geometry addition overlaps or escapes the official inventory")
                selected[code] = geometries[addition["geometry"]][code]
        if set(selected) != set(codes):
            raise ValueError(f"municipality geometry is incomplete: {sorted(set(codes) - set(selected))}")
        rendered[target["file"]] = {"viewBox": f"0 0 {spec['canvas_width']:.0f} {(top-bottom)*scale:.1f}",
                                    "source": target["attribution"], "reference_date": inventory["reference_date"],
                                    "shapes": [{**selected[code], "name": names[code]} for code in sorted(selected)]}
    output.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, content in rendered.items():
        body = json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()
        (output / name).write_bytes(body)
        report[name] = {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "shapes": len(content["shapes"])}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(build(specification(arguments.spec), arguments.inputs, arguments.output), indent=2))
