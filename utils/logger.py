import sys
import os
from loguru import logger

# Create logs directory if it doesn't exist
# Go up one level from utils to project root
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Remove default handler
logger.remove()

# Add console handler
# Format: Time | Level | Module:Function:Line - Message
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# Add file handler
logger.add(
    os.path.join(log_dir, "app.log"),
    rotation="8 MB",
    retention="10 days",
    level="DEBUG",
    encoding="utf-8",
    compression="zip"
)

# Export logger
__all__ = ["logger"]
