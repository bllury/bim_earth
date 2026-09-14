import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..schemas import CameraState, ConvertAccepted, ConvertStatus, RecentModel
from ..services.ifc_converter import ConverterService
from ..services.persistence import PersistenceStore


def create_ifc_router(
    service: ConverterService,
    store: PersistenceStore,
) -> APIRouter:
    router = APIRouter(prefix="/api/ifc", tags=["ifc"])

    @router.post("/convert", response_model=ConvertAccepted)
    async def convert_ifc(
        file: UploadFile = File(...),
        longitude: float = Form(0),
        latitude: float = Form(0),
    ) -> ConvertAccepted:
        if not file.filename or not file.filename.lower().endswith(".ifc"):
            raise HTTPException(status_code=400, detail="只接受 .ifc 文件")

        revision = store.create_revision(file.filename, longitude, latitude)
        task_id = revision["revision_id"]
        ifc_path = Path(revision["source_path"])

        try:
            with ifc_path.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    target.write(chunk)
        finally:
            await file.close()

        if ifc_path.stat().st_size == 0:
            ifc_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="上传的 IFC 文件为空")

        service.start(
            task_id,
            ifc_path,
            output_dir=Path(revision["tiles_path"]),
            model_id=revision["revision_id"],
            project_id=revision["project_id"],
            revision_id=revision["revision_id"],
        )
        return ConvertAccepted(
            taskId=task_id,
            projectId=revision["project_id"],
            revisionId=revision["revision_id"],
        )

    @router.get("/convert/{task_id}", response_model=ConvertStatus)
    async def get_conversion_status(task_id: str) -> ConvertStatus:
        state = service.get_status(task_id)
        if state is None:
            raise HTTPException(status_code=404, detail="转换任务不存在")

        return ConvertStatus(
            taskId=state.task_id,
            status=state.status,  # type: ignore[arg-type]
            progress=state.progress,
            message=state.message,
            tilesetUrl=state.tileset_url,
            metadataUrl=state.metadata_url,
            modelId=state.model_id,
            error=state.error,
            projectId=(
                store.get_revision(state.task_id) or {}
            ).get("project_id"),
            revisionId=state.task_id,
        )

    def find_semantic_element(model_id: str, ifc_guid: str) -> dict:
        revision = store.get_revision(model_id)
        metadata_path = Path(revision["metadata_path"]) if revision else None
        if metadata_path is None:
            raise HTTPException(status_code=404, detail="模型版本不存在")
        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail="模型元数据不存在")

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise HTTPException(status_code=500, detail="模型元数据无法读取") from exc

        records = metadata.get("semanticElements") or metadata.get("features") or []
        for record in records:
            if (
                record.get("ifcGuid") == ifc_guid
                or str(record.get("expressId")) == ifc_guid
            ):
                record["modelId"] = model_id
                return record

        raise HTTPException(status_code=404, detail="未找到对应 IFC 构件")

    @router.get("/models/{model_id}/elements/{ifc_guid}")
    async def get_ifc_element(model_id: str, ifc_guid: str) -> dict:
        return find_semantic_element(model_id, ifc_guid)

    @router.get("/models/{model_id}/elements/{ifc_guid}/properties")
    async def get_ifc_element_properties(model_id: str, ifc_guid: str) -> dict:
        record = find_semantic_element(model_id, ifc_guid)
        return {
            "modelId": model_id,
            "ifcGuid": record.get("ifcGuid", ifc_guid),
            "expressId": record.get("expressId", ""),
            "basic": record.get("basic", {}),
            "materials": record.get("materials", []),
            "propertySets": record.get("propertySets", {}),
            "business": record.get("business", {}),
        }

    @router.get("/recent", response_model=Optional[RecentModel])
    async def get_recent_model() -> Optional[RecentModel]:
        revision = store.get_recent_completed_revision()
        if not revision or not revision.get("model_id"):
            return None
        return RecentModel(
            projectId=revision["project_id"],
            projectName=revision["project_name"],
            revisionId=revision["id"],
            fileName=revision["file_name"],
            modelId=revision["model_id"],
            tilesetUrl=f"/api/ifc/revisions/{revision['id']}/tiles/tileset.json",
            metadataUrl=f"/api/ifc/revisions/{revision['id']}/metadata.json",
            longitude=revision.get("longitude", 0),
            latitude=revision.get("latitude", 0),
            camera=store.get_camera(revision["project_id"]),
        )

    @router.put("/projects/{project_id}/camera")
    async def save_camera(project_id: str, payload: CameraState) -> dict[str, str]:
        if payload.projectId != project_id:
            raise HTTPException(status_code=400, detail="项目 ID 不一致")
        store.save_camera(project_id, payload.camera)
        return {"status": "saved"}

    @router.get("/projects/{project_id}/camera")
    async def get_camera(project_id: str) -> dict:
        return {"projectId": project_id, "camera": store.get_camera(project_id)}

    @router.get("/revisions/{revision_id}/metadata.json")
    async def get_revision_metadata(revision_id: str) -> FileResponse:
        revision = store.get_revision(revision_id)
        if not revision:
            raise HTTPException(status_code=404, detail="模型版本不存在")
        metadata_path = Path(revision["metadata_path"])
        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail="模型元数据不存在")
        return FileResponse(metadata_path)

    @router.get("/revisions/{revision_id}/tiles/{asset_path:path}")
    async def get_revision_asset(revision_id: str, asset_path: str) -> FileResponse:
        revision = store.get_revision(revision_id)
        if not revision:
            raise HTTPException(status_code=404, detail="模型版本不存在")
        tiles_root = Path(revision["tiles_path"]).resolve()
        asset = (tiles_root / asset_path).resolve()
        if tiles_root not in asset.parents or not asset.is_file():
            raise HTTPException(status_code=404, detail="模型资源不存在")
        return FileResponse(asset)

    return router
