from datetime import datetime, timedelta, timezone
import json
import logging
from pprint import pformat

from instagrapi import Client
from mega import Mega

from gist_api import Gist
from instagram_dl_to_mega_instagrapi.load_creds import load_instagram_creds


logger = logging.getLogger(__name__)

DEVICE_SETTINGS = {

    # this is the default from instagrapi.Client.set_device:
    # 'app_version': '203.0.0.29.118',
    # 'android_version': 26,
    # 'android_release': '8.0.0',
    # 'dpi': '480dpi',
    # 'resolution': '1080x1920',
    # 'manufacturer': 'Xiaomi',
    # 'model': 'MI 5s',
    # 'device': 'capricorn',
    # 'cpu': 'qcom',
    # 'version_code': '314665256',

    # we're overriding it with a custom one because the default is fairly old
    # (and probably widely used, so blockable by Instagram)

    # https://www.myfakeinfo.com/mobile/get-android-device-information.php allows
    # generating device info, but it's usually even older, so not much help

    # https://developers.whatismybrowser.com/useragents/explore/software_name/instagram
    # lists lots of device settings, pick a recent Android one

    # Instagram 243.0.0.16.111 Android (31/12; 480dpi; 1080x2176; samsung; SM-G991U; o1q; qcom; en_US; 382290498)
    'app_version': '243.0.0.16.111',
    'android_version': 31,
    'android_release': '12',
    'dpi': '480dpi',
    'resolution': '1080x2176',
    'manufacturer': 'samsung',
    'model': 'SM-G991U',
    'device': 'o1q',
    'cpu': 'qcom',
    'version_code': '382290498'

    # check the release date of the Instagram version on
    # https://instagram.en.uptodown.com/android/versions

    # (https://user-agents.net/applications/instagram-app might also be useful,
    # but it keeps timing out)

}


class LoginNotAllowedError(RuntimeError):
    def __init__(self, timestamp_limit: 'datetime|int', reason_str: str):
        self.permanently = True
        if timestamp_limit != -1:
            self.permanently = False
            self.ts_until = timestamp_limit.strftime('%Y-%m-%d %H:%M:%S %Z')
            self.duration = str(timestamp_limit - datetime.now(timezone.utc))
        self.reason_str = reason_str

    def __str__(self):
        explain_str = 'Logging in is '
        if self.permanently:
            explain_str += 'permanently prohibited.'
        else:
            explain_str += f'prohibited until {self.ts_until} (in {self.duration}).'
        return explain_str + f' Reason: {self.reason_str}'


class LoginManager():
    no_logins_before: 'int|float' = None
    reason_str: str = None
    _was_loaded_this_session = False

    @classmethod
    def prevent_logins_until_timestamp(cls, timestamp: 'int|float', reason: str = ''):
        cls.no_logins_before = timestamp
        cls.reason_str = reason

    @classmethod
    def prevent_logins_for_duration(cls, duration: timedelta, reason: str = ''):
        if duration == timedelta.max:
            timestamp = -1
        else:
            timestamp = (datetime.now(timezone.utc) + duration).timestamp()
        cls.prevent_logins_until_timestamp(timestamp, reason)

    @classmethod
    def check_if_login_is_allowed(cls):
        if cls.no_logins_before is None:
            return
        if cls.no_logins_before == -1:
            raise LoginNotAllowedError(-1, cls.reason_str)
        if cls.no_logins_before > datetime.now(timezone.utc).timestamp():
            raise LoginNotAllowedError(
                datetime.fromtimestamp(cls.no_logins_before, tz=timezone.utc),
                cls.reason_str
            )

    @classmethod
    def _to_json(cls):
        return {
            'ts': cls.no_logins_before,
            'reason': cls.reason_str
        }

    @classmethod
    def _from_json(cls, json_dict: dict):
        cls.no_logins_before = json_dict.get('ts')
        cls.reason_str = json_dict.get('reason')

    @classmethod
    def load(cls):
        gist_text = Gist('LOGINMGR').read()
        try:
            gist_text_as_dict = json.loads(gist_text)
        except json.JSONDecodeError as e:
            logger.exception(e)
            raise e
        else:
            cls._was_loaded_this_session = True
            cls._from_json(gist_text_as_dict)

    @classmethod
    def dump(cls):
        """Write the object to Gist, but only if it was loaded before."""
        if cls._was_loaded_this_session:
            logger.info(Gist('LOGINMGR').write(json.dumps(cls._to_json())))


def _after_new_login(client: Client, new_settings_file, mega: Mega, delete_old_settingsfile=None):
    client.dump_settings(new_settings_file)
    logger.info(f'Saved locally: {new_settings_file}')
    mega.upload(new_settings_file)
    logger.info(f'Uploaded to MEGA: {new_settings_file}')
    if delete_old_settingsfile is not None:
        mega.delete(delete_old_settingsfile)
        logger.info(f'Deleted old settings file on MEGA.')


def login_to_instagram(client: Client, mega: Mega):
    LoginManager.check_if_login_is_allowed()
    username, password = load_instagram_creds()
    settings_file_name = 'cached_instagrapi-dl-to-mega_settings.json'
    settings_file = mega.find(settings_file_name, exclude_deleted=True)
    if settings_file is None:
        # settings file does not exist
        logger.info(f'Unable to find file: {settings_file_name}')
        client.set_device(DEVICE_SETTINGS)
        client.login(username, password)
        _after_new_login(client, settings_file_name, mega)
    else:
        # settings file does exist, download and read it
        mega.download(settings_file)
        logger.info(f'Downloaded from MEGA: {settings_file_name}')
        client.load_settings(settings_file_name)
        logger.info(f'Reusing settings: {settings_file_name}')
        client.login(username, password)

    logger.info(f'Logged in as user ID {client.user_id}.')
