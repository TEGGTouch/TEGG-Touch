"""
TEGG Touch 蛋挞 辅助软件 - 配置管理器

负责配置文件的加载、保存，以及多方案(Profile)管理。
方案存储在 profiles/ 目录，每个方案一个 JSON 文件。
"""

import json
import os
import sys
import copy
import logging

from .constants import (
    CONFIG_FILE, DEFAULT_TRANSPARENCY,
    MIN_WINDOW_SIZE, RUNTIME_FIELDS,
    BUTTON_OPTIONAL_DEFAULTS,
    PROFILES_DIR, PROFILES_INDEX, DEFAULT_PROFILE_NAME,
    PT_ON, PT_OFF, PT_BLOCK,
    HOTKEYS_FILE, DEFAULT_HOTKEYS,
    default_wheel_sectors,
    default_wheel_center_ring,
)

# 默认方案模板文件路径（core/default_profile.json）
# 打包后 __file__ 指向 _internal/ 内部，需要用 EXE 所在目录
if getattr(sys, 'frozen', False):
    DEFAULT_PROFILE_TEMPLATE = os.path.abspath(os.path.join(
        os.path.dirname(sys.executable), 'core', 'default_profile.json'))
else:
    DEFAULT_PROFILE_TEMPLATE = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 'default_profile.json'))

logger = logging.getLogger(__name__)


# ─── 坐标系迁移 ──────────────────────────────────────────────

