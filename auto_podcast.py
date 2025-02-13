import argparse
from gpt_researcher import GPTResearcher
from loguru import logger
import requests
import llama_podcast
import os
import openai
import json
import dotenv
import asyncio
import time

import llama_podcast.hot_news

dotenv.load_dotenv()

lang = os.environ.get("PODCAST_LANG", "zh")
if lang == "zh":
    default_sys_prompt0 = llama_podcast.CN_SYSTEMP_PROMPT_0
    default_sys_prompt1 = llama_podcast.CN_SYSTEMP_PROMPT_1
    default_sys_prompt2 = llama_podcast.CN_SYSTEMP_PROMPT_2
else:
    default_sys_prompt0 = llama_podcast.EN_SYSTEMP_PROMPT_0
    default_sys_prompt1 = llama_podcast.EN_SYSTEMP_PROMPT_1
    default_sys_prompt2 = llama_podcast.EN_SYSTEMP_PROMPT_2

script_path = os.environ.get("SCRIPT_PROMPT", None)
if script_path is not None and os.path.exists(script_path):
    with open(script_path, "r") as file:
        default_sys_prompt1 = file.read()

api_key = os.environ.get("OPENAI_API_KEY", "NA")
base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

if lang == "zh":
    speaker1 = os.environ.get("SPEAKER1", "cctv_male_anchor")
    speaker2 = os.environ.get("SPEAKER2", "cctv_female_anchor")
else:
    speaker1 = os.environ.get("SPEAKER1", "cooper")
    speaker2 = os.environ.get("SPEAKER2", "kelly")

vtb_speaker1 = os.environ.get("VTB_SPEAKER1", "speaker1")
vtb_speaker2 = os.environ.get("VTB_SPEAKER2", "speaker2")
vtb_speaker1_motion = os.environ.get("VTB_SPEAKER1_MOTION", "")
vtb_speaker2_motion = os.environ.get("VTB_SPEAKER2_MOTION", "")

tts_base_url = os.environ.get("TTS_BASE_URL")

llm_model = os.environ.get("LLM_MODEL", "llama")

sleep_sec = float(os.environ.get("SLEEP_SEC", "20"))


def tts(base_url, speaker, text):
    # 发起HTTP请求到后端，获取wav文件

    response = requests.post(
        base_url,
        json={"speaker": speaker, "input": text},
    )
    # 确保请求成功
    if response.status_code == 200:
        return response.content
    else:
        logger.error(f"Failed to get audio from {base_url}")
        logger.error(f"Response: {response.text}")
        return None


def generate_llm(
    llm_model_name: str,
    llm_sys_prompt,
    input_prompt,
):
    openapi_client = openai.Client(
        base_url=base_url,
        api_key=api_key,
        timeout=1000 * 60 * 60,
    )

    messages = [
        {"role": "system", "content": llm_sys_prompt},
        {"role": "user", "content": input_prompt},
    ]
    response = openapi_client.chat.completions.create(
        messages=messages, model=llm_model_name, stream=True
    )
    outputs = ""
    for chunk in response:
        if chunk.choices[0].delta.content != None:
            outputs += chunk.choices[0].delta.content
        else:
            return outputs
    return outputs


def generate_voice_with_list(script, speaker1, speaker2):

    output = []
    script_size = len(script)
    for i, text in enumerate(script):
        speaker, text = text
        if speaker == "Speaker 1":
            audio = tts(tts_base_url, speaker1, text)
        else:
            audio = tts(tts_base_url, speaker2, text)
        if audio is None:
            logger.error(f"Failed to generate audio for {speaker}")
            return None
        logger.info(f"Generated audio for {speaker} ({i+1}/{script_size})")
        output.append((speaker, text, audio))

    return output


def generate_voice(llm_input, speaker1, speaker2):
    try:
        texts = json.loads(llm_input)
    except:
        logger.error("Failed to parse input")
        return None

    return generate_voice_with_list(texts, speaker1, speaker2)


