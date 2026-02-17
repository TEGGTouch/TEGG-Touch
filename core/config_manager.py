"""
TEGG Touch 辅助软件 - 配置管理器

负责配置文件的加载、保存，以及多方案(Profile)管理。
方案存储在 profiles/ 目录，每个方案一个 JSON 文件。
"""

import json
import os
import copy
import logging

from .constants import (
    CONFIG_FILE, DEFAULT_TRANSPARENCY,
    DEFAULT_BUTTONS, MIN_WINDOW_SIZE, RUNTIME_FIELDS,
    BUTTON_OPTIONAL_DEFAULTS,
    PROFILES_DIR, PROFILES_INDEX, DEFAULT_PROFILE_NAME,
    DEFAULT_FREEZE_HOTKEY,
)

logger = logging.getLogger(__name__)


# ─── 内部工具 ────────────────────────────────────────────────

def _validate_geometry(geo: str) -> str:
    try:
        wh = geo.split('+')[0].split('x')
        w, h = int(wh[0]), int(wh[1])
        if w < MIN_WINDOW_SIZE or h < MIN_WINDOW_SIZE:
            return None
        return geo
    except Exception:
        return None


def _ensure_button_fields(btn: dict) -> dict:
    for field, default in BUTTON_OPTIONAL_DEFAULTS.items():
        if field not in btn:
            btn[field] = default
    return btn


def _clean_button_for_save(btn: dict) -> dict:
    return {k: v for k, v in btn.items()
            if k not in RUNTIME_FIELDS and k != 'deleted'}


def _profiles_dir():
    return PROFILES_DIR


def _index_path():
    return os.path.join(_profiles_dir(), PROFILES_INDEX)


def _profile_path(name: str):
    return os.path.join(_profiles_dir(), f"{name}.json")


# ─── 方案索引管理 ─────────────────────────────────────────────

def _load_index() -> dict:
    """加载方案索引。返回 {"active": str, "profiles": [str]}"""
    path = _index_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"索引加载失败: {e}")
    return {"active": DEFAULT_PROFILE_NAME, "profiles": [DEFAULT_PROFILE_NAME]}


def _save_index(index: dict):
    os.makedirs(_profiles_dir(), exist_ok=True)
    try:
        with open(_index_path(), 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"索引保存失败: {e}")


# ─── 初始化 / 迁移 ───────────────────────────────────────────

def init_profiles():
    """初始化方案系统。如果 profiles/ 不存在，从 config.json 迁移。

    Returns:
        (active_name, config_dict)
    """
    os.makedirs(_profiles_dir(), exist_ok=True)

    index_path = _index_path()
    if os.path.exists(index_path):
        index = _load_index()
        name = index.get("active", DEFAULT_PROFILE_NAME)
        cfg = load_profile(name)
        return name, cfg

    # 首次迁移：从 config.json 创建默认方案
    logger.info("首次初始化方案系统，从 config.json 迁移")
    cfg = _load_legacy_config()
    save_profile(DEFAULT_PROFILE_NAME, cfg)
    _save_index({"active": DEFAULT_PROFILE_NAME, "profiles": [DEFAULT_PROFILE_NAME]})
    return DEFAULT_PROFILE_NAME, cfg


def _load_legacy_config() -> dict:
    """从旧版 config.json 加载配置。"""
    return load_config_from_file(CONFIG_FILE)


# ─── 单文件加载/保存 ─────────────────────────────────────────

def load_config_from_file(filepath: str) -> dict:
    """从指定文件加载配置。"""
    result = {
        'geometry': None,
        'transparency': DEFAULT_TRANSPARENCY,
        'buttons': copy.deepcopy(DEFAULT_BUTTONS),
        'ball_x': None,
        'ball_y': None,
        'click_through': False,
        'freeze_hotkey': DEFAULT_FREEZE_HOTKEY,
    }
    if not os.path.exists(filepath):
        return result
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        result['geometry'] = _validate_geometry(data.get('geometry', ''))
        result['transparency'] = data.get('transparency', DEFAULT_TRANSPARENCY)
        result['ball_x'] = data.get('ball_x', None)
        result['ball_y'] = data.get('ball_y', None)
        result['click_through'] = data.get('click_through', False)
        result['freeze_hotkey'] = data.get('freeze_hotkey', DEFAULT_FREEZE_HOTKEY)
        buttons = data.get('buttons', None)
        if buttons is not None:
            result['buttons'] = [_ensure_button_fields(b) for b in buttons]
        logger.info(f"配置加载成功: {filepath}")
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
    return result


