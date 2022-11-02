import os
import json


def _load_common_creds(env_username: str, env_password: str, credsfile: str) -> tuple[str, str]:
    username = os.getenv(env_username)
    password = os.getenv(env_password)
    if None in (username, password):
        try:
            with open(credsfile) as f:
                username, password = tuple(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    return username, password


def load_mega_creds():
    return _load_common_creds('MEGA_EMAIL', 'MEGA_PASSWORD', 'creds_mega.json')


def load_instagram_creds():
    return _load_common_creds('INSTA_USERNAME', 'INSTA_PASSWORD', 'creds_insta.json')
