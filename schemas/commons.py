

from typing import Any, List
from pydantic import BaseModel


class ListResponse(BaseModel):
    total: int
    page: int
    size: int
    data: List[Any]
