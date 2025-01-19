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
    default_sys_prompt1 = llama_podcast.CN_SYSTEMP_PROMPT_1
    default_sys_prompt2 = llama_podcast.CN_SYSTEMP_PROMPT_2
else:
    default_sys_prompt1 = llama_podcast.EN_SYSTEMP_PROMPT_1
    default_sys_prompt2 = llama_podcast.EN_SYSTEMP_PROMPT_2

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


def generate_voice(llm_input, speaker1, speaker2):
    try:
        texts = json.loads(llm_input)
    except:
        logger.error("Failed to parse input")
        return None

    text_len = len(texts)
    output = []
    for i, text in enumerate(texts):
        speaker, text = text
        if speaker == "Speaker 1":
            audio = tts(tts_base_url, speaker1, text)
        else:
            audio = tts(tts_base_url, speaker2, text)
        if audio is None:
            logger.error(f"Failed to generate audio for {speaker}")
            return None
        logger.info(f"Generated audio for {speaker} ({i+1}/{text_len})")
        output.append((speaker, text, audio))

    return output


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


def create_script_from_file(text_path):
    logger.info(f"Creating script from file {text_path}")
    with open(text_path, "r") as file:
        report = file.read()
    llm_input = generate_llm(llm_model, default_sys_prompt1, report)
    if llm_input is None:
        return None
    dir_id = os.path.dirname(text_path)
    script_path = os.path.join(dir_id, "script.txt")
    with open(script_path, "w") as file:
        file.write(llm_input)
    return script_path


def create_optimized_script_from_file(script_path):
    logger.info(f"Creating optimized script from file {script_path}")
    with open(script_path, "r") as file:
        llm_input = file.read()

    dir_id = os.path.dirname(script_path)
    script_path = os.path.join(dir_id, "script.json")
    output = generate_llm(llm_model, default_sys_prompt2, llm_input)
    with open(script_path, "w") as file:
        file.write(output)
    return script_path


def create_voice_from_file(script_path):
    logger.info(f"Creating voice from file {script_path}")

    with open(script_path, "r") as file:
        script = file.read()
    voice = generate_voice(script, speaker1, speaker2)
    if voice is None:
        return None
    dir_id = os.path.dirname(script_path)
    streaming_list = []
    for i, (speaker, text, audio) in enumerate(voice):
        wav_path = os.path.join(dir_id, f"segments_{i}.wav")
        with open(wav_path, "wb") as file:
            file.write(audio)
        streaming_list.append((speaker, text, wav_path))

    streaming_list_path = os.path.join(dir_id, "streaming_list.json")
    with open(streaming_list_path, "w") as file:
        file.write(json.dumps(streaming_list, ensure_ascii=False, indent=4))

    return streaming_list_path


def push_to_streaming_service_from_file(streaming_list_path):
    logger.info(f"Pushing to streaming service from file {streaming_list_path}")
    with open(streaming_list_path, "r") as file:
        streaming_list = json.load(file)
    try_push_to_streaming_service(streaming_list)


def auto_podcast(path, start_step=0, end_step=4):
    if start_step <= 0 and 0 <= end_step:
        if not os.path.exists(path):
            logger.error(f"File {path} does not exist")
            return
        path = create_report_from_file(path)
    if start_step <= 1 and 1 <= end_step:
        if not os.path.exists(path):
            logger.error(f"File {path} does not exist")
            return
        path = create_script_from_file(path)
    if start_step <= 2 and 2 <= end_step:
        if not os.path.exists(path):
            logger.error(f"File {path} does not exist")
            return
        path = create_optimized_script_from_file(path)
    if start_step <= 3 and 3 <= end_step:
        if not os.path.exists(path):
            logger.error(f"File {path} does not exist")
            return
        path = create_voice_from_file(path)
    if start_step <= 4 and 4 <= end_step:
        if not os.path.exists(path):
            logger.error(f"File {path} does not exist")
            return
        push_to_streaming_service_from_file(path)


def try_push_to_streaming_service(streaming_list):
    streaming_server_base_url = os.environ.get("STREAMING_SERVER_BASE_URL")
    if streaming_server_base_url is None:
        logger.warning("Streaming server base URL is not set")
        return None
    for speaker, text, audio in streaming_list:
        if speaker == "Speaker 1":
            vtb_name = vtb_speaker1
        else:
            vtb_name = vtb_speaker2
        logger.debug(f"Pushing {vtb_name} to {streaming_server_base_url}")
        logger.debug(f"Text: {text}")
        logger.debug(f"Audio: {audio}")

        response = requests.post(
            streaming_server_base_url,
            data={"vtb_name": vtb_name, "text": text},
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
        self.version = 0

    def on_modified(self, event):
        if not event.is_directory:
            logger.info(f"File {event.src_path} has been {event.event_type}")
            self.version += 1
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
            auto_podcast(query_path)
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
        auto_podcast(topic[1], int(topic[0]))
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
    # auto_hot_search_podcast()
    auto_file_podcast()
