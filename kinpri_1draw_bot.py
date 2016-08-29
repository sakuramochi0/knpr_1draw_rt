#!/usr/bin/env python3
import datetime

import argparse
import yaml
from pymongo.mongo_client import MongoClient

from get_tweepy import *

def get_ignore_users():
    """ファイルからignore_usersを取得する。"""
    with open('ignores.yaml') as f:
        ignore_users = yaml.load(f)['ignore_users']
    return ignore_users
    
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

def is_right_tweet(t):
    """ツイートがRT対象かどうかを判定する述語。"""
    if type(t) is dict:
        return \
            t['data']['user']['screen_name'] == 'knpr_1draw' \
            or 'media' in t['data']['entities'] \
            and not t['data']['in_reply_to_status_id'] \
            and not t['data']['is_quote_status'] \
            and 'retweeted_status' not in t['data'] \
            and t['data']['user']['screen_name'] not in ignore_users
    else:
        return \
            t.user.screen_name == 'knpr_1draw' \
            or 'media' in t.entities \
            and not t.in_reply_to_status_id \
            and not t.is_quote_status \
            and 'retweeted_status' not in t._json \
            and t.user.screen_name not in ignore_users

def get_all_tweet_by_search():
    """古い順に並べたツイートリストを返す。"""
    return list(reversed(list(tweepy.Cursor(api.search, q='{tag} -RT'.format(tag=tag), count=200).items())))

def retweet():
    """実際にリツイートを行う関数。"""
    ts = get_all_tweet_by_search() + api.user_timeline(screen_name='knpr_1draw', count=200)
    for t in ts:
        # DBにあるものはスキップする
        if tweets.find({'_id': t.id}).count():
            continue
        # 正しい対象のみ処理する
        if is_right_tweet(t):
            try:
                # ドキュメントを作って、リツイートして、DBに登録
                doc = make_doc(t)
                tweets.insert(doc)
                api.retweet(doc['_id'])
                tweets.update({'_id': doc['_id']}, {'$set': {'meta.retweeted': True}})
            except tweepy.TweepError as e:
                print_tweet(t)
                # 削除されている(144)か鍵がかかっていた(328)場合は、エラーを記録して終わり
                if e.api_code == 144 or e.api_code == 328:
                    tweets.update({'_id': doc['_id']}, {'$set': {'meta.error': e.reason}})
                # すでにRTしていた(327)場合は、リツイート済みフラグを立てる
                elif e.api_code == 327:
                    tweets.update({'_id': doc['_id']}, {'$set': {'meta.retweeted': True}})
                else:
                    raise

def update_themes():
    """Update themes database with 1draw main account's tweets in tweets database."""
    num = 0
    for d in tweets.find({'data.user.screen_name': 'knpr_1draw'}).sort('_id'):
        # DBにあるものはスキップする
        if themes.find({'_id': d['_id']}).count():
            continue
        themes = get_themes(d)
        date = get_date(d)
        if themes:
            num += 1
            doc = {
                '_id': d['_id'],
                'num': num,
                'date': date,
                'themes': themes,
                'ignore': False
            }
            print(doc)
            themes.insert(doc)
        
def get_themes(doc):
    """Get themes of the date from given tweet doc."""
    return re.findall(r'「(.+?)」', doc['data']['text'])

def get_date(doc):
    """Get datetime object of the date when tweet doc is published."""
    date = doc['meta']['time'].date()
    # Convert to datetime object in order to save to MongoDB
    date = datetime.datetime.fromordinal(date.toordinal())
    return date

if __name__ == '__main__':
    tag = '#キンプリ深夜の真剣お絵かき60分一本勝負'
    ignore_users = get_ignore_users()

    api = get_api('knpr_1draw_rt')
    tweets = MongoClient().kinpri_1draw.tweets
    themes = MongoClient().kinpri_1draw.themes
    
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['retweet', 'update_themes'])
    args = parser.parse.args()

    if args.command == 'retweet':
        retweet()
    elif args.command == 'update_themes':
        update_themes()
