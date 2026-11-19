"""Shapefile, GeoPackage, GeoTIFF, GeoJSON, KML and a QGIS project.

Field names in the shapefile are at most 10 characters. ``README_fields.csv``
is the map from those short names to the full ones, with units. The ``.cpg``
sidecar is UTF-8 so Turkish characters survive the round trip. GeoPackage is
the format to prefer: one file, no name limit, and ``run.json`` in the metadata.
"""
from __future__ import annotations

import json
import os
import sqlite3
import struct
import zipfile
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

# Short shapefile name -> (long name, unit, type, size)
# type is C / N / F as shapefile field types.
SITE_FIELDS = [
    ("NAME", "name", "", "C", 80),
    ("CONFID", "confidence", "", "C", 20),
    ("START_BC", "start_bc", "cal BC", "N", 8),
    ("END_BC", "end_bc", "cal BC", "N", 8),
    ("ACTIVE", "active_in_window", "1", "N", 2),
    ("DATE_QUAL", "date_quality", "", "C", 16),
    ("DEGREE", "weighted_degree", "min", "F", 12),
    ("CLOSENESS", "closeness", "1", "F", 12),
    ("BETWEEN", "betweenness", "1", "F", 12),
    ("EIGEN", "eigenvector", "1", "F", 12),
]
OD_FIELDS = [
    ("NAME", "name", "", "C", 80),
    ("KIND", "kind", "", "C", 24),
    ("PHASES", "phase_ids", "", "C", 80),
    ("OW", "origin_weight", "1", "F", 8),
    ("DW", "dest_weight", "1", "F", 8),
    ("CAPACITY", "capacity", "persons", "F", 10),
    ("SITE", "site", "", "C", 80),
]
BUILDING_FIELDS = [
    ("KIND", "kind", "", "C", 16),
    ("LAYER", "layer", "", "C", 32),
    ("HEIGHT", "height", "m", "F", 8),
    ("PHASES", "phase_ids", "", "C", 80),
    ("FUNCTION", "function", "", "C", 16),
    ("INHAB", "inhabitants", "persons", "F", 8),
    ("STATE", "state", "", "C", 20),
]

EPSG_32637_WKT = (
    'PROJCS["WGS 84 / UTM zone 37N",'
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],'
    'PARAMETER["central_meridian",39],PARAMETER["scale_factor",0.9996],'
    'PARAMETER["false_easting",500000],PARAMETER["false_northing",0],'
    'UNIT["metre",1],AXIS["Easting",EAST],AXIS["Northing",NORTH]]'
)


def schema_text() -> str:
    """The shapefile field schema, one layer per block. Used by the golden test."""
    lines = []
    for layer, fields in (("sites", SITE_FIELDS), ("ods", OD_FIELDS),
                          ("buildings", BUILDING_FIELDS)):
        lines.append(f"[{layer}]")
        for short, long, unit, kind, size in fields:
            lines.append(f"{short},{long},{unit},{kind},{size}")
    return "\n".join(lines) + "\n"


def _prj(directory: str, layer: str) -> None:
    with open(os.path.join(directory, f"{layer}.prj"), "w", encoding="utf-8") as fh:
        fh.write(EPSG_32637_WKT)
    with open(os.path.join(directory, f"{layer}.cpg"), "w", encoding="utf-8") as fh:
        fh.write("UTF-8")


def _write_shp(path: str, shape_type: str, fields, records, geoms) -> None:
    import shapefile

    kind = {"point": shapefile.POINT, "line": shapefile.POLYLINE,
            "polygon": shapefile.POLYGON}[shape_type]
    writer = shapefile.Writer(path, shapeType=kind, encoding="utf-8")
    for short, _long, _unit, ftype, size in fields:
        if ftype == "C":
            writer.field(short, "C", size=size)
        elif ftype == "N":
            writer.field(short, "N", size=size, decimal=0)
        else:
            writer.field(short, "F", size=18, decimal=4)
    for rec, geom in zip(records, geoms):
        if shape_type == "point":
            writer.point(geom[0], geom[1])
        elif shape_type == "line":
            writer.line([list(geom)])
        else:
            writer.poly([list(geom)])
        writer.record(*rec)
    writer.close()
    directory, layer = os.path.split(os.path.splitext(path)[0])
    _prj(directory or ".", layer)