async def get_news_from_web(query):
    if lang == "zh":
        config_path = "config.json"
    else:
        config_path = None

    researcher = GPTResearcher(
        query=query, report_type="research_report", config_path=config_path
    )
    # Conduct research on the given query
    await researcher.conduct_research()
    # Write the report
    report = await researcher.write_report()
    return report


def get_report(query):
    task = get_news_from_web(query)
    report = asyncio.run(task)
    return report


def create_report_from_file(query_path):
    logger.info(f"Creating report from file {query_path}")
    with open(query_path, "r") as file:
        query = file.read()
    report = get_report(query)
    if report is None or report == "":
        return None

    dir_id = os.path.dirname(query_path)
    report_path = os.path.join(dir_id, "report.txt")
    with open(report_path, "w") as file:
        file.write(report)
    return report_path


def split_sub_topic(article):
    logger.info(f"Split Sub Topic from article")
    llm_input = generate_llm(llm_model, default_sys_prompt0, article)
    if llm_input is None:
        return None
    sub_topics = []
    topics = llm_input.split("\n")
    for i, topic in enumerate(topics):
        if topic.strip() == "":
            continue
        sub_topics.append(topic)
    return sub_topics


def create_script(article, topic):
    logger.info(f"Creating script with topic {topic}")

    llm_input = generate_llm(
        llm_model,
        default_sys_prompt1 + "\n<article>\n" + article + "\n</article>",
        topic,
    )
    if llm_input is None:
        return None
    script = []
    lines = iter(llm_input.split("\n"))
    for line in lines:
        if line.strip() == "":
            continue
        if line.startswith("Speaker 1:"):
            speaker1_text = line.removeprefix("Speaker 1:")
            script.append(["Speaker 1", speaker1_text])
        elif line.startswith("Speaker 2:"):
            speaker2_text = line.removeprefix("Speaker 2:")
            script.append(["Speaker 2", speaker2_text])
        else:
            if len(script) > 0:
                script[-1][1] += "\n" + line
    return script


def create_voice(script, dir_path):
    logger.info(f"Creating voice")

    voice = generate_voice_with_list(script, speaker1, speaker2)
    if voice is None:
        return None
    streaming_list = []
    for i, (speaker, text, audio) in enumerate(voice):
        wav_path = os.path.join(dir_path, f"segments_{i}.wav")
        with open(wav_path, "wb") as file:
            file.write(audio)
        streaming_list.append((speaker, text, wav_path))

    streaming_list_path = os.path.join(dir_path, "streaming_list.json")
    with open(streaming_list_path, "w") as file:
        file.write(json.dumps(streaming_list, ensure_ascii=False, indent=4))

    return streaming_list_path


def push_to_streaming_service_from_file(streaming_list_path):
    logger.info(f"Pushing to streaming service from file {streaming_list_path}")
    with open(streaming_list_path, "r") as file:
        streaming_list = json.load(file)
    try_push_to_streaming_service(streaming_list)


def auto_podcast(path):
    with open(path, "r") as file:
        article = file.read()

    dir_path = os.path.dirname(path)

    sub_topics = split_sub_topic(article)
    if sub_topics is None:
        return None
    # logger.info(f"Sub Topics: {sub_topics}")
    for i, sub_topic in enumerate(sub_topics):
        script = create_script(article, sub_topic)
        sub_topic_path = os.path.join(dir_path, f"sub_topic_{i}")
        if not os.path.exists(sub_topic_path):
            os.makedirs(sub_topic_path)

        if script is None:
            return None
        streaming_list_path = create_voice(script, sub_topic_path)
        if streaming_list_path is None:
            return None
        push_to_streaming_service_from_file(streaming_list_path)


