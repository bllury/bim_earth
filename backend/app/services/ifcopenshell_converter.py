from __future__ import annotations

import json
from pathlib import Path

from .gltf_utils import (
    build_batched_b3dm,
    build_glb_from_triangles_with_batch_ids,
    box_from_vertices,
    write_json,
)
from .ifc_converter import ConvertResult, IfcConverterError


def _as_string(value: object) -> str:
    if value is None:
        return ""
    return str(value)


class IfcOpenShellConverter:
    name = "ifcopenshell"

    def convert(
        self,
        ifc_path: Path,
        output_dir: Path,
        model_id: str,
    ) -> ConvertResult:
        try:
            import ifcopenshell
        except ImportError as exc:
            raise IfcConverterError(
                "IfcOpenShell 未安装。请先执行：pip install ifcopenshell；"
                "或设置 IFC_CONVERTER_MODE=mock 使用本地 mock 转换器。"
            ) from exc

        try:
            import ifcopenshell.geom as ifcopenshell_geom
        except ImportError as exc:
            raise IfcConverterError(
                "当前 IfcOpenShell 安装缺少几何模块 ifcopenshell.geom。"
                "请安装包含几何内核的完整版 IfcOpenShell，"
                "或设置 IFC_CONVERTER_MODE=mock 使用本地 mock 转换器。"
            ) from exc

        if not ifc_path.exists():
            raise IfcConverterError(f"IFC 文件不存在：{ifc_path}")

        model = ifcopenshell.open(str(ifc_path))
        elements = list(model.by_type("IfcElement"))

        if not elements:
            raise IfcConverterError("IFC 文件中没有找到 IfcElement 构件")

        geometry_settings = ifcopenshell_geom.settings()
        geometry_settings.set(geometry_settings.USE_WORLD_COORDS, True)

        shape_records: list[tuple[object, list[float], list[int]]] = []
        global_minimum = [float("inf"), float("inf"), float("inf")]
        global_maximum = [float("-inf"), float("-inf"), float("-inf")]

        for element in elements:
            try:
                shape = ifcopenshell_geom.create_shape(geometry_settings, element)
                if shape is None or shape.geometry is None:
                    continue

                vertices = list(shape.geometry.verts)
                faces = list(shape.geometry.faces)

                if not vertices or not faces:
                    continue

                for index in range(0, len(vertices), 3):
                    x = vertices[index]
                    y = vertices[index + 1]
                    z = vertices[index + 2]
                    global_minimum[0] = min(global_minimum[0], x)
                    global_minimum[1] = min(global_minimum[1], y)
                    global_minimum[2] = min(global_minimum[2], z)
                    global_maximum[0] = max(global_maximum[0], x)
                    global_maximum[1] = max(global_maximum[1], y)
                    global_maximum[2] = max(global_maximum[2], z)

                shape_records.append((element, vertices, faces))
            except Exception:  # noqa: BLE001 - skip a broken element but keep converting others
                continue

        if not shape_records:
            raise IfcConverterError("IFC 构件没有生成可用的 3D Tiles 内容")

        all_vertices: list[float] = []
        all_triangles: list[tuple[int, int, int]] = []
        all_batch_ids: list[int] = []
        metadata_features: list[dict] = []
        metadata_records: list[dict] = []
        vertex_offset = 0

        for feature_id, (element, vertices, faces) in enumerate(shape_records):
            normalized_vertices = [
                vertices[index] - global_minimum[index % 3]
                for index in range(len(vertices))
            ]
            geometry = self._build_geometry_record(normalized_vertices)
            triangles = [
                (faces[index], faces[index + 1], faces[index + 2])
                for index in range(0, len(faces), 3)
            ]

            all_vertices.extend(normalized_vertices)
            all_triangles.extend(
                (a + vertex_offset, b + vertex_offset, c + vertex_offset)
                for a, b, c in triangles
            )
            all_batch_ids.extend([feature_id] * len(triangles))
            vertex_offset += len(normalized_vertices) // 3

            batch_table = self._build_batch_table(element, feature_id)
            metadata_features.append(batch_table)
            metadata_records.append(
                self._build_metadata_record(element, feature_id, geometry)
            )

        glb_bytes = build_glb_from_triangles_with_batch_ids(
            all_vertices,
            all_triangles,
            all_batch_ids,
        )
        b3dm_bytes = build_batched_b3dm(glb_bytes, metadata_features)
        content_name = "model.b3dm"
        (output_dir / content_name).write_bytes(b3dm_bytes)

        bounding_box = box_from_vertices(all_vertices)
        max_half_extent = max(
            abs(bounding_box[3]),
            abs(bounding_box[7]),
            abs(bounding_box[11]),
        )
        tileset_geometric_error = max(max_half_extent * 4.0, 1.0)
        tileset = {
            "asset": {
                "version": "1.0",
                "gltfUpAxis": "Z",
            },
            "geometricError": tileset_geometric_error,
            "root": {
                "boundingVolume": {
                    "box": bounding_box
                },
                "geometricError": 1.0,
                "refine": "ADD",
                "content": {
                    "url": content_name,
                    "boundingVolume": {"box": bounding_box},
                },
            },
        }

        metadata = {
            "modelId": model_id,
            "featureIdField": "featureId",
            "features": metadata_features,
            "semanticElements": metadata_records,
        }

        write_json(output_dir / "tileset.json", tileset)
        write_json(output_dir / "metadata.json", metadata)

        return ConvertResult(
            model_id=model_id,
            tileset_url=f"/api/ifc/revisions/{model_id}/tiles/tileset.json",
            metadata_url=f"/api/ifc/revisions/{model_id}/metadata.json",
            message=f"已转换 {len(metadata_features)} 个 IFC 构件",
        )

    def _build_batch_table(self, element: object, feature_id: int) -> dict:
        ifc_guid = getattr(element, "GlobalId", None)
        express_id = getattr(element, "id", lambda: feature_id)()
        element_type = getattr(element, "is_a", lambda: "IfcElement")()
        name = getattr(element, "Name", None)

        storey = self._get_storey(element)
        material = self._get_material(element)
        properties = self._get_properties(element)

        return {
            "featureId": feature_id,
            "ifcGuid": _as_string(ifc_guid),
            "expressId": _as_string(express_id),
            "elementType": _as_string(element_type),
            "name": _as_string(name),
            "storey": storey,
            "material": material,
            "properties": json.dumps(properties, ensure_ascii=False),
        }

    def _build_geometry_record(self, vertices: list[float]) -> dict:
        minimum = [float("inf"), float("inf"), float("inf")]
        maximum = [float("-inf"), float("-inf"), float("-inf")]
        for index in range(0, len(vertices), 3):
            for axis in range(3):
                minimum[axis] = min(minimum[axis], vertices[index + axis])
                maximum[axis] = max(maximum[axis], vertices[index + axis])

        center = [(minimum[axis] + maximum[axis]) / 2 for axis in range(3)]
        radius = max(
            (
                (vertices[index] - center[0]) ** 2
                + (vertices[index + 1] - center[1]) ** 2
                + (vertices[index + 2] - center[2]) ** 2
            )
            ** 0.5
            for index in range(0, len(vertices), 3)
        )
        return {
            "min": {"x": minimum[0], "y": minimum[1], "z": minimum[2]},
            "max": {"x": maximum[0], "y": maximum[1], "z": maximum[2]},
            "center": {"x": center[0], "y": center[1], "z": center[2]},
            "radius": radius,
        }

    def _build_metadata_record(
        self,
        element: object,
        feature_id: int,
        geometry: dict,
    ) -> dict:
        ifc_guid = getattr(element, "GlobalId", None)
        express_id = getattr(element, "id", lambda: feature_id)()
        element_type = getattr(element, "is_a", lambda: "IfcElement")()
        name = getattr(element, "Name", None)

        return {
            "modelId": "",
            "ifcGuid": _as_string(ifc_guid),
            "expressId": _as_string(express_id),
            "elementType": _as_string(element_type),
            "name": _as_string(name),
            "storey": self._get_storey(element),
            "geometry": geometry,
            "basic": {
                "ifcGuid": _as_string(ifc_guid),
                "expressId": _as_string(express_id),
                "elementType": _as_string(element_type),
                "name": _as_string(name),
                "storey": self._get_storey(element),
                "discipline": "",
            },
            "materials": self._get_materials_normalized(element),
            "propertySets": self._get_properties(element),
            "business": {},
        }

    def _get_materials_normalized(self, element: object) -> list[dict]:
        try:
            from ifcopenshell.util import element as ifc_element_util

            materials = ifc_element_util.get_materials(element)
            normalized: list[dict] = []

            for material in materials:
                material_name = _as_string(
                    getattr(material, "Name", material)
                )
                category = _as_string(getattr(material, "Category", ""))
                grade = ""
                thickness = None

                if getattr(material, "is_a", lambda: "")() == "IfcMaterialLayer":
                    thickness_value = getattr(material, "LayerThickness", None)
                    if isinstance(thickness_value, (int, float)):
                        thickness = thickness_value

                    inner_material = getattr(material, "Material", None)
                    if inner_material is not None:
                        material_name = _as_string(
                            getattr(inner_material, "Name", material_name)
                        )
                        category = _as_string(
                            getattr(inner_material, "Category", category)
                        )

                normalized.append(
                    {
                        "name": material_name or "未提供",
                        "category": category or "未提供",
                        "grade": grade or "未提供",
                        "thickness": thickness,
                        "raw": {
                            key: _as_string(getattr(material, key, ""))
                            for key in (
                                "Name",
                                "Category",
                                "Description",
                            )
                        },
                    }
                )

            return normalized
        except Exception:
            return []

    def _get_storey(self, element: object) -> str:
        try:
            from ifcopenshell.util import element as ifc_element_util

            storey = ifc_element_util.get_storey(element)
            return _as_string(getattr(storey, "Name", storey))
        except Exception:
            return ""

    def _get_material(self, element: object) -> str:
        try:
            from ifcopenshell.util import element as ifc_element_util

            materials = ifc_element_util.get_materials(element)
            names = [
                _as_string(getattr(material, "Name", material))
                for material in materials
            ]
            return ", ".join(name for name in names if name)
        except Exception:
            return ""

    def _get_properties(self, element: object) -> dict:
        try:
            from ifcopenshell.util import element as ifc_element_util

            psets = ifc_element_util.get_psets(element)
            return psets if isinstance(psets, dict) else {}
        except Exception:
            return {}
