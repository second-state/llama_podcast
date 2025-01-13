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

import gpt_researcher

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


def auto_podcast(query):
    local_time = time.localtime()
    local_time_str = time.strftime("%Y%m%d_%H.%M.%S", local_time)

    if not os.path.exists("./output"):
        os.makedirs("./output")
    if not os.path.exists(f"./output/{local_time_str}"):
        os.makedirs(f"./output/{local_time_str}")

    with open(f"./output/{local_time_str}/query.txt", "w") as file:
        file.write(query)

    # Get news from the web
    logger.info(f"Getting news for query: {query}")
    task = get_news_from_web(query)
    report = asyncio.run(task)
    with open(f"./output/{local_time_str}/report.txt", "w") as file:
        file.write(report)

    # Generate podcast script
    logger.info("Generating podcast script")
    llm_input = generate_llm(llm_model, default_sys_prompt1, report)
    if llm_input is None:
        logger.error("Failed to generate LLM input")
        return None
    with open(f"./output/{local_time_str}/script.txt", "w") as file:
        file.write(llm_input)

    # Optimization podcast script
    logger.info("Optimizing podcast script")
    output = generate_llm(llm_model, default_sys_prompt2, llm_input)
    with open(f"./output/{local_time_str}/script.json", "w") as file:
        file.write(output)

    # Generate voice

    if tts_base_url != None:
        logger.info(f"Generating voice at {local_time_str}")
        voice = generate_voice(output, speaker1, speaker2)
        if voice is None:
            logger.error("Failed to generate voice")
            return None
    else:
        voice = []

    streaming_list = []
    # save voice
    for i, (speaker, text, audio) in enumerate(voice):
        with open(f"./output/{local_time_str}/segments_{i}.wav", "wb") as file:
            file.write(audio)
        streaming_list.append(
            (speaker, text, f"./output/{local_time_str}/segments_{i}.wav")
        )
    logger.info(f"Voice save at {local_time_str}")

    with open(f"./output/{local_time_str}/streaming_list.json", "w") as file:
        file.write(json.dumps(streaming_list, ensure_ascii=False, indent=4))

    try_push_to_streaming_service(streaming_list)
    return f"./output/{local_time_str}"


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
        print(f"Pushing {vtb_name} to {streaming_server_base_url}")
        print(f"Text: {text}")
        print(f"Audio: {audio}")

        response = requests.post(
            streaming_server_base_url,
            data={"vtb_name": vtb_name, "text": text},
            files={"voice": (audio, open(audio, "rb"))},
        )
        print(response.status_code)


if __name__ == "__main__":
    # query = "2万吨智利车厘子运抵中国"
    # auto_podcast(query)
    all = set()
    tips = llama_podcast.hot_news.get_bilibili_hot_news()
    tips = set(tips)
    tips = tips - all
    all = all.union(tips)
    for tip in tips:
        auto_podcast(tip)

    # with open("output/20250113_22.02.17/streaming_list.json", "rb") as file:
    # streaming_list = json.load(file)
    # with open("output/20250113_22.02.17/streaming_list.json", "w") as file:
    # file.write(json.dumps(streaming_list, ensure_ascii=False, indent=4))
    # with open("output/20250113_22.02.17/streaming_list.json", "rb") as file:
    #     streaming_list = json.load(file)
    #     try_push_to_streaming_service(streaming_list[-12:])
