import logging

from rich.logging import RichHandler

logging.basicConfig(
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
