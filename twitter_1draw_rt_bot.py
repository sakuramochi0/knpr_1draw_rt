#!/usr/bin/env python3
import datetime
import re
import argparse

import yaml
import tweepy
from dateutil.parser import parse
from get_mongo_client import get_mongo_client

from get_tweepy import get_api

def get_ignore_users():
    """ファイルからignore_usersを取得する。"""
    with open('ignores.yaml') as f:
        ignore_users = yaml.load(f)['ignore_users']
    return ignore_users
    
def get_ignore_dates():
    """ファイルからignore_usersを取得する。"""
    with open('ignores.yaml') as f:
        ignore_dates = yaml.load(f)['ignore_dates']
        ignore_dates = set(map(convert_date_to_datetime, ignore_dates))
    return ignore_dates

def get_ignore_ids():
    """ファイルからignore_idsを取得する。"""
    with open('ignores.yaml') as f:
        ignore_ids = yaml.load(f)['ignore_ids']
    return ignore_ids
    
def convert_date_to_datetime(date):
    """Convert Date object to Datetime object."""
    return datetime.datetime.fromordinal(date.toordinal())

def make_doc(t):
    """tweepy.Statusから、DBに記録するためのdictを作る。"""
    doc = {
        '_id': t.id,
        'data': t._json,
        'meta': {
            'retweeted': False,
            # GMTを日本時間に直す(+9時間)
            'time': t.created_at + datetime.timedelta(hours=9),
        },
    }
    return doc

def make_status_url(t):
    return 'https://twitter.com/{sn}/status/{id}'.format(
        sn = t.user.screen_name,
        id = t.id,
    )

def is_right_tweet(t):
    """ツイートがRT対象かどうかを判定する述語。"""
    if type(t) is tweepy.Status:
        t = t._json
    elif type(t) is dict and 'data' in t:
        t = t['data']
    else:
        raise ValueError('t is not valid document or tweepy.Status')
        
    urls = [url['expanded_url'] for url in t['entities']['urls']]
    return ('media' in t['entities'] \
            or any(['twitpic.com/' in url \
                    or 'pixiv.net/' in url \
                    or 'tl.gd/' in url \
                    or 'twipple.jp/' in url \
                    for url in urls]) \
            ) \
            and not t['in_reply_to_status_id'] \
            and not t['is_quote_status'] \
            and 'retweeted_status' not in t \
            and t['user']['screen_name'] not in IGNORE_USERS \
            and t['id'] not in IGNORE_IDS

def get_all_tweet_by_search():
    """古い順に並べたツイートリストを返す。"""
    ts = list(reversed(list(
        tweepy.Cursor(api.search,
                      q='{tag} -RT'.format(tag=tag),
                      count=200).items()
    )))
    return ts

def retweet():
    """実際にリツイートを行う関数。"""
    ts = get_all_tweet_by_search()# + \
         #api.user_timeline(screen_name=settings['main_screen_name'], count=200)
    for t in ts:
        # DBにあるものはスキップする
        if tws.find({'_id': t.id}).count():
            continue
        # 正しい対象のみ処理する
        print_tweet(t)
        if not args.dry_run and is_right_tweet(t):
            try:
                # ドキュメントを作って、リツイートして、DBに登録
                doc = make_doc(t)
                api.retweet(doc['_id'])
                tws.insert(doc)
                tws.update({'_id': doc['_id']}, {'$set': {'meta.retweeted': True}})
            except tweepy.TweepError as e:
                print(t._json)
                # 削除されている(144)か鍵がかかっていた(328)場合は、エラーを記録して終わり
                if e.api_code == 144 or e.api_code == 328:
                    tws.update({'_id': doc['_id']}, {'$set': {'meta.error': e.reason}})
                # すでにRTしていた(327)場合は、リツイート済みフラグを立てる
                elif e.api_code == 327:
                    tws.update({'_id': doc['_id']}, {'$set': {'meta.retweeted': True}})
                else:
                    raise

def print_tweet(t):
    if is_right_tweet(t):
        right_text = '⭕ right tweet!'
    else:
        right_text = '✗ not right tweet'
    print('-' * 8)
    print(right_text, get_status_url(t))
    print('{u.name}(@{u.screen_name})'.format(u=t.user))
    print(t.text)

def get_status_url(t):
    return 'https://twitter.com/{sn}/status/{id}'.format(
        sn = t.user.screen_name,
        id = t.id_str,
    )

def update_themes():
    """Update themes database with 1draw main account's tweets in tweets database."""
    num = 0
    for d in tws.find({
            'data.user.screen_name': settings['main_screen_name'],
    }).sort('_id'):
        # DBにあるものはスキップする
        themes = get_themes(d)
        date = get_date(d)
        if themes and date not in IGNORE_DATES:
            num += 1
            doc = {
                '_id': d['_id'],
                'num': num,
                'date': date,
                'themes': themes,
            }
            ths.update({'_id': d['_id']}, doc, upsert=True)
        
def get_themes(doc):
    """Get themes of the date from given tweet doc."""
    return re.findall(r'「(.+?)」', doc['data']['text'])

def get_date(doc):
    """Get datetime object of the date when tweet doc is published."""
    date = doc['meta']['time'].date()
    date = convert_date_to_datetime(date)
    return date

def get_settings(account):
    with open('settings.yaml') as f:
        settings = yaml.load(f).get(account)
    if not settings:
        raise ValueError('There is no account name', account)
    return settings

if __name__ == '__main__':
    print(datetime.datetime.now())

    IGNORE_USERS = get_ignore_users()
    IGNORE_DATES = get_ignore_dates()
    IGNORE_IDS = get_ignore_ids()
    
    parser = argparse.ArgumentParser()
    parser.add_argument('account')
    parser.add_argument('command', choices=['retweet', 'update_themes'])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    settings = get_settings(args.account)
    print(settings)
    api = get_api(settings['rt_bot_screen_name'])
    tag = settings['tag']
    tws = get_mongo_client()[settings['db_name']].tweets
    ths = get_mongo_client()[settings['db_name']].themes

    if args.command == 'retweet':
        retweet()
    elif args.command == 'update_themes':
        update_themes()
