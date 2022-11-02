from datetime import timedelta as td

from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword, ReloginAttemptExceeded, ChallengeRequired,
    SelectContactPointRecoveryForm, RecaptchaChallengeForm,
    FeedbackRequired, PleaseWaitFewMinutes, LoginRequired
)

from instagram_dl_to_mega_instagrapi.login_to_instagram import LoginManager


def handle_exception(client: Client, exc):
    if isinstance(exc, BadPassword):
        client.logger.exception(exc)
        if client.relogin_attempt > 0:
            LoginManager.prevent_logins_for_duration(td(days=7), str(exc))
            raise ReloginAttemptExceeded(exc)
        # client.settings = client.rebuild_client_settings()
        return client.set_settings(client.get_settings())

    elif isinstance(exc, LoginRequired):
        client.logger.exception(exc)
        client.relogin()
        return client.set_settings(client.get_settings())

    elif isinstance(exc, ChallengeRequired):
        try:
            client.challenge_resolve(client.last_json)
        except ChallengeRequired as exc:
            LoginManager.prevent_logins_for_duration(td(days=2), 'Manual Challenge Required')
            raise exc
        except (ChallengeRequired, SelectContactPointRecoveryForm, RecaptchaChallengeForm) as exc:
            LoginManager.prevent_logins_for_duration(td(days=4), str(exc))
            raise exc
        client.set_settings(client.get_settings())
        return True

    elif isinstance(exc, FeedbackRequired):
        message = client.last_json["feedback_message"]
        if "This action was blocked. Please try again later" in message:
            LoginManager.prevent_logins_for_duration(td(hours=12), message)
            # client.settings = client.rebuild_client_settings()
            # return client.set_settings(client.get_settings())
        elif "We restrict certain activity to protect our community" in message:
            # 6 hours is not enough
            LoginManager.prevent_logins_for_duration(td(hours=12), message)
        elif "Your account has been temporarily blocked" in message:
            """
            Based on previous use of this feature, your account has been temporarily
            blocked from taking this action.
            This block will expire on 2020-03-27.
            """
            LoginManager.prevent_logins_for_duration(td.max, message)

    elif isinstance(exc, PleaseWaitFewMinutes):
        LoginManager.prevent_logins_for_duration(td(hours=1), str(exc))

    raise exc
