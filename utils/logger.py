import logging
import sys

logging.basicConfig(stream=sys.stdout,
        level=logging.INFO,
        format='%(asctime)s %(process)d %(levelname)-8s %(filename)s(%(lineno)d) %(message)s')

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger()
