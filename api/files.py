from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os

router = APIRouter(tags=["Files"]) 

# Media type mapping for expected file types
MEDIA_TYPE_MAP = {
    # Documents
    "pdf": "application/pdf",
    "csv": "text/csv",
    
    # Images
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png", 
    "gif": "image/gif",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}

@router.get("/{file_path:path}", status_code=200)
async def download(file_path: str) -> FileResponse:
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404, 
            detail={"message": "No such file was found"}
        )
    
    file_extension = file_path.split(".")[-1].lower()
    file_name = os.path.basename(file_path)
    
    # Get media type or default to octet-stream
    media_type = MEDIA_TYPE_MAP.get(file_extension, "application/octet-stream")
    
    return FileResponse(
        file_path, 
        media_type=media_type, 
        filename=file_name
    )