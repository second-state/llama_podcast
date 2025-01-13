import requests
from loguru import logger


# I love bilibili
def get_bilibili_hot_news(limit=20):
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
            return None
        else:
            return [k["keyword"] for k in data["data"]["trending"]["list"]]
    else:
        logger.error(f"Failed to get bilibili hot news")
        logger.error(f"Response: {response.text}")
        return None
