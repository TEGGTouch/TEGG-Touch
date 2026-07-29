# TEGGTouch 手机遥控 — 设计文档

> 状态：**设计阶段，未进入实现**（2026-07-30 定稿存档，待决策后开工）
> 参考原型：`docs/reference/fkb-phone-prototype.py`（FKB 手机遥控原型，只读归档）
> 相关文档：[产品说明](product-overview.md) · [Agent 集成](agent-integration-design.md)

---

## 1. 目标

让**手机变成蛋挞的一块输入面**：手机浏览器打开一个网页，上面是可自定义的按键 / 摇杆，手指触摸 → 通过局域网 WebSocket 下发 → PC 上的蛋挞执行为真实的键盘 / 鼠标 / 手柄输入。

两个使用场景：

1. **手机当手柄**——不方便用鼠标、或想用双手拇指操作的用户；
2. **不挡画面**——用手机做输入面后，游戏画面上就不需要盖全屏叠加层了，这对嫌叠加层遮挡视野的用户是另一条路子。

---

## 2. 现状评估：蛋挞已经有什么

**原型服务端有一半代码在蛋挞里已经存在，而且是更成熟的版本。移植时应当整块丢弃，不要搬。**

| 原型里的实现 | 蛋挞现有对应物 | 差距 |
|---|---|---|
| `press_key/release_key`（裸 SendInput，原型 237-250 行） | `core/input_engine.py` | 蛋挞多了扩展键处理、`INJECT_MAGIC` 防回环、`release_all_keys` 卡键兜底 |
| `press_gamepad/release_gamepad/joystick_float` | `engine/gamepad_engine.py`：`press_button` / `release_button` / `set_stick` / `set_trigger` / `flush` / `release_all` | 蛋挞是单例 + 驱动门控（仅当 profile 含手柄触发才插虚拟手柄） |
| 按键序列 `a+b+gp:A` 字符串解析 | `engine/run_controller.py::_smart_trigger` | 蛋挞还支持 `xmacro:` / `mouse:` / `app:` / `recenter:` |
| ViGEmBus 检测 + 安装 | `core/gamepad_install.py` | 蛋挞是 5 状态检测 + 打包离线安装包 |
| 手机端 canvas 布局编辑器 | 按键编辑器 + 统一候选键位面板 | 原型只能手输动作字符串，蛋挞是可视化面板 |
| 配置存手机 IndexedDB | `profiles/` 方案系统 | 蛋挞有导入导出、分类复制、宏池、应用池 |

**真正需要新写的只有三块**：

1. 进程内的 HTTP + WebSocket 服务；
2. 手机端网页（渲染 + 多点触控 + 摇杆 + 重连）；
3. 手机布局的存储与编辑（PC 侧）。

---

## 3. 已锁定的架构决策

| # | 决策点 | 结论 | 理由 |
|---|---|---|---|
| 1 | WebSocket 实现 | **PyQt6 自带的 `QtWebSockets`**，不用 `websockets` 库 | 见 §3.1 |
| 2 | 布局配置存放 | **PC 的 profile 里**，手机只渲染不落盘 | 见 §3.2 |
| 3 | 手机布局 vs 叠加层布局 | **两套独立布局** | 叠加层按键是照着游戏画面摆的，搬到手机上很别扭 |
| 4 | 编辑方式 | **混合编辑**：手机摆位置、PC 配动作，实时双向同步 | 见 §5 |
| 5 | 坐标系 | **0~1 相对比例**，不用像素 | 换手机 / 横竖屏 / 平板都能自适应 |
| 6 | 动作协议 | **复用 `_smart_trigger` 语法**，不发明新格式 | 与按键、语音、键盘映射同源，零翻译损耗 |
| 7 | 鉴权 | **一期就要有**，不排到二期 | 见 §6 |

### 3.1 为什么用 QtWebSockets 而不是 websockets 库

已验证 `from PyQt6.QtWebSockets import QWebSocketServer` 在当前环境可用（PyQt6 自带，无需新增依赖）。三个理由：

1. **不引入新依赖**，打包体积和 spec 都不用动；
2. **信号槽直接跑在 Qt 主线程**，收到指令可以直接调 `_smart_trigger`。如果用 asyncio 版 `websockets`，回调在另一个线程，而 `_smart_trigger` 会碰 scene item 和 `QTimer`，必须自己做线程编组 —— 纯粹自找的复杂度；
3. **避开上游 API 漂移**。原型就栽在这上面，详见 §8 踩坑记录。

