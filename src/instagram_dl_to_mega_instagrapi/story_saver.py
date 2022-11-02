from datetime import datetime, timezone
import json
import logging
import os
from pprint import pformat
import shutil
import tempfile
import time

from mega import Mega
import requests

from instagrapi import Client


CHUNK_SIZE = 4096 # size for chunk-downloading of images and videos

OSM_URL_FORMAT = 'https://www.openstreetmap.org/query?lat={lat}&lon={lon}#map=99/{lat}/{lon}'

ISO8601 = '%Y-%m-%dT%H-%M-%SZ'

logger = logging.getLogger(__name__)


class TemporaryLocalDownloadDir():
    """Prepare temporary download directory.

    The files will be downloaded to this local directory, in order to upload
    them to MEGA from there.
    """

    def __init__(self, userpk, username):
        child = (
            f'igstories_{userpk}_{username}__'
            f'{time.strftime(ISO8601, time.gmtime())}'
        )
        # e.g. /tmp/igstories_...
        self.dirname = os.path.join(tempfile.gettempdir(), child)

    def __enter__(self):
        try:
            os.mkdir(self.dirname)
        except FileExistsError:
            # directory already exists for whatever reason, no problem
            pass
        return self.dirname

    def __exit__(self, exc_type, exc_value, exc_traceback):
        shutil.rmtree(self.dirname)


class StorySaver():
    def __init__(self, api: Client, mega: Mega, userid):
        self.api = api
        self.mega = mega
        self.userid = userid
        userinfo = api.user_info(userid)
        self.username = userinfo.username
        self.userpk = userinfo.pk  # this should be identical to userid


    def _get_user_folder_on_mega(self):
        """Get the folder object for the user on MEGA.

        Set the attribute to the folder object. Create the folder beforehand
        if necessary.
        """

        self.user_folder_name = f"{self.userpk}_{self.username}"
        user_folder = self.mega.find(self.user_folder_name, exclude_deleted=True)
        if user_folder is None:
            # folder does not exist, so create it
            node_ids = self.mega.create_folder(self.user_folder_name)
            logger.info(f'Created new folder: {self.user_folder_name}')
            self.user_folder_on_mega = node_ids[self.user_folder_name]
        else:
            # folder exists
            self.user_folder_on_mega = user_folder[0]


    def save(self):
        """Upload all currently available stories to MEGA."""

        stories = self.api.user_stories(self.userid)
        self.story_items_count = len(stories)

        if self.story_items_count == 0:
            logger.info(f'{self.username} (pk {self.userpk}): Currently no story items.')
            return

        # self._get_user_folder_on_mega()
        with TemporaryLocalDownloadDir(self.userpk, self.username) as dirname:
            self.dldir = dirname
            for index, story_item in enumerate(stories):
                try:
                    logger.info(pformat(story_item))
                    # StoryItem(self, index, story_item).save()
                except Exception:
                    logger.exception(
                        f'Error while saving story item {index}/'
                        f'{self.story_items_count - 1} of {self.username} '
                        f'(pk {self.userpk})!',
                        exc_info=True
                    )
                    logger.info(f'Skipped this story item.')


        return

        try:
            user_reel_media: dict = self.api.user_reel_media(self.userid)
        except ClientError as e:
            logger.exception(
                f'ClientError {e.msg} while getting stories for user {self.userid} '
                f'(Code: {e.code}, Response: {e.error_response})',
                exc_info=True
            )
            logger.info(f'Skipped user {self.userid}.')
            return

        try:
            self.userinfo = user_reel_media.get('user', {})
            self.username = self.userinfo.get('username')
            # this should be identical to self.userid:
            self.userpk = self.userinfo.get('pk')
            self.story_items = user_reel_media.get('items', [])
            # this should be identical to len(self.story_items):
            self.story_items_count = user_reel_media.get('media_count')

            if user_reel_media.get('latest_reel_media') is None:
                logger.info(f'{self.username}: Currently no story items.')
                return

            self._get_user_folder_on_mega()
            with TemporaryLocalDownloadDir(self.userpk, self.username) as dirname:
                self.dldir = dirname
                for index, story_item in enumerate(self.story_items):
                    try:
                        StoryItem(self, index, story_item).save()
                    except Exception:
                        logger.exception(
                            f'Error while saving story item {index}/'
                            f'{self.story_items_count - 1} of {self.username}!',
                            exc_info=True
                        )
                        logger.info(f'Skipped this story item.')

        except Exception:
            logger.exception(f'Error during story saving of {self.username}!', exc_info=True)
            logger.info(f'Skipped {self.username}.')


