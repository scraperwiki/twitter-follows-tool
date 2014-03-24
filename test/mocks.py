import random
from twitter.api import TwitterHTTPError
from httplib import IncompleteRead

def random_id():
    return random.randrange(999999999)

def random_ids(n):
    return [random_id() for x in range(n)]

def ids(num_ids=None, next_cursor=0, ids=None):
    """fake an 'ids' response: use """
    # {"next_cursor_str": "0", "previous_cursor": 0, "ids": [2151045530, 14284208, 537386838, 72015710, 571602068, 1151009623, 24450319, 41432796, 486759161, 113153902, 105853630, 68366143, 106061815, 103361551, 74178894, 39195990, 56645305, 23512550, 20931484, 22210181, 20104494, 19703625, 17899968, 18673822, 18084850, 1022831, 6549432], "next_cursor": 0, "previous_cursor_str": "0"}
    template = {"previous_cursor": 0, "previous_cursor_str": "0"}

    if ids is None and num_ids is None:
        num_ids = 10
    if ids is None:
       ids = random_ids(num_ids)
    template['ids'] = ids
    template['next_cursor'] = next_cursor
    template['next_cursor_str'] = str(next_cursor)
    return template

def test_ids():
    assert len(ids(10)['ids']) == 10
    assert ids(ids=[1,2,3])['ids'][1] == 2
    assert ids(next_cursor=5)['next_cursor_str'] == '5'
    print "win"


def user(uid=None):
    if uid is None:
        uid=random_id()
    return [{"follow_request_sent": False, "profile_use_background_image": True, "default_profile_image": False, "id": uid, "profile_background_image_url_https": "https://abs.twimg.com/images/themes/theme1/bg.png", "verified": False, "profile_text_color": "333333", "profile_image_url_https": "https://pbs.twimg.com/profile_images/52432180/ouro_anim100_normal.gif", "profile_sidebar_fill_color": "DDEEF6", "entities": {"description": {"urls": []}}, "followers_count": 27, "profile_sidebar_border_color": "C0DEED", "id_str": str(uid), "profile_background_color": "C0DEED", "listed_count": 1, "status": {"contributors": None, "truncated": False, "text": "@ImaginaryMaps You might like http://t.co/b5sSuotYe7 - there's a load of info about the world on the wiki too because it's a new LARP game.", "in_reply_to_status_id": None, "id": 314157547718340609, "favorite_count": 0, "source": "web", "retweeted": False, "coordinates": None, "entities": {"symbols": [], "user_mentions": [{"id": 1262545009, "indices": [0, 14], "id_str": "1262545009", "screen_name": "ImaginaryMaps", "name": "Imaginary Atlas"}], "hashtags": [], "urls": [{"url": "http://t.co/b5sSuotYe7", "indices": [30, 52], "expanded_url": "http://www.profounddecisions.co.uk/empire-wiki/Maps", "display_url": "profounddecisions.co.uk/empire-wiki/Ma\u2026"}]}, "in_reply_to_screen_name": "ImaginaryMaps", "id_str": "314157547718340609", "retweet_count": 0, "in_reply_to_user_id": 1262545009, "favorited": False, "geo": None, "in_reply_to_user_id_str": "1262545009", "possibly_sensitive": False, "lang": "en", "created_at": "Tue Mar 19 23:32:50 +0000 2013", "in_reply_to_status_id_str": None, "place": None}, "is_translation_enabled": False, "utc_offset": None, "statuses_count": 53, "description": "", "friends_count": 14, "location": "", "profile_link_color": "0084B4", "profile_image_url": "http://pbs.twimg.com/profile_images/52432180/ouro_anim100_normal.gif", "following": False, "geo_enabled": False, "profile_background_image_url": "http://abs.twimg.com/images/themes/theme1/bg.png", "screen_name": "dragondave", "lang": "en", "profile_background_tile": False, "favourites_count": 1, "name": "dragondave", "notifications": False, "url": None, "created_at": "Fri Apr 04 13:46:54 +0000 2008", "contributors_enabled": False, "time_zone": None, "protected": False, "default_profile": True, "is_translator": False}]

def users(n):
    return [user()[0] for x in range(n)]

class TwitterError(TwitterHTTPError):
    def __init__(self, error):
        self.response_data = json.dumps({'errors':[{'code': error}]})

def error(e_type):
    if e_type=='read':
        raise IncompleteRead
    if e_type=='not_auth':
        raise TwitterHTTPError("Twitter sent status 401 for URL")
    if e_type=='auth_fail':
        raise TwitterError(32)
    if e_type=='token_expired':
        raise TwitterError(89)
    if e_type=='no_user':
        raise TwitterError(34)
    if e_type=='rate_limit':
        raise TwitterError(88)