def try_push_to_streaming_service(streaming_list):
    streaming_server_base_url = os.environ.get("STREAMING_SERVER_BASE_URL")
    if streaming_server_base_url is None:
        logger.warning("Streaming server base URL is not set")
        return None
    for speaker, text, audio in streaming_list:
        if speaker == "Speaker 1":
            vtb_name = vtb_speaker1
            motion = vtb_speaker1_motion
        else:
            vtb_name = vtb_speaker2
            motion = vtb_speaker2_motion

        logger.debug(f"Pushing {vtb_name} to {streaming_server_base_url}")
        logger.debug(f"Text: {text}")
        logger.debug(f"Audio: {audio}")

        response = requests.post(
            streaming_server_base_url,
            data={"vtb_name": vtb_name, "text": text, "motion": motion},
            files={"voice": (audio, open(audio, "rb"))},
        )
        logger.debug(response.status_code)


from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading


class MyHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.condition = threading.Condition()
        self.trigger = ""
        self.version = 0

    def on_closed(self, event):
        if not event.is_directory:
            logger.info(f"File {event.src_path} has been {event.event_type}")
            with open("./trigger", "r") as file:
                trigger = file.read()
            if trigger != self.trigger:
                self.trigger = trigger
                self.version += 1
                logger.info(f"Trigger updated to {self.trigger}")
                with self.condition:
                    self.condition.notify()


def auto_hot_search_podcast():
    provider = llama_podcast.hot_news.InfoProvider(
        [
            llama_podcast.hot_news.get_weibo_hot_search,
            llama_podcast.hot_news.get_douyin_hot_search,
            llama_podcast.hot_news.get_zhihu_hot_search,
            llama_podcast.hot_news.get_toutiao_hot_search,
            llama_podcast.hot_news.get_netease_news_hot_search,
        ]
    )

    local_time = time.localtime()
    local_time_str = time.strftime("%Y%m%d_auto_", local_time)

    if not os.path.exists("./output"):
        os.makedirs("./output")

    i = -1
    for f in os.listdir("./output"):
        logger.info(f"Checking {f}")
        logger.info("Checking {}", f.startswith(local_time_str))
        if f.startswith(local_time_str):
            i = max(i, int(f.removeprefix(local_time_str)))
            logger.info(f"Found existing folder {f}")
    i += 1

    while True:
        topics = provider.poll()
        for topic in topics:
            if not os.path.exists(f"./output/{local_time_str}{i}"):
                os.makedirs(f"./output/{local_time_str}{i}")

            query_path = f"./output/{local_time_str}{i}/query.txt"
            logger.info(f"Writing query to {query_path}")
            with open(query_path, "w") as file:
                file.write(topic)
            try:
                auto_podcast(query_path)
            except Exception as e:
                logger.error(f"Failed to auto podcast from {query_path}")
                logger.error(e)
            i += 1
            time.sleep(sleep_sec)


def auto_file_podcast_(event_handler):
    current_version = event_handler.version
    logger.info("Starting auto podcast from file {}", current_version)
    if not os.path.exists("./topics_paths"):
        os.open("./topics_paths", os.O_CREAT)

    with open("./topics_paths", "r") as file:
        topics = [p.strip().split(",") for p in file.readlines()]
    for topic in topics:
        if len(topic) != 2:
            logger.error(f"Invalid topic {topic}")
            continue
        try:
            auto_podcast(topic[1])
        except Exception as e:
            logger.error(f"Failed to auto podcast from {topic[1]}")
            logger.error(e)
        if event_handler.version != current_version:
            return
        time.sleep(sleep_sec)
    logger.info("Waiting for new topics")
    with event_handler.condition:
        event_handler.condition.wait()


def auto_file_podcast():
    event_handler = MyHandler()
    observer = Observer()
    if not os.path.exists("./trigger"):
        os.open("./trigger", os.O_CREAT)

    observer.schedule(event_handler, path="./trigger", recursive=False)
    observer.start()
    try:
        while True:
            auto_file_podcast_(event_handler)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto Podcast")
    parser.add_argument(
        "files", metavar="FILE", type=str, nargs="+", help="a file to be processed"
    )

    args = parser.parse_args()
    # auto_hot_search_podcast()
    for file_path in args.files:
        auto_podcast(file_path)
