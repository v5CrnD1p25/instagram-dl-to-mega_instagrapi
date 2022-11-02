import logging
import time

logger = logging.getLogger(__name__)
filehandler = None


class LoggingSetup():
    """Singleton class for logging setup.

    Call `LoggingSetup.setup()` first. Afterwards, the `LoggingSetup.logfilename`
    attribute holds the name of the file that is being logged to.
    """

    _filehandler = None
    logfilename = None
    timestring = None

    @classmethod
    @property
    def filehandler(cls):
        if cls._filehandler is None:
            # create handler
            cls.logfilename = f'instagrapi_dl_to_mega{cls.timestring}.log'
            cls._filehandler = logging.FileHandler(
                filename=cls.logfilename,
                encoding='utf-8'
            )
            cls._filehandler.setLevel(logging.DEBUG)
            # create formatter and attach it to handler
            formatter = logging.Formatter('[%(asctime)s] [%(name)s] %(message)s')
            formatter.converter = time.gmtime  # use UTC instead of local time
            cls._filehandler.setFormatter(formatter)
        return cls._filehandler

    @classmethod
    def setup(cls, put_timestamp_in_logfilename=True):
        """Setup logging to console and to a new logfile."""
        if put_timestamp_in_logfilename:
            cls.timestring = '_' + time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
        else:
            cls.timestring = ''
        logger.setLevel(logging.DEBUG)
        # attach filehandler
        logger.addHandler(cls.filehandler)
        # attach console handler
        streamhandler = logging.StreamHandler()
        streamhandler.setLevel(logging.DEBUG)
        logger.addHandler(streamhandler)


def activate_megapy_logging():
    """Activate the logger messages in mega.py, for debugging."""
    megalogger = logging.getLogger('mega')
    megalogger.setLevel(logging.DEBUG)
    # attach filehandler
    megalogger.addHandler(LoggingSetup.filehandler)
