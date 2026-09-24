import logging
import sys

from loguru import logger



class InterceptHandler(logging.Handler):
    """Intercept standard logging messages and route them to Loguru."""

    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging():
    """Configures structured JSON logging via Loguru."""
    # Remove all existing standard logging handlers
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(logging.INFO)

    for name in logging.root.manager.loggerDict.keys():
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    # Configure Loguru to output JSON (structured logging)
    logger.remove()
    logger.add(
        sys.stdout,
        serialize=True,
        level="INFO",
        backtrace=True,
        diagnose=False,
    )
