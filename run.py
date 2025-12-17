import os
import argparse
import subprocess
import uvicorn


def load_env_file(path: str):
    if not path:
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        raise SystemExit(f"[ERROR] config file not found: {path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.env", help="env file path (default: config.env)")
    p.add_argument("--wechat-token", help="WECHAT_TOKEN (prefer putting it in config.env)")
    p.add_argument("--ollama-url", help="OLLAMA_URL")
    p.add_argument("--ollama-model", help="OLLAMA_MODEL")

    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=80)

    p.add_argument("--natapp", default=".\\natapp\\natapp.exe", help="path to natapp.exe")
    p.add_argument("--no-natapp", action="store_true", help="do not start natapp")
    args = p.parse_args()

    # 1) 先加载 config.env（再用命令行覆盖）
    load_env_file(args.config)

    # 2) 命令行参数覆盖（如果提供）
    if args.wechat_token: os.environ["WECHAT_TOKEN"] = args.wechat_token
    if args.ollama_url:   os.environ["OLLAMA_URL"] = args.ollama_url
    if args.ollama_model: os.environ["OLLAMA_MODEL"] = args.ollama_model

    # 3) 校验必须项
    for k in ("WECHAT_TOKEN", "OLLAMA_URL", "OLLAMA_MODEL"):
        if not os.getenv(k):
            raise SystemExit(f"[ERROR] Missing {k}. Set it in {args.config} or via CLI args.")

    # 4) 启动 natapp（可选）
    if not args.no_natapp:
        subprocess.Popen([args.natapp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 5) 启动 uvicorn
    uvicorn.run("app:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
