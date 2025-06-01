import os
import json
from typing import Dict, Optional, Any
from pathlib import Path
import logging
from pydantic_settings import BaseSettings
import pypdf
import pdfplumber
import pytesseract
import cv2
from openai import OpenAI

class InvoiceExtractor:    
    def __init__(self, 
                 llm_provider: str = "openai",
                 api_key: Optional[str] = None,
                 model_name: str = "gpt-3.5-turbo",
                 local_model_path: Optional[str] = None):
        """
        Initialize the invoice extractor
        
        Args:
            llm_provider: "openai", "anthropic", "local", or "ollama"
            api_key: API key for cloud LLM providers
            model_name: Name of the model to use
            local_model_path: Path to local model (if using local)
        """
        self.llm_provider = llm_provider
        self.model_name = model_name
        if llm_provider == "openai":
            self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        elif llm_provider == "local":
            self.setup_local_model(local_model_path)
        elif llm_provider == "ollama":
            self.setup_ollama()
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def setup_local_model(self, model_path: Optional[str] = None):
        """Setup local model using transformers"""
        raise NotImplementedError
    
    def setup_ollama(self):
        """Setup Ollama for local LLM"""
        raise NotImplementedError
    
    def extract_from_document(self, 
                            document_path: str, 
                            schema: Dict[str, Any],
                            extraction_instructions: Optional[str] = None) -> Dict[str, Any]:
        """
        Main method to extract data from invoice document using user-defined schema
        
        Args:
            document_path: Path to the invoice document (PDF or image)
            schema: User-defined schema dictionary defining expected fields
            extraction_instructions: Optional custom instructions for extraction
            
        Returns:
            Dictionary containing extracted invoice data matching the schema
        """
        if not os.path.exists(document_path):
            raise FileNotFoundError(f"Document not found: {document_path}")
        text, coordinates = self.extract_text_from_document(document_path)
        if not text.strip():
            raise ValueError("No text could be extracted from the document")
        extracted_data = self.llm_extract_data(text, schema, extraction_instructions)
        extracted_data['_metadata'] = {
            'source_file': document_path,
            'extraction_method': f"{self.llm_provider}:{self.model_name}",
            'text_length': len(text),
            'coordinates_available': len(coordinates) > 0
        }
        return extracted_data
    
    def extract_text_from_document(self, document_path: str) -> tuple[str, Dict]:
        """Extract text from PDF or image document"""
        file_ext = Path(document_path).suffix.lower()
        if file_ext == '.pdf':
            return self.extract_from_pdf(document_path)
        elif file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            return self.extract_from_image(document_path)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}. Supported: PDF, JPG, PNG, TIFF, BMP")
    
    def extract_from_pdf(self, pdf_path: str) -> tuple[str, Dict]:
        """Extract text from PDF with coordinate information"""
        text, coordinates = "",{}
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text += f"--- Page {page_num + 1} ---\n{page_text}\n"
                    try:
                        chars = page.chars
                        for char in chars:
                            if char['text'].strip():
                                y_pos = int(char['top'])
                                if y_pos not in coordinates:
                                    coordinates[y_pos] = []
                                coordinates[y_pos].append({
                                    'text': char['text'],
                                    'x': char['x0'],
                                    'y': char['top'],
                                    'page': page_num
                                })
                    except Exception as e:
                        self.logger.warning(f"Could not extract coordinates: {e}")
        
        except Exception as e:
            # Fallback to PyPDF
            self.logger.warning(f"pdfplumber failed, trying PyPDF: {e}")
            try:
                with open(pdf_path, 'rb') as file:
                    pdf_reader = pypdf.PdfReader(file)
                    for page_num, page in enumerate(pdf_reader.pages):
                        text += f"--- Page {page_num + 1} ---\n{page.extract_text()}\n"
            except Exception as e2:
                raise Exception(f"Failed to extract text from PDF: {e2}")
        
        return text, coordinates
    
    def extract_from_image(self, image_path: str) -> tuple[str, Dict]:
        """Extract text from image using OCR"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Could not load image: {image_path}")
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            denoised = cv2.fastNlMeansDenoising(gray)
            _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # # Use local Tesseract binary
            # tesseract_path = os.path.join(os.path.dirname(__file__), 'tesseract')
            # if not os.path.exists(tesseract_path):
            #     raise FileNotFoundError(f"Tesseract binary not found at {tesseract_path}")
            # pytesseract.pytesseract.tesseract_cmd = tesseract_path
            
            data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
            text_parts = []
            coordinates = {}
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > 30:  # Only include confident text
                    text_part = data['text'][i].strip()
                    if text_part:
                        text_parts.append(text_part)
                        
                        y_pos = data['top'][i]
                        if y_pos not in coordinates:
                            coordinates[y_pos] = []
                        coordinates[y_pos].append({
                            'text': text_part,
                            'x': data['left'][i],
                            'y': data['top'][i],
                            'width': data['width'][i],
                            'height': data['height'][i],
                            'confidence': data['conf'][i]
                        })
            text = ' '.join(text_parts)
        except Exception as e:
            raise Exception(f"Failed to extract text from image: {e}")
        
        return text, coordinates
    
    def llm_extract_data(self, 
                        text: str, 
                        schema: Dict[str, Any],
                        instructions: Optional[str] = None) -> Dict[str, Any]:
        """Use LLM to extract structured data from text based on schema"""
        
        # Build the prompt
        prompt = self.build_extraction_prompt(text, schema, instructions)
        
        # Call appropriate LLM
        if self.llm_provider == "openai":
            return self.call_openai(prompt)
        elif self.llm_provider == "local":
            return self.call_local_model(prompt)
        elif self.llm_provider == "ollama":
            return self.call_ollama(prompt)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")
    
    def build_extraction_prompt(self, 
                               text: str, 
                               schema: Dict[str, Any],
                               instructions: Optional[str] = None) -> str:
        """Build prompt for LLM extraction"""
        
        schema_description = self.describe_schema(schema)
        base_instructions = instructions or """
        You are an expert at extracting structured data from invoice documents.
        Extract the requested information accurately and return it as valid JSON.
        If a field cannot be found, use null or an appropriate default value.
        Be precise with numbers and dates.
        """
        prompt = f"""
{base_instructions}

