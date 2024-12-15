import gradio as gr
import requests
import llama_podcast
import openai
import json
import soundfile as sf
import numpy as np
import os

opt = gr.WaveformOptions()
opt.sample_rate = 16000

audios = {}
tts_inputs = []

if not os.path.exists("./output"):
    os.makedirs("./output")


def set_tts_inputs(inputs: list):
    tts_inputs.clear()
    tts_inputs.extend(inputs)


# TTS 功能
def tts(index, base_url, speaker, text):
    # 发起HTTP请求到后端，获取wav文件

    response = requests.post(
        base_url,
        json={"speaker": speaker, "input": text},
    )
    # 确保请求成功
    if response.status_code == 200:
        file_path = f"./output/segments_{index}.wav"
        with open(file_path, "wb") as file:
            file.write(response.content)
        audios[index] = file_path
        return file_path
    else:
        return None


def seq_tts(base_url, speaker1, speaker2):
    size = len(tts_inputs)
    for i, text in enumerate(tts_inputs):
        speaker, text = text
        if speaker == "Speaker 1":
            audio = tts(str(i), base_url, speaker1, text)
        else:
            audio = tts(str(i), base_url, speaker2, text)
        yield f"完成 {i+1}/{size}"
    return "合成完成"


def merge_audio():
    wav_data = []
    for i in range(len(tts_inputs)):
        audio = audios[str(i)]
        data, fs = sf.read(audio)
        wav_data.append(data)
    wav_data = np.concatenate(wav_data)
    SAMPLE_RATE = 32000
    sf.write("./output/podcast.wav", wav_data, SAMPLE_RATE)
    return "./output/podcast.wav"


lang = os.environ.get("LANG", "zh")
if lang == "zh":
    default_sys_prompt1 = llama_podcast.CN_SYSTEMP_PROMPT_1
    default_sys_prompt2 = llama_podcast.CN_SYSTEMP_PROMPT_2
else:
    default_sys_prompt1 = llama_podcast.EN_SYSTEMP_PROMPT_1
    default_sys_prompt2 = llama_podcast.EN_SYSTEMP_PROMPT_2

with gr.Blocks() as demo:
    with gr.Column():
        llm_base_url = gr.Textbox(
            label="LLM BaseURL",
            value="https://llama70b.gaia.domains/v1 ",
        )
        llm_model_name = gr.Textbox(
            label="Model Name",
            value="llama",
        )
        llm_token = gr.Textbox(
            label="API Token",
            value="NA",
        )
        with gr.Tab("1. 撰写演讲稿"):
            llm_sys_prompt = gr.TextArea(
                label="System Prompt",
                value=default_sys_prompt1,
            )
            input_prompt = gr.TextArea(label="文本内容")
            output1 = gr.TextArea(label="LLM Output", value="")
            button = gr.Button(value="开始生成")

            @gr.on(
                triggers=[button.click],
                inputs=[
                    llm_base_url,
                    llm_token,
                    llm_model_name,
                    llm_sys_prompt,
                    input_prompt,
                ],
                outputs=[output1],
            )
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
                    outputs += chunk.choices[0].delta.content
                    yield outputs

        with gr.Tab("2. 润色演讲稿"):
            llm_sys_prompt = gr.TextArea(
                label="System Prompt",
                value=default_sys_prompt2,
            )
            input_prompt = gr.TextArea(label="文本内容", value=output1.value)
            output2 = gr.TextArea(label="LLM Output")
            button = gr.Button(value="开始生成")

            @gr.on(
                triggers=[button.click],
                inputs=[
                    llm_base_url,
                    llm_token,
                    llm_model_name,
                    llm_sys_prompt,
                    input_prompt,
                ],
                outputs=[output2],
            )
            def generate_llm(
                llm_base_url,
                llm_token,
                llm_model_name,
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
                    outputs += chunk.choices[0].delta.content
                    yield outputs

        with gr.Tab("3. 生成播客 TTS"):
            tts_base_url = gr.Textbox(
                label="TTS BaseURL",
                value="http://localhost:8080/v1/audio/speech_gpt",
            )
            speaker1 = gr.Textbox(label="Speaker1", value="speaker1")
            speaker2 = gr.Textbox(label="Speaker2", value="speaker2")

            text_input = gr.TextArea(label="演讲稿", value="")
            update_btn = gr.Button(value="刷新演讲稿")
            update_btn.click(lambda x: x, inputs=[output2], outputs=[text_input])
            seq_tts_btn = gr.Button(value="逐句合成")
            label = gr.Label("未合成音频")
            seq_tts_btn.click(
                seq_tts,
                inputs=[tts_base_url, speaker1, speaker2],
                outputs=[label],
            )

            @gr.render(inputs=[text_input, label])
            def update_tts_input(input, _label):

                with gr.Column("tts_inputs") as col:
                    try:
                        texts = json.loads(input)
                    except:
                        texts = []
                    set_tts_inputs(texts)
                    for i, text in enumerate(texts):
                        speaker, text = text
                        with gr.Row():
                            index = gr.Textbox(label="Index", value=str(i))
                            text = gr.Textbox(label=speaker, value=text)
                        with gr.Row():
                            if str(i) in audios:
                                audio = gr.Audio(value=audios[str(i)], type="filepath")
                            else:
                                audio = gr.Audio()

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

                return col

            gr.Label("合并音频")
            final_audio = gr.Audio(type="filepath")
            button = gr.Button(value="合并")
            button.click(merge_audio, outputs=[final_audio])

# 启动应用
if __name__ == "__main__":
    demo.launch()