def _num(value, default=0):
    if value is None or value == "":
        return default
    return value


def export_shapefiles(directory: str, sites: Sequence[dict], ods: Sequence[dict],
                      buildings: Sequence[dict]) -> List[str]:
    """Write sites, ods and buildings. Coordinates are already in EPSG:32637."""
    os.makedirs(directory, exist_ok=True)
    written = []
    site_recs, site_xy = [], []
    for s in sites:
        site_recs.append([
            s.get("name", ""), s.get("confidence", ""),
            _num(s.get("start_bc"), 0), _num(s.get("end_bc"), 0),
            int(bool(s.get("active", 0))), s.get("date_quality", ""),
            float(s.get("degree", 0) or 0), float(s.get("closeness", 0) or 0),
            float(s.get("betweenness", 0) or 0), float(s.get("eigenvector", 0) or 0),
        ])
        site_xy.append((float(s["x"]), float(s["y"])))
    path = os.path.join(directory, "sites")
    _write_shp(path, "point", SITE_FIELDS, site_recs, site_xy)
    written.append(path + ".shp")

    od_recs, od_xy = [], []
    for od in ods:
        od_recs.append([
            od.get("name", ""), od.get("kind", ""),
            ",".join(od.get("phase_ids") or []),
            float(od.get("origin_weight", 0) or 0),
            float(od.get("dest_weight", 0) or 0),
            float(od.get("capacity") or 0),
            od.get("site", ""),
        ])
        od_xy.append((float(od["x"]), float(od["y"])))
    path = os.path.join(directory, "ods")
    _write_shp(path, "point", OD_FIELDS, od_recs, od_xy)
    written.append(path + ".shp")

    b_recs, b_xy = [], []
    for b in buildings:
        ring = [(float(x), float(y)) for x, y in b["polygon"]]
        if ring and ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        b_recs.append([
            b.get("kind", "building"), b.get("layer", ""),
            float(b.get("height", 0) or 0),
            ",".join(b.get("phase_ids") or []),
            b.get("function", ""),
            float(b.get("inhabitants") or 0),
            b.get("state", "standing"),
        ])
        b_xy.append(ring)
    path = os.path.join(directory, "buildings")
    _write_shp(path, "polygon", BUILDING_FIELDS, b_recs, b_xy)
    written.append(path + ".shp")

    with open(os.path.join(directory, "README_fields.csv"), "w", encoding="utf-8") as fh:
        fh.write("layer,short,long,unit\n")
        for layer, fields in (("sites", SITE_FIELDS), ("ods", OD_FIELDS),
                              ("buildings", BUILDING_FIELDS)):
            for short, long, unit, _t, _s in fields:
                fh.write(f"{layer},{short},{long},{unit}\n")
    return written


def _wkb_point(x: float, y: float) -> bytes:
    return struct.pack("<BIdd", 1, 1, float(x), float(y))


def _wkb_line(coords: Sequence[Tuple[float, float]]) -> bytes:
    body = struct.pack("<BI", 1, 2) + struct.pack("<I", len(coords))
    for x, y in coords:
        body += struct.pack("<dd", float(x), float(y))
    return body


def _wkb_polygon(ring: Sequence[Tuple[float, float]]) -> bytes:
    coords = list(ring)
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    body = struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(coords))
    for x, y in coords:
        body += struct.pack("<dd", float(x), float(y))
    return body


def _gpkg_geom(wkb: bytes, srs: int = 32637) -> bytes:
    # 'GP' + version 0 + flags (little-endian, no envelope) + srs_id + wkb
    return b"GP" + bytes([0, 0x01]) + struct.pack("<i", srs) + wkb


