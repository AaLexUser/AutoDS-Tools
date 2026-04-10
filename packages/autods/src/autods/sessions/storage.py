import json
import logging
import os
import threading
from pathlib import Path

from autods.sessions.domain import (
    CHECKPOINTS_DIRNAME,
    DEFAULT_SESSION_HOME,
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    SESSION_HOME_ENV,
    ManifestStorageError,
    SessionManifest,
)

logger = logging.getLogger(__name__)


class SessionStorage:
    """Filesystem-backed manifest and checkpoint storage."""

    def __init__(self, root: Path | None = None) -> None:
        desired_root = root or Path(
            os.environ.get(SESSION_HOME_ENV, DEFAULT_SESSION_HOME)
        )
        self.root = self._prepare_root(desired_root)
        self.checkpoints_dir = self._ensure_dir(self.root / CHECKPOINTS_DIRNAME)
        self.manifest_path = self.root / MANIFEST_FILENAME
        self._lock = threading.RLock()

    def _prepare_root(self, candidate: Path) -> Path:
        candidate = candidate.expanduser()
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        except PermissionError:
            fallback = Path.cwd() / ".autods" / "sessions"
            fallback.mkdir(parents=True, exist_ok=True)
            logger.warning(
                "Falling back to %s for session storage (permission denied for %s)",
                fallback,
                candidate,
            )
            return fallback.resolve()

    def _ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def load_manifest(self) -> SessionManifest:
        with self._lock:
            if not self.manifest_path.exists():
                return SessionManifest.empty()
            data = json.loads(self.manifest_path.read_text())
            manifest = SessionManifest.model_validate(data)
            if manifest.version != MANIFEST_VERSION:
                raise ManifestStorageError(
                    f"Unsupported manifest version {manifest.version}; expected {MANIFEST_VERSION}"
                )
            return manifest

    def save_manifest(self, manifest: SessionManifest) -> None:
        if manifest.version != MANIFEST_VERSION:
            raise ManifestStorageError(
                f"Cannot save manifest with version {manifest.version}; expected {MANIFEST_VERSION}"
            )
        with self._lock:
            tmp_path = self.manifest_path.with_suffix(".tmp")
            try:
                tmp_path.write_text(manifest.model_dump_json(indent=2))
                tmp_path.replace(self.manifest_path)
            except OSError as e:
                # Clean up any leftover temp file on failure
                tmp_path.unlink(missing_ok=True)
                raise ManifestStorageError(
                    f"Failed to save manifest to {self.manifest_path}: {e}"
                ) from e

    def checkpoint_path(self) -> Path:
        return self.checkpoints_dir / "global.sqlite"
