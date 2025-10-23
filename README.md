# ReceiptIQ API

ReceiptIQ API is a FastAPI-based service that provides intelligent receipt processing using AI-powered data extraction and interpretation. The service processes receipt images and PDFs using OCR (Optical Character Recognition) and then uses AI to intelligently structure and interpret the data according to user-defined schemas.

## Features

- **AI-Powered Data Extraction**: Uses OpenAI GPT models to intelligently extract structured data from receipts
- **Multi-Format Support**: Processes images (JPEG, PNG, GIF) and PDF documents
- **Custom Schema Definition**: Users can define custom fields and data structures for extraction
- **Project Management**: Organize receipts into projects with custom field schemas
- **Subscription Management**: Built-in subscription system with Paystack integration
- **User Authentication**: JWT-based authentication with role-based permissions
- **Data Export**: Export extracted data as JSON or CSV
- **File Storage**: AWS S3 integration for secure file storage
- **PostgreSQL Database**: Robust data storage with SQLAlchemy ORM
- **Docker Support**: Easy deployment with Docker Compose

## Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)
- PostgreSQL (included in Docker setup)
- OpenAI API key (for AI interpretation)
- AWS S3 credentials (for file storage)
- Paystack API key (for subscription payments)
- Resend API key (for email notifications)

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
# Edit .env and add your API keys and configuration
```

4. Start the development environment using Docker Compose:

```bash
docker compose up --build
```

The API will be available at `http://localhost:9000`

## API Documentation

Once the server is running, you can access:

- Interactive API documentation: `http://localhost:9000/docs`
- Alternative API documentation: `http://localhost:9000/redoc`

## Project Structure

```
receiptiq_api/
├── api/                 # API route handlers
│   ├── auth.py         # Authentication endpoints
│   ├── projects.py     # Project management
│   ├── fields.py       # Schema field definitions
│   ├── receipts.py     # Receipt upload and processing
│   ├── data.py         # Data export and management
│   └── subscriptions.py # Subscription management
├── models/             # SQLAlchemy database models
├── schemas/            # Pydantic data validation schemas
├── utils/              # Utility functions and services
│   ├── extractor.py    # AI-powered data extraction
│   ├── storage.py      # File storage service
│   └── rate_limiter.py # Rate limiting
├── migrations/         # Database migrations
├── tests/              # Test suite
├── Dockerfile          # Container configuration
├── compose.yml         # Service orchestration
└── requirements.txt    # Python dependencies
```

## Environment Variables

The following environment variables can be configured:

- `POSTGRES_USER`: PostgreSQL username
- `POSTGRES_PASSWORD`: PostgreSQL password
- `POSTGRES_DB`: Database name
- `POSTGRES_HOST`: Database host
- `POSTGRES_PORT`: Database port
- `SECRET_KEY`: JWT secret key
- `OPENAI_API_KEY`: Your OpenAI API key for AI interpretation
- `AWS_ACCESS_KEY_ID`: AWS S3 access key
- `AWS_SECRET_ACCESS_KEY`: AWS S3 secret key
- `AWS_REGION`: AWS region
- `BUCKET_NAME`: S3 bucket name
- `PAYSTACK_SECRET_KEY`: Paystack payment gateway key
- `RESEND_API_KEY`: Email service API key

## How It Works

1. **User Registration**: Users sign up and verify their email with OTP
2. **Project Creation**: Users create projects and define custom field schemas
3. **Receipt Upload**: Receipt images/PDFs are uploaded to projects
4. **AI Processing**: The system uses OCR and AI to extract data:
   - OCR extracts text from images using Tesseract
   - PDF processing extracts text and coordinates
   - AI (OpenAI GPT) interprets and structures data according to schema
5. **Data Storage**: Extracted data is stored in PostgreSQL with coordinates
6. **Data Access**: Structured data is available through API endpoints
7. **Export**: Data can be exported as JSON or CSV

## API Endpoints

### Authentication

- `POST /api/v1/auth/signup`: Register new user
- `POST /api/v1/auth/otp/get`: Request OTP verification
- `POST /api/v1/auth/otp/check`: Verify OTP and get access token
- `POST /api/v1/auth/token`: Login with email/password
- `POST /api/v1/auth/token/refresh`: Refresh access token
- `POST /api/v1/auth/logout`: Logout and revoke tokens

### Projects

- `POST /api/v1/projects`: Create a new project
- `GET /api/v1/projects`: List all projects
- `GET /api/v1/projects/{project_id}`: Get project details
- `PUT /api/v1/projects/{project_id}`: Update project
- `DELETE /api/v1/projects/{project_id}`: Delete project
- `POST /api/v1/projects/{project_id}/process`: Process all pending receipts

### Fields (Schema Definition)

- `POST /api/v1/projects/{project_id}/fields`: Define a new field
- `GET /api/v1/projects/{project_id}/fields`: List all fields in a project
- `PUT /api/v1/projects/{project_id}/fields/{field_id}`: Update field
- `DELETE /api/v1/projects/{project_id}/fields/{field_id}`: Delete field
- `POST /api/v1/projects/{project_id}/fields/{field_id}/add_child`: Add child field

### Receipts

- `POST /api/v1/projects/{project_id}/receipts`: Upload and process a receipt
- `GET /api/v1/projects/{project_id}/receipts`: List all processed receipts
- `GET /api/v1/projects/{project_id}/receipts/{receipt_id}`: Get receipt details
- `PUT /api/v1/projects/{project_id}/receipts/{receipt_id}`: Update receipt status

### Data

- `GET /api/v1/projects/{project_id}/data`: Get extracted data as JSON
- `GET /api/v1/projects/{project_id}/data/csv`: Export data as CSV
- `PUT /api/v1/projects/{project_id}/data/{data_value_id}`: Update data value

### Subscriptions

- `GET /api/v1/subscriptions/plans`: List subscription plans
- `POST /api/v1/subscriptions/payments/start`: Start payment process
- `POST /api/v1/subscriptions/payments/webhook`: Paystack webhook handler

## Field Types

The system supports various field types for schema definition:

- `string`: Text values
- `number`: Numeric values
- `boolean`: True/false values
- `date`: Date values
- `object`: Nested object structures
- `array`: Array of values

## Development Workflow

1. Make changes to the code
2. The server will automatically reload due to the `--reload` flag
3. Test your changes using the API documentation interface
4. Run tests: `pytest`
5. Check code coverage: `pytest --cov`

## Testing

The project includes comprehensive tests:

- Unit tests for models and utilities
- Integration tests for API endpoints
- Database tests with PostgreSQL
- S3 storage mocking with moto

Run tests with:

```bash
pytest
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[Add your license information here]