def _migrate_to_center_coords(data: dict) -> bool:
    """将旧版左上角原点坐标迁移为中心原点坐标。
    
    旧坐标: screen_x, screen_y (左上角原点, ≥0)
    新坐标: logical_x = old_x - screen_w//2, logical_y = old_y - screen_h//2
    
    Returns True if migration was performed.
    """
    if data.get('coord_system') == 'center':
        return False  # 已迁移

    # 从 geometry 字段推断屏幕尺寸
    geo = data.get('geometry', '')
    sw, sh = 1920, 1080  # 默认值
    try:
        wh = geo.split('+')[0].split('x')
        sw, sh = int(wh[0]), int(wh[1])
    except Exception:
        pass

    offset_x = sw // 2
    offset_y = sh // 2

    buttons = data.get('buttons', [])
    for btn in buttons:
        if 'x' in btn:
            btn['x'] = btn['x'] - offset_x
        if 'y' in btn:
            btn['y'] = btn['y'] - offset_y

    data['coord_system'] = 'center'
    logger.info(f"坐标系迁移完成: {len(buttons)} 个按钮, 偏移 ({offset_x}, {offset_y})")
    return True


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

    # 首次初始化：使用 default_profile.json 模板（必须存在）
    logger.info("首次初始化方案系统，使用默认模板")
    template = _load_default_template()
    buttons = [_ensure_button_fields(b) for b in template.get('buttons', [])]
    save_config_to_file(
        _profile_path(DEFAULT_PROFILE_NAME),
        geometry=template.get('geometry', '2560x1440+0+0'),
        transparency=template.get('transparency', DEFAULT_TRANSPARENCY),
        buttons=buttons,
        click_through=template.get('click_through', PT_ON),
        wheel_visible=template.get('wheel_visible', False),
        wheel_sectors=template.get('wheel_sectors', default_wheel_sectors()),
        wheel_enlarged=template.get('wheel_enlarged', True),
        wheel_mode=template.get('wheel_mode', 'large'),
        wheel_center_ring=template.get('wheel_center_ring', default_wheel_center_ring()),
        wheel_center_ring_visible=template.get('wheel_center_ring_visible', True),
        wheel_middle_ring_visible=template.get('wheel_middle_ring_visible', True),
    )
    _save_index({"active": DEFAULT_PROFILE_NAME, "profiles": [DEFAULT_PROFILE_NAME]})
    cfg = load_profile(DEFAULT_PROFILE_NAME)
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
        'buttons': [],
        'ball_x': None,
        'ball_y': None,
        'click_through': PT_ON,
        'wheel_visible': False,
        'wheel_sectors': default_wheel_sectors(),
        'wheel_enlarged': False,
        'wheel_center_ring': default_wheel_center_ring(),
        'wheel_center_ring_visible': True,
        'wheel_middle_ring_visible': True,
        'run_toolbar_x': None,
        'run_toolbar_y': None,
        'grid_size': None,
        # 语音识别
        'voice_enabled': False,
        'voice_language': 'zh-CN',
        'voice_commands': [],
        'voice_mic_device': None,
        'voice_auto_start': True,
        # 自定义宏
        'macros': [],
    }
    if not os.path.exists(filepath):
        return result
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 自动迁移旧坐标系（左上角原点 → 中心原点）
        if _migrate_to_center_coords(data):
            # 迁移后立即回写文件，避免重复迁移
            try:
                with open(filepath, 'w', encoding='utf-8') as fw:
                    json.dump(data, fw, ensure_ascii=False, indent=2)
                logger.info(f"坐标系迁移已回写: {filepath}")
            except Exception as we:
                logger.warning(f"坐标系迁移回写失败: {we}")
        
        result['geometry'] = _validate_geometry(data.get('geometry', ''))
        result['transparency'] = data.get('transparency', DEFAULT_TRANSPARENCY)
        result['ball_x'] = data.get('ball_x', None)
        result['ball_y'] = data.get('ball_y', None)
        # 兼容旧版布尔值 click_through → 新三态字符串
        raw_ct = data.get('click_through', True)
        if isinstance(raw_ct, bool):
            result['click_through'] = PT_ON if raw_ct else PT_OFF
        elif raw_ct in (PT_ON, PT_OFF, PT_BLOCK):
            result['click_through'] = raw_ct
        else:
            result['click_through'] = PT_ON
        buttons = data.get('buttons', None)
        if buttons is not None:
            result['buttons'] = [_ensure_button_fields(b) for b in buttons]
        # 中心轮盘
        result['wheel_visible'] = data.get('wheel_visible', False)
        result['wheel_enlarged'] = data.get('wheel_enlarged', False)
        raw_sectors = data.get('wheel_sectors', None)
        if raw_sectors and isinstance(raw_sectors, list) and len(raw_sectors) == 8:
            result['wheel_sectors'] = raw_sectors
        # 中心圆环按钮
        raw_ring = data.get('wheel_center_ring', None)
        if raw_ring and isinstance(raw_ring, dict):
            result['wheel_center_ring'] = raw_ring
        result['wheel_center_ring_visible'] = data.get('wheel_center_ring_visible', True)
        result['wheel_middle_ring_visible'] = data.get('wheel_middle_ring_visible', True)
        # 轮盘模式与缩放
        result['wheel_mode'] = data.get('wheel_mode', None)
        result['wheel_offset'] = data.get('wheel_offset', 0)
        # 内环按钮
        raw_inner = data.get('wheel_inner_ring', None)
        if raw_inner and isinstance(raw_inner, dict):
            result['wheel_inner_ring'] = raw_inner
        # 运行工具栏位置（按方案记忆）
        result['run_toolbar_x'] = data.get('run_toolbar_x', None)
        result['run_toolbar_y'] = data.get('run_toolbar_y', None)
        # 网格大小
        result['grid_size'] = data.get('grid_size', None)
        # 坐标格式标记（cells=格子数，无=旧像素格式）
        result['coord_format'] = data.get('coord_format', None)
        # 语音识别
        result['voice_enabled'] = data.get('voice_enabled', False)
        result['voice_language'] = data.get('voice_language', 'zh-CN')
        raw_vc = data.get('voice_commands', [])
        if isinstance(raw_vc, list):
            result['voice_commands'] = raw_vc
        result['voice_mic_device'] = data.get('voice_mic_device', None)
        result['voice_auto_start'] = data.get('voice_auto_start', True)
        # 自定义宏
        raw_macros = data.get('macros', [])
        if isinstance(raw_macros, list):
            result['macros'] = raw_macros
        logger.info(f"配置加载成功: {filepath}")
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
    return result


def _clean_sector_for_save(sec: dict) -> dict:
    """清理轮盘扇区的运行时字段。"""
    return {k: v for k, v in sec.items()
            if k not in RUNTIME_FIELDS and k != 'deleted'}


def save_config_to_file(filepath: str, *, geometry, transparency, buttons,
                        ball_x=None, ball_y=None, click_through=False,
                        wheel_visible=False, wheel_sectors=None,
                        wheel_enlarged=False,
                        wheel_mode=None,
                        wheel_offset=0,
                        wheel_center_ring=None,
                        wheel_inner_ring=None,
                        wheel_center_ring_visible=True,
                        wheel_middle_ring_visible=True,
                         run_toolbar_x=None,
                         run_toolbar_y=None,
                         grid_size=None,
                         coord_format=None,
                         coord_system=None,
                         voice_enabled=None,
                         voice_language=None,
                         voice_commands=None,
                         voice_mic_device=None,
                         voice_auto_start=None,
                         macros=None) -> bool:
    """保存配置到指定文件。"""
    # Bug 5 fix: geometry 为 None 时使用当前屏幕尺寸作为 fallback
    if geometry is None:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            sw = user32.GetSystemMetrics(0)
            sh = user32.GetSystemMetrics(1)
            geometry = f"{sw}x{sh}+0+0"
        except Exception:
            geometry = "1920x1080+0+0"
        logger.warning(f"geometry 为空，使用 fallback: {geometry}")

    geo_to_save = geometry
    try:
        wh = geometry.split('+')[0].split('x')
        w, h = int(wh[0]), int(wh[1])
        if w >= MIN_WINDOW_SIZE and h >= MIN_WINDOW_SIZE:
            geo_to_save = geometry
    except Exception:
        pass

    clean_btns = [_clean_button_for_save(b) for b in buttons if not b.get('deleted')]

    # 清理轮盘扇区运行时字段
    clean_sectors = None
    if wheel_sectors:
        clean_sectors = [_clean_sector_for_save(s) for s in wheel_sectors]

    data = {
        'coord_system': 'center',
        'geometry': geo_to_save,
        'transparency': transparency,
        'buttons': clean_btns,
        'ball_x': ball_x,
        'ball_y': ball_y,
        'click_through': click_through,
        'wheel_visible': wheel_visible,
        'wheel_enlarged': wheel_enlarged,
        'wheel_center_ring_visible': wheel_center_ring_visible,
        'wheel_middle_ring_visible': wheel_middle_ring_visible,
        'run_toolbar_x': run_toolbar_x,
        'run_toolbar_y': run_toolbar_y,
    }
    if grid_size is not None:
        data['grid_size'] = grid_size
    if coord_format:
        data['coord_format'] = coord_format
    if clean_sectors:
        data['wheel_sectors'] = clean_sectors

    # 轮盘模式与缩放
    if wheel_mode is not None:
        data['wheel_mode'] = wheel_mode
    if wheel_offset:
        data['wheel_offset'] = wheel_offset

    # 中心圆环按钮
    if wheel_center_ring:
        clean_ring = {k: v for k, v in wheel_center_ring.items()
                      if k not in RUNTIME_FIELDS and k != 'deleted'}
        data['wheel_center_ring'] = clean_ring

    # 内环按钮
    if wheel_inner_ring:
        clean_inner = {k: v for k, v in wheel_inner_ring.items()
                       if k not in RUNTIME_FIELDS and k != 'deleted'}
        data['wheel_inner_ring'] = clean_inner

    # 语音识别
    if voice_enabled is not None:
        data['voice_enabled'] = voice_enabled
    if voice_language is not None:
        data['voice_language'] = voice_language
    if voice_commands is not None:
        data['voice_commands'] = voice_commands
    if voice_mic_device is not None:
        data['voice_mic_device'] = voice_mic_device
    if voice_auto_start is not None:
        data['voice_auto_start'] = voice_auto_start

    # 自定义宏
    if macros is not None:
        data['macros'] = macros

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


def _load_default_template() -> dict:
    """从 core/default_profile.json 加载默认方案模板（必须存在）。"""
    if not os.path.exists(DEFAULT_PROFILE_TEMPLATE):
        raise FileNotFoundError(
            f"默认方案模板不存在: {DEFAULT_PROFILE_TEMPLATE}\n"
            "请确保 core/default_profile.json 已包含在打包中。")
    try:
        with open(DEFAULT_PROFILE_TEMPLATE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"默认方案模板加载成功: {DEFAULT_PROFILE_TEMPLATE}")
        return data
    except Exception as e:
        raise RuntimeError(f"默认方案模板加载失败: {e}")


def create_profile(name: str, from_template: bool = True) -> bool:
    """创建新方案。

    Args:
        name: 方案名称
        from_template: True=从默认模板创建（完整默认布局），
                       False=空白方案（无按钮/轮盘）

    Returns:
        True if created, False if name already exists
    """
    index = _load_index()
    if name in index.get("profiles", []):
        return False

    if from_template:
        # Bug 6 fix: from_template=True → 从默认模板加载完整布局
        template = _load_default_template()
        buttons = [_ensure_button_fields(b) for b in template.get('buttons', [])]
        save_config_to_file(
            _profile_path(name),
            geometry=template.get('geometry', '2560x1440+0+0'),
            transparency=template.get('transparency', DEFAULT_TRANSPARENCY),
            buttons=buttons,
            click_through=template.get('click_through', PT_ON),
            wheel_visible=template.get('wheel_visible', False),
            wheel_sectors=template.get('wheel_sectors', default_wheel_sectors()),
            wheel_enlarged=template.get('wheel_enlarged', True),
            wheel_mode=template.get('wheel_mode', 'large'),
            wheel_center_ring=template.get('wheel_center_ring', default_wheel_center_ring()),
            wheel_center_ring_visible=template.get('wheel_center_ring_visible', True),
            wheel_middle_ring_visible=template.get('wheel_middle_ring_visible', True),
        )
    else:
        # from_template=False → 空白方案（无按钮，仅默认轮盘）
        save_config_to_file(
            _profile_path(name),
            geometry='2560x1440+0+0',
            transparency=DEFAULT_TRANSPARENCY,
            buttons=[],
            click_through=PT_ON,
            wheel_visible=False,
            wheel_sectors=default_wheel_sectors(),
            wheel_enlarged=False,
            wheel_center_ring=default_wheel_center_ring(),
            wheel_center_ring_visible=True,
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


# ─── 导入导出 ─────────────────────────────────────────────────

def export_profile(name: str, dest_path: str) -> bool:
    """导出指定方案的 JSON 文件到目标路径。"""
    src = _profile_path(name)
    if not os.path.exists(src):
        logger.error(f"导出失败: 方案文件不存在 {src}")
        return False
    try:
        import shutil
        shutil.copy2(src, dest_path)
        logger.info(f"方案导出成功: {name} -> {dest_path}")
        return True
    except Exception as e:
        logger.error(f"方案导出失败: {e}")
        return False


def import_profile(src_path: str) -> str | None:
    """从外部 JSON 文件导入方案。

    自动以文件名（去扩展名）作为方案名，若重名则添加后缀。
    Returns: 新方案名，失败返回 None。
    """
    if not os.path.exists(src_path):
        logger.error(f"导入失败: 文件不存在 {src_path}")
        return None

    # 读取并验证 JSON
    try:
        with open(src_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'buttons' not in data:
            logger.error("导入失败: JSON 格式无效（缺少 buttons 字段）")
            return None
    except Exception as e:
        logger.error(f"导入失败: {e}")
        return None

    # 确定方案名
    base_name = os.path.splitext(os.path.basename(src_path))[0]
    name = base_name
    index = _load_index()
    profiles = index.get("profiles", [])
    counter = 1
    while name in profiles:
        name = f"{base_name}_{counter}"
        counter += 1

    # 写入 profiles 目录
    dest = _profile_path(name)
    try:
        import shutil
        shutil.copy2(src_path, dest)
    except Exception as e:
        logger.error(f"导入复制文件失败: {e}")
        return None

    # 更新索引
    profiles.append(name)
    index["profiles"] = profiles
    _save_index(index)
    logger.info(f"方案导入成功: {src_path} -> {name}")
    return name


# ─── 兼容接口 (旧 API) ───────────────────────────────────────

def load_config(filepath: str = None) -> dict:
    """兼容旧接口。"""
    return load_config_from_file(filepath or CONFIG_FILE)


def save_config(filepath: str = None, **kwargs) -> bool:
    """兼容旧接口。"""
    return save_config_to_file(filepath or CONFIG_FILE, **kwargs)


# ─── 全局快捷键配置 ──────────────────────────────────────────

def load_hotkeys() -> dict:
    """加载全局快捷键配置。不存在则返回默认值。"""
    result = copy.deepcopy(DEFAULT_HOTKEYS)
    if not os.path.exists(HOTKEYS_FILE):
        return result
    try:
        with open(HOTKEYS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for k in DEFAULT_HOTKEYS:
            if k in data:
                result[k] = data[k]
        # 保留 language 字段（不在 DEFAULT_HOTKEYS 中）
        if 'language' in data:
            result['language'] = data['language']
        logger.info(f"快捷键配置加载成功: {HOTKEYS_FILE}")
    except Exception as e:
        logger.error(f"快捷键配置加载失败: {e}")
    return result


def save_hotkeys(hotkeys: dict) -> bool:
    """保存全局快捷键配置（合并写入，保留 language 等额外字段）。"""
    try:
        # 先读取现有文件，合并保存（避免丢失 language 等字段）
        existing = {}
        if os.path.exists(HOTKEYS_FILE):
            try:
                with open(HOTKEYS_FILE, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing.update(hotkeys)
        os.makedirs(os.path.dirname(HOTKEYS_FILE) or '.', exist_ok=True)
        with open(HOTKEYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        logger.info(f"快捷键配置保存成功: {HOTKEYS_FILE}")
        return True
    except Exception as e:
        logger.error(f"快捷键配置保存失败: {e}")
        return False
