from typing import Tuple
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse, RedirectResponse
import requests

from utils import get_current_active_verified_user
from models import User
from utils import StorageService

router = APIRouter(tags=["Files"])

@router.get("/{file_path:path}", status_code=200)
async def download(file_path: str, auth: Tuple[User, str] = Depends(get_current_active_verified_user)):
    try:
        storage = StorageService()
        download_url = storage.get_url(file_path)
        response = requests.get(download_url)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', 'application/octet-stream')
        filename = file_path.split('/')[-1]
        return Response(
            content=response.content,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Content-Type": content_type
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )