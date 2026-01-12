from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .models import NoteCreate, NoteUpdate, NoteVerify, SearchRequest, NoteMetadataUpdate
from .storage import get_store
from .parsers import extract_text_from_file, generate_title_from_content, extract_metadata
from .categories import CATEGORIES, get_category


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


app = FastAPI(title="Knowledge Notebook API", version="0.1.0")

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent.parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


def _store():
    return get_store()


@app.get("/")
def root():
    """Redirect to web UI"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
def health():
    store = _store()
    store.ensure_collection()
    return {"status": "ok", "collection": store.collection}


@app.get("/api/categories")
def list_categories():
    """Get all categories"""
    return [cat.dict() for cat in CATEGORIES.values()]


@app.get("/api/notes/all")
def list_all_notes(limit: int = 100):
    """List all notes (latest versions only)"""
    store = _store()
    all_notes = store.list_all_notes(limit=limit)
    return all_notes


@app.post("/notes")
def create_note(payload: NoteCreate):
    store = _store()
    note_id = str(uuid.uuid4())
    point_id = store.upsert_note_version(
        note_id=note_id,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        source_url=payload.source_url,
        status="unverified",
        verified_at=None,
        version=1,
    )
    latest = store.get_latest_version(note_id)
    return {"note_id": note_id, "point_id": point_id, "latest": latest}


@app.get("/notes/{note_id}")
def get_note(note_id: str):
    store = _store()
    latest = store.get_latest_version(note_id)
    if not latest:
        raise HTTPException(status_code=404, detail="note not found")
    return latest


@app.get("/notes/{note_id}/versions")
def list_versions(note_id: str):
    store = _store()
    versions = store.list_versions(note_id)
    if not versions:
        raise HTTPException(status_code=404, detail="note not found")
    return {"note_id": note_id, "versions": versions}


@app.patch("/notes/{note_id}")
def update_note(note_id: str, payload: NoteUpdate):
    store = _store()
    latest = store.get_latest_version(note_id)
    if not latest:
        raise HTTPException(status_code=404, detail="note not found")

    next_version = int(latest.get("version", 1)) + 1

    title = payload.title if payload.title is not None else latest.get("title", "")
    content = payload.content if payload.content is not None else latest.get("content", "")
    tags = payload.tags if payload.tags is not None else latest.get("tags", [])
    source_url = payload.source_url if payload.source_url is not None else latest.get("source_url")

    point_id = store.upsert_note_version(
        note_id=note_id,
        title=title,
        content=content,
        tags=tags,
        source_url=source_url,
        status=latest.get("status", "unverified"),
        verified_at=latest.get("verified_at"),
        version=next_version,
    )
    return {"note_id": note_id, "point_id": point_id, "latest": store.get_latest_version(note_id)}


@app.post("/notes/{note_id}/verify")
def verify_note(note_id: str, payload: NoteVerify):
    store = _store()
    latest = store.get_latest_version(note_id)
    if not latest:
        raise HTTPException(status_code=404, detail="note not found")

    next_version = int(latest.get("version", 1)) + 1
    verified_at = _utc_now_iso() if payload.status == "verified" else None

    point_id = store.upsert_note_version(
        note_id=note_id,
        title=latest.get("title", ""),
        content=latest.get("content", ""),
        tags=latest.get("tags", []),
        source_url=latest.get("source_url"),
        status=payload.status,
        verified_at=verified_at,
        version=next_version,
    )
    return {"note_id": note_id, "point_id": point_id, "latest": store.get_latest_version(note_id)}


@app.patch("/notes/{note_id}/metadata")
def update_metadata(note_id: str, payload: NoteMetadataUpdate):
    """Update only metadata (title, tags, status, source_url) without creating new version"""
    store = _store()
    latest = store.get_latest_version(note_id)
    if not latest:
        raise HTTPException(status_code=404, detail="note not found")

    # Update only provided fields
    title = payload.title if payload.title is not None else latest.get("title", "")
    tags = payload.tags if payload.tags is not None else latest.get("tags", [])
    status = payload.status if payload.status is not None else latest.get("status", "unverified")
    source_url = payload.source_url if payload.source_url is not None else latest.get("source_url")
    
    verified_at = latest.get("verified_at")
    if payload.status == "verified" and status != latest.get("status"):
        verified_at = _utc_now_iso()
    elif payload.status and payload.status != "verified":
        verified_at = None

    next_version = int(latest.get("version", 1)) + 1
    point_id = store.upsert_note_version(
        note_id=note_id,
        title=title,
        content=latest.get("content", ""),
        tags=tags,
        source_url=source_url,
        status=status,
        verified_at=verified_at,
        version=next_version,
    )
    return {"note_id": note_id, "updated_fields": payload.dict(exclude_none=True), "latest": store.get_latest_version(note_id)}


@app.post("/search")
def search(payload: SearchRequest):
    store = _store()
    results = store.search(payload.query, limit=payload.limit, tags=payload.tags or None)
    return {"query": payload.query, "results": results}


@app.delete("/notes/{note_id}")
def delete_note(note_id: str):
    store = _store()
    deleted_count = store.delete_note(note_id)
    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="note not found")
    return {"note_id": note_id, "deleted_versions": deleted_count}


@app.post("/ingest")
async def ingest_file(file: UploadFile = File(...), tags: str = ""):
    """Ingest a file and create a note from its content"""
    store = _store()
    
    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "file").suffix) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)
    
    try:
        # Extract text content
        text_content = extract_text_from_file(tmp_path, file.content_type)
        
        # Generate title
        title = generate_title_from_content(text_content, file.filename or "Untitled")
        
        # Extract metadata and suggested tags
        metadata = extract_metadata(tmp_path, text_content)
        suggested_tags = metadata['suggested_tags']
        
        # Parse user-provided tags
        user_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        all_tags = list(set(user_tags + suggested_tags + ["ingested"]))
        
        # Add file info to content
        file_info = f"\n\n---\n**Source File**: {file.filename}\n**Size**: {metadata['file_size']} bytes\n**Type**: {metadata['file_type']}"
        full_content = text_content + file_info
        
        # Create note
        note_id = str(uuid.uuid4())
        point_id = store.upsert_note_version(
            note_id=note_id,
            title=title,
            content=full_content,
            tags=all_tags,
            source_url=None,
            status="unverified",
            verified_at=None,
            version=1,
        )
        
        latest = store.get_latest_version(note_id)
        
        return {
            "note_id": note_id,
            "point_id": point_id,
            "title": title,
            "extracted_length": len(text_content),
            "suggested_tags": suggested_tags,
            "latest": latest
        }
    finally:
        # Clean up temp file
        tmp_path.unlink(missing_ok=True)


@app.post("/notes/{note_id}/files")
async def upload_file(note_id: str, file: UploadFile = File(...)):
    store = _store()
    latest = store.get_latest_version(note_id)
    if not latest:
        raise HTTPException(status_code=404, detail="note not found")
    
    files_dir = Path("files") / note_id
    files_dir.mkdir(parents=True, exist_ok=True)
    
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename or "").suffix
    file_path = files_dir / f"{file_id}{file_ext}"
    
    content = await file.read()
    file_path.write_bytes(content)
    
    file_info = {
        "file_id": file_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content),
        "uploaded_at": _utc_now_iso(),
    }
    
    attachments = latest.get("attachments", [])
    attachments.append(file_info)
    
    next_version = int(latest.get("version", 1)) + 1
    store.upsert_note_version(
        note_id=note_id,
        title=latest.get("title", ""),
        content=latest.get("content", ""),
        tags=latest.get("tags", []),
        source_url=latest.get("source_url"),
        status=latest.get("status", "unverified"),
        verified_at=latest.get("verified_at"),
        version=next_version,
        attachments=attachments,
    )
    
    return {"note_id": note_id, "file_id": file_id, "filename": file.filename}


@app.get("/notes/{note_id}/files")
def list_files(note_id: str):
    store = _store()
    latest = store.get_latest_version(note_id)
    if not latest:
        raise HTTPException(status_code=404, detail="note not found")
    return {"note_id": note_id, "files": latest.get("attachments", [])}


@app.get("/files/{note_id}/{file_id}")
def download_file(note_id: str, file_id: str):
    store = _store()
    latest = store.get_latest_version(note_id)
    if not latest:
        raise HTTPException(status_code=404, detail="note not found")
    
    attachments = latest.get("attachments", [])
    file_info = next((f for f in attachments if f["file_id"] == file_id), None)
    if not file_info:
        raise HTTPException(status_code=404, detail="file not found")
    
    files_dir = Path("files") / note_id
    file_ext = Path(file_info["filename"]).suffix
    file_path = files_dir / f"{file_id}{file_ext}"
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="file not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=file_info["filename"],
        media_type=file_info.get("content_type", "application/octet-stream"),
    )
