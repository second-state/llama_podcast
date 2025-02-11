import gradio as gr
import requests
import llama_podcast
import openai
import json
import soundfile as sf
import numpy as np
import os
import dotenv

dotenv.load_dotenv()


opt = gr.WaveformOptions()
opt.sample_rate = 16000

audios = {}
tts_inputs = {}

if not os.path.exists("./output"):
    os.makedirs("./output")


def set_tts_inputs(topic, inputs: list):
    tts_inputs[topic] = inputs


# TTS 功能
def tts(index, base_url, speaker, text):
    # 发起HTTP请求到后端，获取wav文件

    response = requests.post(
        base_url,
        json={"speaker": speaker, "input": text},
    )
    print(index, response.status_code)
    # 确保请求成功
    if response.status_code == 200:
        file_path = f"./output/segments_{index}.wav"
        with open(file_path, "wb") as file:
            file.write(response.content)
        audios[index] = file_path
        return file_path
    else:
        return None


def seq_tts(topic, base_url, speaker1, speaker2):
    size = len(tts_inputs[topic])
    for i, text in enumerate(tts_inputs[topic]):
        speaker, text = text
        if speaker == "Speaker 1":
            audio = tts(f"{topic}_{i}", base_url, speaker1, text)
        else:
            audio = tts(f"{topic}_{i}", base_url, speaker2, text)
        yield f"完成 {i+1}/{size}"
    return "合成完成"


def merge_audio(topic_index: str):
    wav_data = []
    for i in range(len(tts_inputs[topic_index])):
        audio = audios[f"{topic_index}_{i}"]
        data, fs = sf.read(audio)
        wav_data.append(data)
    wav_data = np.concatenate(wav_data)
    SAMPLE_RATE = 32000
    sf.write(f"./output/podcast_{topic_index}.wav", wav_data, SAMPLE_RATE)
    return f"./output/podcast_{topic_index}.wav"


lang = os.environ.get("PODCAST_LANG", "zh")
if lang == "zh":
    default_sys_prompt0 = llama_podcast.CN_SYSTEMP_PROMPT_0
    default_sys_prompt1 = llama_podcast.CN_SYSTEMP_PROMPT_1
    default_sys_prompt2 = llama_podcast.CN_SYSTEMP_PROMPT_2
else:
    default_sys_prompt0 = llama_podcast.EN_SYSTEMP_PROMPT_0
    default_sys_prompt1 = llama_podcast.EN_SYSTEMP_PROMPT_1
    default_sys_prompt2 = llama_podcast.EN_SYSTEMP_PROMPT_2


