import logging

logger = logging.getLogger(__name__)
logging.basicConfig(filename='myapp.log', level=logging.INFO,encoding='utf-8', format='%(asctime)s - %(levelname)s - %(message)s')
logger.info('Finished')


def log(msg):
    logger.info(msg)