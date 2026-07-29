# ══════════════════════════════════════════════════════════════════════
# 【归档 · 只读参考】FKB 手机遥控原型 (2026-07-22 桌面版 main.py 原样归档)
#
# 这不是蛋挞的代码, 不参与构建, 不要 import。仅作为 docs/phone-control-design.md
# 的参考实现留档 —— 设计文档里引用的行号以本文件为准。
#
# 原型自带的输入模拟 (SendInput / vgamepad) 在蛋挞里已有更成熟的版本
# (core/input_engine.py + engine/gamepad_engine.py), 移植时应当整块丢弃,
# 只参考它的 WebSocket 协议、手机端多点触控与摇杆处理。
# ══════════════════════════════════════════════════════════════════════

"""
FKB 手机遥控服务端 (兼容版)
修复 importlib.util 兼容性问题，无需额外库。
"""
import sys, os, traceback, logging, ctypes, socket, threading, asyncio, importlib, time, json, re, subprocess

# 全局异常钩子，防止闪退
def global_excepthook(exc_type, exc_value, exc_tb):
    logging.error("未捕获异常:", exc_info=(exc_type, exc_value, exc_tb))
    print(f"发生错误: {exc_value}\n详情见 fkb_server.log")
sys.excepthook = global_excepthook

def thread_excepthook(args):
    logging.error(f"线程异常: {args.exc_value}", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    print(f"线程异常: {args.exc_value}")
threading.excepthook = thread_excepthook

logging.basicConfig(filename='fkb_server.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

def run_as_admin():
    if ctypes.windll.shell32.IsUserAnAdmin():
        return True
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{sys.argv[0]}"', None, 1)
        sys.exit()
    except Exception as e:
        logging.error(f"提权失败: {e}")
        return False

def set_high_priority():
    try:
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(handle, 0x80)
    except Exception as e:
        logging.warning(f"提升优先级失败: {e}")

def allow_firewall_ports(ports):
    for port in ports:
        try:
            subprocess.run(f'netsh advfirewall firewall add rule name="FKB Server {port}" dir=in action=allow protocol=TCP localport={port}',
                           shell=True, capture_output=True, check=False)
            logging.info(f"防火墙规则添加: 端口{port}")
        except Exception as e:
            logging.warning(f"防火墙规则添加失败: {port}, {e}")

def install_pip_package(pkg):
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        logging.error(f"pip安装失败: {pkg}, {e}")
        return False

def check_module(module_name):
    """通用模块检测函数，兼容所有Python版本"""
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False

def ensure_python_libs():
    required = {
        'keyboard': 'keyboard',
        'vgamepad': 'vgamepad',
        'websockets': 'websockets',
        'qrcode': 'qrcode[pil]',
        'pystray': 'pystray',
        'PIL': 'Pillow'
    }
    missing = []
    for mod, pkg in required.items():
        if not check_module(mod):
            missing.append((mod, pkg))
    if missing:
        print("安装缺失的 Python 库...")
        for _, pkg in missing:
            print(f"  {pkg}")
            if not install_pip_package(pkg):
                print(f"请手动安装: pip install {pkg}")
                return False
        for m, _ in missing:
            if not check_module(m):
                return False
    return True

def check_vigem():
    try:
        r = subprocess.run(['sc', 'query', 'ViGEmBus'], capture_output=True, text=True)
        if 'RUNNING' in r.stdout:
            import vgamepad as vg
            g = vg.VX360Gamepad()
            g.update()
            del g
            return True
    except Exception as e:
        logging.warning(f"ViGEmBus 检测异常: {e}")
    return False

def install_vigem():
    try:
        subprocess.run(['winget', 'install', '--id=ViGEm.ViGEmBus', '-e', '--silent', '--accept-package-agreements'],
                       check=True, capture_output=True, timeout=120)
        time.sleep(5)
        subprocess.run(['sc', 'start', 'ViGEmBus'], capture_output=True, timeout=10)
        time.sleep(2)
        return check_vigem()
    except Exception as e:
        logging.error(f"ViGEmBus 安装失败: {e}")
        return False

def ensure_vigem():
    if check_vigem():
        return True
    print("安装 ViGEmBus 驱动...")
    if install_vigem():
        print("安装成功")
        return True
    else:
        print("手柄功能不可用")
        return False

def get_best_ip():
    try:
        output = subprocess.run(['route', 'print', '0.0.0.0'], capture_output=True, text=True).stdout
        for line in output.splitlines():
            if '0.0.0.0' in line and '255.255.255.255' not in line:
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[3]
                    socket.inet_aton(ip)
                    return ip
    except Exception as e:
        logging.warning(f"路由表解析失败: {e}")
    try:
        ipconf = subprocess.run(['ipconfig'], capture_output=True, text=True).stdout
        blocks = re.split(r'\n\s*\n', ipconf)
        for block in blocks:
            if 'IPv4' in block and ('Wi-Fi' in block or '以太网' in block or 'Ethernet' in block):
                for line in block.splitlines():
                    if 'IPv4' in line:
                        addr = line.strip().split(': ')[-1]
                        if not addr.startswith('127.') and not addr.startswith('169.254'):
                            return addr
    except Exception as e:
        logging.warning(f"ipconfig解析失败: {e}")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def is_port_in_use(port, host='0.0.0.0'):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        return False
    except:
        return True
    finally:
        s.close()

def find_available_port(start_port, max_attempts=20):
    for offset in range(max_attempts):
        port = start_port + offset
        if not is_port_in_use(port):
            return port
    raise RuntimeError("无可用端口")

def create_tray_icon(stop_event, get_qr_func):
    try:
        from PIL import Image, ImageDraw
        import pystray
        img = Image.new('RGB', (16, 16), (0, 128, 128))
        d = ImageDraw.Draw(img)
        d.rectangle([2, 2, 13, 13], fill=(0, 255, 255))
        icon = pystray.Icon("FKB Server", img, "FKB 手机遥控")
        menu = pystray.Menu(
            pystray.MenuItem('显示二维码', lambda: get_qr_func(show=True)),
            pystray.MenuItem('退出', lambda: (stop_event.set(), icon.stop()))
        )
        icon.menu = menu
        threading.Thread(target=icon.run, daemon=True).start()
        return icon
    except Exception as e:
        logging.warning(f"系统托盘创建失败，将使用终端模式: {e}")
        print("托盘创建失败，程序将在终端运行，关闭终端即可退出。")
        return None

def main():
    try:
        logging.info("程序启动")
        if not run_as_admin():
            print("请以管理员身份运行")
            return
        set_high_priority()

        print("检查依赖...")
        if not ensure_python_libs():
            print("依赖安装失败")
            return
        print("依赖就绪")

        print("检查 ViGEmBus...")
        gamepad_available = ensure_vigem()

        # 动态端口
        http_port = find_available_port(8765)
        ws_port = find_available_port(http_port + 1)
        print(f"HTTP端口: {http_port}  WebSocket端口: {ws_port}")
        allow_firewall_ports([http_port, ws_port])

        current_ip = get_best_ip()
        print(f"局域网IP: {current_ip}")

        # 导入主库
        import keyboard, vgamepad, websockets, qrcode
        from vgamepad import VX360Gamepad

        # 输入模拟代码
        PUL = ctypes.POINTER(ctypes.c_ulong)
        class KeyBdInput(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", PUL)]
        class Input_I(ctypes.Union):
            _fields_ = [("ki", KeyBdInput)]
        class Input(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]
        SendInput = ctypes.windll.user32.SendInput

        def press_key(sc):
            extra = ctypes.c_ulong(0)
            ii = Input_I()
            ii.ki = KeyBdInput(0, sc, 0x0008, 0, ctypes.pointer(extra))
            x = Input(1, ii)
            SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

        def release_key(sc):
            extra = ctypes.c_ulong(0)
            ii = Input_I()
            ii.ki = KeyBdInput(0, sc, 0x0008 | 0x0002, 0, ctypes.pointer(extra))
            x = Input(1, ii)
            SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

        def get_scan_code(k):
            try:
                return keyboard.key_to_scan_codes(k)[0]
            except Exception as e:
                logging.warning(f"按键转换失败: {k}, {e}")
                return 0

        GP_BUTTONS = {
            'A': 0x1000, 'B': 0x2000, 'X': 0x4000, 'Y': 0x8000,
            'RB': 0x0200, 'LB': 0x0100, 'RT': 0x0400, 'LT': 0x0800,
            'START': 0x0010, 'SELECT': 0x0020,
            'LS': 0x0040, 'RS': 0x0080,
            'LUP': 0x0001, 'LDOWN': 0x0002, 'LLEFT': 0x0004, 'LRIGHT': 0x0008,
            'RUP': 0x0001, 'RDOWN': 0x0002, 'RLEFT': 0x0004, 'RRIGHT': 0x0008
        }
        gamepad = None

        def init_gamepad():
            global gamepad
            if not gamepad_available:
                return False
            try:
                gamepad = VX360Gamepad()
                gamepad.update()
                return True
            except Exception as e:
                logging.error(f"手柄初始化失败: {e}")
                return False

        def press_gamepad(b):
            if not gamepad: return
            try:
                v = GP_BUTTONS[b]
                gamepad.press_button(button=v)
                if b == 'LT': gamepad.left_trigger_float(1.0)
                elif b == 'RT': gamepad.right_trigger_float(1.0)
                gamepad.update()
            except Exception as e:
                logging.error(f"手柄按下失败: {e}")

        def release_gamepad(b):
            if not gamepad: return
            try:
                v = GP_BUTTONS[b]
                gamepad.release_button(button=v)
                if b == 'LT': gamepad.left_trigger_float(0.0)
                elif b == 'RT': gamepad.right_trigger_float(0.0)
                gamepad.update()
            except Exception as e:
                logging.error(f"手柄释放失败: {e}")

        def joystick_float(lx, ly, rx, ry):
            if not gamepad: return
            try:
                gamepad.left_joystick_float(lx, ly)
                gamepad.right_joystick_float(rx, ry)
                gamepad.update()
            except Exception as e:
                logging.error(f"摇杆更新失败: {e}")

        ws_ready = False

        async def handle_message(websocket, message):
            try:
                data = json.loads(message)
                action = data.get('action')
                if action == 'key_press':
                    sc = get_scan_code(data['key'])
                    if sc: press_key(sc)
                elif action == 'key_release':
                    sc = get_scan_code(data['key'])
                    if sc: release_key(sc)
                elif action == 'gp_press':
                    press_gamepad(data['btn'])
                elif action == 'gp_release':
                    release_gamepad(data['btn'])
                elif action == 'joystick':
                    left = data.get('left', [0, 0])
                    right = data.get('right', [0, 0])
                    joystick_float(left[0], left[1], right[0], right[1])
                logging.info(f"执行: {data}")
            except Exception as e:
                logging.error(f"指令异常: {e}")

        async def ws_handler(websocket, *args):
            # 注意: websockets>=13 的新 asyncio API 只给 handler 传 1 个参数 (websocket);
            # 旧版会多传一个 path。用 *args 兼容两代, 否则新版会 TypeError → 握手失败 → 手机"连接失败"。
            logging.info(f"WebSocket 连接: {websocket.remote_address}")
            try:
                async for message in websocket:
                    await handle_message(websocket, message)
            except websockets.ConnectionClosed:
                logging.info("WebSocket 连接关闭")

        # 完整手机端网页（动态端口）
        CONTROLLER_HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>FKB 控制器</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ background:#111; font-family:Arial; overflow:hidden; touch-action: manipulation; }}
        #canvas {{ display:block; position:absolute; top:0; left:0; }}
        #toolbar {{ position:fixed; bottom:0; left:0; right:0; height:44px; background:#222; display:flex; z-index:10; }}
        .tbtn {{ flex:1; color:#ccc; display:flex; align-items:center; justify-content:center; font-size:15px; border-right:1px solid #444; }}
        .tbtn:last-child {{ border-right:none; }}
        .tbtn:active {{ background:#444; }}
        #status {{ position:fixed; top:0; left:0; right:0; height:24px; background:#000; color:#0f0; font-size:12px; display:flex; align-items:center; justify-content:center; z-index:9; }}
        #overlay {{ position:fixed; top:24px; left:0; right:0; bottom:44px; background:rgba(0,0,0,0.85); display:none; z-index:20; overflow-y:auto; padding:15px; color:white; }}
        .overlay-content {{ max-width:400px; margin:0 auto; }}
        .label {{ font-size:14px; margin:10px 0 4px; }}
        input, select {{ width:100%; padding:8px; background:#333; color:white; border:1px solid #555; border-radius:4px; }}
        button {{ width:100%; padding:10px; margin:8px 0; background:#0a8; color:white; border:none; border-radius:4px; font-size:16px; }}
        button.danger {{ background:#c33; }}
        .flex-row {{ display:flex; gap:10px; }}
        .flex-row button {{ flex:1; }}
    </style>
</head>
<body>
    <div id="status">⏳ 检测连接...</div>
    <canvas id="canvas"></canvas>
    <div id="toolbar">
        <div class="tbtn" id="modeBtn">编辑</div>
        <div class="tbtn" id="addBtn">+ 按钮</div>
        <div class="tbtn" id="saveBtn">保存</div>
        <div class="tbtn" id="loadBtn">加载</div>
        <div class="tbtn" id="connectBtn">🔌 连接</div>
    </div>
    <div id="overlay"></div>

    <script>
        const DB_NAME = 'FKB_Configs';
        const STORE_NAME = 'configs';
        let db;
        function openDB() {{
            return new Promise((resolve, reject) => {{
                const req = indexedDB.open(DB_NAME, 1);
                req.onupgradeneeded = e => {{
                    const db = e.target.result;
                    if (!db.objectStoreNames.contains(STORE_NAME)) {{
                        db.createObjectStore(STORE_NAME, {{ keyPath: 'name' }});
                    }}
                }};
                req.onsuccess = e => {{ db = e.target.result; resolve(); }};
                req.onerror = reject;
            }});
        }}
        async function saveConfig(name, data) {{
            await openDB();
            const tx = db.transaction(STORE_NAME, 'readwrite');
            tx.objectStore(STORE_NAME).put({{ name, data }});
        }}
        async function loadConfig(name) {{
            await openDB();
            const tx = db.transaction(STORE_NAME, 'readonly');
            const store = tx.objectStore(STORE_NAME);
            return new Promise((resolve, reject) => {{
                const req = store.get(name);
                req.onsuccess = e => resolve(e.target.result);
                req.onerror = reject;
            }});
        }}
        async function listConfigs() {{
            await openDB();
            const tx = db.transaction(STORE_NAME, 'readonly');
            const store = tx.objectStore(STORE_NAME);
            return new Promise((resolve, reject) => {{
                const req = store.getAllKeys();
                req.onsuccess = e => resolve(e.target.result);
                req.onerror = reject;
            }});
        }}

        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        let mode = 'edit';
        let buttons = [];
        let ws = null;
        let selectedBtnId = null;
        let dragging = false, dragStart = {{x:0,y:0}}, btnStart = {{}};
        let resizeMode = false;
        let activeTouches = {{}};
        const statusDiv = document.getElementById('status');

        function setStatus(text, color) {{
            statusDiv.textContent = text;
            statusDiv.style.color = color;
        }}

        function resize() {{
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight - 44 - 24;
        }}
        window.addEventListener('resize', resize);
        resize();

        function drawButtons() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            buttons.forEach(btn => {{
                const {{ x, y, w, h, name, shape }} = btn;
                ctx.save();
                if (shape === 'circle') {{
                    const r = w/2;
                    ctx.beginPath();
                    ctx.arc(x, y, r, 0, 2*Math.PI);
                    ctx.fillStyle = '#333';
                    ctx.fill();
                    ctx.strokeStyle = selectedBtnId === btn.id ? '#0f0' : '#0ff';
                    ctx.lineWidth = 3;
                    ctx.stroke();
                }} else if (shape === 'glory') {{
                    ctx.fillStyle = '#1A1A2E';
                    ctx.fillRect(x, y, w, h);
                    ctx.strokeStyle = selectedBtnId === btn.id ? '#0f0' : '#E94560';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(x, y, w, h);
                }} else {{
                    ctx.fillStyle = '#2A2A2A';
                    ctx.fillRect(x, y, w, h);
                    ctx.strokeStyle = selectedBtnId === btn.id ? '#0f0' : '#0ff';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(x, y, w, h);
                }}
                ctx.fillStyle = '#fff';
                ctx.font = '14px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(name, x + w/2, y + h/2);
                ctx.fillStyle = selectedBtnId === btn.id ? '#0f0' : '#888';
                ctx.fillRect(x+w-12, y+h-12, 12, 12);
                ctx.restore();
            }});
        }}

        function hitTest(x, y) {{
            for (let i = buttons.length-1; i >= 0; i--) {{
                const b = buttons[i];
                if (b.shape === 'circle') {{
                    const dx = x - b.x, dy = y - b.y;
                    if (dx*dx + dy*dy <= (b.w/2)*(b.w/2)) return i;
                }} else {{
                    if (x >= b.x && x <= b.x+b.w && y >= b.y && y <= b.y+b.h) return i;
                }}
            }}
            return -1;
        }}

        canvas.addEventListener('pointerdown', e => {{
            if (mode !== 'edit') return;
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left, y = e.clientY - rect.top;
            const idx = hitTest(x, y);
            if (idx >= 0) {{
                const btn = buttons[idx];
                selectedBtnId = btn.id;
                if (x > btn.x + btn.w - 15 && y > btn.y + btn.h - 15) resizeMode = true;
                else resizeMode = false;
                dragging = true;
                dragStart = {{x, y}};
                btnStart = {{x: btn.x, y: btn.y, w: btn.w, h: btn.h}};
            }} else selectedBtnId = null;
            drawButtons();
        }});

        canvas.addEventListener('pointermove', e => {{
            if (mode !== 'edit' || !dragging) return;
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left, y = e.clientY - rect.top;
            const btn = buttons.find(b => b.id === selectedBtnId);
            if (!btn) return;
            const dx = x - dragStart.x, dy = y - dragStart.y;
            if (resizeMode) {{
                btn.w = Math.max(40, btnStart.w + dx);
                if (btn.shape === 'circle') btn.h = btn.w;
                else btn.h = Math.max(40, btnStart.h + dy);
            }} else {{
                btn.x = btnStart.x + dx;
                btn.y = btnStart.y + dy;
            }}
            drawButtons();
        }});

        canvas.addEventListener('pointerup', () => {{
            if (dragging) {{ dragging = false; saveConfig('__auto__', buttons); }}
        }});

        function handleTouchStart(e) {{
            if (mode !== 'run') return;
            e.preventDefault();
            for (const touch of e.changedTouches) {{
                const rect = canvas.getBoundingClientRect();
                const x = touch.clientX - rect.left, y = touch.clientY - rect.top;
                const idx = hitTest(x, y);
                if (idx >= 0) {{
                    activeTouches[touch.identifier] = buttons[idx].id;
                    executeButton('press', buttons[idx]);
                }}
            }}
        }}
        function handleTouchEnd(e) {{
            if (mode !== 'run') return;
            e.preventDefault();
            for (const touch of e.changedTouches) {{
                const btnId = activeTouches[touch.identifier];
                if (btnId) {{
                    const btn = buttons.find(b => b.id === btnId);
                    if (btn) executeButton('release', btn);
                    delete activeTouches[touch.identifier];
                }}
            }}
        }}
        canvas.addEventListener('touchstart', handleTouchStart, {{passive: false}});
        canvas.addEventListener('touchend', handleTouchEnd, {{passive: false}});
        canvas.addEventListener('touchcancel', handleTouchEnd, {{passive: false}});

        function executeButton(type, btn) {{
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            if (btn.actions) {{
                const parts = btn.actions.split('+');
                for (const part of parts) {{
                    const trimmed = part.trim();
                    if (trimmed.startsWith('gp:')) {{
                        ws.send(JSON.stringify({{ action: type === 'press' ? 'gp_press' : 'gp_release', btn: trimmed.substring(3) }}));
                    }} else if (!trimmed.startsWith('delay:')) {{
                        ws.send(JSON.stringify({{ action: type === 'press' ? 'key_press' : 'key_release', key: trimmed }}));
                    }}
                }}
            }}
        }}

        const overlay = document.getElementById('overlay');
        function showOverlay(html) {{
            overlay.innerHTML = `<div class="overlay-content">${{html}}</div>`;
            overlay.style.display = 'block';
        }}
        function hideOverlay() {{ overlay.style.display = 'none'; }}

        canvas.addEventListener('dblclick', e => {{
            if (mode !== 'edit') return;
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left, y = e.clientY - rect.top;
            const idx = hitTest(x, y);
            if (idx >= 0) editButton(idx);
        }});

        function editButton(idx) {{
            const btn = buttons[idx];
            const html = `
                <h3>编辑按钮</h3>
                <div class="label">名称</div>
                <input id="editName" value="${{btn.name}}">
                <div class="label">形状</div>
                <select id="editShape">
                    <option value="rect" ${{btn.shape==='rect'?'selected':''}}>矩形</option>
                    <option value="circle" ${{btn.shape==='circle'?'selected':''}}>圆形(摇杆)</option>
                    <option value="glory" ${{btn.shape==='glory'?'selected':''}}>荣耀摇杆</option>
                </select>
                <div class="label">按键序列 (例: a+b+gp:A+delay:100)</div>
                <input id="editActions" value="${{btn.actions || ''}}">
                <div class="flex-row">
                    <button onclick="saveEdit(${{idx}})">保存</button>
                    <button class="danger" onclick="deleteBtn(${{idx}})">删除</button>
                </div>
                <button onclick="hideOverlay()">取消</button>
            `;
            showOverlay(html);
        }}
        window.saveEdit = function(idx) {{
            const btn = buttons[idx];
            btn.name = document.getElementById('editName').value;
            btn.shape = document.getElementById('editShape').value;
            btn.actions = document.getElementById('editActions').value;
            hideOverlay();
            drawButtons();
            saveConfig('__auto__', buttons);
        }};
        window.deleteBtn = function(idx) {{
            buttons.splice(idx, 1);
            selectedBtnId = null;
            hideOverlay();
            drawButtons();
            saveConfig('__auto__', buttons);
        }};

        const WS_PORT = {ws_port};
        let reconnectTimer = null;
        let wsConnectionTimeout = null;

        function connectWebSocket() {{
            const ip = window.location.hostname;
            const wsUrl = `ws://${{ip}}:${{WS_PORT}}`;
            setStatus('正在连接...', 'yellow');
            doConnect(wsUrl);
        }}

        function doConnect(wsUrl) {{
            if (ws) {{ ws.close(); ws = null; }}
            if (wsConnectionTimeout) {{ clearTimeout(wsConnectionTimeout); wsConnectionTimeout = null; }}
            try {{
                ws = new WebSocket(wsUrl);
            }} catch(e) {{
                setStatus('浏览器不支持 WebSocket', 'red');
                return;
            }}

            wsConnectionTimeout = setTimeout(() => {{
                if (ws.readyState !== WebSocket.OPEN) {{
                    setStatus('连接超时', 'red');
                    ws.close();
                }}
            }}, 5000);

            ws.onopen = () => {{
                clearTimeout(wsConnectionTimeout);
                setStatus('已连接', '#0f0');
                if (reconnectTimer) {{ clearInterval(reconnectTimer); reconnectTimer = null; }}
            }};
            ws.onerror = () => {{
                clearTimeout(wsConnectionTimeout);
                setStatus('连接失败', 'red');
            }};
            ws.onclose = () => {{
                clearTimeout(wsConnectionTimeout);
                setStatus('连接断开', 'red');
                if (!reconnectTimer) {{
                    reconnectTimer = setInterval(() => doConnect(wsUrl), 3000);
                }}
            }};
        }}

        document.getElementById('connectBtn').addEventListener('click', () => {{
            const ip = prompt('输入电脑IP:', window.location.hostname);
            if (ip) doConnect(`ws://${{ip}}:${{WS_PORT}}`);
        }});

        setTimeout(connectWebSocket, 600);

        document.getElementById('modeBtn').addEventListener('click', () => {{
            mode = mode === 'edit' ? 'run' : 'edit';
            document.getElementById('modeBtn').textContent = mode === 'edit' ? '遥控' : '编辑';
            drawButtons();
        }});
        document.getElementById('addBtn').addEventListener('click', () => {{
            if (mode !== 'edit') return;
            buttons.push({{
                id: Date.now(),
                x: Math.random() * (canvas.width-100) + 50,
                y: Math.random() * (canvas.height-100) + 50,
                w: 80, h: 80, shape: 'rect', name: '按钮', actions: ''
            }});
            drawButtons();
            saveConfig('__auto__', buttons);
        }});
        document.getElementById('saveBtn').addEventListener('click', async () => {{
            const name = prompt('输入配置名称:');
            if (name) {{ await saveConfig(name, buttons); alert('已保存'); }}
        }});
        document.getElementById('loadBtn').addEventListener('click', async () => {{
            const names = await listConfigs();
            if (names.length === 0) {{ alert('暂无保存的配置'); return; }}
            const name = prompt('输入配置名称:\\n已有: ' + names.join(', '));
            if (name) {{
                const config = await loadConfig(name);
                if (config) {{ buttons = config.data; drawButtons(); }}
                else alert('未找到');
            }}
        }});

        openDB().then(async () => {{
            const auto = await loadConfig('__auto__');
            if (auto) buttons = auto.data;
            drawButtons();
        }});
    </script>
</body>
</html>"""

        import http.server, socketserver
        class MyHTTPHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path in ('/', '/index.html'):
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(CONTROLLER_HTML.encode('utf-8'))
                elif self.path == '/status':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    status = {'ws_port': ws_port, 'ws_ready': ws_ready, 'gamepad_available': gamepad_available}
                    self.wfile.write(json.dumps(status).encode())
                else:
                    super().do_GET()

        def start_http_server(port):
            server = socketserver.TCPServer(("0.0.0.0", port), MyHTTPHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            return server

        def show_qr_code(url):
            try:
                qrcode.make(url).show()
            except Exception as e:
                print(f"二维码显示失败，请手动访问: {url}")
                logging.warning(f"二维码显示失败: {e}")

        # 启动 HTTP 服务
        url = f"http://{current_ip}:{http_port}"
        print(f"📱 手机浏览器访问: {url}")
        start_http_server(http_port)
        if gamepad_available:
            init_gamepad()
        show_qr_code(url)

        stop_event = threading.Event()
        def get_qr(show=False):
            new_ip = get_best_ip()
            print(f"当前IP: {new_ip}")
            if show:
                show_qr_code(f"http://{new_ip}:{http_port}")
        tray_icon = create_tray_icon(stop_event, get_qr)

        # 启动 WebSocket 异步线程
        def run_ws():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            async def serve():
                global ws_ready
                async with websockets.serve(ws_handler, "0.0.0.0", ws_port):
                    ws_ready = True
                    print(f"WebSocket 服务已启动 (端口 {ws_port})")
                    await stop_event.wait()
                    ws_ready = False
            try:
                loop.run_until_complete(serve())
            except Exception as e:
                logging.error(f"WebSocket 线程异常: {e}")
            finally:
                loop.close()

        ws_thread = threading.Thread(target=run_ws, daemon=True)
        ws_thread.start()

        print("服务运行中，右键托盘图标退出，或关闭此窗口。")
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            print("正在退出...")
            if tray_icon:
                try:
                    tray_icon.stop()
                except:
                    pass
            os._exit(0)

    except Exception as e:
        logging.critical(f"主程序异常: {e}", exc_info=True)
        print(f"程序发生严重错误: {e}\n详情见 fkb_server.log")
        import tkinter.messagebox as msg
        msg.showerror("FKB 错误", f"程序异常退出:\n{e}\n请查看日志 fkb_server.log")

if __name__ == "__main__":
    main()