def generate_llm(
    llm_base_url: str,
    llm_token: str,
    llm_model_name: str,
    llm_sys_prompt,
    input_prompt,
):
    openapi_client = openai.Client(
        base_url=llm_base_url.strip(),
        api_key=llm_token.strip(),
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
            yield outputs
        else:
            return outputs


sub_topics = []


def generate_with_subtopic_llm(
    llm_base_url: str,
    llm_token: str,
    llm_model_name: str,
    llm_sys_prompt,
    article: str,
    sub_topic: str,
):
    llm_sys_prompt_ = llm_sys_prompt + "\n<article>\n" + article + "\n</article>\n"
    openapi_client = openai.Client(
        base_url=llm_base_url.strip(),
        api_key=llm_token.strip(),
        timeout=1000 * 60 * 60,
    )

    messages = [
        {"role": "system", "content": llm_sys_prompt_},
        {"role": "user", "content": sub_topic},
    ]
    response = openapi_client.chat.completions.create(
        messages=messages, model=llm_model_name, stream=True
    )
    outputs = ""

    for chunk in response:
        if chunk.choices[0].delta.content != None:
            outputs += chunk.choices[0].delta.content
            yield outputs
        else:
            break
    for i in range(len(sub_topics)):
        if sub_topics[i][0] == sub_topic:
            sub_topics[i].append(outputs)
            break
    return outputs


with gr.Blocks() as demo:
    with gr.Column():
        llm_base_url = gr.Textbox(
            label="LLM BaseURL",
            value="https://llama70b.gaia.domains/v1",
        )
        llm_model_name = gr.Textbox(
            label="Model Name",
            value="llama",
        )
        llm_token = gr.Textbox(
            label="API Token",
            value="NA",
        )

        with gr.Tab("0. 分离主题"):
            llm_sys_prompt = gr.TextArea(
                label="System Prompt",
                value=default_sys_prompt0,
            )
            input_prompt = gr.TextArea(label="文本内容")
            button = gr.Button(value="开始生成")
            output0 = gr.TextArea(label="LLM Output", value="")
            button.click(
                generate_llm,
                inputs=[
                    llm_base_url,
                    llm_token,
                    llm_model_name,
                    llm_sys_prompt,
                    input_prompt,
                ],
                outputs=[output0],
            )

        with gr.Tab("1. 撰写演讲稿"):

            @gr.render(inputs=[input_prompt, output0])
            def update_input(article, topics):
                llm_sys_prompt = gr.TextArea(
                    label="System Prompt", value=default_sys_prompt1
                )

                sub_topics.clear()
                with gr.Column("tts_inputs") as col:
                    article = gr.TextArea(label="文本内容", value=article)
                    topics = topics.split("\n")
                    for i, topic in enumerate(topics):
                        if topic.strip() == "":
                            continue
                        sub_topics.append([topic])
                        with gr.Row():
                            sub_topic = gr.Label(label=f"主题_{i}", value=topic)
                        with gr.Row():
                            sub_output = gr.TextArea(label=f"主题_{i} Output", value="")
                        with gr.Row():
                            btn = gr.Button(value="生成")
                            btn.click(
                                generate_with_subtopic_llm,
                                inputs=[
                                    llm_base_url,
                                    llm_token,
                                    llm_model_name,
                                    llm_sys_prompt,
                                    article,
                                    sub_topic,
                                ],
                                outputs=[sub_output],
                            )

                    return col

        with gr.Tab("2. 生成播客 TTS"):
            tts_base_url = gr.Textbox(
                label="TTS BaseURL",
                value="http://localhost:8080/v1/audio/speech_gpt",
                interactive=True,
            )
            speaker1 = gr.Textbox(label="Speaker1", value="speaker1", interactive=True)
            speaker2 = gr.Textbox(label="Speaker2", value="speaker2", interactive=True)
            update_btn = gr.Button(value="刷新演讲稿")

            def update_input_label(s):
                if s == "0":
                    return "1"
                else:
                    return "0"

            state = gr.State("0")

            update_btn.click(update_input_label, inputs=[state], outputs=[state])

            @gr.render(inputs=[state])
            def update_tts_input(_label):
                with gr.Column() as col:
                    for topic_index, item in enumerate(sub_topics):
                        content = ""
                        if len(item) > 1:
                            content = item[1]
                        lines = iter(content.split("\n"))
                        script = []
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

                        tts_inputs[str(topic_index)] = script

                        t_index = gr.Label(
                            label=f"topic_{topic_index}", value=topic_index
                        )
                        with gr.Row():
                            seq_tts_btn = gr.Button(value="逐句合成")
                            seq_tts_btn.click(
                                seq_tts,
                                inputs=[t_index, tts_base_url, speaker1, speaker2],
                                outputs=[state],
                            )

                        for i, text in enumerate(script):
                            speaker, text = text
                            with gr.Row():
                                index = gr.Textbox(
                                    label="Index", value=f"{topic_index}_{i}"
                                )
                            with gr.Row():
                                text = gr.Textbox(label=speaker, value=text)

                            with gr.Row():
                                if f"{topic_index}_{i}" in audios:
                                    audio = gr.Audio(
                                        value=audios[f"{topic_index}_{i}"],
                                        type="filepath",
                                    )
                                else:
                                    audio = gr.Audio()
                            with gr.Row():
                                btn = gr.Button(value="重新生成")
                                if speaker == "Speaker 1":
                                    btn.click(
                                        tts,
                                        inputs=[index, tts_base_url, speaker1, text],
                                        outputs=[audio],
                                    )
                                else:
                                    btn.click(
                                        tts,
                                        inputs=[index, tts_base_url, speaker2, text],
                                        outputs=[audio],
                                    )

                        gr.Label("合并音频")
                        final_audio = gr.Audio(type="filepath")
                        button = gr.Button(value="合并")
                        button.click(
                            merge_audio, inputs=[t_index], outputs=[final_audio]
                        )
                return col


# 启动应用
if __name__ == "__main__":
    demo.launch()
