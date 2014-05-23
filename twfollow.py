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
import random
import datetime
import logging

from secrets import *

MAX_TO_GET=100000
if len(sys.argv) > 1 and sys.argv[1] == 'log':
    logging.basicConfig(level=logging.INFO)
else:
    logging.basicConfig(level=logging.CRITICAL)

class FollowerLimitError(Exception):
    pass

class QuickRun(Exception):
    pass

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
    data['verified'] = user['verified']

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
    logging.info("Exiting with status {!r}:{!r}".format(status, message))
    extra['status'] = status
    print json.dumps(extra)
    scraperwiki.status(typ, message)
    scraperwiki.sql.save(data={"current_status": status,
                               "id": "global",
	                       'when': datetime.datetime.now().isoformat()
                              },
                         table_name= '__status',
                         unique_keys = ['id'])

    sys.exit()




# http://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks-in-python
def chunks(l, n):
    return [l[i:i+n] for i in range(0, len(l), n)]


def move_legacy_table():
    # Rename old status table to new __status name.
    # This can be removed after it has been active long enough to
    # update all existing tools.
    try :
        scraperwiki.sql.execute("SELECT 1 FROM status")
    except sqlite3.OperationalError:
        logging.info("No legacy status table detected.")
        pass
    else:
        logging.warn("Legacy status table detected.")
        scraperwiki.sql.execute("ALTER TABLE status RENAME TO __status")

def shutdown(): # _if_static_dataset():
    #live_dataset = 'LIVE_DATASET' in os.environ
    #if not live_dataset:
	# Disable cron job, we're done
    logging.warn("All done: disabling cronjob")
    os.system("crontab -r >/dev/null 2>&1")
    set_status_and_exit("ok-done", 'ok', "Finished")


def install_crontab():
    if not os.path.isfile("crontab"):
        logging.warn("Crontab not detected. Installing...")
        crontab = open("tool/crontab.template").read()
        # ... run at a random minute to distribute load XXX platform should do this for us
        crontab = crontab.replace("RANDOM", str(random.randint(0, 59)))
        open("crontab", "w").write(crontab)
    else:
        logging.info("Crontab present. Activating...")
    os.system("crontab crontab")

def clean_slate():
    logging.warn("Cleaning slate")
    scraperwiki.sql.execute("drop table if exists twitter_followers")
    scraperwiki.sql.execute("drop table if exists twitter_following")
    scraperwiki.sql.execute("drop table if exists __status")
    scraperwiki.sql.execute("create table __status (batch_got, batch_expected)")
    os.system("crontab -r >/dev/null 2>&1")
    set_status_and_exit('clean-slate', 'error', 'No user set')
    sys.exit()

