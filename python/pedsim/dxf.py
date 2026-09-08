"""DXF importer -- a Python port of the Java ``utility.DXFHandler`` family.

Parses the ASCII DXF ENTITIES section into:

* ``lines``    -- :class:`DXFLine` segments (with layer),
* ``lwpolys``  -- :class:`DXFPoly` lightweight polylines (footprints),
* ``polys``    -- :class:`DXFPoly` old-style polylines / poly-face meshes,
* ``meshes``   -- :class:`DXFMesh` 3D meshes, from which a ground **footprint**
  is extracted by isolating the bottom faces and stitching the triangles into a
  ring (``DXFMesh.footprint``).

As in the original, the Y coordinate is negated on import (DXF is Y-up, the
sketch works Y-down), and geometry can be scaled by a global factor.

This reads the very files shipped with the project (``text/GBuildings.dxf`` etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Vertex = Tuple[float, float, float]


@dataclass
class DXFLine:
    layer: str = ""
    x1: float = 0.0
    y1: float = 0.0
    z1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    z2: float = 0.0

    def scale(self, s: float) -> None:
        self.x1 *= s; self.y1 *= s; self.z1 *= s
        self.x2 *= s; self.y2 *= s; self.z2 *= s


@dataclass
class DXFPoly:
    layer: str = ""
    vertices: List[List[float]] = field(default_factory=list)

    def scale(self, s: float) -> None:
        for v in self.vertices:
            v[0] *= s; v[1] *= s; v[2] *= s


@dataclass
class DXFMesh:
    layer: str = ""
    vertices: List[List[float]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)  # indices into vertices
    footprint: List[List[float]] = field(default_factory=list)
    minz: float = 0.0
    maxz: float = 0.0

    def scale(self, s: float) -> None:
        for v in self.vertices:
            v[0] *= s; v[1] *= s; v[2] *= s

    def set_min_max_z(self) -> None:
        zs = [v[2] for v in self.vertices]
        self.minz = min(zs) if zs else 0.0
        self.maxz = max(zs) if zs else 0.0

    def build_footprint(self) -> None:
        """Isolate the faces on the bottom (z == minz) and stitch them into a
        single ring, matching ``DXFMesh.setBottomFaces`` + ``joinBottomFaces``."""
        thres = 0.1
        bottom: List[List[int]] = []
        for face in self.faces:
            if all(abs(self.vertices[idx][2] - self.minz) <= thres for idx in face):
                bottom.append(face)
        self.footprint = []
        if not bottom:
            return
        first = bottom.pop(0)
        fp = [list(self.vertices[idx]) for idx in first]

        def join(face: List[int]) -> bool:
            jthres = 0.01
            lenfp = len(fp)
            lenff = len(face)
            fverts = [self.vertices[idx] for idx in face]
            for i in range(lenfp):
                v1 = fp[i]
                v2 = fp[(i + 1) % lenfp]
                for j in range(lenff):
                    vv1 = fverts[j]
                    vv2 = fverts[(j + 1) % lenff]
                    if abs(v1[0] - vv1[0]) < jthres and abs(v1[1] - vv1[1]) < jthres:
                        if abs(v2[0] - vv2[0]) < jthres and abs(v2[1] - vv2[1]) < jthres:
                            fp.insert(i, list(fverts[(j + 2) % lenff]))
                            return True
                    if abs(v1[0] - vv2[0]) < jthres and abs(v1[1] - vv2[1]) < jthres:
                        if abs(v2[0] - vv1[0]) < jthres and abs(v2[1] - vv1[1]) < jthres:
                            fp.insert(i + 1, list(fverts[(j + 2) % lenff]))
                            return True
            return False

        success = True
        while success and bottom:
            success = False
            for i, face in enumerate(bottom):
                if join(face):
                    success = True
                    bottom.pop(i)
                    break
        self.footprint = fp


class DXFHandler:
    def __init__(self) -> None:
        self.lines: List[DXFLine] = []
        self.polys: List[DXFPoly] = []
        self.lwpolys: List[DXFPoly] = []
        self.meshes: List[DXFMesh] = []

    def import_dxf(self, path: str) -> "DXFHandler":
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            tokens = [ln.strip() for ln in fh.readlines()]

        i = 0
        n = len(tokens)
        do_entities = False

        active_line: Optional[DXFLine] = None
        active_poly: Optional[DXFPoly] = None
        active_lwpoly: Optional[DXFPoly] = None
        active_mesh: Optional[DXFMesh] = None
        do_vertices = False
        num_vertices = 0
        vertex_count = 0
        do_faces = False
        face_expect = -1
        cur_face_v = 0

        def finish():
            nonlocal active_line, active_poly, active_lwpoly, active_mesh
            if active_line is not None:
                self.lines.append(active_line)
                active_line = None
            if active_poly is not None:
                if not active_poly.vertices:
                    pass
                self.polys.append(active_poly)
                active_poly = None
            if active_lwpoly is not None:
                self.lwpolys.append(active_lwpoly)
                active_lwpoly = None
            if active_mesh is not None:
                self.meshes.append(active_mesh)
                active_mesh = None

        while i + 1 < n:
            skey = tokens[i]
            sval = tokens[i + 1]
            i += 2

            if skey == "0" and sval == "SECTION":
                if i + 1 < n and tokens[i] == "2":
                    do_entities = tokens[i + 1] == "ENTITIES"
                    i += 2
                continue
            if skey == "0" and sval == "ENDSEC":
                do_entities = False
                continue
            if not do_entities:
                continue

            if skey == "0" and sval == "LINE":
                finish()
                active_line = DXFLine()
                continue
            if skey == "0" and sval == "POLYLINE":
                finish()
                active_poly = DXFPoly()
                do_vertices = False
                num_vertices = 0
                vertex_count = 0
                continue
            if skey == "0" and sval == "LWPOLYLINE":
                finish()
                active_lwpoly = DXFPoly()
                continue
            if skey == "0" and sval == "MESH":
                finish()
                active_mesh = DXFMesh()
                do_faces = False
                face_expect = -1
                continue
            if skey == "0" and sval == "SEQEND":
                finish()
                continue
            if skey == "0" and sval == "VERTEX" and active_poly is not None:
                do_vertices = True
                vertex_count += 1
                active_poly.vertices.append([0.0, 0.0, 0.0])
                continue
            if skey == "0" and sval not in ("VERTEX", "SEQEND"):
                # Any other entity terminates the current object.
                if active_line or active_poly or active_lwpoly or active_mesh:
                    finish()
                # fall through: nothing else to do for unsupported entities

            if active_line is not None:
                _line_attr(active_line, skey, sval)
            elif active_lwpoly is not None:
                _lwpoly_attr(active_lwpoly, skey, sval)
            elif active_poly is not None:
                do_vertices, num_vertices = _poly_attr(
                    active_poly, skey, sval, do_vertices, num_vertices, vertex_count
                )
            elif active_mesh is not None:
                do_faces, face_expect, cur_face_v = _mesh_attr(
                    active_mesh, skey, sval, do_faces, face_expect, cur_face_v
                )

        finish()
        for m in self.meshes:
            m.set_min_max_z()
            m.build_footprint()
        return self


def _line_attr(l: DXFLine, skey: str, sval: str) -> None:
    if skey == "8":
        l.layer = sval
    elif skey == "10":
        l.x1 = float(sval)
    elif skey == "20":
        l.y1 = float(sval) * -1
    elif skey == "30":
        l.z1 = float(sval)
    elif skey == "11":
        l.x2 = float(sval)
    elif skey == "21":
        l.y2 = float(sval) * -1
    elif skey == "31":
        l.z2 = float(sval)


def _lwpoly_attr(poly: DXFPoly, skey: str, sval: str) -> None:
    if skey == "8":
        poly.layer = sval
    elif skey == "10":
        poly.vertices.append([float(sval), 0.0, 0.0])
    elif skey == "20" and poly.vertices:
        poly.vertices[-1][1] = float(sval) * -1
    elif skey == "30" and poly.vertices:
        poly.vertices[-1][2] = float(sval)


def _poly_attr(poly, skey, sval, do_vertices, num_vertices, vertex_count):
    if not do_vertices:
        if skey == "8":
            poly.layer = sval
        elif skey == "71":
            num_vertices = int(float(sval))
        return do_vertices, num_vertices
    if poly.vertices and (vertex_count <= num_vertices or num_vertices == 0):
        if skey == "10":
            poly.vertices[-1][0] = float(sval)
        elif skey == "20":
            poly.vertices[-1][1] = float(sval) * -1
        elif skey == "30":
            poly.vertices[-1][2] = float(sval)
    return do_vertices, num_vertices


def _mesh_attr(mesh, skey, sval, do_faces, expect_n, cur_n):
    """State machine port of ``DXFHandler.importMesh``.

    ``expect_n`` mirrors ``vertexCount`` (number of indices in the current face,
    ``-1`` before the first face) and ``cur_n`` mirrors ``currVertexCount``.
    """
    if skey == "8":
        mesh.layer = sval
        return do_faces, expect_n, cur_n
    if skey == "10":
        mesh.vertices.append([float(sval), 0.0, 0.0])
        return do_faces, expect_n, cur_n
    if skey == "20" and mesh.vertices:
        mesh.vertices[-1][1] = float(sval) * -1
        return do_faces, expect_n, cur_n
    if skey == "30" and mesh.vertices:
        mesh.vertices[-1][2] = float(sval)
        return do_faces, expect_n, cur_n
    if skey == "93" and not do_faces:
        do_faces = True
        expect_n = -1
        cur_n = 0
        return do_faces, expect_n, cur_n
    if skey == "94":
        do_faces = False
        return do_faces, expect_n, cur_n
    if do_faces and skey == "90":
        val = int(float(sval))
        if expect_n == -1 or expect_n <= cur_n:
            expect_n = val
            cur_n = 0
            mesh.faces.append([])
        else:
            if 0 <= val < len(mesh.vertices):
                mesh.faces[-1].append(val)
            cur_n += 1
        return do_faces, expect_n, cur_n
    return do_faces, expect_n, cur_n
