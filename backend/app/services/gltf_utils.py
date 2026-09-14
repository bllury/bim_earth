from __future__ import annotations

import base64
import json
import math
import struct
from pathlib import Path
from typing import Iterable


GLB_MAGIC = 0x46546C67
GLB_VERSION = 2
GLB_JSON_CHUNK_TYPE = 0x4E4F534A
GLB_BIN_CHUNK_TYPE = 0x004E4942


def _pad_to_4(value: bytes) -> bytes:
    remainder = len(value) % 4
    if remainder == 0:
        return value
    return value + b" " * (4 - remainder)


def _triangle_normal(
    positions: list[float],
    indices: tuple[int, int, int],
) -> tuple[float, float, float]:
    i0 = indices[0] * 3
    i1 = indices[1] * 3
    i2 = indices[2] * 3

    ax = positions[i0]
    ay = positions[i0 + 1]
    az = positions[i0 + 2]
    bx = positions[i1] - ax
    by = positions[i1 + 1] - ay
    bz = positions[i1 + 2] - az
    cx = positions[i2] - ax
    cy = positions[i2 + 1] - ay
    cz = positions[i2 + 2] - az

    nx = by * cz - bz * cy
    ny = bz * cx - bx * cz
    nz = bx * cy - by * cx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)

    if length < 1e-10:
        return 0.0, 0.0, 1.0

    return nx / length, ny / length, nz / length


def build_glb_from_triangles(
    positions: Iterable[float],
    triangles: Iterable[tuple[int, int, int]],
    base_color: tuple[float, float, float, float] = (0.5, 0.6, 0.8, 1.0),
) -> bytes:
    source_positions = list(positions)
    flat_positions: list[float] = []
    flat_normals: list[float] = []
    min_position = [float("inf"), float("inf"), float("inf")]
    max_position = [float("-inf"), float("-inf"), float("-inf")]

    for triangle in triangles:
        i0 = triangle[0]
        i1 = triangle[1]
        i2 = triangle[2]
        normal = _triangle_normal(source_positions, triangle)

        for index in (i0, i1, i2):
            offset = index * 3
            x = source_positions[offset]
            y = source_positions[offset + 1]
            z = source_positions[offset + 2]

            flat_positions.extend((x, y, z))
            flat_normals.extend(normal)

            min_position[0] = min(min_position[0], x)
            min_position[1] = min(min_position[1], y)
            min_position[2] = min(min_position[2], z)
            max_position[0] = max(max_position[0], x)
            max_position[1] = max(max_position[1], y)
            max_position[2] = max(max_position[2], z)

    if not flat_positions:
        raise ValueError("没有可写入 glTF 的三角面")

    position_bytes = struct.pack(f"<{len(flat_positions)}f", *flat_positions)
    normal_bytes = struct.pack(f"<{len(flat_normals)}f", *flat_normals)
    binary_chunk = _pad_to_4(position_bytes + normal_bytes)

    position_count = len(flat_positions) // 3
    normal_count = len(flat_normals) // 3
    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1},
                        "material": 0,
                        "mode": 4,
                    }
                ]
            }
        ],
        "materials": [
            {
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(base_color),
                    "metallicFactor": 0.05,
                    "roughnessFactor": 0.8,
                },
            }
        ],
        "buffers": [{"byteLength": len(binary_chunk)}],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": 0,
                "byteLength": len(position_bytes),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": len(position_bytes),
                "byteLength": len(normal_bytes),
                "target": 34962,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": position_count,
                "type": "VEC3",
                "min": min_position,
                "max": max_position,
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": normal_count,
                "type": "VEC3",
            },
        ],
    }

    json_bytes = _pad_to_4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"))
    total_length = 12 + 8 + len(json_bytes) + 8 + len(binary_chunk)

    header = struct.pack(
        "<III",
        GLB_MAGIC,
        GLB_VERSION,
        total_length,
    )
    json_header = struct.pack("<II", len(json_bytes), GLB_JSON_CHUNK_TYPE)
    bin_header = struct.pack("<II", len(binary_chunk), GLB_BIN_CHUNK_TYPE)

    return header + json_header + json_bytes + bin_header + binary_chunk


