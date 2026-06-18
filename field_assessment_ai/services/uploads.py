from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid

from .common import sanitize_filename


@dataclass(slots=True)
class SavedUpload:
    original_filename: str
    stored_filename: str
    relative_path: str
    public_url: str
    mime_type: str | None
    file_size_bytes: int


def save_upload_bytes(
    base_dir: Path,
    *,
    relative_dir: str,
    original_filename: str,
    contents: bytes,
    mime_type: str | None = None,
    prefix: str | None = None,
    public_prefix: str = "/uploads",
) -> SavedUpload:
    safe_filename = sanitize_filename(original_filename)
    stored_filename = (
        f"{prefix}_{uuid.uuid4().hex}_{safe_filename}" if prefix else f"{uuid.uuid4().hex}_{safe_filename}"
    )
    relative_path = Path(relative_dir) / stored_filename
    destination = base_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(contents)
    public_url = f"{public_prefix}/{relative_path.as_posix()}"
    return SavedUpload(
        original_filename=original_filename or safe_filename,
        stored_filename=stored_filename,
        relative_path=relative_path.as_posix(),
        public_url=public_url,
        mime_type=mime_type,
        file_size_bytes=len(contents),
    )
