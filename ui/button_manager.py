"""
TEGG Touch - 按钮管理 Mixin

负责按钮的增删改、空位查找、拖拽/缩放、Toast 提示。
"""

from core.i18n import t
from core.constants import GRID_SIZE, BTN_TYPE_CENTER_BAND
from ui.canvas_renderer import update_button_coords
from ui.edit_panel import open_button_editor, open_center_band_editor


class ButtonManagerMixin:
    """按钮 CRUD 与编辑交互，由 FloatingApp 继承使用。"""

    # ─── 按钮 CRUD ───────────────────────────────────────────

    def add_btn(self):
        w, h = GRID_SIZE, GRID_SIZE
        pos = self._find_empty_slot(w, h, start_x=0, start_y=0, scan='spiral')
        if pos:
            cx, cy = pos
        else:
            cx, cy = 0, 0
        new_btn = {
            'x': cx, 'y': cy,
            'w': w, 'h': h,
            'name': t("button_defaults.name"), 'hover_delay': 200, 'hover_release_delay': 0,
            'hover': '', 'lclick': '', 'rclick': '', 'mclick': '',
            'wheelup': '', 'wheeldown': '',
        }
        self.buttons.append(new_btn)
        self.redraw_all()
        self.show_toast(t("toast.created"))

    def add_center_band_btn(self):
        """新建回中带按钮。"""
        w, h = GRID_SIZE, GRID_SIZE
        pos = self._find_empty_slot(w, h, start_x=0, start_y=0, scan='spiral')
        if pos:
            cx, cy = pos
        else:
            cx, cy = 0, 0
        new_btn = {
            'x': cx, 'y': cy,
            'w': w, 'h': h,
            'name': t("button_defaults.center_band"), 'type': BTN_TYPE_CENTER_BAND,
            'hover_delay': 0, 'hover_release_delay': 0,
            'hover': '', 'lclick': '', 'rclick': '', 'mclick': '',
            'wheelup': '', 'wheeldown': '',
        }
        self.buttons.append(new_btn)
        self.redraw_all()
        self.show_toast(t("toast.center_band_created"))

    def edit_btn(self, idx):
        if self.current_mode != 'main':
            return
        btn = self.buttons[idx]

        # 回中带按钮：打开简单弹窗
        if btn.get('type') == BTN_TYPE_CENTER_BAND:
            def on_delete_cb(del_btn):
                del_btn['deleted'] = True
                self.redraw_all()

            def on_copy_cb(src_btn):
                w, h = src_btn['w'], src_btn['h']
                pos = self._find_empty_slot(w, h, start_x=src_btn['x'], start_y=src_btn['y'], scan='spiral')
                if pos:
                    nx, ny = pos
                else:
                    nx, ny = src_btn['x'], src_btn['y']
                new_btn = {
                    'x': nx, 'y': ny, 'w': w, 'h': h,
                    'name': t("button_defaults.center_band"), 'type': BTN_TYPE_CENTER_BAND,
                    'hover_delay': 0, 'hover_release_delay': 0,
                    'hover': '', 'lclick': '', 'rclick': '', 'mclick': '',
                    'wheelup': '', 'wheeldown': '',
                }
                self.buttons.append(new_btn)
                self.redraw_all()
                self.show_toast(t("toast.copy_success"))

            open_center_band_editor(self.root, btn,
                                    on_delete=on_delete_cb,
                                    on_copy=on_copy_cb)
            return

        def on_save(updated_btn):
            self.redraw_all()

        def on_delete(del_btn):
            del_btn['deleted'] = True
            self.redraw_all()

        def on_copy(src_btn):
            w, h = src_btn['w'], src_btn['h']
            pos = self._find_empty_slot(w, h, start_x=src_btn['x'], start_y=src_btn['y'], scan='spiral')
            if pos:
                nx, ny = pos
            else:
                nx, ny = src_btn['x'], src_btn['y']
            new_btn = {
                'x': nx, 'y': ny,
                'w': w, 'h': h,
                'name': src_btn.get('name', t("button_defaults.name")),
                'hover': src_btn.get('hover', ''),
                'hover_delay': src_btn.get('hover_delay', 200),
                'hover_release_delay': src_btn.get('hover_release_delay', 0),
                'lclick': src_btn.get('lclick', ''),
                'rclick': src_btn.get('rclick', ''),
                'mclick': src_btn.get('mclick', ''),
                'wheelup': src_btn.get('wheelup', ''),
                'wheeldown': src_btn.get('wheeldown', ''),
            }
            self.buttons.append(new_btn)
            self.redraw_all()
            self.show_toast(t("toast.copy_success"))

        open_button_editor(
            self.root, btn,
            on_save=on_save,
            on_delete=on_delete,
            on_copy=on_copy,
            set_window_style=self.set_window_style
        )

    # ─── 拖拽 / 缩放 ────────────────────────────────────────

    def on_btn_drag(self, e, idx):
        btn = self.buttons[idx]
        ox, oy = self._offset_x, self._offset_y
        raw_x = max(0, min(self.win_w - btn['w'], e.x - btn['w'] / 2))
        raw_y = max(0, min(self.win_h - btn['h'], e.y - btn['h'] / 2))
        logical_x = round((raw_x - ox) / GRID_SIZE) * GRID_SIZE
        logical_y = round((raw_y - oy) / GRID_SIZE) * GRID_SIZE
        btn['x'] = logical_x
        btn['y'] = logical_y
        update_button_coords(self.canvas, btn, offset_x=ox, offset_y=oy)

    def on_btn_resize(self, e, idx):
        btn = self.buttons[idx]
        ox, oy = self._offset_x, self._offset_y
        screen_x = btn['x'] + ox
        screen_y = btn['y'] + oy
        raw_w = max(GRID_SIZE, e.x - screen_x)
        raw_h = max(GRID_SIZE, e.y - screen_y)
        btn['w'] = round(raw_w / GRID_SIZE) * GRID_SIZE
        btn['h'] = round(raw_h / GRID_SIZE) * GRID_SIZE
        update_button_coords(self.canvas, btn, offset_x=ox, offset_y=oy)

    # ─── 空位查找 ────────────────────────────────────────────

    def _find_empty_slot(self, w, h, start_x=0, start_y=0, scan='spiral'):
        """在网格上查找不与现有按钮重叠的空位（逻辑坐标，中心原点）。"""
        gs = GRID_SIZE
        ox, oy = self._offset_x, self._offset_y
        min_lx = -ox
        min_ly = -oy
        max_lx = self.screen_w - w - ox
        max_ly = self.screen_h - h - oy

        occupied = [(b['x'], b['y'], b['w'], b['h'])
                    for b in self.buttons if not b.get('deleted')]

        def overlaps(nx, ny):
            for bx, by, bw, bh in occupied:
                if not (nx + w <= bx or nx >= bx + bw or ny + h <= by or ny >= by + bh):
                    return True
            return False

        def in_bounds(nx, ny):
            return min_lx <= nx <= max_lx and min_ly <= ny <= max_ly

        cx = round(start_x / gs) * gs
        cy = round(start_y / gs) * gs

        if in_bounds(cx, cy) and not overlaps(cx, cy):
            return (cx, cy)

        max_radius = max(self.screen_w, self.screen_h) // gs
        for ring in range(1, max_radius + 1):
            for dx in range(-ring, ring + 1):
                for dy in [-ring, ring]:
                    nx, ny = cx + dx * gs, cy + dy * gs
                    if in_bounds(nx, ny) and not overlaps(nx, ny):
                        return (nx, ny)
            for dy in range(-ring + 1, ring):
                for dx in [-ring, ring]:
                    nx, ny = cx + dx * gs, cy + dy * gs
                    if in_bounds(nx, ny) and not overlaps(nx, ny):
                        return (nx, ny)

        return None

    # ─── Toast ───────────────────────────────────────────────

    def show_toast(self, text, duration=1500):
        """在屏幕中央显示 toast 提示，duration 毫秒后消失。"""
        tag = "_toast"
        self.canvas.delete(tag)
        cx = self.screen_w // 2
        cy = self.screen_h // 2
        pw, ph = 200, 40
        self.canvas.create_rectangle(
            cx - pw, cy - ph, cx + pw, cy + ph,
            fill="#000000", outline="", stipple="gray50", tags=tag)
        self.canvas.create_text(
            cx, cy, text=text, fill="#FFFFFF",
            font=("Microsoft YaHei", 16, "bold"), tags=tag)
        self.canvas.tag_raise(tag)
        self.root.after(duration, lambda: self.canvas.delete(tag))
