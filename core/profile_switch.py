"""Shared profile-switch buttons and per-input destination selection."""

import json
import logging
import os

from core.constants import APP_DIR

TRIGGER_FIELDS = ('hover', 'lclick', 'rclick', 'mclick', 'wheelup', 'wheeldown',
                  'xbutton1', 'xbutton2')
SWITCHES_FILE = os.path.join(APP_DIR, 'settings', 'profile_switches.json')
logger = logging.getLogger(__name__)


def normalize_actions(actions):
    result = {}
    if not isinstance(actions, dict):
        return result
    for key in TRIGGER_FIELDS:
        action = actions.get(key)
        if not isinstance(action, dict) or action.get('mode') not in ('fixed', 'cycle'):
            continue
        raw = action.get('profiles', [])
        if not isinstance(raw, list):
            continue
        names = list(dict.fromkeys(n for n in raw if isinstance(n, str) and n.strip()))
        if names:
            result[key] = {'mode': action['mode'],
                           'profiles': names[:1] if action['mode'] == 'fixed' else names}
    return result


def select_destination(action, current, available):
    """Cycle after the current profile; start at the first entry when outside the list."""
    if not action:
        return None
    if action['mode'] == 'fixed':
        target = action['profiles'][0] if action['profiles'] else None
        return target if target in available else None
    names = [n for n in action['profiles'] if n in available]
    if not names:
        return None
    return names[(names.index(current) + 1) % len(names)] if current in names else names[0]


def load_switch_buttons():
    try:
        with open(SWITCHES_FILE, encoding='utf-8') as source:
            buttons = json.load(source)
        return [b for b in buttons if isinstance(b, dict) and b.get('type') == 'profile_switch'] if isinstance(buttons, list) else []
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        logger.exception('Cannot load shared profile-switch buttons')
        return []


def save_switch_buttons(buttons):
    from core.config_manager import _atomic_write_json
    os.makedirs(os.path.dirname(SWITCHES_FILE), exist_ok=True)
    _atomic_write_json(SWITCHES_FILE, buttons)
