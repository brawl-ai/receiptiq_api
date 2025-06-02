import datetime
import json
import uuid
from typing import Dict, Optional, Any, List
from mongoengine import (
    Document, StringField, DateTimeField, ReferenceField,
    ListField, UUIDField, DictField, EmbeddedDocument,
    EmbeddedDocumentListField, FileField
)
from enum import Enum
from app.extractor import InvoiceExtractor
from app.models.auth import User

class FieldType(str, Enum):
    STRING = 'string'
    NUMBER = 'number'
    DATE = 'date'
    BOOLEAN = 'boolean'
    OBJECT = 'object'
    ARRAY = 'array'

class Field(Document):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    name = StringField(required=True, max_length=100)
    field_type = StringField(required=True, max_length=50, choices=[t.value for t in FieldType])
    description = StringField(max_length=500)
    schema = ReferenceField("Schema", required=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField()

    meta = {
        'collection': 'fields',
        'indexes': ['name', 'schema']
    }

    def clean(self):
        """
        Validate that field_type is a valid FieldType
        """
        if self.field_type not in [t.value for t in FieldType]:
            raise ValueError(f"Invalid field type: {self.field_type}. Must be one of {[t.value for t in FieldType]}")

class Schema(Document):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    name = StringField(required=True, max_length=100)
    description = StringField(max_length=500)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField()

    meta = {
        'collection': 'schemas',
        'indexes': ['name']
    }
    
    @property
    def fields(self):
        """Get all fields for this schema"""
        return Field.objects(schema=self)

class DataValue(Document):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    field = ReferenceField(Field, required=True)
    value = DictField(required=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField()

    meta = {
        'collection': 'data_values',
        'indexes': ['field']
    }
    
class Receipt(Document):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    schema = ReferenceField(Schema, required=True, reverse_delete_rule='CASCADE')
    file_path = StringField(required=True, max_length=500)
    file_name = StringField(required=True, max_length=255)
    mime_type = StringField(required=True, max_length=100)
    data_values = ListField(ReferenceField(DataValue, reverse_delete_rule='CASCADE'))
    status = StringField(required=True, max_length=50, default='pending', 
                        choices=['pending', 'processing', 'completed', 'failed'])
    error_message = StringField(max_length=500)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField()

    meta = {
        'collection': 'receipts',
        'indexes': [
            'schema',
            'status',
            ('schema'),
            ('status')
        ]
    }

    def add_data_value(self, field: Field, value: Any) -> DataValue:
        """
        Add a new data value to the receipt
        """
        data_value = DataValue(
            field=field,
            value={'data': value}
        )
        data_value.save()
        self.data_values.append(data_value)
        self.save()
        return data_value

    def get_data_value_by_field_name(self, field_name: str) -> Optional[DataValue]:
        """
        Get a data value by field name
        """
        for data_value in self.data_values:
            if data_value.field.name == field_name:
                return data_value
        return None

    def update_status(self, status: str, error_message: Optional[str] = None) -> None:
        """
        Update the receipt status and optionally set an error message
        """
        self.status = status
        if error_message:
            self.error_message = error_message
        self.save()
        
    def process(self, extractor: InvoiceExtractor, schema: Dict[str, Any])->List[DataValue]:
        try:
            result = extractor.extract_from_document(
                document_path=self.file_path,
                schema=schema,
                extraction_instructions="Focus on accuracy for financial amounts and dates."
            )            
            # Update status to processing
            self.status = "processing"
            self.save()
            
            # Add each extracted value as a DataValue
            for field_name, value in result.items():
                # Find the corresponding field in the schema
                field = None
                for f in self.schema.fields:
                    if f.name == field_name:
                        field = f
                        break
                if field:
                    # Create and add the data value
                    self.add_data_value(field, value)
            
            # Update status to completed
            self.status = "completed"
            self.save()
            
            return self.data_values
        
        except Exception as e:
            # Update status to failed and store error message
            self.status = "failed"
            self.error_message = str(e)
            self.save()
            print(f"Extraction failed: {e}")
            raise e

class Project(Document):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    name = StringField(required=True, max_length=100)
    description = StringField(max_length=500)
    owner = ReferenceField(User, required=True, reverse_delete_rule='CASCADE')
    schema = ReferenceField(Schema, reverse_delete_rule='CASCADE')
    receipts = ListField(ReferenceField(Receipt, reverse_delete_rule='CASCADE'))
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField()

    meta = {
        'collection': 'projects',
        'indexes': [
            'name',
            'owner',
            ('owner', 'name')  # Compound index for faster queries
        ]
    }

    def add_schema(self, name: str, description: str = None) -> Schema:
        """
        Create and add a new schema to the project
        """
        schema = Schema(
            name=name,
            description=description
        )
        schema.save()
        self.schema = schema
        self.save()
        return schema

    def add_field_to_schema(self, schema_id: uuid.UUID, field_name: str, field_type: FieldType, description: str = None) -> Optional[Field]:
        """
        Add a new field to a schema
        """
        field = Field(
            name=field_name,
            field_type=field_type.value,
            description=description,
            schema=self.schema
        )
        field.save()
        return field

    def create_data_value(self, schema_id: uuid.UUID, field_name: str, value: Any) -> Optional[DataValue]:
        """
        Create a new data value for a field in a schema
        """
        field = None
        for f in self.schema.fields:
            if f.name == field_name:
                field = f
                break

        if not field:
            return None

        data_value = DataValue(
            field=field,
            value={'data': value}
        )
        data_value.save()
        return data_value

    def create_receipt(self, schema_id: uuid.UUID, file_path: str, file_name: str, mime_type: str) -> Optional["Receipt"]:
        """
        Create a new receipt for the project
        """
        receipt = Receipt(
            schema=self.schema,
            file_path=file_path,
            file_name=file_name,
            mime_type=mime_type
        )
        receipt.save()
        self.receipts.append(receipt)
        self.save()
        return receipt

    def get_receipts_by_status(self, status: str) -> List["Receipt"]:
        """
        Get all receipts with a specific status
        """
        return [r for r in self.receipts if r.status == status]