class TwitterPeople(object):
    def __init__(self, table_id, screen_name):
        self.table_id=table_id
        if self.table_id == 'followers': self.function = tw.followers
        if self.table_id == 'following': self.function = tw.friends
        assert self.function
        self.full_table = 'twitter_'+table_id
        self.screen_name = screen_name
        self.make_table()
        self.get_status()
        self.pages_got = 0

    def make_table(self):
	# Make the followers table *first* with dumb data, calling DumpTruck directly,
	# so it appears before the status one in the list
	scraperwiki.sql.dt.create_table({'id': 1, 'batch': 1}, self.full_table)
	scraperwiki.sql.execute("CREATE INDEX IF NOT EXISTS batch_index "
				"ON "+self.full_table+" (batch)")

    def get_more_ids(self):
        # get the identifiers of followers - one page worth (up to 5000 people)
        logging.info("next_cursor: {!r}".format(self.next_cursor))
        result = self.function.ids(screen_name=self.screen_name,
                                   cursor=self.next_cursor)
        ids = result['ids']
        next_cursor = result['next_cursor']
        return ids, next_cursor

    def crawl_once(self):
        """One page of followers. Return True if more to do."""
        # get the identifiers of followers - one page worth (up to 5000 people)
        logging.info("Crawling...")
        ids, next_cursor = self.get_more_ids()
        # and then the user details for all the ids
        self.fetch_and_save_users(ids)
        # and now we faff about deciding if we do the timewarp again.
        # TODO TODO TODO TODO TODO I've faffed this up somehow.
        # we have all the info for one page - record got and save it
        self.pages_got += 1
        self.next_cursor = next_cursor

        # While debugging, only do one page to avoid rate limits by uncommenting this:
        # break

        if self.next_cursor == 0:
            logging.warn("Excellent! We've finished a batch!")
            # We've finished a batch
            self.next_cursor = -1
            self.current_batch += 1
            self.save_status("batch-complete")
            return False
        return True

    def crawl_until_done(self):
        if self.batch_status != "batch-complete":
            while self.crawl_once():
                pass
        return False  # batch is complete


    def fetch_and_save_users(self, ids):
	global tw
	logging.info("processing ids {!r}".format(ids[:10]))
	for chunk in chunks(ids, 100):
            logging.info(chunk[:3])
	    users = tw.users.lookup(user_id=(",".join(map(str, chunk))))
	    data = []
	    for user in users:
		datum = convert_user(self.current_batch, user)
		data.append(datum)
	    scraperwiki.sql.save(['id'], data, table_name=self.full_table)
	    # "twitter_followers"
	    self.save_status()
	    logging.info("... ok")

	    # Don't allow more than a certain number
	    if self.batch_got >= MAX_TO_GET:
		raise FollowerLimitError

	    # If being run from the user interface, return quickly after being
	    # sure we've got *something* (the Javascript will then spawn us
	    # again in the background to slowly get the rest)
	    onetime = 'ONETIME' in os.environ
	    if onetime:
                logging.info("We're only processing one page.")
		raise QuickRun


    # Store all our progress variables
    def save_status(self, status="indeterminate"):
	# Update progress indicators...

	# For number of users got, we count the total of:
	# 1) all followers in the last full batch
	# 2) all followers transferred into the new batch so far
	# i.e. all those for whom batch >= (current_batch - 1)
	try:
	    self.batch_got = scraperwiki.sql.select("count(*) as c from %s where batch >= %d" % (self.full_table, self.current_batch - 1))[0]['c']
	except Exception, e:
	    self.batch_got = 0

	data = {
	    'id': self.table_id,
	    'current_batch': self.current_batch,
	    'next_cursor': self.next_cursor,
	    'batch_got': self.batch_got,
	    'batch_expected': self.batch_expected,
	    'current_status': status,
	    'when': datetime.datetime.now().isoformat()

	}
	scraperwiki.sql.save(['id'], data, table_name='__status')


    def get_status(self):
	try:
	    data = scraperwiki.sql.select("* from __status where id='{}'".format(self.table_id))
	except sqlite3.OperationalError, e:
	    if str(e) == "no such table: __status":
		self.set_default_status()
                return
	    raise
	if len(data) == 0:
	    self.set_default_status()
            return
	assert(len(data) == 1)
	data = data[0]
        # global_status = scraperwiki.sql.select("current_status from __status where id='global'")[0]

	self.current_batch = data['current_batch']
	self.next_cursor = data['next_cursor']
	self.batch_got = data['batch_got']
	self.batch_expected = data['batch_expected']
	self.batch_status = data['current_status']

    def set_default_status(self):
        logging.warn("Using default status for {}!".format(self.table_id))
        self.current_batch = 1
        self.next_cursor = -1
        self.batch_got = 0
        self.batch_expected = 0
        self.batch_status = 'default'


#########################################################################
# Main code

