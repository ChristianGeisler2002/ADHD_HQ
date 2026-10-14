"""Run the local app inside a native window."""

import logging
import socket
import threading
import time
from logging.handlers import RotatingFileHandler

import uvicorn

import db
from app import app


def main():
    import webview

    db.DATA_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        db.DATA_DIR / "desktop.log", maxBytes=1_000_000, backupCount=2
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", log_config=None))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError(
                    "The local server could not start. See desktop.log for details."
                )
            time.sleep(0.05)
        webview.create_window(
            "ADHD HQ",
            f"http://127.0.0.1:{port}/dashboard",
            width=1400,
            height=900,
            min_size=(680, 560),
        )
        webview.start()
    except Exception:
        logging.getLogger(__name__).exception("Desktop startup failed")
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            0,
            f"ADHD HQ could not open.\nCheck {db.DATA_DIR / 'desktop.log'}",
            "ADHD HQ",
            0x10,
        )
        raise
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


if __name__ == "__main__":
    main()