def export_gpkg(path: str, sites: Sequence[dict], ods: Sequence[dict],
                buildings: Sequence[dict], run_json: str = "") -> str:
    """One GeoPackage. ``run_json`` is stored in ``gpkg_metadata``."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("PRAGMA application_id = 1196444487")
    cur.execute("PRAGMA user_version = 10300")
    cur.executescript(
        """
        CREATE TABLE gpkg_spatial_ref_sys (
            srs_name TEXT NOT NULL, srs_id INTEGER NOT NULL PRIMARY KEY,
            organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
            definition TEXT NOT NULL, description TEXT);
        CREATE TABLE gpkg_contents (
            table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
            identifier TEXT UNIQUE, description TEXT DEFAULT '',
            last_change TEXT NOT NULL, min_x DOUBLE, min_y DOUBLE,
            max_x DOUBLE, max_y DOUBLE, srs_id INTEGER);
        CREATE TABLE gpkg_geometry_columns (
            table_name TEXT NOT NULL, column_name TEXT NOT NULL,
            geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
            z TINYINT NOT NULL, m TINYINT NOT NULL,
            PRIMARY KEY (table_name, column_name));
        CREATE TABLE gpkg_metadata (
            id INTEGER PRIMARY KEY, md_scope TEXT NOT NULL DEFAULT 'dataset',
            md_standard_uri TEXT NOT NULL, mime_type TEXT NOT NULL,
            metadata TEXT NOT NULL);
        """
    )
    cur.execute(
        "INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)",
        ("WGS 84 / UTM zone 37N", 32637, "EPSG", 32637, EPSG_32637_WKT, "UTM 37N"),
    )
    _gpkg_points(cur, "sites", sites, lambda s: (s["x"], s["y"]),
                 ["name", "confidence", "start_bc", "end_bc", "active"])
    _gpkg_points(cur, "ods", ods, lambda s: (s["x"], s["y"]),
                 ["name", "kind", "site"])
    _gpkg_polygons(cur, "buildings", buildings)
    cur.execute(
        "INSERT INTO gpkg_metadata (md_scope, md_standard_uri, mime_type, metadata) "
        "VALUES ('dataset', 'pedsim:run', 'application/json', ?)",
        (run_json or "{}",),
    )
    con.commit()
    con.close()
    return path


def _gpkg_points(cur, table, rows, xy, columns):
    cols = ", ".join(f"{c} TEXT" for c in columns)
    cur.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, geom BLOB, {cols})")
    xs, ys = [], []
    for i, row in enumerate(rows, start=1):
        x, y = xy(row)
        xs.append(float(x))
        ys.append(float(y))
        values = [str(row.get(c, "")) for c in columns]
        placeholders = ", ".join(["?"] * (2 + len(columns)))
        cur.execute(
            f"INSERT INTO {table} (id, geom, {', '.join(columns)}) VALUES ({placeholders})",
            [i, _gpkg_geom(_wkb_point(x, y)), *values],
        )
    _gpkg_register(cur, table, "POINT", xs, ys)


def _gpkg_polygons(cur, table, rows):
    cur.execute(
        f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, geom BLOB, name TEXT, function TEXT, phase_ids TEXT)"
    )
    xs, ys = [], []
    for i, row in enumerate(rows, start=1):
        ring = [(float(x), float(y)) for x, y in row["polygon"]]
        for x, y in ring:
            xs.append(x)
            ys.append(y)
        cur.execute(
            f"INSERT INTO {table} (id, geom, name, function, phase_ids) VALUES (?,?,?,?,?)",
            [i, _gpkg_geom(_wkb_polygon(ring)), row.get("name", ""),
             row.get("function", ""), ",".join(row.get("phase_ids") or [])],
        )
    _gpkg_register(cur, table, "POLYGON", xs, ys)


def _gpkg_register(cur, table, geom_type, xs, ys):
    if not xs:
        xs, ys = [0.0], [0.0]
    cur.execute(
        "INSERT INTO gpkg_contents VALUES (?,?,?,?,?,?,?,?,?,?)",
        (table, "features", table, "", "2026-01-01T00:00:00Z",
         min(xs), min(ys), max(xs), max(ys), 32637),
    )
    cur.execute(
        "INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)",
        (table, "geom", geom_type, 32637, 0, 0),
    )


def read_gpkg_buildings(path: str) -> List[dict]:
    """Read building rings back, for the QGIS round trip."""
    con = sqlite3.connect(path)
    cur = con.cursor()
    try:
        rows = cur.execute("SELECT id, geom, function, phase_ids FROM buildings").fetchall()
    except sqlite3.OperationalError:
        con.close()
        return []
    out = []
    for _id, blob, function, phases in rows:
        ring = _ring_from_gpkg(blob)
        out.append({
            "polygon": ring, "function": function or "",
            "phase_ids": [p for p in (phases or "").split(",") if p],
        })
    con.close()
    return out


def _ring_from_gpkg(blob: bytes) -> List[Tuple[float, float]]:
    # header: GP + version + flags + srs (4) then WKB
    wkb = blob[8:]
    _order, gtype, nrings = struct.unpack_from("<BII", wkb, 0)
    npts = struct.unpack_from("<I", wkb, 9)[0]
    coords = []
    offset = 13
    for _ in range(npts):
        x, y = struct.unpack_from("<dd", wkb, offset)
        coords.append((x, y))
        offset += 16
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    return coords


def export_geojson(path: str, features: Sequence[dict]) -> str:
    """Features are ``{geometry, properties}`` already in EPSG:4326."""
    collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": f["geometry"], "properties": f.get("properties", {})}
        for f in features
    ]}
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(collection, fh, ensure_ascii=False, indent=2)
    return path


def export_kml(path: str, placemarks: Sequence[dict]) -> str:
    """``placemarks`` have ``name``, ``lon``, ``lat``."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>']
    for mark in placemarks:
        parts.append(
            "<Placemark><name>{}</name><Point><coordinates>{:.7f},{:.7f},0</coordinates></Point></Placemark>".format(
                escape(str(mark.get("name", ""))), float(mark["lon"]), float(mark["lat"]),
            )
        )
    parts.append("</Document></kml>")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return path


