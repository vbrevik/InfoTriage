#!/usr/bin/env python3
"""OpenAI-compatible LLM router for InfoTriage (local-only, ADR-004).

Routing:
  /v1/chat/completions -> Spark vLLM (primary) when reachable, else oMLX (fallback).
      Spark: remap model -> "model", EXTEND max_tokens (thinking model needs room),
             strip <think>...</think> so the scorer's JSON parser gets clean output.
      oMLX : model "qwen36-ud-4bit", max_tokens left as the caller sent it.
  /v1/embeddings       -> oMLX only ("multilingual-e5-large"); Spark serves no embedder.

Listens on 127.0.0.1:8600 (InfoTriage's 8500-8599 range). Point LLM_BASE_URL here.
"""
import json, re, subprocess, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SPARK = "http://192.168.10.2:8000/v1"
SPARK_MODEL = "model"
SPARK_MIN_MAXTOK = 4096  # extend on Spark only, so <think> + JSON both fit
OMLX = "http://127.0.0.1:8000/v1"
OMLX_CHAT = "qwen36-ud-4bit"
OMLX_EMBED = "multilingual-e5-large"
KEY = "omlx"
THINK = re.compile(r"<think>.*?</think>", re.S)
PORT = 8600


def up(base: str) -> bool:
    try:
        urllib.request.urlopen(base + "/models", timeout=3)
        return True
    except Exception:
        return False


def ensure_omlx() -> None:
    if up(OMLX):
        return
    try:
        subprocess.run(["omlx-ensure-server"], timeout=120, capture_output=True)
    except Exception:
        pass


def fwd(base: str, path: str, body: dict, timeout: int):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, data: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.endswith("/models"):
            self._send(
                200,
                json.dumps(
                    {"object": "list", "data": [{"id": "router", "object": "model"}]}
                ).encode(),
            )
        else:
            self._send(404, b"{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw)
        except Exception:
            self._send(400, b'{"error":"bad json"}')
            return
        p = self.path.split("/v1", 1)[1] if "/v1" in self.path else self.path
        try:
            if p.startswith("/embeddings"):
                ensure_omlx()
                body["model"] = OMLX_EMBED
                code, out = fwd(OMLX, "/embeddings", body, 120)
                self._send(code, out)
                return
            # chat/completions
            if up(SPARK):
                b = dict(body)
                b["model"] = SPARK_MODEL
                b["max_tokens"] = max(
                    int(body.get("max_tokens", 400) or 400), SPARK_MIN_MAXTOK
                )
                # Qwen3.6 is a thinking model. For InfoTriage's bounded JSON
                # classification we do NOT want chain-of-thought: it burns 25-30s
                # and thousands of tokens per call (blowing the entity-NER budget)
                # for no quality gain on a fixed-schema task. Disabling thinking
                # drops latency to ~5s with clean JSON (finish_reason=stop). The
                # <think>-strip below stays as a belt-and-suspenders fallback.
                kw = dict(b.get("chat_template_kwargs") or {})
                kw.setdefault("enable_thinking", False)
                b["chat_template_kwargs"] = kw
                code, out = fwd(SPARK, "/chat/completions", b, 600)
                try:  # strip <think> from returned content
                    d = json.loads(out)
                    msg = d["choices"][0]["message"]
                    msg["content"] = THINK.sub("", msg.get("content") or "").strip()
                    out = json.dumps(d).encode()
                except Exception:
                    pass
                self._send(code, out)
                return
            # fallback: oMLX (do NOT extend max_tokens)
            ensure_omlx()
            b = dict(body)
            b["model"] = OMLX_CHAT
            code, out = fwd(OMLX, "/chat/completions", b, 600)
            self._send(code, out)
        except urllib.error.HTTPError as e:
            self._send(e.code, e.read())
        except Exception as e:
            self._send(502, json.dumps({"error": str(e)}).encode())


if __name__ == "__main__":
    print(f"llm-router on 127.0.0.1:{PORT}  (chat->Spark/oMLX, embeddings->oMLX)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
