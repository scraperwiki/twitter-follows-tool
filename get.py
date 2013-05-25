#!/usr/bin/python

import os
import json
import urllib
import sys
import collections
import dateutil.parser
import subprocess
import httplib
import sqlite3
import datetime
import scraperwiki
import httplib

from secrets import *

# Horrendous hack to work around some Twitter / Python incompatibility
# http://bobrochel.blogspot.co.nz/2010/11/bad-servers-chunked-encoding-and.html
def patch_http_response_read(func):
    def inner(*args):
        try:
            return func(*args)
        except httplib.IncompleteRead, e:
            return e.partial

    return inner
httplib.HTTPResponse.read = patch_http_response_read(httplib.HTTPResponse.read)

# Make sure you install this version of "twitter":
# http://pypi.python.org/pypi/twitter
# http://mike.verdone.ca/twitter/
# https://github.com/sixohsix/twitter
import twitter

#########################################################################
# Authentication to Twitter

# This is designed to, when good, be submitted as a patch to add to twitter.oauth_dance (which
# currently only has a function for PIN authentication, not redirect)
from twitter.api import Twitter
from twitter.oauth import OAuth, write_token_file, read_token_file
from twitter.oauth_dance import parse_oauth_tokens
def oauth_url_dance(consumer_key, consumer_secret, callback_url, oauth_verifier, pre_verify_token_filename, verified_token_filename):
    # Verification happens in two stages...

    # 1) If we haven't done a pre-verification yet... Then we get credentials from Twitter
    # that will be used to sign our redirect to them, find the redirect, and instruct the Javascript
    # that called us to do the redirect.
    if not os.path.exists(CREDS_PRE_VERIFIY):
        twitter = Twitter(auth=OAuth('', '', consumer_key, consumer_secret), format='', api_version=None)
        oauth_token, oauth_token_secret = parse_oauth_tokens(twitter.oauth.request_token(oauth_callback = callback_url))
        write_token_file(pre_verify_token_filename, oauth_token, oauth_token_secret)

        oauth_url = 'https://api.twitter.com/oauth/authorize?' + urllib.urlencode({ 'oauth_token': oauth_token })
        return oauth_url

    # 2) We've done pre-verification, hopefully the user has authed us in Twitter
    # and we've been redirected to. Check we are and ask for the permanent tokens.
    oauth_token, oauth_token_secret = read_token_file(CREDS_PRE_VERIFIY)
    twitter = Twitter(auth=OAuth( oauth_token, oauth_token_secret, consumer_key, consumer_secret), format='', api_version=None)
    oauth_token, oauth_token_secret = parse_oauth_tokens(twitter.oauth.access_token(oauth_verifier=oauth_verifier))
    write_token_file(verified_token_filename, oauth_token, oauth_token_secret)
    return oauth_token, oauth_token_secret


def do_tool_oauth():
    if not os.path.exists(CREDS_VERIFIED):
        if len(sys.argv) < 3:
            result = "need-oauth"
        else:
            (callback_url, oauth_verifier) = (sys.argv[1], sys.argv[2])
            result = oauth_url_dance(CONSUMER_KEY, CONSUMER_SECRET, callback_url, oauth_verifier, CREDS_PRE_VERIFIY, CREDS_VERIFIED)
        # a string means a URL for a redirect (otherwise we get a tuple back with auth tokens in)
        if type(result) == str:
            set_status_and_exit('auth-redirect', 'error', 'Permission needed from Twitter', { 'url': result } )

    oauth_token, oauth_token_secret = read_token_file(CREDS_VERIFIED)
    tw = twitter.Twitter(auth=twitter.OAuth( oauth_token, oauth_token_secret, CONSUMER_KEY, CONSUMER_SECRET))
    return tw

#########################################################################
# Helper functions

