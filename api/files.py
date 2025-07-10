from typing import Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse

from utils import get_current_active_verified_user
from models import User
from utils import StorageService

router = APIRouter(tags=["Files"])
storage = StorageService()

@router.get("/{file_path:path}", status_code=200)
async def download(file_path: str, auth: Tuple[User, str] = Depends(get_current_active_verified_user)) -> FileResponse:
    try:
        download_url = storage.get_url(file_path)
        return RedirectResponse(url=download_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )