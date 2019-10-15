# coding=utf-8
"""Mastodon source class.

Mastodon is an ActivityPub implementation, but it also has a REST + OAuth 2 API
independent of AP. API docs: https://docs.joinmastodon.org/api/
"""
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()

import logging
import urllib.parse

from oauth_dropins.webutil import util
from oauth_dropins.webutil.util import json_dumps, json_loads

from . import appengine_config
from . import source

API_ACCOUNT_STATUSES = '/api/v1/accounts/%s/statuses'
API_CONTEXT = '/api/v1/statuses/%s/context'
API_FAVORITE = '/api/v1/statuses/%s/favourite'
API_MEDIA = '/api/v1/media'
API_REBLOG = '/api/v1/statuses/%s/reblog'
API_STATUSES = '/api/v1/statuses'
API_VERIFY_CREDENTIALS = '/api/v1/accounts/verify_credentials'

# https://docs.joinmastodon.org/api/rest/media/#parameters
MAX_ALT_LENGTH = 420

# maps Mastodon media attachment type to AS1 objectType
# https://docs.joinmastodon.org/api/entities/#type
MEDIA_TYPES = {
  'image': 'image',
  'video': 'video',
  'gifv': 'video',
  'unknown': None,
}


class Mastodon(source.Source):
  """Mastodon source class. See file docstring and Source class for details.

  Attributes:
    instance: string, base URL of Mastodon instance, eg https://mastodon.social/
    user_id: integer, optional, current user's id (not username!) on this instance
    access_token: string, optional, OAuth access token
  """
  DOMAIN = 'N/A'
  BASE_URL = 'N/A'
  NAME = 'Mastodon'

  # https://docs.joinmastodon.org/usage/basics/#text
  TRUNCATE_TEXT_LENGTH = 500
  TRUNCATE_URL_LENGTH = 23

  def __init__(self, instance, access_token, user_id=None):
    """Constructor.

    If user_id is not provided, it will be fetched via the API.

    Args:
      instance: string, base URL of Mastodon instance, eg https://mastodon.social/
      user_id: string or integer, optional, current user's id (not username!) on
        this instance
      access_token: string, optional OAuth access token
    """
    assert instance
    self.instance = self.BASE_URL = instance
    assert access_token
    self.access_token = access_token
    self.DOMAIN = util.domain_from_link(instance)

    if user_id:
      self.user_id = user_id
    else:
      creds = self._get(API_VERIFY_CREDENTIALS)
      self.user_id = creds['id']

  def user_url(self, username):
    return urllib.parse.urljoin(self.instance, '@' + username)

  def _get(self, *args, **kwargs):
    return self._api(util.requests_get, *args, **kwargs)

  def _post(self, *args, **kwargs):
    return self._api(util.requests_post, *args, **kwargs)

  def _api(self, fn, path, *args, **kwargs):
    headers = kwargs.setdefault('headers', {})
    headers['Authorization'] = 'Bearer ' + self.access_token

    url = urllib.parse.urljoin(self.instance, path)
    resp = fn(url, *args, **kwargs)
    try:
      resp.raise_for_status()
    except BaseException as e:
      util.interpret_http_exception(e)
      raise

    return json_loads(resp.text)

  def get_activities_response(self, user_id=None, group_id=None, app_id=None,
                              activity_id=None, fetch_replies=False,
                              fetch_likes=False, fetch_shares=False,
                              fetch_events=False, fetch_mentions=False,
                              search_query=None, **kwargs):
    """Fetches toots and converts them to ActivityStreams activities.

    See :meth:`Source.get_activities_response` for details.
    """
    if (fetch_shares or fetch_events or fetch_mentions or search_query or
        group_id or user_id or activity_id):
      raise NotImplementedError()

    statuses = self._get(API_ACCOUNT_STATUSES % self.user_id)
    activities = []

    for status in statuses:
      activity = self.status_to_activity(status)
      activities.append(activity)

      id = status.get('id')
      if id:
        if fetch_replies:
          context = self._get(API_CONTEXT % id)
          activity['object']['replies'] = {
            'items': [self.status_to_activity(reply)
                      for reply in context.get('descendants', [])]
          }

    return self.make_activities_base_response(util.trim_nulls(activities))

  def status_to_activity(self, status):
    """Converts a status to an activity.

    Args:
      status: dict, a decoded JSON status

    Returns:
      an ActivityStreams activity dict, ready to be JSON-encoded
    """
    obj = self.status_to_object(status)
    activity = {
      'verb': 'post',
      'published': obj.get('published'),
      'id': obj.get('id'),
      'url': obj.get('url'),
      'actor': obj.get('author'),
      'object': obj,
      'context': {'inReplyTo': obj.get('inReplyTo')},
      }

    reblogged = status.get('reblog')
    if reblogged:
      activity.update({
        'objectType': 'activity',
        'verb': 'share',
        'object': self.status_to_object(reblogged),
      })

    app = status.get('application')
    if app:
      activity['generator'] = {
        'displayName': app.get('name'),
        'url': app.get('url'),
      }

    return self.postprocess_activity(activity)

  def status_to_object(self, status):
    """Converts a status to an object.

    Args:
      status: dict, a decoded JSON status

    Returns:
      an ActivityStreams object dict, ready to be JSON-encoded
    """
    id = status.get('id')
    if not id:
      return {}

    obj = {
      'objectType': 'note',
      'id': self.tag_uri(id),
      'url': status.get('url'),
      'published': status.get('created_at'),
      'author': self.account_to_actor(status.get('account')),
      'attachments': [],
    }

    reblog = status.get('reblog')
    base_status = reblog if reblog else status
    content = util.WideUnicode(base_status.get('content') or '')

    # media! into attachments.
    for media in status.get('media_attachments', []):
      type = media.get('type')
      att = {
        'id': self.tag_uri(media.get('id')),
        'objectType': MEDIA_TYPES.get(type),
        'displayName': media.get('description'),
      }
      url = media.get('url')
      if type == 'image':
        att['image'] = {'url': url}
      elif type in ('gifv', 'video'):
        att.update({
          'stream': {'url': url},
          'image': {'url': media.get('preview_url')},
        })
      obj['attachments'].append(att)

    if obj['attachments']:
      first = obj['attachments'][0]
      if first['objectType'] == 'video':
        obj['stream'] = first['stream']
      else:
        obj['image'] = first['image']

    # tags
    obj['tags'] = [{
      'objectType': 'mention',
      'id': self.tag_uri(t.get('id')),
      'url': t.get('url'),
      'displayName': t.get('username'),
    } for t in status.get('mentions', [])] + [{
      'objectType': 'hashtag',
      'url': t.get('url'),
      'displayName': t.get('name'),
    } for t in status.get('tags', [])]

    # 'Boosted @username:' prefix for retweets
    if reblog and reblog.get('content'):
      reblog_account = reblog.get('account')
      content = 'Boosted <a href="%s">@%s</a>: ' % (
        (reblog_account.get('url'), reblog_account.get('username'))) + content

    obj.update({
      'tags': [t for t in obj['tags'] if t['objectType'] != 'image'] +
              [self.retweet_to_object(r) for r in status.get('retweets', [])],
      'content': content,
    })

    # inReplyTo
    reply_to_id = status.get('in_reply_to_id')
    if reply_to_id:
      obj['inReplyTo'] = [{
        'id': self.tag_uri(reply_to_id),
        # XXX TODO need to generate URL for in-reply-to status, but we don't
        # have its author's username, just their account id
        'url': urllib.parse.urljoin(self.instance, '/TODO/status/' + reply_to_id),
      }]

    # to (ie visibility)
    visibility = status.get('visibility')
    if visibility:
      obj['to'] = [{
        'objectType': 'group',
        'alias': '@' + visibility,
      }]

    return self.postprocess_object(obj)

  def account_to_actor(self, account):
    """Converts a Mastodon account to an AS1 actor.

    Args:
      actor: dict, Mastodon account

    Returns: dict, AS1 actor
    """
    username = account.get('username')
    if not username:
      return {}

    url = account.get('url')
    # mastodon's 'Web site' fields are HTML links, so extract their URLs
    web_sites = [util.parse_html(f.get('value')).find('a')['href']
                 for f in account.get('fields', [])
                 if f.get('name') == 'Web site']

    return util.trim_nulls({
      'objectType': 'person',
      'id': self.tag_uri(username),
      'numeric_id': account.get('id'),
      'username': username,
      'displayName': account.get('display_name') or username,
      'url': url,
      'urls': [{'value': u} for u in [url] + web_sites],
      'image': {'url': account.get('avatar')},
      'published': account.get('created_at'),
      'description': account.get('note'),
    })

  def create(self, obj, include_link=source.OMIT_LINK,
             ignore_formatting=False):
    """Creates a status (aka toot), reply, boost (aka reblog), or favorite.

    https://docs.joinmastodon.org/api/rest/statuses/

    Args:
      obj: ActivityStreams object
      include_link: string
      ignore_formatting: boolean

    Returns: CreationResult whose content will be a dict with 'id', 'url', and
      'type' keys (all optional) for the newly created object (or None)
    """
    return self._create(obj, preview=False, include_link=include_link,
                        ignore_formatting=ignore_formatting)

  def preview_create(self, obj, include_link=source.OMIT_LINK,
                     ignore_formatting=False):
    """Preview creating a status (aka toot), reply, boost (aka reblog), or favorite.

    https://docs.joinmastodon.org/api/rest/statuses/

    Args:
      obj: ActivityStreams object
      include_link: string
      ignore_formatting: boolean

    Returns: CreationResult whose content will be a unicode string HTML
      snippet (or None)
    """
    return self._create(obj, preview=True, include_link=include_link,
                        ignore_formatting=ignore_formatting)

  def _create(self, obj, preview=None, include_link=source.OMIT_LINK,
              ignore_formatting=False):
    """Creates or previews a status (aka toot), reply, boost (aka reblog), or favorite.

    https://docs.joinmastodon.org/api/rest/statuses/

    Based on :meth:`Twitter._create`.

    Args:
      obj: ActivityStreams object
      preview: boolean
      include_link: string
      ignore_formatting: boolean

    Returns: CreationResult. If preview is True, the content will be a unicode
      string HTML snippet. If False, it will be a dict with 'id' and 'url' keys
      for the newly created object.
    """
    assert preview in (False, True)
    type = obj.get('objectType')
    verb = obj.get('verb')

    base_obj = self.base_object(obj)
    base_id = base_obj.get('id')
    base_url = base_obj.get('url')

    is_reply = type == 'comment' or obj.get('inReplyTo')
    is_rsvp = (verb and verb.startswith('rsvp-')) or verb == 'invite'
    images = util.get_list(obj, 'image')
    videos = util.get_list(obj, 'stream')
    has_media = (images or videos) and (type in ('note', 'article') or is_reply)

    # prefer displayName over content for articles
    type = obj.get('objectType')
    prefer_content = type == 'note' or (base_url and is_reply)
    preview_description = ''
    content = self._content_for_create(
      obj, ignore_formatting=ignore_formatting, prefer_name=not prefer_content)
      # TODO: convert strip_first_video_tag=bool(videos) to strip_all_video_tags

    if not content:
      if type == 'activity' and not is_rsvp:
        content = verb
      elif has_media:
        content = ''
      else:
        return source.creation_result(
          abort=False,  # keep looking for things to publish,
          error_plain='No content text found.',
          error_html='No content text found.')

    if is_reply and not base_url:
      # TODO: support replies on federated (ie other) instances. details:
      #
      # https://mastodon.social/@jkreeftmeijer/101245063526942536
      # "Got it. This is how federation works.
      # You need the local ID for the status you’re replying to. https://mastodon.social/@jkreeftmeijer/101236371751163533 is posted on https://mastodon.social, but you need the ID from https://mastodon.technology/web/statuses/101236371815734043 when posting a reply on https://mastodon.technology, for example."
      #
      # https://mastodon.social/@jkreeftmeijer/101290086224931209
      # "To get the local ID for a Mastodon status on another instance, use the search API (https://docs.joinmastodon.org/api/rest/search/), or the search bar in your web client.
      # Searching for a status URL (like https://mastodon.social/@jkreeftmeijer/101236371751163533) returns the status on your instance, including the local ID."
      return source.creation_result(
        abort=True,
        error_plain='Could not find a toot on %s to reply to.' % self.DOMAIN,
        error_html='Could not find a toot on <a href="%s">%s</a> to <a href="http://indiewebcamp.com/reply">reply to</a>. Check that your post has the right <a href="http://indiewebcamp.com/comment">in-reply-to</a> link.' % (self.instance, self.DOMAIN))

    # truncate and ellipsize content if necessary
    content = self.truncate(content, obj.get('url'), include_link, type)

    # linkify defaults to Twitter's link shortening behavior
    preview_content = util.linkify(content, pretty=True, skip_bare_cc_tlds=True)
    # TODO
    # preview_content = MENTION_RE.sub(
    #   r'\1<a href="https://twitter.com/\2">@\2</a>', preview_content)
    # preview_content = HASHTAG_RE.sub(
    #   r'\1<a href="https://twitter.com/hashtag/\2">#\2</a>', preview_content)

    if type == 'activity' and verb == 'like':
      if not base_url:
        return source.creation_result(
          abort=True,
          error_plain='Could not find a toot on %s to favorite.' % self.DOMAIN,
          error_html='Could not find a toot on <a href="%s">%s</a> to <a href="http://indiewebcamp.com/favorite">favorite</a>. Check that your post has the right <a href="http://indiewebcamp.com/like">u-like-of link</a>.' % (self.instance, self.DOMAIN))

      if preview:
        preview_description += '<span class="verb">favorite</span> <a href="%s">this toot</a>.' % base_url
        return source.creation_result(description=preview_description)
      else:
        resp = self._post(API_FAVORITE % base_id)
        resp['type'] = 'like'

    elif type == 'activity' and verb == 'share':
      if not base_url:
        return source.creation_result(
          abort=True,
          error_plain='Could not find a toot to boost.',
          error_html='Could not find a toot on <a href="%s">%s</a> to <a href="http://indiewebcamp.com/repost">boost</a>. Check that your post has the right <a href="http://indiewebcamp.com/repost">repost-of</a> link.' % (self.instance, self.DOMAIN))

      if preview:
          preview_description += '<span class="verb">boost</span> <a href="%s">this toot</a>.' % base_url
          return source.creation_result(description=preview_description)
      else:
        resp = self._post(API_REBLOG % base_id)
        resp['type'] = 'repost'

    elif type in ('note', 'article') or is_reply or is_rsvp:  # a post
      data = {'status': content}

      if is_reply:
        preview_description += '<span class="verb">reply</span> to <a href="%s">this toot</a>:' % base_url
        data['in_reply_to_id'] = base_id
      else:
        preview_description += '<span class="verb">toot</span>:'

      if preview:
        video_urls = [util.get_url(vid) for vid in videos]
        media_previews = [
          '<video controls src="%s"><a href="%s">this video</a></video>' % (url, url)
          for url in video_urls
        ] + [
          '<img src="%s" alt="%s" />' % (util.get_url(img), img.get('displayName', ''))
           for img in images
        ]
        if media_previews:
          preview_content += '<br /><br />' + ' &nbsp; '.join(media_previews)
        return source.creation_result(content=preview_content,
                                      description=preview_description)

      else:
        ids = self.upload_media(images + videos)
        if ids:
          data['media_ids'] = ids
        resp = self._post(API_STATUSES, json=data)

    else:
      return source.creation_result(
        abort=False,
        error_plain='Cannot publish type=%s, verb=%s to Mastodon' % (type, verb),
        error_html='Cannot publish type=%s, verb=%s to Mastodon' % (type, verb))

    if 'url' not in resp:
      resp['url'] = base_url

    return source.creation_result(resp)

  def upload_media(self, media):
    """Uploads one or more images or videos from web URLs.

    https://docs.joinmastodon.org/api/rest/media/

    Args:
      media: sequence of AS image or stream objects, eg:
        [{'url': 'http://picture', 'displayName': 'a thing'}, ...]

    Returns: list of string media ids for uploaded files
    """
    ids = []
    for obj in media:
      url = util.get_url(obj)
      if not url:
        continue

      data = {}
      alt = obj.get('displayName')
      if alt:
        data['description'] = util.ellipsize(alt, chars=MAX_ALT_LENGTH)

      # TODO: mime type check?
      with util.requests_get(url, stream=True) as fetch:
        fetch.raise_for_status()
        upload = self._post(API_MEDIA, files={'file': fetch.raw})

      logging.info('Got: %s', upload)
      media_id = upload['id']
      ids.append(media_id)

    return ids