def build_glb_from_triangles_with_batch_ids(
    positions: Iterable[float],
    triangles: Iterable[tuple[int, int, int]],
    batch_ids: Iterable[int],
    base_color: tuple[float, float, float, float] = (0.5, 0.6, 0.8, 1.0),
) -> bytes:
    source_positions = list(positions)
    triangle_list = list(triangles)
    batch_id_list = list(batch_ids)

    if len(triangle_list) != len(batch_id_list):
        raise ValueError("triangles 和 batch_ids 数量必须一致")

    flat_positions: list[float] = []
    flat_normals: list[float] = []
    flat_batch_ids: list[int] = []
    min_position = [float("inf"), float("inf"), float("inf")]
    max_position = [float("-inf"), float("-inf"), float("-inf")]

    for triangle, batch_id in zip(triangle_list, batch_id_list):
        i0 = triangle[0]
        i1 = triangle[1]
        i2 = triangle[2]
        normal = _triangle_normal(source_positions, triangle)

        for index in (i0, i1, i2):
            offset = index * 3
            x = source_positions[offset]
            y = source_positions[offset + 1]
            z = source_positions[offset + 2]

            flat_positions.extend((x, y, z))
            flat_normals.extend(normal)
            flat_batch_ids.append(batch_id)

            min_position[0] = min(min_position[0], x)
            min_position[1] = min(min_position[1], y)
            min_position[2] = min(min_position[2], z)
            max_position[0] = max(max_position[0], x)
            max_position[1] = max(max_position[1], y)
            max_position[2] = max(max_position[2], z)

    if not flat_positions:
        raise ValueError("没有可写入 glTF 的三角面")

    max_batch_id = max(flat_batch_ids)
    if max_batch_id <= 255:
        batch_id_component_type = 5121
        batch_id_pack_format = "<B"
        batch_id_byte_size = 1
    elif max_batch_id <= 65535:
        batch_id_component_type = 5123
        batch_id_pack_format = "<H"
        batch_id_byte_size = 2
    else:
        batch_id_component_type = 5125
        batch_id_pack_format = "<I"
        batch_id_byte_size = 4

    position_bytes = struct.pack(f"<{len(flat_positions)}f", *flat_positions)
    normal_bytes = struct.pack(f"<{len(flat_normals)}f", *flat_normals)
    batch_id_bytes = struct.pack(
        f"<{len(flat_batch_ids)}{batch_id_pack_format[1]}",
        *flat_batch_ids,
    )
    binary_chunk = _pad_to_4(position_bytes + normal_bytes + batch_id_bytes)

    position_count = len(flat_positions) // 3
    normal_count = len(flat_normals) // 3
    batch_id_count = len(flat_batch_ids)
    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                            "_BATCHID": 2,
                        },
                        "material": 0,
                        "mode": 4,
                    }
                ]
            }
        ],
        "materials": [
            {
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": list(base_color),
                    "metallicFactor": 0.05,
                    "roughnessFactor": 0.8,
                },
            }
        ],
        "buffers": [{"byteLength": len(binary_chunk)}],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": 0,
                "byteLength": len(position_bytes),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": len(position_bytes),
                "byteLength": len(normal_bytes),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": len(position_bytes) + len(normal_bytes),
                "byteLength": len(batch_id_bytes),
                "target": 34962,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": position_count,
                "type": "VEC3",
                "min": min_position,
                "max": max_position,
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": normal_count,
                "type": "VEC3",
            },
            {
                "bufferView": 2,
                "componentType": batch_id_component_type,
                "count": batch_id_count,
                "type": "SCALAR",
            },
        ],
    }

    json_bytes = _pad_to_4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"))
    total_length = 12 + 8 + len(json_bytes) + 8 + len(binary_chunk)

    header = struct.pack(
        "<III",
        GLB_MAGIC,
        GLB_VERSION,
        total_length,
    )
    json_header = struct.pack("<II", len(json_bytes), GLB_JSON_CHUNK_TYPE)
    bin_header = struct.pack("<II", len(binary_chunk), GLB_BIN_CHUNK_TYPE)

    return header + json_header + json_bytes + bin_header + binary_chunk