def _get_best_image(media_info_dict: dict) -> dict:
    """Return the image candidate with the highest resolution from the `media_info`."""
    available_images = media_info_dict.get('image_versions2', {}).get('candidates', [])
    if available_images:
        images_by_resolution = sorted(available_images, key=lambda i: i['height'] * i['width'])
        return images_by_resolution[-1]
    return {}


def _get_best_video(media_info_dict: dict) -> dict:
    """Return the video with the highest resolution from the `media_info`."""
    available_videos = media_info_dict.get('video_versions', [])
    if available_videos:
        videos_by_resolution = sorted(available_videos, key=lambda i: i['height'] * i['width'])
        return videos_by_resolution[-1]
    return {}


class StoryItem():
    def __init__(self, saver: StorySaver, index: int, data_dict: dict):
        self.saver = saver
        self.index = index
        self.data = data_dict
        self._fill_data_attributes()
        filename_common = datetime.fromtimestamp(self.taken_at, tz=timezone.utc).strftime(ISO8601)
        self.filename_localdl = os.path.join(self.saver.dldir, filename_common)
        self.dirname_megaupload = self.saver.user_folder_on_mega
        self.filename_megaupload = filename_common
        self.was_last_upload_skipped = False


    def _fill_data_attributes(self):
        self.taken_at = self.data.get('taken_at')
        media_type = self.data.get('media_type')
        self.is_video = media_type == 2
        self.media_type_description = {
            1: 'photo',
            2: 'video',
        }.get(media_type, f'unknown-mediatype({media_type})')
        self.has_locations = 'story_locations' in self.data
        self.has_feed_media = 'story_feed_media' in self.data

    def save(self):
        """Upload the story item to MEGA."""
        self._best_image()
        self._best_video()

        json_data = self._prepare_json()

        self._upload_json_to_mega(json_data)
        self._print_upload_info('JSON')

        self._upload_binary_to_mega('.jpg', self.best_image.get('url'))
        self._print_upload_info('image')

        if self.is_video:
            self._upload_binary_to_mega('.mp4', self.best_video.get('url'))
            self._print_upload_info('video')


    def _print_upload_info(self, type: str):
        common_str = (
            f' {type} for story '
            f'{self.index}/{self.saver.story_items_count - 1} to MEGA'
        )
        if self.was_last_upload_skipped:
            logger.info(
                f'{self.saver.username}: Skipped uploading' +
                common_str + ' (already exists).'
            )
        else:
            logger.info(f'{self.saver.username}: Uploaded' + common_str + '.')


    def _best_image(self):
        self.best_image = _get_best_image(self.data)


    def _best_video(self):
        self.best_video = {}
        if self.is_video:
            self.best_video = _get_best_video(self.data)


    def _prepare_json(self):
        return {
            'id': self.data.get('pk'),
            'media_type': self.media_type_description,
            'taken_at': self.taken_at,
            'imported_taken_at': self.data.get('imported_taken_at'),
            'original_dimensions': {
                'width': self.data.get('original_width'),
                'height': self.data.get('original_height')
            },
            'image': {
                'url': self.best_image.get('url'),
                'width': self.best_image.get('width'),
                'height': self.best_image.get('height'),
            },
            'video': {
                'id': self.best_video.get('id'),
                'url': self.best_video.get('url'),
                'width': self.best_video.get('width'),
                'height': self.best_video.get('height'),
                'duration': self.data.get('video_duration'),
                'codec': self.data.get('video_codec'),
                'dash_manifest': self.data.get('video_dash_manifest'),
            } if self.is_video else None,
            'locations': (
                list(self._location_info_dicts())
            ) if self.has_locations else None,
            'feed_media': (
                list(self._feed_media_dicts())
            ) if self.has_feed_media else None
        }


    def _location_info_dicts(self):
        """Get a dict with all relevant location information for each location in the story."""
        for story_location in self.data.get('story_locations', []):
            location_id: str = story_location.get('location', {}).get('pk')
            location_data: dict = self.saver.api.location_info(location_id).get('location', {})
            location_url = OSM_URL_FORMAT.format(
                lat=location_data.get('lat'), lon=location_data.get('lng')
            )
            yield {
                'id': location_id,
                'name': location_data.get('name'),
                'city': location_data.get('city'),
                'address': location_data.get('address'),
                'coordinates': {
                    'lat': location_data.get('lat'),
                    'lon': location_data.get('lng')
                },
                'url': location_url
            }


    def _feed_media_dicts(self):
        """Get a dict with all relevant feed media information for each feed media in the story."""
        for feed_media in self.data.get('story_feed_media', []):
            media_id = feed_media.get('media_id')
            if media_id is None:
                continue
            media_info = self.saver.api.media_info(media_id).get('items', [])
            if len(media_info) == 0:
                continue
            media_info = media_info[0]
            feed_media_dict = {
                'media_id': media_id,
                'caption': (media_info.get('caption') or {}).get('text'), # caption might exist but be None
                'comment_count': media_info.get('comment_count'),
                'like_count': media_info.get('like_count'),
                'taken_at': media_info.get('taken_at'),
                'user': {
                    'user_id': media_info['user'].get('pk'),
                    'username': media_info['user'].get('username')
                } if 'user' in media_info and media_info['user'] is not None else None,
                'carousel_media': [],
                'noncarousel_media': {}
            }
            if 'carousel_media' not in media_info:
                best_image_candidate = _get_best_image(media_info)
                best_video = _get_best_video(media_info)
                feed_media_dict['noncarousel_media'] = {
                    'id': media_info.get('id'),
                    'image': {
                        'url': best_image_candidate.get('url'),
                        'width': best_image_candidate.get('width'),
                        'height': best_image_candidate.get('height')
                    },
                    'video': {
                        'id': best_video.get('id'),
                        'url': best_video.get('url'),
                        'width': best_video.get('width'),
                        'height': best_video.get('height'),
                        'duration': media_info.get('video_duration'),
                        'codec': media_info.get('video_codec'),
                        'dash_manifest': media_info.get('video_dash_manifest'),
                        'view_count': media_info.get('view_count'),
                    } if best_video else None
                }
            for carousel_media in media_info.get('carousel_media', []):
                best_image_candidate = _get_best_image(carousel_media)
                best_video = _get_best_video(carousel_media)
                feed_media_dict['carousel_media'].append(
                    {
                        'id': carousel_media.get('id'),
                        'image': {
                            'url': best_image_candidate.get('url'),
                            'width': best_image_candidate.get('width'),
                            'height': best_image_candidate.get('height')
                        },
                        'video': {
                            'id': best_video.get('id'),
                            'url': best_video.get('url'),
                            'width': best_video.get('width'),
                            'height': best_video.get('height'),
                            'duration': carousel_media.get('video_duration'),
                            'codec': carousel_media.get('video_codec'),
                            'dash_manifest': carousel_media.get('video_dash_manifest'),
                        } if best_video else None
                    }
                )
            yield feed_media_dict


    def _upload_json_to_mega(self, json_data: dict):
        """Upload the given dict to a JSON file on MEGA."""
        ext = '.json'
        f_local = self.filename_localdl + ext
        f_mega = self.filename_megaupload + ext
        # write to local filesystem first
        with open(f_local, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
        # then upload to MEGA
        self._safe_upload_to_mega(f_local, f_mega)


    def _upload_binary_to_mega(self, ext: str, source_url: str):
        """Upload the data from the given URL to MEGA."""
        f_local = self.filename_localdl + ext
        f_mega = self.filename_megaupload + ext
        # download data to local filesystem first
        request = requests.get(source_url, stream=True)
        request.raise_for_status()
        with open(f_local, 'wb') as f:
            for chunk in request.iter_content(chunk_size=CHUNK_SIZE):
                f.write(chunk)
        # then upload to MEGA
        self._safe_upload_to_mega(f_local, f_mega)


    def _safe_upload_to_mega(self, filename: str, dest_filename: str):
        """Upload the given file, but only if a file of that name doesn't exist yet."""
        # mega.find() must be called with 'folder/file.txt', but mega.upload()
        # must be called with dest='node_id_of_folder', dest_filename='file.txt'
        filename_to_find = '/'.join([self.saver.user_folder_name, dest_filename])
        if self.saver.mega.find(filename_to_find, exclude_deleted=True) is not None:
            # file already exists, skip it
            self.was_last_upload_skipped = True
        else:
            self.was_last_upload_skipped = False
            self.saver.mega.upload(
                filename, dest=self.saver.user_folder_on_mega,
                dest_filename=dest_filename
            )
