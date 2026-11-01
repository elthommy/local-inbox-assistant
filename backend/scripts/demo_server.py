"""Run the backend against seeded demo data with no model at all.

For screenshots and video capture where neither Ollama nor Anthropic is
reachable (seed first with `scripts.seed_demo --skip-embed`). Compared to
the real app, this launcher:

- answers chat from scripts/demo_chat.py (scripted, identical every take);
- skips the startup index run (it would try to embed through Ollama);
- reports Ollama as up with the configured models pulled, so the header and
  settings show the state a normal install shows instead of "offline".

Everything else (list, priority, tasks, events, reading view, dismiss, mute)
is the unmodified app reading the demo DB. Never point it at a real mailbox.

    uv run python -m scripts.demo_server [--dir PATH] [--port 8000]

Then start the frontend from the repo root: `npm run dev`.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

import app.api as api_module
import app.main as main_module
from app.config import settings
from app.llm.ollama import OllamaClient
from scripts.demo_chat import fake_stream_answer
from scripts.seed_demo import DEMO_DIR, MARKER_FILE, DemoPaths, point_settings_at_demo

# sizes shown in the model picker; plausible values for the default models
_FAKE_MODEL_BYTES = 5_000_000_000


async def _no_index(*args, **kwargs) -> None:
    """Stand-in for the startup index run: the demo DB is already seeded."""
    return None


async def _ollama_up(self) -> bool:
    """Pretend the Ollama server answers."""
    return True


async def _fake_models_info(self) -> list[dict]:
    """Pretend the configured chat, extraction and embedding models are pulled."""
    names = dict.fromkeys(
        [settings.chat_model, settings.extraction_model, settings.embed_model]
    )
    return [{"name": name, "size": _FAKE_MODEL_BYTES} for name in names]


def install_demo_patches() -> None:
    """Swap the model-backed pieces of the app for offline demo stand-ins."""
    api_module.stream_answer = fake_stream_answer
    main_module.run_index = _no_index
    OllamaClient.available = _ollama_up
    OllamaClient.list_models_info = _fake_models_info


def main() -> None:
    """Parse arguments, point the app at the demo data and serve it."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dir", type=Path, default=DEMO_DIR, help="seeded demo dir")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    paths = DemoPaths(args.dir.resolve())
    if not (paths.root / MARKER_FILE).exists() or not paths.db.exists():
        raise SystemExit(
            f"{paths.root} is not a seeded demo dir: run "
            "`uv run python -m scripts.seed_demo --skip-embed` first"
        )
    point_settings_at_demo(paths)
    install_demo_patches()
    # loopback only, like the real app (see AGENTS.md security model)
    uvicorn.run(main_module.app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