def build_cube_glb() -> bytes:
    vertices = [
        -1.0, -1.0, -1.0,
        1.0, -1.0, -1.0,
        1.0, 1.0, -1.0,
        -1.0, 1.0, -1.0,
        -1.0, -1.0, 1.0,
        1.0, -1.0, 1.0,
        1.0, 1.0, 1.0,
        -1.0, 1.0, 1.0,
    ]
    triangles = [
        (0, 1, 2),
        (0, 2, 3),
        (4, 5, 6),
        (4, 6, 7),
        (0, 4, 5),
        (0, 5, 1),
        (2, 6, 7),
        (2, 7, 3),
        (0, 3, 7),
        (0, 7, 4),
        (1, 5, 6),
        (1, 6, 2),
    ]
    return build_glb_from_triangles(
        vertices,
        triangles,
        base_color=(0.42, 0.58, 0.8, 1.0),
    )


def build_b3dm(glb_bytes: bytes, batch_table: dict) -> bytes:
    feature_table = {"BATCH_LENGTH": 1}
    feature_table_json = _pad_to_4(
        json.dumps(feature_table, separators=(",", ":")).encode("utf-8")
    )
    batch_table_json = _pad_to_4(
        json.dumps(batch_table, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    total_length = 28 + len(feature_table_json) + len(batch_table_json) + len(glb_bytes)
    header = struct.pack(
        "<4s6I",
        b"b3dm",
        1,
        total_length,
        len(feature_table_json),
        0,
        len(batch_table_json),
        0,
    )
    return header + feature_table_json + batch_table_json + glb_bytes


def build_batched_b3dm(
    glb_bytes: bytes,
    batch_table_features: list[dict],
) -> bytes:
    batch_length = len(batch_table_features)
    if batch_length == 0:
        raise ValueError("batch_table_features 不能为空")

    property_names = [
        "featureId",
        "ifcGuid",
        "expressId",
        "elementType",
        "name",
        "storey",
        "material",
        "properties",
    ]
    batch_table: dict[str, list[object]] = {
        name: [feature.get(name, "") for feature in batch_table_features]
        for name in property_names
    }

    feature_table = {"BATCH_LENGTH": batch_length}
    feature_table_json = _pad_to_4(
        json.dumps(feature_table, separators=(",", ":")).encode("utf-8")
    )
    batch_table_json = _pad_to_4(
        json.dumps(
            batch_table,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    total_length = 28 + len(feature_table_json) + len(batch_table_json) + len(glb_bytes)
    header = struct.pack(
        "<4s6I",
        b"b3dm",
        1,
        total_length,
        len(feature_table_json),
        0,
        len(batch_table_json),
        0,
    )
    return header + feature_table_json + batch_table_json + glb_bytes


def build_box(center: list[float], half_size: float = 1.0) -> list[float]:
    return [
        center[0],
        center[1],
        center[2],
        half_size,
        0.0,
        0.0,
        0.0,
        half_size,
        0.0,
        0.0,
        0.0,
        half_size,
    ]


def box_from_vertices(vertices: Iterable[float]) -> list[float]:
    source = list(vertices)
    if not source:
        return build_box([0.0, 0.0, 0.0], half_size=1.0)

    minimum = [float("inf"), float("inf"), float("inf")]
    maximum = [float("-inf"), float("-inf"), float("-inf")]

    for index in range(0, len(source), 3):
        x = source[index]
        y = source[index + 1]
        z = source[index + 2]

        minimum[0] = min(minimum[0], x)
        minimum[1] = min(minimum[1], y)
        minimum[2] = min(minimum[2], z)
        maximum[0] = max(maximum[0], x)
        maximum[1] = max(maximum[1], y)
        maximum[2] = max(maximum[2], z)

    center = [
        (minimum[0] + maximum[0]) / 2,
        (minimum[1] + maximum[1]) / 2,
        (minimum[2] + maximum[2]) / 2,
    ]
    half_x = max((maximum[0] - minimum[0]) / 2, 1e-6)
    half_y = max((maximum[1] - minimum[1]) / 2, 1e-6)
    half_z = max((maximum[2] - minimum[2]) / 2, 1e-6)

    return [
        center[0],
        center[1],
        center[2],
        half_x,
        0.0,
        0.0,
        0.0,
        half_y,
        0.0,
        0.0,
        0.0,
        half_z,
    ]


def write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_data_uri_base64(value: str) -> str:
    return "data:application/json;base64," + base64.b64encode(value.encode("utf-8")).decode(
        "ascii"
    )
