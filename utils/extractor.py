import json
from typing import Dict, List, Any
import logging
from openai import OpenAI
from config import get_settings
from typing import Dict, Any

def prepare_openai_schema(fields: List):
    properties = {}
    for field in fields:
        if field["type"].value == "object":
            props = prepare_openai_schema(field["children"])
            properties[field["name"]] = {
                "type": "object",
                "properties": props,
                "required": list(props.keys()),
                "additionalProperties": False
            }
        elif field["type"].value == "array":
            props = prepare_openai_schema(field["children"])
            properties[field["name"]] = {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": props,
                    "required": list(props.keys()),
                    "additionalProperties": False
                },
                "additionalProperties": False
            }
        else:
            if field["type"].value == "date":
                field_value = {
                    "type": "string",
                    "format": "date",
                    "description": field["description"]
                }
            else:
                field_value = {
                    "type": field["type"].value,
                    "description": field["description"]
                }
            properties[field["name"]] = {
                "type": "object",
                "properties": {
                    "value": field_value,
                    "coordinates": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                        },
                        "required": ["x","y","width","height"],
                        "additionalProperties": False
                    }
                },
                "required": ["value","coordinates"],
                "additionalProperties": False
            }
    return properties


class InvoiceExtractor:    
    def __init__(self, llm_provider: str = "openai", model_name: str = "gpt-5-mini"):
        """
        Initialize the invoice extractor
        
        Args:
            llm_provider: "openai", "receiptiq"
            model_name: Name of the model to use
        """
        self.llm_provider = llm_provider
        self.model_name = model_name
        if llm_provider == "openai":
            settings = get_settings()
            self.client = OpenAI(api_key=settings.openai_api_key)
        elif llm_provider == "receiptiq":
            raise NotImplementedError(f"Unsupported LLM provider: {llm_provider}")
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def call_receiptiq_model(self, document_url: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """call receiptiq model"""
        raise NotImplementedError
    
    def extract_from_document(self, document_url: str, fields: List, file_type: str) -> Dict[str, Any]:
        """
        Main method to extract data from invoice document using user-defined schema
        
        Args:
            document_path: Path to the invoice document (PDF or image)
            schema: User-defined schema dictionary defining expected fields
            extraction_instructions: Optional custom instructions for extraction
            
        Returns:
            Dictionary containing extracted invoice data matching the schema
        """
        if self.llm_provider == "openai":
            properties = prepare_openai_schema(fields=fields)
            schema = {
                "type": "json_schema",
                "strict": True,
                "name": "receipt_response",
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties.keys()),
                    "additionalProperties": False
                }
            }
            # print(schema)
            return self.call_openai(document_url, schema, file_type)

        elif self.llm_provider == "ollama":
            return self.call_receiptiq_model(document_url, schema)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    def call_openai(self, document_url: str, schema: Dict[str, Any], file_type: str) -> Dict[str, Any]:
        system_prompt = """
            You are a precise data extraction assistant. 
            Given the receipt and schema, extract the data that matches the schema.
            If a field cannot be found, use null or an appropriate default value.
            Be precise with numbers and dates.
            Make sure to include estimates for coordinates in the format given: 
                x is your estimate x coordinate of the start of the value,
                y is your estimate y coordinate of the start of the value,
                w is the pixel width of the extracted value,
                h is the pixel height of the extracted value.
        """
        try:
            if file_type == "application/pdf":
                receipt = {
                    "type": "input_file",
                    "file_url": document_url
                }
            else:
                receipt = {
                    "type": "input_image",
                    "image_url": document_url
                }
            print(receipt)
            response = self.client.responses.create(
                model=self.model_name,
                input=[
                    {
                        "role": "system", 
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "Extract the data from the receipt that matches the schema"
                            },
                            receipt
                        ]
                    }
                ],
                text = {"format": schema }
            )
            result_text = response.output_text
            return json.loads(result_text)
        except Exception as e:
            raise Exception(f"OpenAI API call failed: {e}")