DOCUMENT TEXT:
{text}

REQUIRED SCHEMA:
{schema_description}

Extract the data that matches the schema from the document text above.
Return ONLY valid JSON that matches the schema structure.
Do not include any explanations or additional text.

JSON Response:
"""
        
        return prompt
    
    def describe_schema(self, schema: Dict[str, Any]) -> str:
        """Convert schema dictionary to description for LLM"""
        description = "{\n"
        for key, value in schema.items():
            if isinstance(value, dict):
                if 'type' in value:
                    field_type = value['type']
                    field_desc = value.get('description', '')
                    required = value.get('required', False)
                    
                    description += f'  "{key}": {field_type}'
                    if field_desc:
                        description += f' // {field_desc}'
                    if required:
                        description += ' (required)'
                    description += ',\n'
                else:
                    # Nested object
                    description += f'  "{key}": {{\n'
                    for nested_key, nested_value in value.items():
                        description += f'    "{nested_key}": {nested_value},\n'
                    description += '  },\n'
            else:
                description += f'  "{key}": "{value}",\n'
        
        description = description.rstrip(',\n') + '\n}'
        return description
    
    def call_openai(self, prompt: str) -> Dict[str, Any]:
        """Call OpenAI API for extraction"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a precise data extraction assistant. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=2000
            )
            
            result_text = response.choices[0].message.content.strip()
            try:
                return json.loads(result_text)
            except json.JSONDecodeError:
                import re
                json_match = re.search(r'```(?:json)?\n?(.*?)\n?```', result_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                else:
                    raise ValueError(f"Invalid JSON response: {result_text}")
        except Exception as e:
            raise Exception(f"OpenAI API call failed: {e}")
    
    def call_local_model(self, prompt: str) -> Dict[str, Any]:
        """Call local model for extraction"""
        raise NotImplementedError
    
    def call_ollama(self, prompt: str) -> Dict[str, Any]:
        """Call Ollama local API for extraction"""
        raise NotImplementedError

"""
if __name__ == "__main__":
    sample_schema = {
        "vendor_name": {"type": "string", "description": "Name of the vendor/supplier", "required": True},
        "vendor_address": {"type": "string", "description": "Vendor's address"},
        "invoice_number": {"type": "string", "description": "Invoice number", "required": True},
        "invoice_date": {"type": "string", "description": "Invoice date in YYYY-MM-DD format"},
        "due_date": {"type": "string", "description": "Payment due date in YYYY-MM-DD format"},
        "total_amount": {"type": "number", "description": "Total amount due", "required": True},
        "subtotal": {"type": "number", "description": "Subtotal before tax"},
        "tax_amount": {"type": "number", "description": "Tax amount"},
        "currency": {"type": "string", "description": "Currency code (e.g., USD, EUR)"},
        "line_items": {
            "type": "array",
            "description": "List of line items",
            "items": {
                "description": {"type": "string"},
                "quantity": {"type": "number"},
                "unit_price": {"type": "number"},
                "total_price": {"type": "number"}
            }
        }
    }
    extractor = InvoiceExtractor(
        llm_provider="openai",  # or "ollama" for local
        model_name="gpt-4.1-nano-2025-04-14",
        api_key=settings.openai_api_key
    )
    try:
        result = extractor.extract_from_document(
            document_path="sample_receipt.jpg",
            schema=sample_schema,
            extraction_instructions="Focus on accuracy for financial amounts and dates."
        )
        
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Extraction failed: {e}")
        
"""