HTTP 那一侧只服务一两个静态文件，用 `QTcpServer` 手写极简响应即可，和 WS 共用一套生命周期。

### 3.2 为什么配置存 PC 而不是手机

原型是手机端 IndexedDB 自己存自己编（原型 388-426 行），等于在 JS 里重写一个功能弱得多的编辑器，还和 PC 的方案体系完全割裂。

改成 PC 存储后：手机连上就拉当前 profile 的手机布局，动作字符串复用同一套语法，宏池 / 应用池 / 方案导入导出全部白嫖。**单一数据源始终在 PC 的 profile 里**，手机只是渲染端 + 输入端，本地只留一份缓存供断线时继续显示。

---

## 4. 数据模型

profile 里新增一段，与 `key_remaps` 同级：

```json
"phone_control": {
  "enabled": false,
  "aspect": [2340, 1080],
  "buttons": [
    {
      "id": 1,
      "x": 0.82, "y": 0.70,
      "w": 0.10, "h": 0.18,
      "shape": "rect",
      "name": "跳",
      "actions": "space"
    },
    {
      "id": 2,
      "x": 0.14, "y": 0.68,
      "w": 0.22, "h": 0.39,
      "shape": "stick",
      "name": "左摇杆",
      "stick": "L",
      "deadzone": 0.15
    }
  ]
}
```

**坐标必须是 0~1 的相对比例，不能存像素。** 这是与叠加层按键最重要的差别 —— 叠加层是固定屏幕坐标，手机端换设备 / 转屏就废了。`aspect` 只用于在 PC 画布上还原正确比例，不参与定位计算。

`shape` 取值：`rect`（矩形按钮）、`circle`（圆形按钮）、`stick`（模拟摇杆）。原型里的 `glory`（荣耀摇杆）是纯绘制样式，不是独立交互类型，可并入 `stick` 的外观选项。

`actions` 复用 `_smart_trigger` 语法，因此手机按钮天然支持：普通键、组合键、`mouse:*`、`gp:*`、`xmacro:*`、`app:*`、`recenter:*`。

配套改动：`core/config_manager.py` 的 `load_config_from_file` 默认值 + `save_config_to_file` 参数 + 一个 `_validate_phone_control()` 校验函数（参照 `_validate_key_remaps` 的写法，丢弃缺字段的脏数据）。

---

## 5. 编辑方式：混合编辑

### 5.1 为什么不能只在一边编辑

编辑一个按钮其实是两件事，它们的最佳场所正好相反：

| | 在手机上做 | 在 PC 上做 |
|---|---|---|
| 摆位置 / 调大小 | ✅ 拇指够不够得着、热区舒不舒服，手指一放就知道 | ❌ 对着模拟的手机框瞎估 |
| 配动作 | ❌ 几百个键 + 手柄键 + 宏 + 应用，手机上翻是灾难 | ✅ 现成的统一候选面板 |

原型全在手机上做，所以动作只能靠手输字符串（`a+b+gp:A+delay:100`，原型 616 行），在蛋挞里这是退步。

### 5.2 职责划分

- **手机端**：拖动、缩放、新增、删除按钮 —— 所见即所得；
- **PC 端**：选中按钮后，用现有候选面板配动作、改名、设参数；
- **实时联动**：手机上点一下按钮，PC 端编辑器立刻选中它；PC 上改完动作，手机上的标签立刻更新。

同步几乎不要额外成本 —— WebSocket 本来就是为遥控开的双向长连接，编辑期复用同一条连接即可。**没有导入 / 导出 / 合并冲突那一套**，因为数据源唯一。

### 5.3 三个必须处理的细节

1. **编辑模式下服务端必须丢弃输入指令**。否则在手机上拖按钮，每碰一下就往游戏里打一个键。协议里带 `mode`，服务端按 `mode` 门控 —— 不做的话第一次试用就会踩到。
2. **手机没连时 PC 画布也要能编辑**。用上次记录的 `aspect` 画框，照样能拖能配。不能变成"必须手机在线才能改布局"。
3. **PC 画布单独写，不要复用 `OverlayScene`**。那个场景绑着全屏坐标系、穿透模式、hover 状态机，全是手机布局用不上的东西。复用 `ButtonData` 模型和候选面板即可，画布本身是个轻量 `QGraphicsView`。

---

## 6. 安全模型

**这是原型最大的问题，也是本功能的头号风险。**

