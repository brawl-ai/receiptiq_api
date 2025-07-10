import os
import json
import pprint
from typing import Dict, List, Optional, Any, Tuple
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
                            extraction_instructions: Optional[str] = None) -> Tuple[Dict[str, Any],List]:
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
        extracted_data = self.llm_extract_data(text, coordinates, schema, extraction_instructions)
        metadata = {
            'source_file': document_path,
            'extraction_method': f"{self.llm_provider}:{self.model_name}",
            'text_length': len(text),
            'coordinates_available': len(coordinates) > 0,
            'coordinates': coordinates
        }
        return extracted_data, metadata
    
    def extract_text_from_document(self, document_path: str) -> tuple[str, List]:
        """Extract text from PDF or image document"""
        file_ext = Path(document_path).suffix.lower()
        if file_ext == '.pdf':
            return self.extract_from_pdf(document_path)
        elif file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            return self.extract_from_image(document_path)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}. Supported: PDF, JPG, PNG, TIFF, BMP")
    
    def extract_from_pdf(self, pdf_path: str) -> tuple[str, List]:
        """Extract text from PDF with coordinate information"""
        text, char_coodinates, word_coordinates = "",{}, []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text += f"--- Page {page_num + 1} ---\n{page_text}\n"
                    try:
                        for char in page.chars:
                            y_pos = int(char['top'])
                            if y_pos not in char_coodinates:
                                char_coodinates[y_pos] = []
                            char_coodinates[y_pos].append({
                                'text': char['text'],
                                'x': char['x0'],
                                'y': char['top'],
                                'height': char["height"],
                                'page': page_num
                            })
                    except Exception as e:
                        self.logger.warning(f"Could not extract coordinates: {e}")
            char_coodinates = {k:v for k,v in char_coodinates.items() if len(v)>1}
            for y, line in char_coodinates.items():
                current_word = ""
                start_x = line[0]["x"]
                for (id,char) in enumerate(line):
                    if not char["text"].strip():
                        end_x = int(char["x"])
                        width = end_x-start_x
                        word_coordinates.append({
                            "text": current_word,
                            'x': start_x,
                            'y': y,
                            'width': width,
                            'height': char["height"],
                            'confidence': 100
                        })
                        current_word = ""
                        start_x = line[id+1]["x"] if id < (len(line)-1) else 0
                    else:
                        current_word += char["text"]
                else:
                    end_x = int(char["x"])
                    width = end_x-start_x
                    word_coordinates.append({
                        'text': current_word,
                        'x': start_x,
                        'y': y,
                        'width': width,
                        'height': char['height'],
                        'confidence': 100
                    })
        except Exception as e:
            self.logger.warning(f"pdfplumber failed, trying PyPDF: {e}")
            try:
                with open(pdf_path, 'rb') as file:
                    pdf_reader = pypdf.PdfReader(file)
                    for page_num, page in enumerate(pdf_reader.pages):
                        text += f"--- Page {page_num + 1} ---\n{page.extract_text()}\n"
            except Exception as e2:
                raise Exception(f"Failed to extract text from PDF: {e2}")
        
        return text, word_coordinates
    
    def extract_from_image(self, image_path: str) -> tuple[str, List]:
        """Extract text from image using OCR"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Could not load image: {image_path}")
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            denoised = cv2.fastNlMeansDenoising(gray)
            _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)            
            data = pytesseract.image_to_data(thresh, output_type=pytesseract.Output.DICT)
            text_parts,coordinates = [],[]
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > 30:  # Only include confident text
                    text_part = data['text'][i].strip()
                    if text_part:
                        text_parts.append(text_part)
                        coordinates.append({
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
                        coordinates: List, 
                        schema: Dict[str, Any],
                        instructions: Optional[str] = None) -> Dict[str, Any]:
        """Use LLM to extract structured data from text based on schema"""
        
        # Build the prompt
        prompt = self.build_extraction_prompt(text, coordinates, schema, instructions)
        
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
                               coordinates: List, 
                               schema: Dict[str, Any],
                               instructions: Optional[str] = None) -> str:
        """Build prompt for LLM extraction"""
        
        data_schema = self.describe_schema(schema)
        print(f"JSON SCHEMA: {data_schema}")
        base_instructions = f"""
        You are an expert at extracting structured data from invoice documents.
        Extract the requested information accurately and return it as valid JSON.
        If a field cannot be found, use null or an appropriate default value.
        Be precise with numbers and dates. 
        Use the TEXT COORDINATES to estimate the coordinates of the values. The text part contains the character or group of characters. The x shows the x coordinate and y the line. The height is the height of the characters. The width can be computed from looking at the full value.  The coordinates of the value can be calculated from checking the start and end chunks
        {instructions}
        """
        prompt = f"""
{base_instructions}

DOCUMENT TEXT:
{text}

TEXT COORDINATES:
{coordinates}

REQUIRED SCHEMA:
{data_schema}

Extract the data that matches the schema from the document text above.
Return ONLY valid JSON that matches the schema structure.
Do not include any explanations or additional text.

JSON Response:
"""
        
        return prompt
    
    def describe_schema(self, schema: Dict[str, Any]) -> str:
        """Convert schema dictionary to description for LLM"""
        coordinates_schema = '{ "x": x coodinate of the first letter,"y": y coodinate of the line, "width": width of the whole segment,"height": height of the whole line }'
        description = "{\n"
        for key, value in schema.items():
            if 'type' in value: # is this the leaf
                field_type = value['type']
                field_desc = value.get('description', '')
                description += f'  "{key}": {{\n "value": {field_type} // {field_desc}, "coordinates": {coordinates_schema}  }},\n'
            else: # Nested object
                description += f'  "{key}": '
                description += self.describe_schema(value)
        
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