def save_config_to_file(filepath: str, *, geometry, transparency, buttons,
                        ball_x=None, ball_y=None, click_through=False,
                        freeze_hotkey=None,
                        is_hidden=False, saved_geometry=None, root=None) -> bool:
    """保存配置到指定文件。"""
    geo_to_save = saved_geometry or geometry
    try:
        wh = geometry.split('+')[0].split('x')
        w, h = int(wh[0]), int(wh[1])
        if w >= MIN_WINDOW_SIZE and h >= MIN_WINDOW_SIZE:
            geo_to_save = geometry
    except Exception:
        pass

    if is_hidden and root:
        try:
            ball_x = root.winfo_x()
            ball_y = root.winfo_y()
        except Exception:
            pass

    clean_btns = [_clean_button_for_save(b) for b in buttons if not b.get('deleted')]

    data = {
        'geometry': geo_to_save,
        'transparency': transparency,
        'buttons': clean_btns,
        'ball_x': ball_x,
        'ball_y': ball_y,
        'click_through': click_through,
        'freeze_hotkey': freeze_hotkey or DEFAULT_FREEZE_HOTKEY,
    }

    try:
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"配置保存成功: {filepath}")
        return True
    except Exception as e:
        logger.error(f"配置保存失败: {e}")
        return False


# ─── 方案 CRUD ────────────────────────────────────────────────

def list_profiles() -> list:
    """返回所有方案名称列表。"""
    index = _load_index()
    return index.get("profiles", [DEFAULT_PROFILE_NAME])


def get_active_profile_name() -> str:
    """返回当前活跃方案名。"""
    index = _load_index()
    return index.get("active", DEFAULT_PROFILE_NAME)


def load_profile(name: str) -> dict:
    """加载指定方案。"""
    path = _profile_path(name)
    return load_config_from_file(path)


def save_profile(name: str, cfg_kwargs: dict = None, **kwargs) -> bool:
    """保存方案到文件。

    可以传 cfg_kwargs dict 或 **kwargs。
    """
    path = _profile_path(name)
    if cfg_kwargs:
        kwargs.update(cfg_kwargs)
    return save_config_to_file(path, **kwargs)


def set_active_profile(name: str):
    """设置活跃方案。"""
    index = _load_index()
    if name in index.get("profiles", []):
        index["active"] = name
        _save_index(index)


def create_profile(name: str, from_template: bool = False) -> bool:
    """创建新方案。

    Args:
        name: 方案名称
        from_template: True=从模板创建(占位)，False=空白方案

    Returns:
        True if created, False if name already exists
    """
    index = _load_index()
    if name in index.get("profiles", []):
        return False

    # 创建空白配置
    cfg = {
        'geometry': None,
        'transparency': DEFAULT_TRANSPARENCY,
        'buttons': copy.deepcopy(DEFAULT_BUTTONS) if not from_template else copy.deepcopy(DEFAULT_BUTTONS),
        'ball_x': None,
        'ball_y': None,
        'click_through': False,
    }

    # 写入文件
    save_config_to_file(
        _profile_path(name),
        geometry=cfg['geometry'] or '1920x1080+0+0',
        transparency=cfg['transparency'],
        buttons=cfg['buttons'],
        click_through=cfg['click_through'],
    )

    index.setdefault("profiles", []).append(name)
    _save_index(index)
    return True


def delete_profile(name: str) -> bool:
    """删除方案。不允许删除当前活跃方案。"""
    index = _load_index()
    if name == index.get("active"):
        return False
    if name not in index.get("profiles", []):
        return False

    index["profiles"].remove(name)
    _save_index(index)

    path = _profile_path(name)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logger.error(f"删除方案文件失败: {e}")

    return True


def rename_profile(old_name: str, new_name: str) -> bool:
    """重命名方案。"""
    index = _load_index()
    if old_name not in index.get("profiles", []):
        return False
    if new_name in index.get("profiles", []):
        return False

    # 重命名文件
    old_path = _profile_path(old_name)
    new_path = _profile_path(new_name)
    if os.path.exists(old_path):
        try:
            os.rename(old_path, new_path)
        except Exception as e:
            logger.error(f"重命名方案文件失败: {e}")
            return False

    # 更新索引
    idx = index["profiles"].index(old_name)
    index["profiles"][idx] = new_name
    if index.get("active") == old_name:
        index["active"] = new_name
    _save_index(index)
    return True


# ─── 兼容接口 (旧 API) ───────────────────────────────────────

def load_config(filepath: str = None) -> dict:
    """兼容旧接口。"""
    return load_config_from_file(filepath or CONFIG_FILE)


def save_config(filepath: str = None, **kwargs) -> bool:
    """兼容旧接口。"""
    return save_config_to_file(filepath or CONFIG_FILE, **kwargs)
