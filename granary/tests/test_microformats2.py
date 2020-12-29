# coding=utf-8
"""Unit tests for microformats2.py.

Most of the tests are in testdata/. This is just a few things that are too small
for full testdata tests.
"""
import re

from oauth_dropins.webutil import testutil
import mf2py

from .. import microformats2


class Microformats2Test(testutil.TestCase):

  def test_post_type_discovery(self):
    for prop, verb in ('like-of', 'like'), ('repost-of', 'share'):
      obj = microformats2.json_to_object(
        {'type': ['h-entry'],
          'properties': {prop: ['http://foo/bar']}})
      self.assertEqual('activity', obj['objectType'])
      self.assertEqual(verb, obj['verb'])

  def test_verb_require_of_suffix(self):
    for prop in 'like', 'repost':
      obj = microformats2.json_to_object(
        {'type': ['h-entry'],
         'properties': {prop: ['http://foo/bar']}})
      self.assertNotIn('verb', obj)

  def test_ignore_h_as(self):
    """https://github.com/snarfed/bridgy/issues/635"""
    obj = microformats2.json_to_object({'type': ['h-entry']})
    self.assertEqual('note', obj['objectType'])

  def test_html_content_and_summary(self):
    for expected_content, expected_summary, value in (
        ('my html', 'my val', {'value': 'my val', 'html': 'my html'}),
        ('my html', None, {'html': 'my html'}),
        ('my val', 'my val', {'value': 'my val'}),
        ('my str', 'my str', 'my str'),
        (None, None, {})):
      obj = microformats2.json_to_object({'properties': {'content': [value],
                                                         'summary': [value]}})
      self.assertEqual(expected_content, obj.get('content'))
      self.assertEqual(expected_summary, obj.get('summary'))

  def test_photo_property_is_not_url(self):
    """handle the case where someone (incorrectly) marks up the caption
    with p-photo
    """
    mf2 = {'properties':
           {'photo': ['the caption', 'http://example.com/image.jpg']}}
    obj = microformats2.json_to_object(mf2)
    self.assertEqual([{'url': 'http://example.com/image.jpg'}], obj['image'])

  def test_photo_property_has_no_url(self):
    """handle the case where the photo property is *only* text, not a url"""
    mf2 = {'properties':
           {'photo': ['the caption', 'alternate text']}}
    obj = microformats2.json_to_object(mf2)
    self.assertFalse(obj.get('image'))

  def test_video_stream(self):
    """handle the case where someone (incorrectly) marks up the caption
    with p-photo
    """
    mf2 = {'properties':
           {'video': ['http://example.com/video.mp4']}}
    obj = microformats2.json_to_object(mf2)
    self.assertEqual([{'url': 'http://example.com/video.mp4'}], obj['stream'])

  def test_nested_compound_url_object(self):
    mf2 = {'properties': {
             'repost-of': [{
               'type': ['h-outer'],
               'properties': {
                 'url': [{
                   'type': ['h-inner'],
                   'properties': {'url': ['http://nested']},
                 }],
               },
             }],
           }}
    obj = microformats2.json_to_object(mf2)
    self.assertEqual('http://nested', obj['object']['url'])

  def test_object_to_json_unescapes_html_entities(self):
    self.assertEqual({
      'type': ['h-entry'],
      'properties': {'content': [{
        'html': 'Entity &lt; <a href="http://my/link">link too</a>',
        'value': 'Entity < link too',
      }]},
     }, microformats2.object_to_json({
       'verb': 'post',
       'object': {
        'content': 'Entity &lt; link too',
        'tags': [{'url': 'http://my/link', 'startIndex': 12, 'length': 8}]
       }
     }))

  def test_object_to_json_note_with_in_reply_to(self):
    self.assertEqual({
      'type': ['h-entry'],
      'properties': {
        'content': ['@hey great post'],
        'in-reply-to': ['http://reply/target'],
      },
    }, microformats2.object_to_json({
      'verb': 'post',
      'object': {
        'content': '@hey great post',
      },
      'context': {
        'inReplyTo': [{
          'url': 'http://reply/target',
        }],
      }}))

  def test_object_to_json_context_string(self):
    """Can happen for objects converted from AS2.

    e.g. https://console.cloud.google.com/errors/CLWDpPG37eirUw
    """
    self.assertEqual({
      'type': ['h-entry'],
      'properties': {
        'content': ['@hey great post'],
        # 'in-reply-to': ['http://reply/target'],
      },
    }, microformats2.object_to_json({
      'verb': 'post',
      'object': {'content': '@hey great post'},
      'context': 'http://foo/bar',
      }))

  def test_object_to_json_preserves_url_order(self):
    self.assertEqual({
      'type': ['h-card'],
      'properties': {
        'url': ['http://2', 'http://4', 'http://6'],
      },
    }, microformats2.object_to_json({
      'objectType': 'person',
      'url': 'http://2',
      'urls': [{'value': 'http://4'},
               {'value': 'http://6'}],
    }))

  def test_object_to_html_note_with_in_reply_to(self):
    expected = """\
<article class="h-entry">
<span class="p-uid"></span>
<div class="e-content p-name">
@hey great post
</div>
<a class="u-in-reply-to" href="http://reply/target"></a>
</article>
"""
    result = microformats2.object_to_html({
      'verb': 'post',
      'context': {
        'inReplyTo': [{
          'url': 'http://reply/target',
        }],
      },
      'object': {
        'content': '@hey great post',
      }
    })
    self.assertEqual(re.sub('\n\s*', '\n', expected),
                      re.sub('\n\s*', '\n', result))

  def test_render_content_link_with_image(self):
    obj = {
      'content': 'foo',
      'tags': [{
        'objectType': 'article',
        'url': 'http://link',
        'displayName': 'name',
        'image': {'url': 'http://image'},
      }]
    }

    self.assert_equals("""\
foo
<a class="tag" href="http://link">name</a>
""", microformats2.render_content(obj, render_attachments=False))

    self.assert_equals("""\
foo
<p>
<a class="link" href="http://link">
<img class="u-photo" src="http://image" alt="name" />
<span class="name">name</span>
</a>
</p>""", microformats2.render_content(obj, render_attachments=True))

  def test_render_content_multiple_image_attachments(self):
    obj = {
      'content': 'foo',
      'attachments': [
        {'objectType': 'image', 'image': {'url': 'http://1'}},
        {'objectType': 'image', 'image': {'url': 'http://2'}},
      ],
    }

    self.assert_equals('foo', microformats2.render_content(obj))

    self.assert_equals("""\
foo
<p>
<img class="u-photo" src="http://1" alt="" />
</p>
<p>
<img class="u-photo" src="http://2" alt="" />
</p>""", microformats2.render_content(obj, render_attachments=True))

  def test_render_content_render_image(self):
    self.assert_equals("""\
foo
<p>
<a class="link" href="http://obj">
<img class="u-photo" src="http://1/" alt="" />
</a>
</p>
""", microformats2.render_content({
      'content': 'foo',
      'url': 'http://obj',
      'image': 'http://1',
    }, render_image=True))

  def test_render_content_render_image_dedupes_render_attachments(self):
    self.assert_equals("""\
foo
<p>
<a class="link" href="http://obj">
<img class="u-photo" src="http://pic/1" alt="" />
</a>
</p>
<p>
<a class="link" href="http://obj">
<img class="u-photo" src="http://pic/2" alt="" />
</a>
</p>
<p>
<a class="link" href="http://obj">
<img class="u-photo" src="http://pic/3" alt="" />
</a>
</p>
""", microformats2.render_content({
      'content': 'foo',
      'url': 'http://obj',
      'image': [
        {'url': 'http://pic/1'},
        {'url': 'http://pic/2'},
      ],
      'attachments': [
        {'objectType': 'image', 'image': {'url': 'http://pic/1'}},
        {'objectType': 'image', 'image': {'url': 'http://pic/3'}},
      ],
    }, render_attachments=True, render_image=True))

  def test_render_content_newlines_default_white_space_pre(self):
    self.assert_equals("""\
<div style="white-space: pre">foo
bar
<a href="http://baz">baz</a></div>
""", microformats2.render_content({
  'content': 'foo\nbar\nbaz',
  'tags': [{'url': 'http://baz', 'startIndex': 8, 'length': 3}]
}))

  def test_render_content_convert_newlines_to_brs(self):
    self.assert_equals("""\
foo<br />
bar<br />
<a href="http://baz">baz</a>
""", microformats2.render_content({
  'content': 'foo\nbar\nbaz',
  'tags': [{'url': 'http://baz', 'startIndex': 8, 'length': 3}]
}, white_space_pre=False))

  def test_render_content_omits_tags_without_urls(self):
    self.assert_equals("""\
foo
<a class="tag" aria-hidden="true" href="http://baj"></a>
<a class="tag" href="http://baz">baz</a>
""", microformats2.render_content({
      'content': 'foo',
      'tags': [
        {'displayName': 'bar'},
        {'url': 'http://baz', 'displayName': 'baz'},
        {'url': 'http://baj'},
      ],
    }))

  def test_render_content_location(self):
    self.assert_multiline_equals("""\
foo
<p>  <span class="p-location h-card">
  <a class="p-name u-url" href="http://my/place">My place</a>

</span>
</p>
""", microformats2.render_content({
        'content': 'foo',
        'location': {
          'displayName': 'My place',
          'url': 'http://my/place',
        }
      }), ignore_blanks=True)

  def test_render_content_synthesize_content(self):
    for verb, phrase in ('like', 'likes'), ('share', 'shared'):
      obj = {
        'verb': verb,
        'object': {'url': 'http://orig/post'},
      }
      self.assert_equals('<a href="http://orig/post">%s this.</a>' % phrase,
                         microformats2.render_content(obj, synthesize_content=True))
      self.assert_equals('',
                         microformats2.render_content(obj, synthesize_content=False))

      obj['content'] = 'Message from actor'
      for val in False, True:
        self.assert_equals(obj['content'],
                           microformats2.render_content(obj, synthesize_content=val))

  def test_render_content_video_audio(self):
    obj = {
      'content': 'foo',
      'attachments': [{
        'image': [{'url': 'http://im/age'}],
        'stream': [{'url': 'http://vid/eo'}],
        'objectType': 'video',
      }, {
        'stream': [{'url': 'http://aud/io'}],
        'objectType': 'audio',
      }],
    }

    self.assert_equals('foo', microformats2.render_content(obj))

    self.assert_equals("""\
foo
<p><video class="u-video" src="http://vid/eo" controls="controls" poster="http://im/age">Your browser does not support the video tag. <a href="http://vid/eo">Click here to view directly. <img src="http://im/age" /></a></video>
</p>
<p><audio class="u-audio" src="http://aud/io" controls="controls">Your browser does not support the audio tag. <a href="http://aud/io">Click here to listen directly.</a></audio>
</p>
""", microformats2.render_content(obj, render_attachments=True))

  def test_render_content_shared_object_attachments(self):
    share = {
      'verb': 'share',
      'object': {
        'content': 'foo',
        'attachments': [{
          'image': [{'url': 'http://im/age'}],
          'stream': [{'url': 'http://vid/eo'}],
          'objectType': 'video',
        }, {
          'stream': [{'url': 'http://aud/io'}],
          'objectType': 'audio',
        }],
      },
    }

    out = microformats2.render_content(share, render_attachments=True)
    self.assert_multiline_equals("""
Shared <a href="#">a post</a> by foo
<p><video class="u-video" src="http://vid/eo" controls="controls" poster="http://im/age">Your browser does not support the video tag. <a href="http://vid/eo">Click here to view directly. <img src="http://im/age" /></a></video>
</p>
<p><audio class="u-audio" src="http://aud/io" controls="controls">Your browser does not support the audio tag. <a href="http://aud/io">Click here to listen directly.</a></audio>
</p>""", out, ignore_blanks=True)

  def test_render_content_unicode_high_code_points(self):
    """Test Unicode high code point chars.

    The first three unicode chars in the content are the '100' emoji, which is a
    high code point, ie above the Basic Multi-lingual Plane (ie 16 bits). The
    emacs font i use doesn't render it, so it looks blank.

    First discovered in https://twitter.com/schnarfed/status/831552681210556416
    """
    self.assert_equals(
      '💯💯💯 (by <a href="https://twitter.com/itsmaeril">@itsmaeril</a>)',
      microformats2.render_content({
        'content': '💯💯💯 (by @itsmaeril)',
        'tags': [{
          'displayName': 'Maeril',
          'objectType': 'person',
          'startIndex': 8,
          'length': 10,
          'url': 'https://twitter.com/itsmaeril',
        }]}))

  def test_escape_html_attribute_values(self):
    obj = {
      'author': {
        'image': {'url': 'author-img'},
        'displayName': 'a " b \' c',
      },
      'attachments': [{
        'objectType': 'image',
        'image': {'url': 'att-img'},
        'displayName': 'd & e'}],
    }

    self.assert_multiline_equals("""\
<article class="h-entry">
<span class="p-uid"></span>
<span class="p-author h-card">
<span class="p-name">a " b ' c</span>
<img class="u-photo" src="author-img" alt="" />
</span>
<span class="p-name"></span>
<div class="">
</div>
<img class="u-photo" src="att-img" alt="" />
</article>""", microformats2.object_to_html(obj), ignore_blanks=True)

    content = microformats2.render_content(obj, render_attachments=True)
    self.assert_multiline_equals("""\
<p>
<img class="u-photo" src="att-img" alt="d &amp; e" />
<span class="name">d & e</span>
</p>""", content, ignore_blanks=True)

  def test_mention_and_hashtag(self):
    self.assert_equals("""
<a class="p-category" href="http://c">c</a>
<a class="u-mention" aria-hidden="true" href="http://m"></a>""",
                       microformats2.render_content({
        'tags': [{'objectType': 'mention', 'url': 'http://m', 'displayName': 'm'},
                 {'objectType': 'hashtag', 'url': 'http://c', 'displayName': 'c'}],
      }))

  def test_tag_multiple_urls(self):
    expected_urls = ['http://1', 'https://2']
    expected_html = """
<a class="tag" aria-hidden="true" href="http://1"></a>
<a class="tag" aria-hidden="true" href="https://2"></a>
"""
    for tag in ({'url': 'http://1',
                  'urls': [{'value': 'http://1'}, {'value': 'https://2'}]},
                {'url': 'http://1',
                 'urls': [{'value': 'https://2'}]},
                {'urls': [{'value': 'http://1'}, {'value': 'https://2'}]}):
      self.assert_equals(expected_urls,
                         microformats2.object_to_json(tag)['properties']['url'],
                         tag)
      self.assert_equals(expected_html,
                         microformats2.render_content({'tags': [tag]}),
                         tag)

  def test_dont_render_images_inside_non_image_attachments(self):
    self.assert_equals('my content', microformats2.render_content({
       'content': 'my content',
       'attachments': [{
         'objectType': 'note',
         'image': {'url': 'http://attached/image'},
       }],
    }))

  def test_dont_stop_at_unknown_tag_type(self):
    obj = {'tags': [
      {'objectType': 'x', 'url': 'http://x'},
      {'objectType': 'person', 'url': 'http://p', 'displayName': 'p'}],
    }
    self.assert_equals({
      'type': ['h-entry'],
      'properties': {
        'category': [{
          'type': ['h-card'],
          'properties': {
            'name': ['p'],
            'url': ['http://p'],
          },
        }],
        'content': [{'html': '\n<a class="tag" aria-hidden="true" href="http://x"></a>'}],
      },
    }, microformats2.object_to_json(obj))

  def test_attachments_to_children(self):
    obj = {'attachments': [
      {'objectType': 'note', 'url': 'http://p', 'displayName': 'p'},
      {'objectType': 'x', 'url': 'http://x'},
      {'objectType': 'article', 'url': 'http://a'},
    ]}

    self.assert_equals([{
      'type': ['u-quotation-of', 'h-cite'],
      'properties': {'url': ['http://p'], 'name': ['p']},
    }, {
      'type': ['h-cite'],
      'properties': {'url': ['http://a']},
    }], microformats2.object_to_json(obj)['children'])

    html = microformats2.object_to_html(obj)
    self.assert_multiline_in("""\
<article class="u-quotation-of h-cite">
<span class="p-uid"></span>

<a class="p-name u-url" href="http://p">p</a>
<div class="">

</div>

</article>

<article class="h-cite">
<span class="p-uid"></span>

<a class="p-name u-url" href="http://a"></a>
<div class="">

</div>

</article>
""", html)

  def test_object_to_json_reaction(self):
    self.assert_equals({
      'type': ['h-entry'],
      'properties': {
        'content': ['✁'],
        'in-reply-to': ['https://orig/post'],
      },
    }, microformats2.object_to_json({
      'objectType': 'activity',
      'verb': 'react',
      'content': '✁',
      'object': {'url': 'https://orig/post'},
    }))

  def test_object_to_json_multiple_object_urls(self):
    self.assert_equals({
      'type': ['h-entry'],
      'properties': {
        'content': ['✁'],
        'in-reply-to': ['https://orig/post/1', 'https://orig/post/2'],
      },
    }, microformats2.object_to_json({
      'objectType': 'activity',
      'verb': 'react',
      'content': '✁',
      'object': [
        {'url': 'https://orig/post/1'},
        {'url': 'https://orig/post/2'},
      ],
    }))

  def test_object_to_json_not_dict(self):
    """This can happen if we get a dict instead of a list, e.g. with AS 2.0.

    Found via AS2 on http://evanminto.com/indieweb/activity-stream.php, e.g.:

    {
      "@context": "https://www.w3.org/ns/activitystreams",
      "0": {
        "name": "Evan reposted another post.",
        "type": "Announce",
        "actor": {
          "type": "Person",
          "name": "Evan Minto",
          "url": "http://evanminto.com"
        },
        "object": "http://www.harkavagrant.com/index.php?id=402"
      },
    ...
    """
    self.assert_equals({}, microformats2.object_to_json('foo bar'))

  def test_get_string_urls(self):
    for expected, objs in (
        ([], []),
        (['asdf'], ['asdf']),
        ([], [{'type': 'h-ok'}]),
        ([], [{'properties': {'url': ['nope']}}]),
        ([], [{'type': ['h-ok'], 'properties': {'no': 'url'}}]),
        (['good1', 'good2'], ['good1',
                            {'type': ['h-ok']},
                            {'type': ['h-ok'], 'properties': {'url': ['good2']}}]),
        (['nested'], [{'type': ['h-ok'], 'properties': {'url': [
            {'type': ['h-nested'], 'url': ['nested']}]}}]),
        ):
      self.assertEqual(expected, microformats2.get_string_urls(objs))

  def test_img_blank_alt(self):
    self.assertEqual('<img class="u-photo" src="foo" alt="" />',
                      microformats2.img('foo'))

  def test_json_to_html_no_properties_or_type(self):
    # just check that we don't crash
    microformats2.json_to_html({'x': 'y'})

  def test_json_to_object_with_location_hcard(self):
    obj = microformats2.json_to_object({
      'type': ['h-entry'],
      'properties': {
        'location': [{
          'type': ['h-card'],
          'properties': {
            'name': ['Timeless Coffee Roasters'],
            'locality': ['Oakland'],
            'region': ['California'],
            'latitude': ['50.820641'],
            'longitude': ['-0.149522'],
            'url': ['https://kylewm.com/venues/timeless-coffee-roasters-oakland-california'],
          },
          'value': 'Timeless Coffee Roasters',
        }],
      }})
    self.assertEqual({
      'objectType': 'place',
      'latitude': 50.820641,
      'longitude': -0.149522,
      'position': '+50.820641-000.149522/',
      'displayName': 'Timeless Coffee Roasters',
      'url': 'https://kylewm.com/venues/timeless-coffee-roasters-oakland-california',
    }, obj['location'])

  def test_json_to_object_with_location_geo(self):
    self._test_json_to_object_with_location({
      'location': [{
        'type': ['h-geo'],
        'properties': {
          'latitude': ['50.820641'],
          'longitude': ['-0.149522'],
        }
      }],
    })

  def test_json_to_object_with_geo(self):
    self._test_json_to_object_with_location({
      'geo': [{
        'properties': {
          'latitude': ['50.820641'],
          'longitude': ['-0.149522'],
        },
      }]
    })

  def test_json_to_object_with_geo_url(self):
    self._test_json_to_object_with_location({
      'geo': ['geo:50.820641,-0.149522;foo=bar'],
    })

  def test_json_to_object_with_lat_lon_top_level(self):
    self._test_json_to_object_with_location({
      'latitude': ['50.820641'],
      'longitude': ['-0.149522'],
    })

  def _test_json_to_object_with_location(self, props):
    obj = microformats2.json_to_object({
      'type': ['h-entry'],
      'properties': props,
    })
    self.assertEqual({
      'latitude': 50.820641,
      'longitude': -0.149522,
      'position': '+50.820641-000.149522/',
      'objectType': 'place',
    }, obj.get('location'))

  def test_json_to_object_with_categories(self):
    obj = microformats2.json_to_object({
      'type': ['h-entry'],
      'properties': {
        'category': [
          {
            'type': ['h-card'],
            'properties': {
              'name': ['Kyle Mahan'],
              'url': ['https://kylewm.com'],
            },
          },
          'cats',
          'indieweb']
      },
    })

    self.assertEqual([
      {
        'objectType': 'person',
        'displayName': 'Kyle Mahan',
        'url': 'https://kylewm.com',
      },
      {
        'objectType': 'hashtag',
        'displayName': 'cats',
      },
      {
        'objectType': 'hashtag',
        'displayName': 'indieweb',
      },
    ], obj.get('tags'))

  def test_json_to_object_text_newlines(self):
    """Text newlines should not be converted to <br>s."""
    self.assert_equals({
      'objectType': 'note',
      'content': 'asdf\nqwer',
    }, microformats2.json_to_object({
      'properties': {'content': [{'value': 'asdf\nqwer'}]},
    }))

  def test_json_to_object_keeps_html_newlines(self):
    """HTML newlines should be preserved."""
    self.assert_equals({
      'objectType': 'note',
      'content': 'asdf\nqwer',
    }, microformats2.json_to_object({
      'properties': {'content': [{'html': 'asdf\nqwer', 'value': ''}]},
    }))

  def test_json_to_object_simple_url_author(self):
    """Simple URL-only authors should be handled ok."""
    self.assert_equals({
      'objectType': 'note',
      'content': 'foo',
      'author': {
        'url': 'http://example.com',
        'objectType': 'person',
      },
    }, microformats2.json_to_object({
      'properties': {
        'content': ['foo'],
        'author': ['http://example.com'],
      },
    }))

  def test_json_to_object_simple_name_author(self):
    """Simple name-only authors should be handled ok."""
    self.assert_equals({
      'objectType': 'note',
      'content': 'foo',
      'author': {
        'displayName': 'My Name',
        'objectType': 'person',
      },
    }, microformats2.json_to_object({
      'properties': {
        'content': ['foo'],
        'author': ['My Name'],
      },
    }))

  def test_json_to_object_authorship_fetch_mf2_func(self):
    self.expect_requests_get('http://example.com', """
<div class="h-card">
<a class="p-name u-url" rel="me" href="/">Ms. ☕ Baz</a>
<img class="u-photo" src="/my/pic" />
</div>
""", response_headers={'content-type': 'text/html; charset=utf-8'})
    self.mox.ReplayAll()

    self.assert_equals({
      'objectType': 'note',
      'content': 'foo',
      'author': {
        'url': 'http://example.com/',
        'objectType': 'person',
        'displayName': 'Ms. ☕ Baz',
        'image': [{'url': 'http://example.com/my/pic'}],
      },
    }, microformats2.json_to_object({
      'type': ['h-entry'],
      'properties': {
        'content': ['foo'],
        'author': ['http://example.com'],
      },
    }, fetch_mf2=True))

  def test_find_author(self):
    self.assert_equals({
    'displayName': 'my name',
    'image': {'url': 'http://pic/ture'},
  }, microformats2.find_author(mf2py.parse(doc="""\
<body class="h-entry">
<div class="p-author h-card">
<a class="p-name" href="http://li/nk">my name</a>
<img class="u-photo" src="http://pic/ture" />
</div>
</body>
""", url='http://123')))

  def test_object_urls(self):
    for expected, actor in (
        ([], {}),
        ([], {'displayName': 'foo'}),
        ([], {'url': None, 'urls': []}),
        (['http://foo'], {'url': 'http://foo'}),
        (['http://foo'], {'urls': [{'value': 'http://foo'}]}),
        (['http://foo', 'https://bar', 'http://baz'], {
          'url': 'http://foo',
          'urls': [{'value': 'https://bar'},
                   {'value': 'http://foo'},
                   {'value': 'http://baz'},
          ],
        }),
    ):
      self.assertEqual(expected, microformats2.object_urls(actor))

  def test_hcard_to_html_no_properties(self):
    self.assertEqual('', microformats2.hcard_to_html({}))
    self.assertEqual('', microformats2.hcard_to_html({'properties': {}}))

  def test_share_activity_to_json_html(self):
    """Should translate the full activity, not just the object."""
    share = {
      'verb': 'share',
      'actor': {'displayName': 'sharer'},
      'object': {
        'content': 'original',
        'actor': {'displayName': 'author'},
      },
    }

    self.assert_equals({
      'type': ['h-entry'],
      'properties': {
        'author': [{
          'type': ['h-card'],
          'properties': {'name': ['sharer']},
        }],
        'repost-of': [{
          'type': ['h-cite'],
          'properties': {
            'content': ['original'],
            'author': [{
              'type': ['h-card'],
              'properties': {'name': ['author']},
            }],
          }
        }],
      },
    }, microformats2.activity_to_json(share, synthesize_content=False))

    self.assert_multiline_in("""\
Shared <a href="#">a post</a> by   <span class="h-card">
<span class="p-name">author</span>
""", microformats2.activities_to_html([share]), ignore_blanks=True)

  def test_activities_to_html_like(self):
    self.assert_multiline_equals("""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<article class="h-entry">
  <span class="p-uid">http://localhost:3000/users/ryan#likes/7</span>
  <span class="p-author h-card">
    <a class="u-url" href="http://localhost:3000/users/ryan">http://localhost:3000/users/ryan</a>
  </span>
  <div class="e-content p-name">
  <a href="http://localhost/2017-10-01_mastodon-dev-6">likes this.</a>
  </div>
<a class="u-like-of" href="http://localhost/2017-10-01_mastodon-dev-6"></a>
</article>
</body>
</html>
""", microformats2.activities_to_html([{
  'id': 'http://localhost:3000/users/ryan#likes/7',
  'objectType': 'activity',
  'verb': 'like',
  'object': {'url': 'http://localhost/2017-10-01_mastodon-dev-6'},
  'actor': {'url': 'http://localhost:3000/users/ryan'},
}]), ignore_blanks=True)

  def test_combined_reply_and_tag_of_error(self):
    """https://github.com/snarfed/bridgy/issues/832"""
    with self.assertRaises(NotImplementedError):
      microformats2.json_to_object({
        'type': ['h-entry'],
        'properties': {
          'tag-of': [{'value': 'https://a/post'}],
          'in-reply-to': [{'value': 'https://another/post'}],
        }
      })

  def test_html_to_activities_brs_to_newlines(self):
    """Mostly tests that mf2py converts <br>s to \ns.

    Background:
    https://github.com/snarfed/granary/issues/142
    https://github.com/microformats/mf2py/issues/51
    https://pin13.net/mf2/whitespace.html
    """
    html = """\
<article class="h-entry">
<div class="e-content p-name">foo bar<br />baz <br><br> baj</div>
</article>"""
    activities = microformats2.html_to_activities(html)
    self.assert_equals([{'object': {
      'objectType': 'note',
      'content': 'foo bar<br/>baz <br/><br/> baj',
      'content_is_html': True,
      'displayName': 'foo bar\nbaz \n\n baj',
    }}], activities)

  def test_html_to_activities_filters_items(self):
    """Check that we omit h-cards inside h-feeds."""
    self.assert_equals([], microformats2.html_to_activities("""\
<div class="h-feed">
  <article class="h-card">
    <a href="http://foo">bar</a>
  </article>
</div>"""))

  def test_size_to_bytes(self):
    for input, expected in (
        (None, None),
        ('', None),
        (123, 123),
        ('123', 123),
        ('  123\n  ', 123),
        ('1.23 KB', 1230),
        ('5 MB', 5000000),
    ):
      self.assertEqual(expected, microformats2.size_to_bytes(input), input)
