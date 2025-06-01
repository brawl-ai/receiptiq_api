# ReceiptIQ API

ReceiptIQ API is a FastAPI-based service that provides intelligent receipt processing using OCR (Optical Character Recognition) and AI-powered data interpretation. The service extracts text from receipts using Tesseract OCR and then uses AI to intelligently structure and interpret the data according to predefined schemas.

## Features

- OCR text extraction from receipt images using Tesseract
- AI-powered intelligent data interpretation and structuring
- Automatic field detection and mapping
- Project management for organizing receipt processing
- Custom field definitions for data extraction
- MongoDB integration for data storage
- Docker support for easy deployment

## Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- MongoDB (included in Docker setup)
- OpenAI API key (for AI interpretation)

## Development Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd receiptiq_api
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

4. Start the development environment using Docker Compose:
```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`

## API Documentation

Once the server is running, you can access:
- Interactive API documentation: `http://localhost:8000/docs`
- Alternative API documentation: `http://localhost:8000/redoc`

## Project Structure

```
receiptiq_api/
├── app/
│   ├── models/         # MongoDB models
│   ├── extractor.py    # OCR text extraction
│   ├── interpreter.py  # AI-powered data interpretation
│   └── main.py         # FastAPI application
├── uploads/           # Temporary storage for uploaded images
├── Dockerfile         # Container configuration
├── docker-compose.yml # Service orchestration
└── requirements.txt   # Python dependencies
```

## Environment Variables

The following environment variables can be configured:

- `MONGODB_URL`: MongoDB connection URL (default: mongodb://mongodb:27017)
- `MONGODB_DB`: Database name (default: receiptiq)
- `OPENAI_API_KEY`: Your OpenAI API key for AI interpretation

## How It Works

1. **Image Upload**: Receipt images are uploaded to the service
2. **OCR Processing**: Tesseract OCR extracts raw text from the image
3. **AI Interpretation**: The extracted text is processed by AI to:
   - Identify relevant fields (date, total, items, etc.)
   - Map data to the project's schema
   - Handle variations in receipt formats
   - Extract structured data
4. **Data Storage**: The interpreted data is stored in MongoDB
5. **API Access**: Structured data is available through the API

## API Endpoints

### Projects
- `POST /projects/`: Create a new project
- `GET /projects/`: List all projects
- `GET /projects/{project_id}`: Get project details

### Fields
- `POST /projects/{project_id}/fields/`: Define a new field
- `GET /projects/{project_id}/fields/`: List all fields in a project

### Receipts
- `POST /projects/{project_id}/receipts/`: Upload and process a receipt
- `GET /projects/{project_id}/receipts/`: List all processed receipts
- `GET /projects/{project_id}/receipts/{receipt_id}`: Get receipt details

## Development Workflow

1. Make changes to the code
2. The server will automatically reload due to the `--reload` flag
3. Test your changes using the API documentation interface

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