# Stores one Twitter user in the ScraperWiki database
def convert_user(batch, user):
    data = collections.OrderedDict()

    data['id'] = user['id']
    data['name'] = user['name']
    data['screen_name'] = user['screen_name']
    data['profile_url'] = "https://twitter.com/" + user['screen_name']
    data['profile_image'] = user['profile_image_url_https'] # shorten name to avoid wasting horizontal space

    data['description'] = user['description']
    data['location'] = user['location']
    data['url'] = user['url']

    data['followers_count'] = user['followers_count']
    data['following_count'] = user['friends_count'] # rename as "friends" is confusing to end users
    data['statuses_count'] = user['statuses_count']

    data['created_at'] = dateutil.parser.parse(user['created_at'])

    data['batch'] = batch # this is needed internally to track progress of getting all the followers

    return data

# After detecting an auth failed error mid work, call this
def clear_auth_and_restart():
    # remove auth files and respawn
    try:
        os.remove(CREDS_PRE_VERIFIY)
        os.remove(CREDS_VERIFIED)
    except OSError:
        # don't worry if the files aren't there
        pass
    subprocess.call(sys.argv)
    sys.exit()

# Signal back to the calling Javascript, to the database, and custard's status API, our status
def set_status_and_exit(status, typ, message, extra = {}):
    global current_status

    extra['status'] = status
    print json.dumps(extra)

    scraperwiki.status(typ, message)

    current_status = status
    save_status()

    sys.exit()


# Store all our progress variables
def save_status():
    global current_batch, next_cursor, batch_got, batch_expected, current_status

    # Update progress indicators...

    # For number of users got, we count the total of:
    # 1) all followers in the last full batch
    # 2) all followers transferred into the new batch so far
    # i.e. all those for whom batch >= (current_batch - 1)
    try:
        batch_got = scraperwiki.sql.select("count(*) as c from twitter_followers where batch >= %d" % (current_batch - 1))[0]['c']
    except:
        batch_got = 0

    data = { 
        'id': 'followers',
        'current_batch': current_batch,
        'next_cursor': next_cursor,
        'batch_got': batch_got,
        'batch_expected': batch_expected,
        'current_status': current_status
    }
    scraperwiki.sql.save(['id'], data, table_name='__status')

# Load in all our progress variables
current_batch = 1
next_cursor = -1
batch_got = 0
batch_expected = 0
current_status = 'clean-slate'
def get_status():
    global current_batch, next_cursor, batch_got, batch_expected, current_status

    try:
        data = scraperwiki.sql.select("* from __status where id='followers'")
    except sqlite3.OperationalError, e:
        if str(e) == "no such table: __status":
            return
        raise
    if len(data) == 0:
        return
    assert(len(data) == 1)
    data = data[0]

    current_batch = data['current_batch']
    next_cursor = data['next_cursor']
    batch_got = data['batch_got']
    batch_expected = data['batch_expected']
    current_status = data['current_status']

# http://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks-in-python
def chunks(l, n):
    return [l[i:i+n] for i in range(0, len(l), n)]

#########################################################################
# Main code

