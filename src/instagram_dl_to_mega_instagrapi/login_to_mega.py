from mega import Mega

from instagram_dl_to_mega_instagrapi.load_creds import load_mega_creds


def login_to_mega():
    mega = Mega()
    mega.login(*load_mega_creds())
    return mega


def storage_threshold_exceeded(mega: Mega, threshold: float):
    storage_space = mega.get_storage_space()
    if storage_space['used'] / storage_space['total'] > threshold:
        return (
            f'There is less than {1 - threshold:.1%} storage space '
            'remaining on MEGA. Aborted.'
        )
    return ''
