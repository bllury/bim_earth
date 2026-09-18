from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Callable, Optional

from .gltf_utils import (
    build_batched_b3dm,
    build_glb_from_triangles_with_batch_ids,
    box_from_vertices,
    write_json,
)
from .ifc_converter import ConvertResult, IfcConverterError, ProgressCallback


# Models smaller than this convert faster serially than they pay for a thread pool.
SMALL_MODEL_ELEMENT_LIMIT = 200
# Above ~8 threads the geometry kernel saturates memory bandwidth (measured).
DEFAULT_MAX_GEOMETRY_THREADS = 8


def _container_cpu_quota() -> Optional[int]:
    """Reads a container CPU quota from cgroup v2/v1 when one is present."""
    try:
        cpu_max = Path("/sys/fs/cgroup/cpu.max")
        if cpu_max.exists():
            parts = cpu_max.read_text(encoding="utf-8").split()
            if len(parts) >= 2 and parts[0] != "max":
                quota, period = int(parts[0]), int(parts[1])
                if quota > 0 and period > 0:
                    return max(1, math.ceil(quota / period))
    except (OSError, ValueError):
        pass

    try:
        quota_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if quota_path.exists() and period_path.exists():
            quota = int(quota_path.read_text(encoding="utf-8").strip())
            period = int(period_path.read_text(encoding="utf-8").strip())
            if quota > 0 and period > 0:
                return max(1, math.ceil(quota / period))
    except (OSError, ValueError):
        pass

    return None


def available_cpu_count() -> int:
    """Counts usable CPUs, honoring CPU affinity and container CPU quotas."""
    try:
        cores = len(os.sched_getaffinity(0))  # Linux only
    except (AttributeError, OSError):
        cores = os.cpu_count() or 1

    quota = _container_cpu_quota()
    if quota is not None:
        cores = min(cores, quota)

    return max(1, cores)


def resolve_geometry_threads(element_count: int) -> int:
    """Picks the triangulation thread count for this machine and model size.

    Priority: IFC_CONVERT_THREADS override > container/affinity core count,
    capped by IFC_CONVERT_MAX_THREADS (default 8).
    """
    override = os.getenv("IFC_CONVERT_THREADS", "").strip()
    if override:
        try:
            threads = int(override)
        except ValueError:
            threads = 0
        if threads >= 1:
            return threads

    if element_count < SMALL_MODEL_ELEMENT_LIMIT:
        return 1

    try:
        max_threads = int(
            os.getenv("IFC_CONVERT_MAX_THREADS", str(DEFAULT_MAX_GEOMETRY_THREADS))
        )
    except ValueError:
        max_threads = DEFAULT_MAX_GEOMETRY_THREADS

    return max(1, min(available_cpu_count(), max(1, max_threads)))


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
        on_progress: Optional[ProgressCallback] = None,
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

        # Progress is weighted: geometry dominates the runtime (~90%), the
        # 3D Tiles packaging of the remaining elements is comparatively fast.
        last_reported = [-1.0]

        def emit(percent: float, message: str) -> None:
            if on_progress is None:
                return
            value = min(max(percent, 0.0), 100.0)
            if value - last_reported[0] < 1.0 and value < 100.0:
                return
            last_reported[0] = value
            on_progress(value, message)

        emit(1.0, "正在解析 IFC 模型")

        thread_count = resolve_geometry_threads(len(elements))
        shape_records: list[tuple[object, list[float], list[int]]] = []
        global_minimum = [float("inf"), float("inf"), float("inf")]
        global_maximum = [float("-inf"), float("-inf"), float("-inf")]

        for element, vertices, faces in self._extract_shapes(
            model,
            elements,
            geometry_settings,
            thread_count,
            on_progress=lambda fraction: emit(
                2.0 + fraction * 88.0,
                f"正在三角化构件 {int(fraction * len(elements))}/{len(elements)}",
            ),
        ):
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

        if not shape_records:
            raise IfcConverterError("IFC 构件没有生成可用的 3D Tiles 内容")

        emit(90.0, f"正在生成 3D Tiles（{len(shape_records)} 个构件）")

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
            emit(
                90.0 + ((feature_id + 1) / len(shape_records)) * 8.0,
                f"正在写入构件数据 {feature_id + 1}/{len(shape_records)}",
            )

        emit(98.0, "正在打包 3D Tiles 资源")
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
        emit(100.0, "转换完成")

        return ConvertResult(
            model_id=model_id,
            tileset_url=f"/api/ifc/revisions/{model_id}/tiles/tileset.json",
            metadata_url=f"/api/ifc/revisions/{model_id}/metadata.json",
            message=(
                f"已转换 {len(metadata_features)} 个 IFC 构件 · {thread_count} 线程"
            ),
        )

    def _extract_shapes(
        self,
        model: object,
        elements: list[object],
        geometry_settings: object,
        thread_count: int,
        on_progress: Optional[Callable[[float], None]] = None,
    ) -> list[tuple[object, list[float], list[int]]]:
        """Triangulates every IfcElement, in parallel when the machine allows it.

        The geometry iterator walks every product that carries geometry (it also
        yields IfcSpace and similar spatial elements), so results are filtered
        back to the IfcElement set and re-sorted into file order. That keeps
        batch ids and metadata ordering identical to the serial implementation.
        """
        import ifcopenshell.geom as ifcopenshell_geom

        order = {element.id(): index for index, element in enumerate(elements)}
        allowed = set(order)
        total = max(1, len(elements))
        matched = 0
        reported = -1.0

        def collect(threads: int) -> list[tuple[object, list[float], list[int]]]:
            nonlocal matched, reported
            matched = 0
            reported = -1.0
            shapes: list[tuple[object, list[float], list[int]]] = []
            iterator = ifcopenshell_geom.iterator(
                geometry_settings, model, threads
            )
            if not iterator.initialize():
                return shapes

            while True:
                try:
                    shape = iterator.get()
                    # `shape.product` returns an unusable proxy (attributes such
                    # as GlobalId/Name read back empty), so always resolve the
                    # element through the model we opened ourselves.
                    element = model.by_id(shape.id)
                    if element is not None and element.id() in allowed:
                        geometry = shape.geometry
                        if geometry is not None:
                            vertices = list(geometry.verts)
                            faces = list(geometry.faces)
                            if vertices and faces:
                                shapes.append((element, vertices, faces))
                                matched += 1
                                if on_progress is not None:
                                    fraction = min(matched / total, 1.0)
                                    if fraction - reported >= 0.01 or fraction >= 1.0:
                                        reported = fraction
                                        on_progress(fraction)
                except Exception:  # noqa: BLE001 - skip a broken element, keep going
                    pass

                if not iterator.next():
                    break

            return shapes

        try:
            shapes = collect(thread_count)
        except Exception:  # noqa: BLE001 - fall back to the serial path below
            shapes = []

        if thread_count > 1 and not shapes:
            shapes = collect(1)

        shapes.sort(key=lambda item: order.get(item[0].id(), 0))
        return shapes

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
