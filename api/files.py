from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse

from utils import StorageService

router = APIRouter(tags=["Files"])
storage = StorageService()

@router.get("/{file_path:path}", status_code=200)
async def download(file_path: str) -> FileResponse:
    try:
        download_url = storage.get_url(file_path)
        return RedirectResponse(url=download_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )