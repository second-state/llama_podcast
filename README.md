# QuickStart

Install dependencies

```bash
pip install gradio
pip install soundfile
pip install openai
```

Start the server with default English prompts

```
python main.py
```

Start the server with Chinese prompts

```
LANG=zh python main.py
```

Start the server on an alternative port (8080 instead of 7680) with Chinese prompts

```
GRADIO_SERVER_PORT=8080 LANG=zh python main.py
```

Start the server with a public access URL

```
GRADIO_SHARE="True" python main.py
```
