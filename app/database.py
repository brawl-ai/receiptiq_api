from mongoengine import connect, disconnect
from app.config import settings
import logging

logger = logging.getLogger(__name__)

def connect_to_mongodb():
    """
    Connect to MongoDB using the settings from config
    """
    try:
        uri = f"mongodb://{settings.MONGODB_USERNAME}:{settings.MONGODB_PASSWORD}@mongodb:27017/{settings.MONGODB_DB}?authSource={settings.MONGODB_AUTH_SOURCE}"
        connection = connect(
            db=settings.MONGODB_DB,
            host=uri,
            uuidRepresentation="standard"
        )
        logger.info(f"connected {connection} to db: {uri}")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        raise

def close_mongodb_connection():
    """
    Close the MongoDB connection
    """
    try:
        disconnect()
        logger.info("Successfully disconnected from MongoDB")
    except Exception as e:
        logger.error(f"Failed to disconnect from MongoDB: {str(e)}")
        raise