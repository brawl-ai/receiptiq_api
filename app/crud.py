from typing import Optional, Sequence, TypeVar
from fastapi import HTTPException, Query
from pydantic import UUID4, BaseModel
from sqlalchemy import exc, or_, select
from sqlalchemy.orm import Session
from app.models import Model
from app.schemas import ListResponse
from app.config import logger

async def get_obj_or_404(db: Session, model: Model, id: UUID4) -> Model:
    """
        Returns one object from the database by pk id or raise an exception:  sqlalchemy.orm.exc.NoResultFound if no result is found
    """
    logger.info(f"Getting {model.__name__} with id: {id}")
    try:
        return db.execute(select(model).where(model.id == id)).scalar_one()
    except exc.NoResultFound:
        raise HTTPException(status_code=404,detail={"message":f"{model.__name__} with id {id} not found"})

async def filter_objects(db: Session, model: Model, params: dict = {}, sort_by:str = "created_at,asc" ) -> Sequence[Model]:
    """
        Returns a list of objects from the database filtered by the given params
    """
    logger.info(f"Filtering {model.__tablename__} with params: {params}")
    try:
        sort_key, sort_order = tuple(sort_by.split(','))
        sort_column = getattr(model, sort_key)
        CONDITION_MAP = {
            'eq': lambda col, val: col == val,
            'ne': lambda col, val: col != val,
            'lt': lambda col, val: col < val,
            'lte': lambda col, val: col <= val,
            'gt': lambda col, val: col > val,
            'gte': lambda col, val: col >= val,
            'like': lambda col, val: col.like(val),
            'ilike': lambda col, val: col.ilike("%"+val+"%"),
            'contains': lambda col, val: col.contains(val),
            'in': lambda col, val: col.in_(val),
        }
        query = select(model)
        for key, value in params.items():
            if '__' in key:
                column_name, condition = key.split('__', 1)
            else:
                column_name, condition = key, 'eq'
            column = getattr(model, column_name)
            query = query.where(CONDITION_MAP[condition](column, value))
        query = query.order_by(sort_column.asc() if sort_order == 'asc' else sort_column.desc())
        logger.info(f"Query: {query.compile()}")
        return db.scalars(query).all()
    except Exception as e:
        logger.error(f"Error: {str(e)} filtering {model.__tablename__} with params: {params}")
        raise e
    
async def search_objects(db: Session, model: Model, q: str) -> Sequence[Model]:
    logger.info(f"Searching {model.__tablename__} with query: {q}")
    query = select(model)
    conditions = []
    for column in model.__table__.columns:
        if column.type.python_type == str:
            conditions.append(column.ilike(f"%{q}%"))
    if conditions:
        query = query.where(or_(*conditions))
    return db.scalars(query).all()

async def paginate(
                    db: Session, 
                    model: Model,
                    schema: BaseModel,
                    q: Optional[str] = None,
                    page: int = Query(1, ge=1),
                    size: int = Query(10, ge=1, le=100),
                    sort_by: str = "created_at,asc",
                    **params
                ) -> ListResponse:
    if q:
        data = await search_objects(db=db, model=model,q=q)
    elif params and len(params) > 0:
        data = await filter_objects(db=db, model=model,params=params,sort_by=sort_by)
    else:
        data = await filter_objects(db=db, model=model, params={},sort_by=sort_by)
    offset = (page - 1) * size
    total = len(data)
    paginated_items = data[offset:offset + size]
    paginated_items = [schema.model_validate(item) for item in paginated_items]
    return ListResponse(**{
        "total": total,
        "page": page,
        "size": size,
        "data": paginated_items
    })