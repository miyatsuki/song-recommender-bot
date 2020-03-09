import json
from requests_oauthlib import OAuth1Session
from http import HTTPStatus
from datetime import datetime
import math
import random

def get_mentions(twitter):
    # ツイート処理
    res = twitter.get("https://api.twitter.com/1.1/statuses/mentions_timeline.json", params={"count": 200})

    # エラー処理
    if res.status_code != HTTPStatus.OK:
        print(f"Failed: {res.status_code}")
        return []
    
    mentions = []
    for mention in res.json():

        # 会話中の@mentionは無視する
        if mention["in_reply_to_status_id_str"]:
            continue

        unixtime = int(datetime.strptime(mention["created_at"], '%a %b %d %H:%M:%S %z %Y').timestamp())
        mentions.append((unixtime, mention["user"]["screen_name"], mention["text"], mention["id"]))

    return mentions


def get_new_tweets(twitter, screen_name):
    # ツイート処理
    res = twitter.get("https://api.twitter.com/1.1/statuses/user_timeline.json", params={"screen_name": screen_name, "count": 20})

    # エラー処理
    tweets = []
    if not res.status_code == HTTPStatus.OK:
        print(f"Failed: {res.status_code}")
        return []

    for res_i in res.json():
        print(res_i["text"])
        tweet = res_i["text"]
        if "@" in tweet:
            continue

        tweets.append(tweet)

        if len(tweets) >= 5:
            break

    return tweets

N = 1
def get_wv_from_tweets(features, feature_idf_map, tweets):
    wv = [0.0] * len(features)

    count = 0
    for tweet in tweets:
        for i in range(len(tweet) - N + 1):
            token = tweet[i:i+N]
            if token in features:
                # この時点でidfを計算
                wv[features.index(token)] += feature_idf_map[token]
                count += 1

    if count == 0:
        return

    # tf対応
    for i in range(len(wv)):
        wv[i] /= count

    # L2正規化
    l2_acc = 0
    for val in wv:
        l2_acc += val * val

    for i in range(len(wv)):
        wv[i] /= math.sqrt(l2_acc)

    return wv

def get_nearest_title(title_vector_map, wv):
    max_sim = 0
    max_title = None

    for title, vec in title_vector_map.items():
        sim = 0
        for val_wv, val_test in zip(vec, wv):
            sim += val_wv * val_test

        if sim > max_sim:
            print(title, sim)
            max_sim = sim
            max_title = title

    if sim == 0:
        return
    else:
        return max_title

def post_tweet(twitter, body, reply_id):
    res = twitter.post("https://api.twitter.com/1.1/statuses/update.json", params={"status": body, "in_reply_to_status_id": reply_id})
    print(res)

    # エラー処理
    if res.status_code == HTTPStatus.OK:
        print("Successfuly posted: ", body)
    else:
        print(f"Failed: {res.status_code}")
        print(body)


def lambda_handler(event, context):
    """Sample pure Lambda function

    Parameters
    ----------
    event: dict, required
        API Gateway Lambda Proxy Input Format

        Event doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format

    context: object, required
        Lambda Context runtime methods and attributes

        Context doc: https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    Returns
    ------
    API Gateway Lambda Proxy Output Format: dict

        Return doc: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
    """

    with open("secrets.json") as f:
        keys = json.load(f)

    # twitter操作用クラス
    twitter = OAuth1Session(
        keys["CONSUMER_KEY"],
        keys["CONSUMER_SECRET"],
        keys["ACCESS_TOKEN_KEY"],
        keys["ACCESS_TOKEN_SECRET"]
    )

    current_unixtime = datetime.now().timestamp()

    # mention = (unixtime, screen_name, text, id)
    mentions = get_mentions(twitter)
    if not mentions:
        print("failed to recieve mentions")
        return
    else:
        print(mentions)

    # check for new mentions
    new_mentioned_user_map = {}
    minute_thr = 5
    for mention in mentions:
        if current_unixtime <= mention[0] + 60 * minute_thr:
            screen_name = mention[1]
            status_id = mention[3]

            if screen_name not in new_mentioned_user_map:
                new_mentioned_user_map[screen_name] = status_id

    if not new_mentioned_user_map:
        print("no new mentions")
        return

    user_tweets_map = {}
    for screen_name in new_mentioned_user_map.keys():
        tweets =  get_new_tweets(twitter, screen_name)
        if tweets:
            user_tweets_map[screen_name] = tweets

    if not user_tweets_map:
        print("failed to fetch tweets")
        return
    else:
        print(user_tweets_map)

    with open("features.json") as f:
        features = json.load(f)

    with open("feature_idf.json") as f:
        feature_idf_map = json.load(f)

    user_wv_map = {}
    for screen_name, tweets in user_tweets_map.items():
        wv = get_wv_from_tweets(features, feature_idf_map, tweets)
        if wv:
            user_wv_map[screen_name] = wv

    if not user_wv_map:
        print("failed to get tokens")
        return
    else:
        print(user_wv_map)

    with open("title_tfidf.json") as f:
        title_vector_map = json.load(f)

    user_title_map = {}
    for screen_name, wv in user_wv_map.items():
        nearest_title = get_nearest_title(title_vector_map, wv)
        if nearest_title:
            user_title_map[screen_name] = nearest_title

    if not user_title_map:
        print("failed to get tokens")
        return
    else:
        print(user_title_map)

    with open("url_map.json") as f:
        title_url_map = json.load(f)


    random_sentences = [
        "こちらの曲はいかがでしょうか",
        "こちらの曲をどうぞ",
        "この曲がオススメです",
        "この曲はどうですか"
    ]
    for screen_name, title in user_title_map.items():
        sentence = random.choice(random_sentences)
        reply_id = new_mentioned_user_map[screen_name]
        post_tweet(twitter, "@{} {}\n{}\n{}".format(screen_name, sentence, title, title_url_map[title]), reply_id)

    return
