import hashlib
import time
from fastapi import FastAPI, Request, Response
from lxml import etree
import requests

app = FastAPI()

WECHAT_TOKEN = "521aihjyhybaihhhhhh"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "deepseek-r1"


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


def call_ollama(user_text: str, style_system: str = "") -> str:
    system_prompt = "你是公众号里的智能助理，回答要清晰、简洁、可执行。"
    if style_system:
        system_prompt += f"\n【风格要求】\n{style_system}\n"

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "stream": False
    }
    # 被动回复建议 <5 秒内返回，否则微信可能重试。:contentReference[oaicite:2]{index=2}
    r = requests.post(OLLAMA_URL, json=payload, timeout=4.5)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


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
        answer = call_ollama(user_text, style_system="")
    except Exception:
        # 兜底：避免卡死导致微信重试
        answer = "我这边刚刚没算出来，你再发一次我就能接上。"

    reply = build_text_reply(from_user, to_user, answer)
    return Response(content=reply, media_type="application/xml")
