import logging

logger = logging.getLogger(__name__)
logging.basicConfig(filename='myapp.log', level=logging.INFO)
logger.info('Finished')


def log(msg):
    logger.info(msg)