def export_qgz(path: str, gpkg_name: str, run_id: str, layers: Sequence[str]) -> str:
    """A zipped QGIS project that references ``gpkg_name`` and records ``run_id``."""
    layer_xml = []
    for name in layers:
        layer_xml.append(
            f'<maplayer type="vector" name="{escape(name)}">'
            f'<datasource>./{escape(gpkg_name)}|layername={escape(name)}</datasource>'
            f'<provider>ogr</provider>'
            f'<layername>{escape(name)}</layername>'
            f'</maplayer>'
        )
    qgs = (
        '<qgis version="3.28" projectname="pedsim">'
        f'<title>pedsim {escape(run_id)}</title>'
        f'<properties><run_id>{escape(run_id)}</run_id></properties>'
        '<projectlayers>' + "".join(layer_xml) + '</projectlayers>'
        '</qgis>'
    )
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project.qgs", qgs)
    return path


def export_csv(path: str, columns: Sequence[str], rows: Iterable[Sequence],
               units: Dict[str, str]) -> str:
    from .tables import write_table
    return write_table(path, columns, rows, units)


def import_buildings_gpkg(path: str, sim) -> List[str]:
    """Replace building geometry from a GeoPackage edited elsewhere.

    Unknown attribute names are returned, not dropped quietly. Matching is by
    row order, which is how the export wrote them.
    """
    rows = read_gpkg_buildings(path)
    notes = []
    con = sqlite3.connect(path)
    cols = [r[1] for r in con.execute("PRAGMA table_info(buildings)").fetchall()]
    con.close()
    known = {"id", "geom", "name", "function", "phase_ids"}
    for col in cols:
        if col not in known:
            notes.append(f"unknown field: {col}")
    for building, row in zip(sim.buildings, rows):
        building.footprint.vertices.clear()
        building.footprint.min_x = building.footprint.min_y = float("inf")
        building.footprint.max_x = building.footprint.max_y = float("-inf")
        for x, y in row["polygon"]:
            building.footprint.add_vertex(x, y, 0.0)
        if row["phase_ids"]:
            building.phase_ids = list(row["phase_ids"])
        if row["function"]:
            building.function = row["function"]
    sim.grid.set_geometry(*sim.geometry_for_grid(), sim.site_polygon)
    return notes