原型在局域网上开了一个**无认证的远程输入服务**：同一个 WiFi 下任何人打开 `http://<你的IP>:8765` 就能往你电脑里打字、按手柄键。宿舍、公司、咖啡厅网络下，这就是一个远程控制后门。

一期必须具备：

| 要求 | 做法 |
|---|---|
| 令牌鉴权 | 每次启动生成随机 token，二维码 URL 里带上；WS 握手校验，不匹配直接拒绝 |
| 单设备锁 | 同时只允许一个设备连接，第二个连接请求需 PC 端确认 |
| 随运行模式起停 | 退出运行模式立即关闭服务，不留后台监听 |
| 可见性 | 界面上明确显示「已连接 1 台设备」+ 对端 IP，随时可踢 |
| 显式开启 | 默认关闭，用户主动开启并知晓风险提示 |

> token 走明文 LAN（`ws://` 无 TLS）。对局域网场景这是可接受的取舍——上 TLS 需要证书，自签名会让手机浏览器报警，体验代价大于收益。但要在文案里说明。

---

## 7. 通信协议

### 7.1 遥控指令（手机 → PC）

沿用原型的 JSON 结构（原型 313-334 行 `handle_message`），扩展为：

```jsonc
{"action": "key_press",   "key": "space"}
{"action": "key_release", "key": "space"}
{"action": "gp_press",    "btn": "A"}
{"action": "gp_release",  "btn": "A"}
{"action": "stick",       "id": "L", "x": 0.42, "y": -0.87}   // -1.0 ~ 1.0
{"action": "trigger",     "id": "LT", "v": 0.75}              // 0.0 ~ 1.0
{"action": "invoke",      "actions": "xmacro:连招1"}           // 直接走 _smart_trigger
```

前四条直接映射到 `GamepadEngine` / `input_engine`；`invoke` 是新增的通用出口，把动作字符串原样交给 `_smart_trigger`，宏 / 应用 / 回中都走它。

### 7.2 编辑与同步

```jsonc
// 手机 → PC
{"type": "hello",         "screen": [2340, 1080], "token": "…"}
{"type": "mode",          "mode": "edit"}          // edit | run
{"type": "layout_update", "id": 1, "x": 0.8, "y": 0.7, "w": 0.1, "h": 0.18}
{"type": "select",        "id": 1}

// PC → 手机
{"type": "layout_push",   "buttons": [...]}         // 整份推送
{"type": "select",        "id": 1}
```

### 7.3 生命周期与兜底

- **断连即释放**：手机在按住状态下断网 / 息屏，键会永久卡住。必须在 `disconnected` 信号里调 `release_all_keys()` + `GamepadEngine.release_all()`，与 F12 停止走同一条兜底路径。
- **服务随运行模式起停**：进运行模式启服务，退出即关，和 `keyboard_hook` 的生命周期一致。

---

## 8. 踩坑记录

### 坑 1：websockets ≥13 改了 handler 签名（原型已修复）

> 本节即原桌面 `BUGFIX-websocket.md` 的内容，已并入本文档统一保管，不另留副本。

**现象**：手机能打开控制页面，但状态栏一直显示"连接失败"。与防火墙、WiFi、路由器无关，纯代码不兼容。

**原因**：`websockets` ≥ 13 起，`websockets.serve` 走新的 asyncio API，**只给处理器传 1 个参数**（`websocket`），不再传 `path`。原型的 `async def ws_handler(websocket, path)` 于是每次连接都抛：

```
TypeError: ws_handler() missing 1 required positional argument: 'path'
```

握手当场失败 → 连接被中断 → 手机端 `ws.onerror` 刷成"连接失败"。HTTP 页面走的是另一条链路（`http.server`），所以页面能正常打开，只有 WebSocket 连不上 —— 这个不对称是排查时最容易被误导的地方。

**修复**：签名改 `async def ws_handler(websocket, *args)` 吃掉差异，两代都能跑（本机实测 websockets 16.0 确认）。

**对蛋挞的启示**：这正是决策 #1 选 `QtWebSockets` 的直接原因 —— Qt 的 API 稳定性由 PyQt6 版本统一约束，不会因为某个第三方库自己升 major 就把握手打挂。

### 坑 2：原型的摇杆是死的

服务端有 `joystick` 分支（原型 329-332 行），但**手机端从来没有发过这条消息** —— 全文只有两处 `ws.send`（579、581 行），都是按键；也没有注册 `touchmove` 监听。也就是说原型的"圆形(摇杆)"和"荣耀摇杆"只是画了个图形，按下去等同普通按钮，**模拟摇杆功能实际未实现**。

