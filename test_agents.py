import json
from pathlib import Path
from typing import Optional, Iterable, Dict, List, Any


def normalize_items(capabilities: Any) -> Iterable[dict]:
    """
    Normalize capabilities -> iterable of item dicts.

    Handles:
      - capabilities == dict with item as list or dict
      - capabilities == "" / None / invalid
    """
    if not isinstance(capabilities, dict):
        return []

    items = capabilities.get("item")

    if isinstance(items, list):
        return items

    if isinstance(items, dict):
        return [items]

    return []


def extract_presenter_src(agent: dict) -> Optional[str]:
    """
    Extract capture.device.presenter.src from agent.
    Returns None if missing or invalid.
    """
    for item in normalize_items(agent.get("capabilities")):
        if item.get("key") == "capture.device.presenter.src":
            return item.get("value")

    return None


def load_agents(path: Path) -> List[Dict[str, Optional[str]]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    agents = data.get("agents", {}).get("agent", [])

    return [
        {
            "name": agent.get("name"),
            "state": agent.get("state"),
            "src": extract_presenter_src(agent),
        }
        for agent in agents
    ]


agents = load_agents(Path("agents.json"))

for agent in agents:
    print(agent)