def main_function():
    logging.info("main_function()")

    # Rename old status table to new __status name.
    # This can be removed after it has been active long enough to
    # update all existing tools.
    move_legacy_table()

    # Parameters to this command vary:
    #   a. None: try and scrape Twitter followers
    #   b. callback_url oauth_verifier: have just come back from Twitter with these oauth tokens
    #   c. "clean-slate": wipe database and start again
    #   d. "diagnostics": return diagnostics only
    if len(sys.argv) > 1 and sys.argv[1] == 'clean-slate':
        clean_slate()

    # Called for diagnostic information only
    if len(sys.argv) > 1 and sys.argv[1] == 'diagnostics':
        diagnostics = {}
        diagnostics['_rate_limit_status'] = tw.application.rate_limit_status()

        diagnostics['followers_limit'] = diagnostics['_rate_limit_status']['resources']['followers']['/followers/ids']['limit']
        diagnostics['followers_remaining'] = diagnostics['_rate_limit_status']['resources']['followers']['/followers/ids']['remaining']
        diagnostics['followers_reset'] = diagnostics['_rate_limit_status']['resources']['followers']['/followers/ids']['reset']
        diagnostics['friends_limit'] = diagnostics['_rate_limit_status']['resources']['friends']['/friends/ids']['limit']
        diagnostics['friends_remaining'] = diagnostics['_rate_limit_status']['resources']['friends']['/friends/ids']['remaining']
        diagnostics['friends_reset'] = diagnostics['_rate_limit_status']['resources']['friends']['/friends/ids']['reset']
        diagnostics['users_limit'] = diagnostics['_rate_limit_status']['resources']['users']['/users/lookup']['limit']
        diagnostics['users_remaining'] = diagnostics['_rate_limit_status']['resources']['users']['/users/lookup']['remaining']
        diagnostics['users_reset'] = diagnostics['_rate_limit_status']['resources']['users']['/users/lookup']['reset']

        diagnostics['_account_settings'] = tw.account.settings()
        diagnostics['user'] = diagnostics['_account_settings']['screen_name']

        statuses = scraperwiki.sql.select('* from __status')[0]
        diagnostics['status'] = statuses['current_status']

        crontab = subprocess.check_output("crontab -l | grep twfollow.py; true", stderr=subprocess.STDOUT, shell=True)
        diagnostics['crontab'] = crontab

        print json.dumps(diagnostics)
        sys.exit()


    # Get user we're working on from file we store it in
    screen_name = open("user.txt").read().strip()
    followers = TwitterPeople("followers", screen_name)
    following = TwitterPeople("following", screen_name)

    # A batch is one scan through the list of followers - we have to scan as
    # our API calls are limited.  The cursor is Twitter's identifier of where
    # in the current batch we are.

    # Note that each user is only in the most recent batch they've been found in
    # (we don't keep all the history)

    # Look up latest followers count
    profile = tw.users.lookup(screen_name=screen_name)
    logging.debug("User details: {!r}".format(profile))
    followers.batch_expected = profile[0]['followers_count']
    following.batch_expected = profile[0]['friends_count']
    logging.info("Batches expected: {!r}, {!r}".format(followers.batch_expected, following.batch_expected))

    # Things basically working, so make sure we run again by writing a crontab.
    install_crontab()

    # Get as many pages in the batch as we can (most likely 15!)

    # pages_got = followers.crawl_once()
    stopped_early = False

    try:
        followers.crawl_until_done()
    except QuickRun:
        stopped_early = True
        pass

    try:
        following.crawl_until_done()
    except QuickRun:
        stopped_early = True
        pass

    if stopped_early:
        set_status_and_exit("ok-updating", 'ok', "Running... %d/%d" % (followers.batch_got + following.batch_got, following.batch_expected + followers.batch_expected))

    # We're done here.
    shutdown() #_if_static_dataset()




def output_example_data():
    with open("ids.json", "w") as f:
        response = tw.followers.ids(screen_name='dragondave',
                                    cursor=-1)
        f.write(json.dumps(response))
    with open("lookup_1.json", "w") as f:
        response = tw.users.lookup(screen_name='dragondave')
        f.write(json.dumps(response))
    ids = [2151045530, 14284208, 537386838, 72015710]
    with open("lookup_many.json", "w") as f:
        response = tw.users.lookup(user_id=(",".join(map(str, ids))))
        f.write(json.dumps(response))
    logging.critical("Example data provided. Exiting.")
    exit()



try:
    tw = do_tool_oauth()
    # output_example_data()
    main_function()
except twitter.api.TwitterHTTPError, e:
    if "Twitter sent status 401 for URL" in str(e):
        clear_auth_and_restart()

    # https://dev.twitter.com/docs/error-codes-responses
    obj = json.loads(e.response_data)
    code = obj['errors'][0]['code']
    logging.warn("Twitter Error {!r}".format(code))
    # authentication failure
    if (code in [32, 89]):
        clear_auth_and_restart()
    # page not found
    if code == 34:
        set_status_and_exit('not-there', 'error', 'User not on Twitter')
    # rate limit exceeded
    if code == 88:
        # provided we got at least one page, rate limit isn't an error but expected
        set_status_and_exit('rate-limit', 'error', 'Twitter has asked us to slow down')
    else:
        # anything else is an unexpected error - if ones occur a lot, add the above instead
        raise
except httplib.IncompleteRead, e:
    logging.warn("Incomplete Read")
    # I think this is effectively a rate limit error - so only count if it was first error
    if pages_got == 0:
        set_status_and_exit('rate-limit', 'error', 'Twitter broke the connection')
except FollowerLimitError, e:
    logging.warn("Follower Limit reached")
    os.system("crontab -r >/dev/null 2>&1")
    set_status_and_exit("ok-limit", 'ok', "Reached %d person limit" % MAX_TO_GET)