pages_got = 0
try:
    # Rename old status table to new __status name.
    # This can be removed after it has been active long enough to
    # update all existing tools.
    try :
        scraperwiki.sql.execute("SELECT 1 FROM status")
    except sqlite3.OperationalError:
       pass
    else:
        scraperwiki.sql.execute("ALTER TABLE status RENAME TO __status")

    # Parameters to this command vary:
    #   a. None: try and scrape Twitter followers
    #   b. callback_url oauth_verifier: have just come back from Twitter with these oauth tokens
    #   c. "clean-slate": wipe database and start again
    if len(sys.argv) > 1 and sys.argv[1] == 'clean-slate':
        scraperwiki.sql.execute("drop table if exists twitter_followers")
        scraperwiki.sql.execute("drop table if exists __status")
        os.system("crontab -r >/dev/null 2>&1")
        set_status_and_exit('clean-slate', 'error', 'No user set')
        sys.exit()

    # Make the followers table *first* with dumb data, calling DumpTruck directly,
    # so it appears before the status one in the list
    scraperwiki.sql.dt.create_table({'id': 1}, 'twitter_followers')

    # Get user we're working on from file we store it in
    screen_name = open("user.txt").read().strip()

    # Connect to Twitter
    tw = do_tool_oauth()

    # A batch is one scan through the list of followers - we have to scan as we only
    # get 20 per API call, and have 15 API calls / 15 minutes (as of Feb 2013).
    # The cursor is Twitter's identifier of where in the current batch we are.
    get_status()
    # Note that each user is only in the most recent batch they've been found in
    # (we don't keep all the history)

    # Look up latest followers count
    profile = tw.users.lookup(screen_name=screen_name)
    batch_expected = profile[0]['followers_count']

    # Things basically working, so make sure we run again
    os.system("crontab -l >/dev/null 2>&1 || crontab tool/crontab")

    # Get as many pages in the batch as we can (most likely 15!)
    onetime = 'ONETIME' in os.environ
    while True:
        #raise httplib.IncompleteRead('hi') # for testing
        #print "getting", next_cursor

        # get the identifiers of followers - one page worth (up to 5000 people)
        if next_cursor == -1:
            result = tw.followers.ids(screen_name=screen_name)
        else:
            result = tw.followers.ids(screen_name=screen_name, cursor=next_cursor)
        ids = result['ids']

        # and then the user details for all the ids
        double_break = False
        for chunk in chunks(ids, 100):
            users = tw.users.lookup(user_id=(",".join(map(str, chunk))))
            data = []
            for user in users:
                datum = convert_user(current_batch, user)
                data.append(datum)
            scraperwiki.sql.save(['id'], data, table_name="twitter_followers")
            save_status()

            # If we have exactly the number of followers claimed, then only do one
            # API call each time to save on rate limiting. This will gradually
            # refresh everything anyway...  And realistically, if someone has
            # churning followers, we'll get badly out of count soon enough.
            if batch_got == batch_expected:
                double_break = True
                break

            # If being run from the user interface, return quickly after being
            # sure we've got *something* (the Javascript will then spawn us
            # again in the background to slowly get the rest)
            if onetime:
                double_break = True
                break
        if double_break:
            break
      
        # we have all the info for one page - record got and save it
        pages_got += 1
        next_cursor = result['next_cursor']

        # While debugging, only do one page to avoid rate limits by uncommenting this:
        # break

        if next_cursor == 0:
            # We've finished a batch
            next_cursor = -1
            current_batch += 1
            save_status()
            break

except twitter.api.TwitterHTTPError, e:
    if "Twitter sent status 401 for URL" in str(e):
        clear_auth_and_restart()

    # https://dev.twitter.com/docs/error-codes-responses
    obj = json.loads(e.response_data)
    code = obj['errors'][0]['code'] 
    # authentication failure
    if (code in [32, 89]):
        clear_auth_and_restart()
    # page not found
    if code == 34:
        set_status_and_exit('not-there', 'error', 'User not on Twitter')
    # rate limit exceeded
    if code == 88:
        # provided we got at least one page, rate limit isn't an error but expected
        if pages_got == 0:
            set_status_and_exit('rate-limit', 'error', 'Twitter is rate limiting you')
    else:
        # anything else is an unexpected error - if ones occur a lot, add the above instead
        raise
except httplib.IncompleteRead, e:
    # I think this is effectively a rate limit error - so only count if it was first error
    if pages_got == 0:
        set_status_and_exit('rate-limit', 'error', 'Twitter broke the connection')

# Save progress message
if batch_got == batch_expected:
    set_status_and_exit("ok-updating", 'ok', "Fully up to date")
else:
    set_status_and_exit("ok-updating", 'ok', "Running... %d/%d" % (batch_got, batch_expected))





