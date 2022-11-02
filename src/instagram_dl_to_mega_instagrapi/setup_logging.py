import logging

logger = logging.getLogger(__name__)


def setup_logging(debug_on_console: bool = False):
    rootLogger = logging.getLogger(__name__).parent
    rootLogger.setLevel(logging.DEBUG)

    # create a new handler to print to console
    print_to_console = logging.StreamHandler()
    print_to_console.setLevel(logging.DEBUG if debug_on_console else logging.INFO)

    # register handler to logger
    rootLogger.addHandler(print_to_console)

    # enable warnings from the mega.py library
    megalogger = logging.getLogger('mega')
    megalogger.setLevel(logging.WARNING)
    megalogger.addHandler(print_to_console)
