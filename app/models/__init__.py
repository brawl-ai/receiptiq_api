
import datetime
import uuid
from sqlalchemy.orm import DeclarativeBase


class Model(DeclarativeBase):
    def to_dict(self):
        object_dict = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        for key, value in object_dict.items():
            if isinstance(value, datetime.datetime):
                object_dict[key] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                object_dict[key] = str(value)
        return object_dict
    
from .auth_models import *
from .project_models import *