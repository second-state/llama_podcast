import requests
import feedparser

from loguru import logger


# I love bilibili
def get_bilibili_hot_search(limit=20):
    response = requests.get(
        f"https://api.bilibili.com/x/web-interface/wbi/search/square?limit={limit}&platform=web",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        },
    )
    if response.status_code == 200:
        data = response.json()
        if data["code"] != 0:
            logger.error(f"Failed to get bilibili hot news")
            err_msg = data["message"]
            logger.error(f"Response: {err_msg}")
            return []
        else:
            return [k["keyword"] for k in data["data"]["trending"]["list"]]
    else:
        logger.error(f"Failed to get bilibili hot news")
        logger.error(f"Response: {response.text}")
        return []


def make_search_function_from_imsyy_url(url):
    def get_hot_search():
        print(url)
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
            },
        )
        if response.status_code == 200:
            data = response.json()
            if data["code"] != 200:
                logger.error(f"Failed to get hot news")
                err_msg = data["message"]
                logger.error(f"Response: {err_msg}")
                return []
            else:
                return [k["title"] for k in data["data"]]
        else:
            logger.error(f"Failed to get hot news")
            logger.error(f"Response: {response.text}")
            return []

    return get_hot_search


get_weibo_hot_search = make_search_function_from_imsyy_url(
    "https://api-hot.imsyy.top/weibo?cache=false"
)

get_douyin_hot_search = make_search_function_from_imsyy_url(
    "https://api-hot.imsyy.top/douyin?cache=false"
)

get_zhihu_hot_search = make_search_function_from_imsyy_url(
    "https://api-hot.imsyy.top/zhihu?cache=false"
)

get_toutiao_hot_search = make_search_function_from_imsyy_url(
    "https://api-hot.imsyy.top/toutiao?cache=false"
)

get_netease_news_hot_search = make_search_function_from_imsyy_url(
    "https://api-hot.imsyy.top/netease-news?cache=false"
)


def make_rss_function_from_url(url):
    def get_rss_feed():
        feed = feedparser.parse(url)
        if feed != None:
            return [e.title for e in feed.entries]
        else:
            return []


class InfoProvider:
    def __init__(self, funcs):
        self.providers = funcs
        self.index = 0
        self.length = len(funcs)
        self.cache = set()

    def add_provider(self, provider):
        self.providers.append(provider)
        self.length += 1

    def poll(self):
        data = self.providers[self.index]()
        self.index = (self.index + 1) % self.length
        data = set(data)
        data = data - self.cache
        self.cache = self.cache.union(data)
        return data
