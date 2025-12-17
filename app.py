import hashlib
import time
from fastapi import FastAPI, Request, Response
from lxml import etree
import requests
import traceback
import re
import os

app = FastAPI()


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v or not v.strip():
        raise RuntimeError(f"Missing env var: {name}")
    return v.strip()


WECHAT_TOKEN = _require_env("WECHAT_TOKEN")
OLLAMA_URL = _require_env("OLLAMA_URL")
OLLAMA_MODEL = _require_env("OLLAMA_MODEL")


def check_signature(signature: str, timestamp: str, nonce: str) -> bool:
    arr = [WECHAT_TOKEN, timestamp, nonce]
    arr.sort()
    sha1 = hashlib.sha1("".join(arr).encode("utf-8")).hexdigest()
    return sha1 == signature


def build_text_reply(to_user: str, from_user: str, content: str) -> str:
    now = int(time.time())
    return f"""<xml>
  <ToUserName><![CDATA[{to_user}]]></ToUserName>
  <FromUserName><![CDATA[{from_user}]]></FromUserName>
  <CreateTime>{now}</CreateTime>
  <MsgType><![CDATA[text]]></MsgType>
  <Content><![CDATA[{content}]]></Content>
</xml>"""


def strip_think(text: str) -> str:
    if not text:
        return ""

    # 1) 去掉完整 <think>...</think> 块
    text = re.sub(r"(?is)<think>.*?</think>", "", text)

    # 2) 如果还有未闭合的 <think>，从 <think> 开始整段裁掉
    idx = text.lower().find("<think>")
    if idx != -1:
        text = text[:idx]

    # 3) 清掉残留标签
    text = re.sub(r"(?i)</?think>", "", text)

    # 4) 清理多余空行
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def call_ollama(user_text: str, style_system: str = "") -> str:
    system_prompt = (
        "你是用户的异地恋女友，性格温柔体贴，请根据用户的消息用女友的口吻回答。\n"
        "【硬性要求】不要输出任何思考过程/推理草稿；不要输出 <think> 或 </think>；只输出最终答案。"
    )
    if style_system:
        system_prompt += f"\n【风格要求】\n{style_system}\n"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "stream": False,
        # 可选：限制输出长度，避免又慢又长
        "options": {"num_predict": 128},
        "keep_alive": "10m",
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=7.5)
    r.raise_for_status()

    raw = (r.json().get("message", {}).get("content", "") or "").strip()
    cleaned = strip_think(raw)

    # 清洗后为空：给用户一个可接受的短答复，而不是把 <think> 发出去
    return cleaned if cleaned else "我明白了。你把目标/限制条件再补充一句，我给你一个更准确的答复。"


@app.get("/wx")
async def wx_verify(signature: str, timestamp: str, nonce: str, echostr: str):
    if check_signature(signature, timestamp, nonce):
        return Response(content=echostr)
    return Response(content="forbidden", status_code=403)


@app.post("/wx")
async def wx_message(request: Request):
    q = request.query_params
    signature = q.get("signature", "")
    timestamp = q.get("timestamp", "")
    nonce = q.get("nonce", "")
    if not check_signature(signature, timestamp, nonce):
        return Response(content="forbidden", status_code=403)

    body = await request.body()
    root = etree.fromstring(body)
    msg_type = root.findtext("MsgType")
    from_user = root.findtext("FromUserName")  # 用户openid
    to_user = root.findtext("ToUserName")  # 公众号id

    if msg_type != "text":
        reply = build_text_reply(from_user, to_user, "当前仅支持文本消息。")
        return Response(content=reply, media_type="application/xml")

    user_text = (root.findtext("Content") or "").strip()
    if not user_text:
        reply = build_text_reply(from_user, to_user, "你发了空消息，我接不到内容。")
        return Response(content=reply, media_type="application/xml")

    try:
        answer = call_ollama(user_text, style_system="温柔可爱")
    except Exception as e:
        print("OLLAMA ERROR:", repr(e))
        traceback.print_exc()
        answer = "我这边刚刚没算出来，你再发一次我就能接上。"

    reply = build_text_reply(from_user, to_user, answer)
    return Response(content=reply, media_type="application/xml")
