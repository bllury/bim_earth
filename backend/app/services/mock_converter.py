from __future__ import annotations

from pathlib import Path
from typing import Optional

from .gltf_utils import (
    build_batched_b3dm,
    build_box,
    build_cube_glb,
    write_json,
)
from .ifc_converter import ConvertResult, ProgressCallback


class MockConverter:
    name = "mock"

    def convert(
        self,
        ifc_path: Path,
        output_dir: Path,
        model_id: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ConvertResult:
        if on_progress is not None:
            on_progress(50.0, "Mock 转换中")
        glb_bytes = build_cube_glb()
        batch_table = {
            "featureId": 0,
            "ifcGuid": f"mock-{model_id}",
            "expressId": "0",
            "elementType": "IfcMockElement",
            "name": "Mock IFC Element",
            "storey": "Mock Storey",
            "material": "Mock Material",
            "properties": "{}",
        }

        (output_dir / "0.b3dm").write_bytes(
            build_batched_b3dm(glb_bytes, [batch_table])
        )

        tileset = {
            "asset": {"version": "1.0"},
            "geometricError": 20.0,
            "root": {
                "boundingVolume": {
                    "box": build_box([0.0, 0.0, 0.0], half_size=1.0)
                },
                "geometricError": 0.0,
                "refine": "ADD",
                "content": {"url": "0.b3dm"},
            },
        }
        metadata = {
            "modelId": model_id,
            "featureIdField": "featureId",
            "features": [batch_table],
        }

        write_json(output_dir / "tileset.json", tileset)
        write_json(output_dir / "metadata.json", metadata)

        return ConvertResult(
            model_id=model_id,
            tileset_url=f"/api/ifc/revisions/{model_id}/tiles/tileset.json",
            metadata_url=f"/api/ifc/revisions/{model_id}/metadata.json",
            message="Mock 转换完成。此结果仅用于验证 3D Tiles 加载链路，不代表真实 IFC 几何。",
        )
