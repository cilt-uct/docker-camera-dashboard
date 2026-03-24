import logging
import redis.asyncio as redis

from utils.settings import FetchSettings, logger

settings = FetchSettings()
settings.TITLE = "Display Camera Images Service"

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True
)

# Bridge uvicorn error logs for parse issues into our main logger with more context
class UvicornParseErrorHandler(logging.Handler):
    """Re-logs uvicorn parse errors (e.g., invalid HTTP requests) with extra context."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            if "Invalid HTTP request received" in msg:
                client = getattr(record, 'client_addr', None) or getattr(record, 'addr', None)
                if client:
                    logger.warning(f"[HTTP PARSE ERROR] {msg} client={client}", exc_info=record.exc_info)
                else:
                    logger.warning(f"[HTTP PARSE ERROR] {msg}", exc_info=record.exc_info)
        except Exception:
            # Never let logging failures crash the app
            pass

def _attach_uvicorn_parse_handler():
    try:
        uv_err = logging.getLogger("uvicorn.error")
        uv_err.setLevel(logging.DEBUG)
        uv_err.addHandler(UvicornParseErrorHandler())
    except Exception:
        pass

# Attach the handler early so uvicorn warnings are forwarded to our logger
_attach_uvicorn_parse_handler()