移植时不要以为这块能直接抄，摇杆需要从零做：`touchmove` 追踪 + 圆心偏移归一化 + 死区 + 松手回中。

### 坑 3：防火墙规则会无限堆积

原型用动态端口（`find_available_port(8765)`），每次启动按新端口新增一条 `netsh advfirewall` 规则（原型 38-45 行），规则名带端口号，于是**每换一个端口就多一条规则，永不清理**。

蛋挞要么用固定端口，要么用固定规则名做「删旧建新」。另外蛋挞已经是提权运行，`netsh` 能跑通，但加防火墙规则属于对系统的侵入性改动，应当由用户显式确认。

### 坑 4：手机浏览器的老问题

- `touch-action: none` + `preventDefault`，否则滑动会触发页面滚动 / 缩放（原型用 `{passive: false}` 处理了，可参考 568-570 行）；
- Wake Lock API 防息屏，否则玩着玩着屏幕黑了；
- iOS Safari 的全屏 / 安全区（刘海、底部横条）处理。

---

## 9. 分期计划

### 一期：手机当手柄（跑通风险点）

- 内置**一套固定布局**：十字键 + ABXY + LB/RB/LT/RT + 双摇杆，不做自定义编辑；
- 完整的服务端：QtWebSockets + 极简 HTTP + 令牌鉴权 + 单设备锁 + 断连释放；
- 二维码连接；
- 配置只有一个开关。

目的是**用最小的 UI 成本，把服务端、鉴权、延迟、断连、打包这些真正的风险点全部验证掉**。反过来先做编辑器，风险就全压在最后。

即便一期不做编辑，**手机上报分辨率**和**相对坐标渲染**这两件事也要按 §4 的格式做对，二期加编辑器时才不用回头改协议和存储。

### 二期：自定义布局

- profile 增加 `phone_control` 完整字段；
- PC 端手机布局编辑器（轻量 `QGraphicsView` + 复用候选面板）；
- 混合编辑与实时双向同步（§5）。

### 工作量粗估

| 模块 | 估时 |
|---|---|
| 服务端 + 鉴权 + 生命周期 | 1 天 |
| 手机端网页（渲染 / 多点触控 / 摇杆 / 重连） | 1~2 天 |
| PC 端手机布局编辑器 | 2~3 天 |
| 打包 + 联调 | 1 天 |

---

## 10. 打包注意

- 手机端 HTML/JS/CSS 要作为数据文件进 `teggtouch.spec`；
- **必须同步加进 `smoke_test_build.py` 的 `REQUIRED_PATHS`**。该文件开头就写明「加新依赖时往这里加一行，不要单纯依赖手工测启动」——v0.3.0 漏装 vgamepad DLL 的事故就是这么来的；
- 若决定引入 `qrcode` 依赖（当前未安装），要评估打包体积；也可以自己算二维码矩阵用 `QPainter` 画，省一个依赖。

---

## 11. 待决策

| # | 问题 | 备选 |
|---|---|---|
| 1 | 一期范围 | A. 固定布局先跑通（推荐）　B. 一步到位做自定义布局 |
| 2 | 二维码 | A. 引入 `qrcode` 依赖　B. 自绘矩阵省依赖 |
| 3 | 端口策略 | A. 固定端口（防火墙规则干净）　B. 动态端口（避免占用冲突） |
| 4 | 延迟预期 | WiFi 往返通常 5~30ms，休闲游戏无感，竞技 FPS 不适用 —— 需在文案上说清楚 |

---

## 附：关键代码位置速查

| 用途 | 位置 |
|---|---|
| 动作字符串统一分发 | `engine/run_controller.py::_smart_trigger` |
| 键盘注入（含防回环魔数） | `core/input_engine.py` |
| 手柄引擎（按钮 / 摇杆 / 扳机） | `engine/gamepad_engine.py`：`press_button` / `set_stick` / `set_trigger` / `release_all` |
| profile 读写与字段校验 | `core/config_manager.py`：`load_config_from_file` / `save_config_to_file` / `_validate_key_remaps`（可作校验函数范本） |
| 候选键位面板（可复用组件） | `views/button_editor_dialog.py`：`_get_key_categories` / `_get_mouse_keys` / `populate_gp_palette` / `TagInput` |
| 服务生命周期参照物 | `core/keyboard_hook.py` + `engine/run_controller.py::_start_key_remap`（随运行模式起停 + 兜底释放） |
| 原型全文 | `docs/reference/fkb-phone-prototype.py` |
