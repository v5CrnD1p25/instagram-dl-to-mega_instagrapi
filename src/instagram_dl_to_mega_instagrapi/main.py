import logging
import sys
import time

from gist_api import Gist
from instagrapi import Client
from mega import Mega

from instagram_dl_to_mega_instagrapi.handle_exceptions import handle_exception
from instagram_dl_to_mega_instagrapi.login_to_instagram import LoginManager, login_to_instagram
from instagram_dl_to_mega_instagrapi.login_to_mega import storage_threshold_exceeded, login_to_mega
from instagram_dl_to_mega_instagrapi.setup_logging import LoggingSetup
from instagram_dl_to_mega_instagrapi.story_saver import StorySaver

logger = logging.getLogger(__name__)


def main():
    LoggingSetup.setup()
    logger.info(f'Started main.py: {time.asctime(time.gmtime())}')
    LoggingSetup.activate_megapy_logging()

    mega = login_to_mega()
    storage_threshold_msg = storage_threshold_exceeded(mega, 0.95)
    if storage_threshold_msg:
        logger.critical(storage_threshold_msg)
        _cleanup_and_exit(mega, 1)

    LoginManager.load()
    try:
        cl = Client()
        login_to_instagram(cl, mega)
        cl.handle_exception = handle_exception
        for userid in _get_userids():
            StorySaver(cl, mega, userid).save()
    except Exception as exc:
        logger.exception(exc)
        logger.info('Canceled program due to error.')
        _cleanup_and_exit(mega, 1)
    _cleanup_and_exit(mega)


def _get_userids():
    """Return the user IDs from the command line arguments as a generator."""
    #   182168285     mattxiv
    #  1320014941     jamie.wlms
    #  1333668641     uonlad
    #  2211022868     jorellwilliams
    #  7690949314     galerie.arschgeweih
    # 20322442223     georgenotfound
    # 32730627860     aroundtheword
    # 41633318439     etvarqe_
    # 46693997484     codetekt
    for userid in sys.argv[1:]:
        if not userid.isdigit():
            logger.warning(f'Skipped invalid user ID "{userid}"!')
        else:
            yield userid


def _cleanup_and_exit(mega: Mega, exitcode: int = 0):
    LoginManager.dump()
    mega.logout_session()
    with open(LoggingSetup.logfilename, encoding='utf-8') as f:
        Gist('LOG').write(f.read())
    sys.exit(exitcode)
