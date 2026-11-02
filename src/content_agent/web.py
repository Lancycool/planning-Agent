"""Local-only web adapter. Static files are served through an explicit allowlist."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv

from .engine import Agent
from .models import MockModel, OnlineModel
from .schemas import Request
from .storage import Store
from .tools import load_catalog

ROOT = Path(__file__).resolve().parents[2]
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css")}
EXAMPLES = {"normal": "E01-normal", "replan": "E05-replan", "failure": "E04-tool-failure"}


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, data, content_type="application/json"):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ASSETS:
            file, mime = ASSETS[self.path]
            self.reply(200, (ROOT / "web" / file).read_bytes(), mime)
        elif self.path.startswith("/api/example/") and self.path.rsplit("/", 1)[-1] in EXAMPLES:
            case = EXAMPLES[self.path.rsplit("/", 1)[-1]]
            self.reply(200, (ROOT / "examples" / "online" / case / "output.json").read_bytes())
        else:
            self.reply(404, {"error": "页面不存在"})

    def do_POST(self):
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != host or self.headers.get("Origin") != f"http://{host}":
            self.reply(403, {"error": "请从本机网页发起运行"})
            return
        if self.path != "/api/run":
            self.reply(404, {"error": "接口不存在"})
            return
        store = None
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise ValueError("invalid size")
            payload = json.loads(self.rfile.read(size))
            mode = payload.pop("mode")
            if mode not in ("mock", "online"):
                raise ValueError("invalid mode")
            # The client keeps one ID through retries; only a new task gets a new ID.
            request = Request.model_validate(payload)
            store = Store(ROOT / ".runtime" / "web.sqlite3")
            model = OnlineModel() if mode == "online" else MockModel()
            result = Agent(store, model, load_catalog(ROOT / "data/catalog.json")).run(request)
            self.reply(200, result)
        except (ValueError, TypeError, KeyError):
            self.reply(400, {"error": "请检查主题、整数预算和带时区的截止时间"})
        except Exception:
            self.reply(500, {"error": "本机运行失败，请检查服务终端和本地配置"})
        finally:
            if store:
                store.close()


def main():
    load_dotenv(ROOT / ".env", override=False)
    server = HTTPServer(("127.0.0.1", 8765), Handler)
    print("Content studio: http://127.0.0.1:8765", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
