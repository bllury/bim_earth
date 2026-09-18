from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import shutil
from threading import Lock
from typing import Callable, Optional, Protocol

from .persistence import PersistenceStore


# (percent 0-100, human readable step message)
ProgressCallback = Callable[[float, str], None]


class IfcConverterError(RuntimeError):
    """Raised when the IFC converter is missing or cannot run."""


@dataclass
class ConvertResult:
    model_id: str
    tileset_url: str
    metadata_url: Optional[str] = None
    message: Optional[str] = None


class IfcConverter(Protocol):
    def convert(
        self,
        ifc_path: Path,
        output_dir: Path,
        model_id: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ConvertResult:
        ...


@dataclass
class ConversionTaskState:
    task_id: str
    status: str
    progress: float = 0.0
    message: Optional[str] = None
    tileset_url: Optional[str] = None
    metadata_url: Optional[str] = None
    model_id: Optional[str] = None
    error: Optional[str] = None


class ConverterService:
    def __init__(
        self,
        converter: IfcConverter,
        output_root: Path,
        persistence: Optional[PersistenceStore] = None,
    ) -> None:
        self.converter = converter
        self.output_root = output_root
        self.persistence = persistence
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.tasks: dict[str, ConversionTaskState] = {}
        self.cancelled: set[str] = set()
        self.lock = Lock()

    def start(
        self,
        task_id: str,
        ifc_path: Path,
        output_dir: Optional[Path] = None,
        model_id: Optional[str] = None,
        project_id: Optional[str] = None,
        revision_id: Optional[str] = None,
    ) -> None:
        output_dir = output_dir or self.output_root / task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        with self.lock:
            self.tasks[task_id] = ConversionTaskState(
                task_id=task_id,
                status="processing",
                message="IFC 转换任务已提交",
            )

        self.executor.submit(
            self._run,
            task_id,
            ifc_path,
            output_dir,
            model_id or task_id,
            project_id,
            revision_id,
        )

    def get_status(self, task_id: str) -> Optional[ConversionTaskState]:
        with self.lock:
            return self.tasks.get(task_id)

    def cancel(self, task_id: str) -> None:
        with self.lock:
            self.cancelled.add(task_id)
            self.tasks[task_id] = ConversionTaskState(
                task_id=task_id,
                status="failed",
                error="IFC conversion task deleted",
            )

    def _is_cancelled(self, task_id: str) -> bool:
        with self.lock:
            return task_id in self.cancelled

    def _progress_reporter(self, task_id: str) -> ProgressCallback:
        """Builds a callback that mirrors converter progress onto the task."""

        def report(percent: float, message: str) -> None:
            with self.lock:
                state = self.tasks.get(task_id)
                if state is None or state.status not in ("pending", "processing"):
                    return
                state.progress = max(state.progress, min(max(percent, 0.0), 100.0))
                if message:
                    state.message = message

        return report

    def _update(self, state: ConversionTaskState) -> None:
        with self.lock:
            if state.task_id in self.cancelled:
                return
            self.tasks[state.task_id] = state

    def _run(
        self,
        task_id: str,
        ifc_path: Path,
        output_dir: Path,
        model_id: str,
        project_id: Optional[str],
        revision_id: Optional[str],
    ) -> None:
        try:
            if self._is_cancelled(task_id):
                return
            result = self.converter.convert(
                ifc_path,
                output_dir,
                model_id,
                on_progress=self._progress_reporter(task_id),
            )
            if self._is_cancelled(task_id):
                return
            if self.persistence and revision_id:
                revision = self.persistence.get_revision(revision_id)
                source_metadata = output_dir / "metadata.json"
                if revision and source_metadata.exists():
                    shutil.copyfile(source_metadata, Path(revision["metadata_path"]))
            if self.persistence and revision_id:
                self.persistence.update_revision(
                    revision_id,
                    status="completed",
                    model_id=result.model_id,
                )
            self._update(
                ConversionTaskState(
                    task_id=task_id,
                    status="completed",
                    progress=100.0,
                    message=result.message or "IFC 转换完成",
                    tileset_url=result.tileset_url,
                    metadata_url=result.metadata_url,
                    model_id=result.model_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 - report any converter failure to the client
            if self._is_cancelled(task_id):
                return
            if self.persistence and revision_id:
                self.persistence.update_revision(
                    revision_id,
                    status="failed",
                    error=str(exc) or "IFC 转换失败",
                )
            self._update(
                ConversionTaskState(
                    task_id=task_id,
                    status="failed",
                    error=str(exc) or "IFC 转换失败",
                )
            )
