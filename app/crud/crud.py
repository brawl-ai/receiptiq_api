from typing import List, Optional, Any, Dict, TypeVar, Generic, Type
from uuid import UUID
from mongoengine import Document, DoesNotExist
from app.models.projects import Project, Schema, Field, Receipt, DataValue, FieldType
from app.models.auth import User

ModelType = TypeVar("ModelType", bound=Document)

class ServiceBase(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, id: UUID) -> Optional[ModelType]:
        try:
            return self.model.objects.get(id=id)
        except DoesNotExist:
            return None

    def get_multi(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        return list(self.model.objects.skip(skip).limit(limit))

    def create(self, **kwargs) -> ModelType:
        obj = self.model(**kwargs)
        obj.save()
        return obj

    def update(self, id: UUID, **kwargs) -> Optional[ModelType]:
        try:
            obj = self.model.objects.get(id=id)
            for key, value in kwargs.items():
                setattr(obj, key, value)
            obj.save()
            return obj
        except DoesNotExist:
            return None

    def delete(self, id: UUID) -> bool:
        try:
            obj = self.model.objects.get(id=id)
            obj.delete()
            return True
        except DoesNotExist:
            return False

class ProjectService(ServiceBase[Project]):
    def get_by_owner(self, owner_id: UUID, skip: int = 0, limit: int = 100) -> List[Project]:
        return list(Project.objects(owner=owner_id).skip(skip).limit(limit))

    def get_by_name(self, owner_id: UUID, name: str) -> Optional[Project]:
        try:
            return Project.objects.get(owner=owner_id, name=name)
        except DoesNotExist:
            return None

    def create_with_owner(self, *, owner: User, **kwargs) -> Project:
        project = Project(owner=owner, **kwargs)
        project.save()
        return project

class SchemaService(ServiceBase[Schema]):
    def get_by_project(self, project_id: UUID, skip: int = 0, limit: int = 100) -> List[Schema]:
        return list(Schema.objects(project=project_id).skip(skip).limit(limit))

    def get_by_name(self, project_id: UUID, name: str) -> Optional[Schema]:
        try:
            return Schema.objects.get(project=project_id, name=name)
        except DoesNotExist:
            return None

    def create_with_project(self, *, project: Project, **kwargs) -> Schema:
        schema = Schema(project=project, **kwargs)
        schema.save()
        return schema

class ReceiptService(ServiceBase[Receipt]):
    def get_by_project(self, project_id: UUID, skip: int = 0, limit: int = 100) -> List[Receipt]:
        return list(Receipt.objects(project=project_id).skip(skip).limit(limit))

    def get_by_status(self, project_id: UUID, status: str, skip: int = 0, limit: int = 100) -> List[Receipt]:
        return list(Receipt.objects(project=project_id, status=status).skip(skip).limit(limit))

    def get_by_schema(self, schema_id: UUID, skip: int = 0, limit: int = 100) -> List[Receipt]:
        return list(Receipt.objects(schema=schema_id).skip(skip).limit(limit))

    def create_with_project_and_schema(
        self, 
        *, 
        project: Project, 
        schema: Schema,
        file_path: str,
        file_name: str,
        mime_type: str
    ) -> Receipt:
        receipt = Receipt(
            project=project,
            schema=schema,
            file_path=file_path,
            file_name=file_name,
            mime_type=mime_type
        )
        receipt.save()
        return receipt

    def update_status(self, id: UUID, status: str, error_message: Optional[str] = None) -> Optional[Receipt]:
        try:
            receipt = Receipt.objects.get(id=id)
            receipt.status = status
            if error_message:
                receipt.error_message = error_message
            receipt.save()
            return receipt
        except DoesNotExist:
            return None

class DataValueService(ServiceBase[DataValue]):
    def get_by_receipt(self, receipt_id: UUID, skip: int = 0, limit: int = 100) -> List[DataValue]:
        return list(DataValue.objects(receipt=receipt_id).skip(skip).limit(limit))

    def get_by_field(self, field_id: UUID, skip: int = 0, limit: int = 100) -> List[DataValue]:
        return list(DataValue.objects(field=field_id).skip(skip).limit(limit))

    def create_with_receipt_and_field(
        self,
        *,
        receipt: Receipt,
        field: Field,
        value: Dict[str, Any]
    ) -> DataValue:
        data_value = DataValue(
            receipt=receipt,
            field=field,
            value=value
        )
        data_value.save()
        return data_value

# Create instances for use in the application
project_service = ProjectService(Project)
schema_service = SchemaService(Schema)
receipt_service = ReceiptService(Receipt)
data_value_service = DataValueService(DataValue) 