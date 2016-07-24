#!/usr/bin/env python3
import yaml
from pymongo.mongo_client import MongoClient
from get_tweepy import *

def main():
    retweet()

def get_ignore_users():
    """
    ファイルからignore_usersを取得する
    """
    with open('kinpri.yaml') as f:
        ignore_users = yaml.load(f)['ignore_users']
    return ignore_users
    
def make_doc(t):
    """
    tweepy.Statusから、DBに記録するためのdictを作る
    """
    doc = {}
    doc['_id'] = t.id
    doc['data'] = t._json
    doc['meta'] = {'retweeted': False, 'time': t.created_at}
    return doc

def is_right_tweet(t):
    """
    ツイートがRT対象かどうかを判定する述語
    """
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
    """
    古い順に並べたツイートリストを返す
    """
    return list(reversed(list(tweepy.Cursor(api.search, q='{tag} -RT'.format(tag=tag), count=200).items())))

def retweet():
    """
    実際にリツイートを行う関数
    """
    for t in get_all_tweet_by_search():
        # DBにあるものはスキップする
        if c.find({'_id': t.id}).count():
            continue
        # 正しい対象のみ処理する
        if is_right_tweet(t):
            try:
                # ドキュメントを作って、リツイートして、DBに登録
                doc = make_doc(t)
                c.insert(doc)
                api.retweet(doc['_id'])
                c.update({'_id': doc['_id']}, {'$set': {'meta.retweeted': True}})
            except tweepy.TweepError as e:
                print_tweet(t)
                # 削除されている(144)か鍵がかかっていた(328)場合は、エラーを記録して終わり
                if e.api_code == 144 or e.api_code == 328:
                    c.update({'_id': doc['_id']}, {'$set': {'meta.error': e.reason}})
                # すでにRTしていた(327)場合は、リツイート済みフラグを立てる
                elif e.api_code == 327:
                    c.update({'_id': doc['_id']}, {'$set': {'meta.retweeted': True}})
                else:
                    raise

if __name__ == '__main__':
    tag = '#キンプリ深夜の真剣お絵かき60分一本勝負'
    ignore_users = get_ignore_users()

    api = get_api('knpr_1draw_rt')
    c = MongoClient().kinpri_1draw.tweets
    
    main()
