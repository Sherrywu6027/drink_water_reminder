import tkinter as tk
from tkinter import messagebox, colorchooser, simpledialog
import json
import os
import shutil
from datetime import datetime, date, timedelta
import traceback  # 用于打印详细异常
import winreg  # 用于注册表操作
import sys
import logging
import socket  # 用于网络通信
import threading  # 用于多线程
import time  # 用于时间处理
import uuid  # 用于生成唯一ID
import random  # 用于健康知识随机推送
import webbrowser  # 用于打开本地HTML文件
import http.server
import urllib.parse

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

from app_storage import (
    APP_DIR,
    APP_NAME,
    DATA_FILE,
    FRIENDS_FILE,
    FRIEND_REMINDERS_FILE,
    LOG_FILE,
    RESOURCE_DIR,
    SETTINGS_FILE,
    USER_CONFIG_FILE,
    USER_PERMISSIONS_FILE,
    backup_file as storage_backup_file,
    can_send_reminder as storage_can_send_reminder,
    load_friends as storage_load_friends,
    load_json_file as storage_load_json_file,
    load_json_from_resource as storage_load_json_from_resource,
    load_shareable_data as storage_load_shareable_data,
)
from app_storage import (
    load_user_id as storage_load_user_id,
    load_user_permissions as storage_load_user_permissions,
    log as storage_log,
    log_exception as storage_log_exception,
    migrate_drink_data as storage_migrate_drink_data,
    record_reminder_sent as storage_record_reminder_sent,
    save_friends as storage_save_friends,
    save_user_config_fields as storage_save_user_config_fields,
    save_user_permissions as storage_save_user_permissions,
)
from friend_network import FriendNetworkManager as ImportedFriendNetworkManager
from protocol_helpers import (
    recv_json_message as protocol_recv_json_message,
    send_json_message as protocol_send_json_message,
)
from reminder_challenge import (
    generate_math_challenge,
    is_correct_answer,
    normalize_challenge_config,
)
from dashboard_ui import (
    calculate_window_geometry,
    count_completed_items,
    get_dashboard_colors,
    get_day_greeting,
)


APP_VERSION = "v0.5.0"
POMODORO_FOCUS_SECONDS = 25 * 60


def resource_path(relative_path):
    """Return a resource path that works both in source and PyInstaller one-file mode."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def open_path_with_default_app(path):
    try:
        if not path:
            return False
        resolved_path = os.path.abspath(path)
        if sys.platform == "win32":
            os.startfile(resolved_path)
        else:
            webbrowser.open(resolved_path)
        return True
    except Exception as e:
        log("打开路径失败：{}，{}".format(path, e))
        return False


def enable_windows_dpi_awareness():
    """Enable system DPI awareness before Tk starts, with safe fallbacks."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        try:
            # PROCESS_SYSTEM_DPI_AWARE keeps Tk logical geometry aligned with
            # the physical work area on supported versions of Windows.
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            return True
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
            return True
    except Exception:
        return False


def bounded_window_geometry(window, preferred_width, preferred_height, min_width, min_height, width_ratio=0.9, height_ratio=0.85):
    screen_width = max(1, window.winfo_screenwidth())
    screen_height = max(1, window.winfo_screenheight())
    max_width = max(min_width, int(screen_width * width_ratio))
    max_height = max(min_height, int(screen_height * height_ratio))
    width = min(max(preferred_width, min_width), max_width)
    height = min(max(preferred_height, min_height), max_height)
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    return width, height, x, y


def apply_safe_window_geometry(window, preferred_width, preferred_height, min_width, min_height, width_ratio=0.9, height_ratio=0.85):
    width, height, x, y = bounded_window_geometry(
        window, preferred_width, preferred_height, min_width, min_height,
        width_ratio=width_ratio, height_ratio=height_ratio,
    )
    window.minsize(min(min_width, width), min(min_height, height))
    window.geometry("{}x{}+{}+{}".format(width, height, x, y))
    return width, height


def create_scrollable_body(parent, bg, padx=0, pady=0):
    outer = tk.Frame(parent, bg=bg, padx=padx, pady=pady)
    canvas = tk.Canvas(outer, bg=bg, bd=0, highlightthickness=0)
    scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    body = tk.Frame(canvas, bg=bg)
    window_id = canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_scrollregion(event=None):
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
        except tk.TclError:
            pass

    def resize_body(event):
        try:
            canvas.itemconfigure(window_id, width=event.width)
        except tk.TclError:
            pass

    def on_mousewheel(event):
        try:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass

    body.bind("<Configure>", refresh_scrollregion)
    canvas.bind("<Configure>", resize_body)
    outer.bind("<MouseWheel>", on_mousewheel)
    body.bind("<MouseWheel>", on_mousewheel)
    canvas.bind("<MouseWheel>", on_mousewheel)
    outer.scroll_canvas = canvas
    outer.scroll_body = body
    outer.scrollbar = scrollbar
    return outer, body


def create_dialog_header(parent, title, subtitle, colors):
    header = tk.Frame(parent, bg=colors["surface"], padx=18, pady=14,
                      highlightbackground=colors["border"], highlightthickness=1)
    header.pack(fill=tk.X)
    tk.Label(
        header, text=title, font=("微软雅黑", 18, "bold"),
        bg=colors["surface"], fg=colors["text_primary"],
    ).pack(anchor="w")
    if subtitle:
        tk.Label(
            header, text=subtitle, font=("微软雅黑", 10),
            bg=colors["surface"], fg=colors["text_secondary"],
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 0))
    return header


def create_dialog_card(parent, colors, padx=16, pady=14, fill=tk.X, expand=False):
    card = tk.Frame(parent, bg=colors["surface"], padx=padx, pady=pady,
                    highlightbackground=colors["border"], highlightthickness=1)
    card.pack(fill=fill, expand=expand, pady=(12, 0))
    return card


def dialog_button_options(colors, primary=False, danger=False):
    if danger:
        return dict(
            font=("微软雅黑", 10, "bold"), bg=colors["danger_muted"],
            fg=colors["danger_text"], activebackground=colors["danger_muted"],
            relief=tk.FLAT, bd=0, padx=14, pady=9,
        )
    if primary:
        return dict(
            font=("微软雅黑", 10, "bold"), bg=colors["primary"],
            fg=colors["on_primary"], activebackground=colors["primary_active"],
            relief=tk.FLAT, bd=0, padx=14, pady=9,
        )
    return dict(
        font=("微软雅黑", 10), bg=colors["surface_alt"],
        fg=colors["text_primary"], activebackground=colors["surface_alt"],
        relief=tk.FLAT, bd=0, padx=14, pady=9,
    )


class EyeTrainingApi:
    def record_eye(self, duration):
        eye_file = os.path.join(APP_DIR, "eye_autorecord.txt")
        with open(eye_file, "a", encoding="utf-8") as f:
            f.write(f"{int(time.time())},{duration}\n")
        return "ok"


def append_eye_autorecord(duration):
    try:
        duration = int(float(duration))
    except (TypeError, ValueError):
        return False
    if duration < 60:
        return False
    eye_file = os.path.join(APP_DIR, "eye_autorecord.txt")
    with open(eye_file, "a", encoding="utf-8") as f:
        f.write(f"{int(time.time())},{duration}\n")
    return True


class EyeRecordHttpServer:
    def __init__(self):
        self.server = None
        self.thread = None
        self.url = None

    def start(self):
        if self.server is not None:
            return self.url

        class Handler(http.server.BaseHTTPRequestHandler):
            def _send_plain(self, status, body):
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def do_OPTIONS(self):
                self._send_plain(204, "")

            def do_POST(self):
                if self.path.split("?", 1)[0] != "/eye-record":
                    self._send_plain(404, "not found")
                    return
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode("utf-8", errors="ignore")
                ok = append_eye_autorecord(raw.strip())
                self._send_plain(200 if ok else 204, "ok" if ok else "ignored")

            def log_message(self, format, *args):
                return

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{port}/eye-record"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.url

    def stop(self):
        if self.server is None:
            return
        try:
            self.server.shutdown()
            self.server.server_close()
        finally:
            self.server = None
            self.thread = None
            self.url = None


def build_eye_training_url(record_url=None):
    html_path = os.path.join(RESOURCE_DIR, "护眼", "index.html")
    if not os.path.exists(html_path):
        raise FileNotFoundError(html_path)
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    if record_url:
        url += "?autorecord=" + urllib.parse.quote(record_url, safe="")
    return url


def launch_eye_training_window(autostart=False):
    return open_eye_training_in_browser(autostart=autostart)


def open_eye_training_in_browser(record_url=None, autostart=False):
    url = build_eye_training_url(record_url)
    if autostart:
        separator = "&" if "?" in url else "?"
        url += separator + "autostart=1"
    webbrowser.open(url)
    return True

# 兼容旧代码中的全局名称，实际路径由 app_storage 提供。

def log(msg):
    print(f"[LOG] {msg}")

def log_exception(e):
    logging.error("Exception occurred", exc_info=e)

def load_json_file(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log(f"加载JSON文件异常 {path}: {e}")
    return default

def save_user_config_fields(**updates):
    """合并保存用户配置，避免覆盖已有 user_id 等字段。"""
    config = load_json_file(USER_CONFIG_FILE, {})
    if not isinstance(config, dict):
        config = {}
    config.update(updates)
    with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return config

def send_json_message(sock, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sock.sendall(len(data).to_bytes(4, byteorder="big") + data)

def recv_exactly(sock, size):
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("连接在消息接收完成前已关闭")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)

def recv_json_message(sock):
    header = recv_exactly(sock, 4)
    total_size = int.from_bytes(header, byteorder="big")
    payload = recv_exactly(sock, total_size)
    return json.loads(payload.decode("utf-8"))

def backup_file(path, suffix):
    if not os.path.exists(path):
        return None
    backup_path = f"{path}.{suffix}"
    shutil.copy2(path, backup_path)
    return backup_path

def normalize_day_data(day_value):
    """将历史数据标准化为 {reminder_key: [time, ...]}。"""
    if isinstance(day_value, dict):
        normalized = {}
        for key, value in day_value.items():
            if isinstance(value, list):
                normalized[key] = [item for item in value if isinstance(item, str)]
        return normalized
    if isinstance(day_value, list):
        legacy_times = [item for item in day_value if isinstance(item, str)]
        if legacy_times:
            return {"drink": legacy_times}
    return {}

def migrate_drink_data(data):
    if not isinstance(data, dict):
        return {}, True

    migrated = {}
    changed = False
    for day, day_value in data.items():
        normalized = normalize_day_data(day_value)
        if normalized != day_value:
            changed = True
        migrated[day] = normalized
    return migrated, changed

# ========== 好友功能相关工具函数 ==========
def generate_user_id():
    """生成用户唯一ID"""
    return str(uuid.uuid4())[:8]

def load_user_id():
    """加载或生成用户ID"""
    try:
        if os.path.exists(USER_CONFIG_FILE):
            with open(USER_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                if "user_id" in config:
                    return config["user_id"]
    except Exception as e:
        log(f"加载用户ID异常：{e}")
    
    # 生成新的用户ID
    user_id = generate_user_id()
    try:
        config = load_user_config()
        config["user_id"] = user_id
        with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"保存用户ID异常：{e}")
    
    return user_id

def load_friends():
    """加载好友列表"""
    try:
        if os.path.exists(FRIENDS_FILE):
            with open(FRIENDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        log(f"加载好友列表异常：{e}")
        return []

def save_friends(friends):
    """保存好友列表"""
    try:
        with open(FRIENDS_FILE, "w", encoding="utf-8") as f:
            json.dump(friends, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"保存好友列表异常：{e}")

def load_friend_reminders():
    """加载好友提醒记录"""
    try:
        if os.path.exists(FRIEND_REMINDERS_FILE):
            with open(FRIEND_REMINDERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        log(f"加载好友提醒记录异常：{e}")
        return {}

def save_friend_reminders(reminders):
    """保存好友提醒记录"""
    try:
        with open(FRIEND_REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(reminders, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"保存好友提醒记录异常：{e}")

def load_user_permissions():
    """加载用户权限设置"""
    try:
        if os.path.exists(USER_PERMISSIONS_FILE):
            with open(USER_PERMISSIONS_FILE, "r", encoding="utf-8") as f:
                permissions = json.load(f)
                if isinstance(permissions, dict):
                    return {"allow_data_view": permissions.get("allow_data_view", True)}
        return {"allow_data_view": True}
    except Exception as e:
        log(f"加载用户权限异常：{e}")
        return {"allow_data_view": True}

def save_user_permissions(permissions):
    """保存用户权限设置"""
    try:
        with open(USER_PERMISSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"allow_data_view": permissions.get("allow_data_view", True)},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        log(f"保存用户权限异常：{e}")

def can_send_reminder(friend_id):
    """检查是否可以发送提醒（10分钟限制）"""
    reminders = load_friend_reminders()
    user_id = load_user_id()
    key = f"{user_id}_{friend_id}"
    
    if key in reminders:
        last_time = datetime.fromisoformat(reminders[key])
        if datetime.now() - last_time < timedelta(minutes=10):
            return False
    
    return True

def record_reminder_sent(friend_id):
    """记录提醒发送时间"""
    reminders = load_friend_reminders()
    user_id = load_user_id()
    key = f"{user_id}_{friend_id}"
    reminders[key] = datetime.now().isoformat()
    save_friend_reminders(reminders)


# 切到拆分后的存储/协议实现，保留主文件 UI 逻辑不变。
log = storage_log
log_exception = storage_log_exception
load_json_file = storage_load_json_file
load_json_from_resource = storage_load_json_from_resource
save_user_config_fields = storage_save_user_config_fields
send_json_message = protocol_send_json_message
recv_json_message = protocol_recv_json_message
backup_file = storage_backup_file
migrate_drink_data = storage_migrate_drink_data
load_user_id = storage_load_user_id
load_friends = storage_load_friends
save_friends = storage_save_friends
load_user_permissions = storage_load_user_permissions
save_user_permissions = storage_save_user_permissions
can_send_reminder = storage_can_send_reminder
record_reminder_sent = storage_record_reminder_sent

# 默认提醒类型及配置
DEFAULT_REMINDERS = [
    {"key": "drink", "name": "喝水", "interval": 30, "enabled": True, "msg": "{nickname}，该喝水啦！"},
    {"key": "stand", "name": "站立", "interval": 60, "enabled": True, "msg": "{nickname}，起来站一会儿，活动下身体！"},
    {"key": "eye", "name": "护眼", "interval": 45, "enabled": True, "msg": "{nickname}，该做护眼操或远眺啦！"},
    {"key": "sport", "name": "运动", "interval": 120, "enabled": True, "msg": "{nickname}，起来运动一下，保持健康！"},
]
REMINDER_MIN = 5  # 最小间隔分钟
REMINDER_MAX = 480  # 最大间隔分钟

# 主题配置
THEMES = {
    "健康绿": {
        "name": "健康绿",
        "bg": "#e8f5e8",
        "button_bg": "#4caf50",
        "button_fg": "white",
        "button_active": "#66bb6a"
    },
    "天空蓝": {
        "name": "天空蓝", 
        "bg": "#e3f2fd",
        "button_bg": "#2196f3",
        "button_fg": "white",
        "button_active": "#42a5f5"
    },
    "暖橙色": {
        "name": "暖橙色",
        "bg": "#fff3e0",
        "button_bg": "#ff9800",
        "button_fg": "white",
        "button_active": "#ffb74d"
    },
    "淡紫色": {
        "name": "淡紫色",
        "bg": "#f3e5f5",
        "button_bg": "#9c27b0",
        "button_fg": "white",
        "button_active": "#ba68c8"
    },
    "深蓝色": {
        "name": "深蓝色",
        "bg": "#e8eaf6",
        "button_bg": "#3f51b5",
        "button_fg": "white",
        "button_active": "#5c6bc0"
    }
}

DEFAULT_THEME = "健康绿"


def restore_custom_theme(config):
    """Register a persisted custom theme when its complete palette is valid."""
    if not isinstance(config, dict):
        return False
    custom_theme = config.get("custom_theme")
    required = ("name", "bg", "button_bg", "button_fg", "button_active")
    if not isinstance(custom_theme, dict) or not all(
            isinstance(custom_theme.get(key), str) and custom_theme.get(key)
            for key in required):
        return False
    THEMES["自定义"] = dict(custom_theme)
    return True

class WelcomePage:
    def __init__(self, root, on_complete):
        self.root = root
        self.on_complete = on_complete
        
        # 获取主题颜色
        self.theme_colors = get_theme_colors()
        
        # 清空主窗口
        for widget in root.winfo_children():
            widget.destroy()
        
        # 设置欢迎页面样式
        self.root.title("欢迎使用健康助手")
        self.root.geometry("400x300")
        self.root.configure(bg=self.theme_colors["bg"])
        self.root.resizable(False, False)
        
        # 欢迎标题
        self.welcome_label = tk.Label(
            root, text="欢迎使用健康助手", 
            font=("微软雅黑", 20, "bold"),
            bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"]
        )
        self.welcome_label.pack(pady=(40, 20))
        
        # 说明文字
        self.desc_label = tk.Label(
            root, text="为了给您更好的体验，请告诉我您的昵称", 
            font=("微软雅黑", 12),
            bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"]
        )
        self.desc_label.pack(pady=(0, 30))
        
        # 昵称输入框
        self.nickname_frame = tk.Frame(root, bg=self.theme_colors["bg"])
        self.nickname_frame.pack(pady=10)
        
        self.nickname_label = tk.Label(
            self.nickname_frame, text="昵称：", 
            font=("微软雅黑", 12),
            bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"]
        )
        self.nickname_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.nickname_entry = tk.Entry(
            self.nickname_frame, 
            font=("微软雅黑", 12),
            width=15,
            relief=tk.SOLID,
            bd=1
        )
        self.nickname_entry.pack(side=tk.LEFT)
        self.nickname_entry.focus()
        
        # 绑定回车键
        self.nickname_entry.bind('<Return>', self.on_enter_pressed)
        
        # 开始使用按钮
        self.start_button = tk.Button(
            root, text="开始使用", 
            font=("微软雅黑", 14, "bold"),
            bg=self.theme_colors["button_bg"], fg=self.theme_colors["button_fg"], 
            activebackground=self.theme_colors["button_active"],
            width=12, height=2,
            bd=0, command=self.start_app
        )
        self.start_button.pack(pady=30)
        
        log("欢迎页面初始化完成")
    
    def on_enter_pressed(self, event):
        self.start_app()
    
    def start_app(self):
        nickname = self.nickname_entry.get().strip()
        if not nickname:
            messagebox.showwarning("提示", "请输入您的昵称")
            return
        
        # 保存用户配置
        self.save_user_config(nickname)
        
        # 调用完成回调
        self.on_complete(nickname)
    
    def save_user_config(self, nickname):
        try:
            save_user_config_fields(
                nickname=nickname,
                first_run=False,
                theme=DEFAULT_THEME,
            )
            log(f"用户配置已保存：{nickname}")
        except Exception as e:
            log(f"保存用户配置异常：{e}")
            traceback.print_exc()

def load_user_config():
    """加载用户配置"""
    try:
        if os.path.exists(USER_CONFIG_FILE):
            config = load_json_file(USER_CONFIG_FILE, {})
            if not isinstance(config, dict):
                config = {}
            log("用户配置加载成功")
            # 确保主题配置存在
            if "theme" not in config:
                config["theme"] = DEFAULT_THEME
            restore_custom_theme(config)
            return config
        else:
            log("未找到用户配置文件")
            return {"first_run": True, "nickname": "", "theme": DEFAULT_THEME}
    except Exception as e:
        log(f"加载用户配置异常：{e}")
        return {"first_run": True, "nickname": "", "theme": DEFAULT_THEME}

def get_theme_colors(theme_name=None):
    """获取主题颜色配置"""
    if theme_name is None:
        config = load_user_config()
        theme_name = config.get("theme", DEFAULT_THEME)
    
    if theme_name in THEMES:
        return THEMES[theme_name]
    else:
        return THEMES[DEFAULT_THEME]

# ========== 多段休眠时段工具函数 ==========
def is_in_any_sleep_period(sleep_periods):
    """判断当前时间是否在任一休眠时段内"""
    now = datetime.now().time()
    for period in sleep_periods:
        try:
            start = datetime.strptime(period["start"], "%H:%M").time()
            end = datetime.strptime(period["end"], "%H:%M").time()
            if start < end:
                if start <= now < end:
                    return True
            else:
                # 跨天
                if now >= start or now < end:
                    return True
        except Exception as e:
            log(f"休眠时段解析异常: {e}")
    return False

# ========== 加载/保存提醒设置，兼容多段休眠时段 ==========
def load_reminder_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
            reminders = [r for r in settings if isinstance(r, dict) and "key" in r]
            challenge_raw = next(
                (r for r in settings if isinstance(r, dict) and "answer_required" in r),
                None,
            )
            challenge_cfg = normalize_challenge_config(challenge_raw)
            # 兼容多种休眠配置
            sleep_cfg = next((r for r in settings if isinstance(r, dict) and ("sleep_periods" in r or ("sleep_start" in r and "sleep_end" in r))), None)
            # 自动升级旧配置
            if sleep_cfg is None:
                sleep_cfg = {"sleep_periods": [{"start": "23:00", "end": "07:00"}]}
            elif "sleep_start" in sleep_cfg and "sleep_end" in sleep_cfg:
                sleep_cfg = {"sleep_periods": [{"start": sleep_cfg["sleep_start"], "end": sleep_cfg["sleep_end"]}]}
            elif "sleep_periods" not in sleep_cfg:
                sleep_cfg = {"sleep_periods": [{"start": "23:00", "end": "07:00"}]}
            # 补全缺省项
            keys = {r["key"] for r in DEFAULT_REMINDERS}
            for def_r in DEFAULT_REMINDERS:
                if def_r["key"] not in [r["key"] for r in reminders]:
                    reminders.append(def_r)
            reminders = [r for r in reminders if r["key"] in keys]
            return reminders, sleep_cfg, challenge_cfg
        else:
            return DEFAULT_REMINDERS.copy(), {"sleep_periods": [{"start": "23:00", "end": "07:00"}]}, normalize_challenge_config(None)
    except Exception as e:
        print("[LOG] 加载提醒设置异常", e)
        return DEFAULT_REMINDERS.copy(), {"sleep_periods": [{"start": "23:00", "end": "07:00"}]}, normalize_challenge_config(None)

def save_reminder_settings(reminders, sleep_cfg, challenge_cfg):
    try:
        settings = reminders + [sleep_cfg, normalize_challenge_config(challenge_cfg)]
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[LOG] 保存提醒设置异常", e)

def is_autostart_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False

def enable_autostart():
    try:
        app_path = os.path.abspath(sys.argv[0])
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, app_path)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        log_exception(e)
        return False

def disable_autostart():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE)
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        finally:
            winreg.CloseKey(key)
        return True
    except Exception as e:
        log_exception(e)
        return False

class SettingsPage(tk.Toplevel):
    def __init__(self, master, nickname, reminders, topmost, autostart, theme, on_save, sleep_cfg=None, challenge_cfg=None, desktop_pet_autostart=False):
        super().__init__(master)
        self.title("设置")
        self.resizable(True, True)
        self._configure_window_geometry()
        self.on_save = on_save
        self.reminders = reminders
        self.current_theme = theme
        self.challenge_cfg = normalize_challenge_config(challenge_cfg)
        # 兼容sleep_cfg
        if sleep_cfg and "sleep_periods" in sleep_cfg:
            self.sleep_periods = [dict(p) for p in sleep_cfg["sleep_periods"]]
        else:
            self.sleep_periods = [{"start": "23:00", "end": "07:00"}]
        
        # 获取当前主题颜色
        self.theme_colors = get_theme_colors(theme)
        self.dialog_colors = get_dashboard_colors(self.theme_colors)
        self.configure(bg=self.dialog_colors["app_bg"])
        
        # 变量
        self.nickname_var = tk.StringVar(value=nickname)
        self.topmost_var = tk.BooleanVar(value=topmost)
        self.autostart_var = tk.BooleanVar(value=autostart)
        self.desktop_pet_autostart_var = tk.BooleanVar(value=desktop_pet_autostart)
        self.theme_var = tk.StringVar(value=theme)
        self.answer_required_var = tk.BooleanVar(
            value=self.challenge_cfg["answer_required"]
        )
        
        # 窗口设置
        self.transient(master)
        self.grab_set()
        self.focus()
        self.lift()
        
        self.create_widgets()

    def _configure_window_geometry(self):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(620, max(320, screen_width - 80))
        height = min(720, max(320, screen_height - 120))
        self.minsize(min(520, width), min(600, height))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        
    def create_widgets(self):
        colors = self.dialog_colors
        shell = tk.Frame(self, bg=colors["app_bg"], padx=18, pady=16)
        shell.pack(fill=tk.BOTH, expand=True)
        create_dialog_header(
            shell,
            "设置",
            "调整个人信息、提醒频率、休眠时段和桌面宠物选项。",
            colors,
        )
        # 创建滚动框架
        content_card = create_dialog_card(shell, colors, padx=0, pady=0, fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(content_card, bg=colors["surface"], highlightthickness=0)
        scrollbar = tk.Scrollbar(content_card, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=colors["surface"])
        # 居中内容容器
        self.center_frame = tk.Frame(self.scrollable_frame, bg=colors["surface"])
        self.center_frame.pack(fill=tk.X, expand=True, padx=28, pady=16)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        self.settings_canvas_window = canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(
                self.settings_canvas_window, width=event.width
            ),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        # 个人设置区
        self.create_personal_settings()
        # 主题设置区
        self.create_theme_settings()
        # 提醒设置区
        self.create_reminder_settings()
        # 休眠时段设置区
        self.create_sleep_settings()
        # 保存按钮
        save_btn = tk.Button(
            self.center_frame, text="保存", 
            width=12,
            command=self.save,
            **dialog_button_options(colors, primary=True)
        )
        save_btn.pack(pady=20)
        # 布局滚动组件
        canvas.pack(side="left", fill="both", expand=True, padx=(0, 5))
        scrollbar.pack(side="right", fill="y")
        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.bind("<MouseWheel>", _on_mousewheel)
        # 绑定键盘滚动
        def _on_key(event):
            if event.keysym == "Up":
                canvas.yview_scroll(-1, "units")
            elif event.keysym == "Down":
                canvas.yview_scroll(1, "units")
        canvas.bind("<Up>", _on_key)
        canvas.bind("<Down>", _on_key)
    
    def create_personal_settings(self):
        colors = self.dialog_colors
        section = create_dialog_card(self.center_frame, colors, padx=16, pady=14)
        # 个人设置标题
        tk.Label(
            section, text="个人设置", 
            font=("微软雅黑", 14, "bold"), 
            bg=colors["surface"], 
            fg=colors["text_primary"]
        ).pack(pady=(0, 10))
        # 设置表单
        form = tk.Frame(section, bg=colors["surface"])
        form.pack(pady=(0, 10), padx=0)
        # 昵称
        tk.Label(
            form, text="昵称", 
            font=("微软雅黑", 12), 
            bg=colors["surface"],
            fg=colors["text_primary"]
        ).grid(row=0, column=0, sticky='e', padx=(0,8), pady=6)
        nickname_entry = tk.Entry(
            form, textvariable=self.nickname_var, 
            font=("微软雅黑", 12), width=18, 
            relief=tk.FLAT, bg="#ffffff", 
            highlightbackground=self.theme_colors["button_bg"], 
            highlightcolor=self.theme_colors["button_active"], 
            highlightthickness=2, bd=0, 
            fg="#333333"
        )
        nickname_entry.grid(row=0, column=1, padx=6, pady=6)
        # 窗口置顶
        self.topmost_cb = tk.Checkbutton(
            form, text="窗口置顶", 
            variable=self.topmost_var, 
            font=("微软雅黑", 11), 
            bg=colors["surface"], 
            fg=colors["text_primary"]
        )
        self.topmost_cb.grid(row=1, column=0, columnspan=2, pady=(10,0), sticky='w')
        # 开机自启动
        self.autostart_cb = tk.Checkbutton(
            form, text="开机自启动", 
            variable=self.autostart_var, 
            font=("微软雅黑", 11), 
            bg=colors["surface"], 
            fg=colors["text_primary"]
        )
        self.autostart_cb.grid(row=2, column=0, columnspan=2, pady=(5,0), sticky='w')

        self.desktop_pet_autostart_cb = tk.Checkbutton(
            form, text="启动应用时自动打开桌面宠物",
            variable=self.desktop_pet_autostart_var,
            font=("微软雅黑", 11),
            bg=colors["surface"],
            fg=colors["text_primary"]
        )
        self.desktop_pet_autostart_cb.grid(row=3, column=0, columnspan=2, pady=(5,0), sticky='w')
        
        # 好友权限设置
        permissions = load_user_permissions()
        self.allow_data_view_var = tk.BooleanVar(value=permissions.get("allow_data_view", True))
        
        tk.Label(
            form, text="好友权限：", 
            font=("微软雅黑", 12), 
            bg=colors["surface"],
            fg=colors["text_primary"]
        ).grid(row=4, column=0, sticky='e', padx=(0,8), pady=(15,6))
        
        self.data_view_cb = tk.Checkbutton(
            form, text="允许好友查看健康数据", 
            variable=self.allow_data_view_var, 
            font=("微软雅黑", 11), 
            bg=colors["surface"], 
            fg=colors["text_primary"]
        )
        self.data_view_cb.grid(row=5, column=0, columnspan=2, pady=(0,5), sticky='w')
        support_row = tk.Frame(section, bg=colors["surface"])
        support_row.pack(fill=tk.X, pady=(8, 0))
        tk.Label(
            support_row, text="当前版本：{}".format(APP_VERSION),
            font=("微软雅黑", 10), bg=colors["surface"], fg=colors["text_secondary"],
        ).pack(side=tk.LEFT)
        tk.Button(
            support_row, text="打开日志文件",
            command=self.open_log_file,
            **dialog_button_options(colors),
        ).pack(side=tk.RIGHT, padx=(8, 0))
        tk.Button(
            support_row, text="打开程序目录",
            command=self.open_app_folder,
            **dialog_button_options(colors),
        ).pack(side=tk.RIGHT)
        # 居中form
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

    def open_log_file(self):
        if not os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "a", encoding="utf-8"):
                    pass
            except Exception as e:
                messagebox.showerror("打开失败", "无法创建日志文件：\n{}".format(e), parent=self)
                return
        if not open_path_with_default_app(LOG_FILE):
            messagebox.showerror("打开失败", "无法打开日志文件：\n{}".format(LOG_FILE), parent=self)

    def open_app_folder(self):
        if not open_path_with_default_app(APP_DIR):
            messagebox.showerror("打开失败", "无法打开程序目录：\n{}".format(APP_DIR), parent=self)
    
    def create_theme_settings(self):
        colors = self.dialog_colors
        section = create_dialog_card(self.center_frame, colors, padx=16, pady=14)
        tk.Label(
            section, text="主题设置", 
            font=("微软雅黑", 14, "bold"), 
            bg=colors["surface"], 
            fg=colors["text_primary"]
        ).pack(pady=(0, 10))
        theme_frame = tk.Frame(section, bg=colors["surface"])
        theme_frame.pack(pady=(0, 10))
        tk.Label(
            theme_frame, text="预设主题：", 
            font=("微软雅黑", 12), 
            bg=colors["surface"],
            fg=colors["text_primary"]
        ).pack(anchor='center', pady=(0, 5))
        themes_frame = tk.Frame(theme_frame, bg=colors["surface"])
        themes_frame.pack()
        for i, theme_name in enumerate(THEMES.keys()):
            theme_btn = tk.Button(
                themes_frame, text=theme_name,
                font=("微软雅黑", 10),
                bg=self.theme_colors["button_bg"] if theme_name == self.current_theme else "#f0f0f0",
                fg=self.theme_colors["button_fg"] if theme_name == self.current_theme else "#333333",
                relief=tk.FLAT,
                bd=1,
                command=lambda t=theme_name: self.select_theme(t)
            )
            theme_btn.pack(side=tk.LEFT, padx=(0, 5), pady=2)
        custom_frame = tk.Frame(section, bg=colors["surface"])
        custom_frame.pack(pady=(10, 0))
        custom_btn = tk.Button(
            custom_frame, text="自定义颜色",
                font=("微软雅黑", 11),
            bg="#666666", fg="white",
            relief=tk.FLAT,
            command=self.custom_color
        )
        custom_btn.pack(anchor='center')
    
    def create_reminder_settings(self):
        colors = self.dialog_colors
        section = create_dialog_card(self.center_frame, colors, padx=16, pady=14)
        tk.Label(
            section, text="提醒设置", 
            font=("微软雅黑", 14, "bold"), 
            bg=colors["surface"], 
            fg=colors["text_primary"]
        ).pack(pady=(0, 10))
        reminder_frame = tk.Frame(section, bg=colors["surface"])
        reminder_frame.pack(pady=6)
        self.reminder_vars = {}
        self.interval_vars = {}
        for r in self.reminders:
            row = tk.Frame(reminder_frame, bg=colors["surface"])
            row.pack(pady=6)
            var = tk.BooleanVar(value=r["enabled"])
            self.reminder_vars[r["key"]] = var
            interval_var = tk.IntVar(value=r["interval"])
            self.interval_vars[r["key"]] = interval_var
            cb = tk.Checkbutton(
                row, text=r["name"], 
                variable=var, 
                bg=colors["surface"], 
                font=("微软雅黑", 12), 
                fg=self.theme_colors["button_bg"]
            )
            cb.pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(
                row, text="间隔(分钟)", 
                bg=colors["surface"], 
                font=("微软雅黑", 10), 
                fg=self.theme_colors["button_bg"]
            ).pack(side=tk.LEFT)
            entry = tk.Spinbox(
                row, from_=REMINDER_MIN, to=REMINDER_MAX, 
                width=4, textvariable=interval_var, 
                font=("微软雅黑", 10), 
                relief=tk.FLAT, bg="#ffffff", 
                fg="#333333", highlightthickness=0
            )
            entry.pack(side=tk.LEFT, padx=(2, 0))

        challenge_frame = tk.Frame(reminder_frame, bg=colors["surface"])
        challenge_frame.pack(fill=tk.X, pady=(10, 0))
        tk.Checkbutton(
            challenge_frame,
            text="关闭提醒时需要答题",
            variable=self.answer_required_var,
            bg=colors["surface"],
            fg=self.theme_colors["button_bg"],
            font=("微软雅黑", 11),
        ).pack(anchor="w")
        tk.Label(
            challenge_frame,
            text="开启后定时健康提醒将全屏显示；可稍后提醒 2 次，每次 5 分钟。",
            bg=colors["surface"],
            fg="#888888",
            font=("微软雅黑", 9),
            wraplength=380,
            justify=tk.LEFT,
        ).pack(anchor="w", padx=(24, 0), pady=(2, 0))
    
    def create_sleep_settings(self):
        colors = self.dialog_colors
        section = create_dialog_card(self.center_frame, colors, padx=16, pady=14)
        tk.Label(
            section, text="休眠时段设置", 
            font=("微软雅黑", 14, "bold"), 
            bg=colors["surface"], 
            fg=colors["text_primary"]
        ).pack(pady=(20, 10))
        self.sleep_frame = tk.Frame(section, bg=colors["surface"])
        self.sleep_frame.pack(pady=(0, 10))
        self.sleep_period_vars = []
        self.render_sleep_periods()
        add_btn = tk.Button(
            self.sleep_frame, text="添加时段", font=("微软雅黑", 10),
            bg=self.theme_colors["button_bg"], fg=self.theme_colors["button_fg"], relief=tk.FLAT,
            command=self.add_sleep_period
        )
        add_btn.grid(row=99, column=0, columnspan=5, sticky='w', pady=(8,0))
        tk.Label(self.sleep_frame, text="格式: HH:MM (24小时制)", font=("微软雅黑", 9), bg=self.theme_colors["bg"], fg="#888888").grid(row=100, column=0, columnspan=5, sticky='w', pady=(2,0))
    
    def render_sleep_periods(self):
        colors = getattr(self, "dialog_colors", get_dashboard_colors(self.theme_colors))
        # 清空原有
        for widgets in getattr(self, '_sleep_widgets', []):
            for w in widgets:
                w.destroy()
        self._sleep_widgets = []
        self.sleep_period_vars.clear()
        for idx, period in enumerate(self.sleep_periods):
            start_var = tk.StringVar(value=period.get("start", "23:00"))
            end_var = tk.StringVar(value=period.get("end", "07:00"))
            self.sleep_period_vars.append((start_var, end_var))
            row_widgets = []
            lbl1 = tk.Label(self.sleep_frame, text=f"时段{idx+1}", font=("微软雅黑", 11), bg=colors["surface"], fg=colors["text_primary"])
            lbl1.grid(row=idx, column=0, padx=(0,6), pady=4)
            row_widgets.append(lbl1)
            entry1 = tk.Entry(self.sleep_frame, textvariable=start_var, font=("微软雅黑", 11), width=8, relief=tk.FLAT, bg="#ffffff", fg="#333333")
            entry1.grid(row=idx, column=1, padx=2)
            row_widgets.append(entry1)
            lbl2 = tk.Label(self.sleep_frame, text="-", font=("微软雅黑", 11), bg=colors["surface"], fg=colors["text_primary"])
            lbl2.grid(row=idx, column=2)
            entry2 = tk.Entry(self.sleep_frame, textvariable=end_var, font=("微软雅黑", 11), width=8, relief=tk.FLAT, bg="#ffffff", fg="#333333")
            entry2.grid(row=idx, column=3, padx=2)
            row_widgets.append(entry2)
            del_btn = tk.Button(self.sleep_frame, text="删除", font=("微软雅黑", 9), bg="#e57373", fg="white", relief=tk.FLAT, command=lambda i=idx: self.delete_sleep_period(i))
            del_btn.grid(row=idx, column=4, padx=(8,0))
            row_widgets.append(del_btn)
            self._sleep_widgets.append(row_widgets)
    
    def add_sleep_period(self):
        self.sleep_periods.append({"start": "12:00", "end": "13:00"})
        self.render_sleep_periods()
    
    def delete_sleep_period(self, idx):
        if len(self.sleep_periods) > 1:
            self.sleep_periods.pop(idx)
            self.render_sleep_periods()
    
    def select_theme(self, theme_name):
        """选择预设主题"""
        self.current_theme = theme_name
        self.theme_var.set(theme_name)
        self.theme_colors = get_theme_colors(theme_name)
        self.apply_theme_preview()
    
    def custom_color(self):
        """自定义颜色"""
        color = colorchooser.askcolor(title="选择主题颜色")
        if color[1]:  # 如果用户选择了颜色
            # 创建自定义主题
            custom_theme = {
                "name": "自定义",
                "bg": color[1],
                "button_bg": color[1],
                "button_fg": "white",
                "button_active": color[1]
            }
            THEMES["自定义"] = custom_theme
            self.current_theme = "自定义"
            self.theme_var.set("自定义")
            self.theme_colors = custom_theme
            self.apply_theme_preview()
    
    def apply_theme_preview(self):
        """应用主题预览"""
        # 更新窗口背景
        self.configure(bg=self.theme_colors["bg"])
        
        # 更新滚动框架背景
        if hasattr(self, 'scrollable_frame'):
            self.scrollable_frame.configure(bg=self.theme_colors["bg"])
        
        # 只更新标题和框架背景，完全不更新复选框
        for widget in self.winfo_children():
            if isinstance(widget, tk.Label) and widget.cget("text") in ["设置"]:
                widget.configure(bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"])
            elif isinstance(widget, tk.Canvas):
                widget.configure(bg=self.theme_colors["bg"])
                # 更新滚动框架内的组件
                self.update_scrollable_frame_colors()
            elif isinstance(widget, tk.Frame):
                widget.configure(bg=self.theme_colors["bg"])
                # 只更新框架内的标签和按钮，完全跳过复选框
                self.update_widget_colors_safe(widget)
    
    def update_scrollable_frame_colors(self):
        """更新滚动框架内的组件颜色"""
        if hasattr(self, 'scrollable_frame'):
            for widget in self.scrollable_frame.winfo_children():
                if isinstance(widget, tk.Label) and widget.cget("text") in ["个人设置", "主题设置", "提醒设置"]:
                    widget.configure(bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"])
                elif isinstance(widget, tk.Frame):
                    widget.configure(bg=self.theme_colors["bg"])
                    self.update_widget_colors_safe(widget)
                elif isinstance(widget, tk.Button):
                    widget.configure(
                        bg=self.theme_colors["button_bg"],
                        fg=self.theme_colors["button_fg"],
                        activebackground=self.theme_colors["button_active"]
                    )
    
    def update_widget_colors_safe(self, parent):
        """安全更新组件颜色，完全保护复选框"""
        for widget in parent.winfo_children():
            if isinstance(widget, tk.Label):
                widget.configure(bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"])
            elif isinstance(widget, tk.Frame):
                widget.configure(bg=self.theme_colors["bg"])
                self.update_widget_colors_safe(widget)
            elif isinstance(widget, tk.Button):
                # 更新按钮颜色，但保持主题选择按钮的特殊逻辑
                if widget.cget("text") in THEMES.keys():
                    widget.configure(
                        bg=self.theme_colors["button_bg"] if widget.cget("text") == self.current_theme else "#f0f0f0",
                        fg=self.theme_colors["button_fg"] if widget.cget("text") == self.current_theme else "#333333"
                    )
                else:
                    widget.configure(
                        bg=self.theme_colors["button_bg"],
                        fg=self.theme_colors["button_fg"],
                        activebackground=self.theme_colors["button_active"]
                    )
            # 完全跳过复选框，不进行任何操作
    
    def save(self):
        """保存设置"""
        # 更新提醒设置
        for r in self.reminders:
            r["enabled"] = self.reminder_vars[r["key"]].get()
            r["interval"] = self.interval_vars[r["key"]].get()
        
        # 获取设置值
        nickname = self.nickname_var.get().strip()
        topmost = self.topmost_var.get()
        autostart = self.autostart_var.get()
        desktop_pet_autostart = self.desktop_pet_autostart_var.get()
        theme = self.current_theme
        
        # 休眠时段
        sleep_periods = []
        for start_var, end_var in self.sleep_period_vars:
            start = start_var.get().strip() or "23:00"
            end = end_var.get().strip() or "07:00"
            sleep_periods.append({"start": start, "end": end})
        sleep_cfg = {"sleep_periods": sleep_periods}
        challenge_cfg = {
            **self.challenge_cfg,
            "answer_required": self.answer_required_var.get(),
        }
        
        # 处理开机自启动
        if autostart:
            enable_autostart()
        else:
            disable_autostart()
        
        # 保存用户配置
        try:
            save_user_config_fields(
                nickname=nickname,
                first_run=False,
                topmost=topmost,
                theme=theme,
                desktop_pet_autostart=desktop_pet_autostart,
                custom_theme=THEMES.get("自定义"),
            )
        except Exception as e:
            log(f"保存用户配置异常：{e}")
        
        # 保存好友权限设置
        try:
            permissions = {
                "allow_data_view": self.allow_data_view_var.get()
            }
            save_user_permissions(permissions)
        except Exception as e:
            log(f"保存好友权限异常：{e}")
        
        # 保存提醒设置和休眠配置
        save_reminder_settings(self.reminders, sleep_cfg, challenge_cfg)
        
        # 调用保存回调
        self.on_save(nickname, self.reminders, topmost, autostart, theme, sleep_cfg, challenge_cfg)
        self.destroy()

DESKTOP_PETS = [
    {
        "id": "eye_duck_pet_ready",
        "name": "护眼鸭鸭",
        "color": "#f2c94c",
        "accent": "#ffe08a",
        "belly": "#fff7d6",
        "art": "",
        "messages": ["嘎嘎，记得喝水。", "看远一点，眼睛会舒服。", "起来活动一下，我陪你。"],
    },
    {
        "id": "dog_XB_white_pet_ready",
        "name": "小白狗",
        "color": "#f8f8f8",
        "accent": "#d8d8d8",
        "belly": "#ffffff",
        "art": "",
        "messages": ["我在旁边看着你，别忘了休息。", "喝点水，状态会更稳。", "站起来活动一下吧。"],
    },
    {
        "id": "dog_XTM",
        "name": "小透明",
        "color": "#f8f8f8",
        "accent": "#d8d8d8",
        "belly": "#ffffff",
        "art": "",
        "messages": ["我很透明，但会认真提醒你。", "休息一下，别一直硬撑。", "喝点水，我在。"],
    },
    {
        "id": "dog_XJM_pet_ready",
        "name": "小鸡毛",
        "color": "#ffd86b",
        "accent": "#ffb36b",
        "belly": "#fff4cc",
        "art": "",
        "messages": ["上班也要记得喝水。", "看远一点，别让眼睛太累。", "先伸个懒腰，再继续工作。"],
    },
    {
        "id": "capybara_pet_ready",
        "name": "卡皮巴拉",
        "color": "#d69a5b",
        "accent": "#b87942",
        "belly": "#f2c58c",
        "art": "",
        "messages": ["慢一点也没关系，先照顾身体。", "喝水时间到了。", "放松肩颈，休息一分钟。"],
    },
]


def get_desktop_pet(pet_id=None):
    for pet in DESKTOP_PETS:
        if pet["id"] == pet_id:
            return pet
    return random.choice(DESKTOP_PETS)


def choose_desktop_pet_id():
    return random.choice(DESKTOP_PETS)["id"]


def normalize_desktop_pet_name(name, fallback):
    fallback = (fallback or "桌面宠物").strip()
    if not isinstance(name, str):
        return fallback
    clean_name = name.strip()
    if not clean_name:
        return fallback
    return clean_name[:8]


def get_desktop_pet_autostart(config=None):
    config = config if isinstance(config, dict) else load_user_config()
    return bool(config.get("desktop_pet_autostart", False))


def parse_reminder_pause_until(config=None):
    config = config if isinstance(config, dict) else load_user_config()
    pause_until = config.get("reminder_pause_until")
    if not isinstance(pause_until, str) or not pause_until.strip():
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(pause_until.strip(), fmt)
        except ValueError:
            continue
    return None


def is_reminder_paused(config=None, now=None):
    now = now or datetime.now()
    pause_until = parse_reminder_pause_until(config)
    return bool(pause_until and now < pause_until)


def format_reminder_pause_status(config=None, now=None):
    pause_until = parse_reminder_pause_until(config)
    now = now or datetime.now()
    if pause_until and now < pause_until:
        return "免打扰中，{} 后恢复提醒".format(pause_until.strftime("%H:%M"))
    return "提醒正常"


def clear_expired_reminder_pause(config=None, now=None):
    config = config if isinstance(config, dict) else load_user_config()
    pause_until = parse_reminder_pause_until(config)
    now = now or datetime.now()
    if pause_until and now >= pause_until:
        save_user_config_fields(reminder_pause_until="")
        return True
    return False


PET_LIFE_MILESTONES = {
    3: "生命 3 天，解锁开心表情。",
    7: "生命 7 天，解锁休息表情。",
    14: "生命 14 天，解锁健康提醒表情。",
    30: "生命 30 天，成为熟悉的伙伴。",
}
PET_MOOD_DEFAULT = 60
PET_MOOD_MIN = 0
PET_MOOD_MAX = 100
PET_STATE_UNLOCK_DAYS = {
    "happy": 3,
    "sleep": 7,
    "drink": 14,
    "eye": 14,
    "stand": 14,
    "sport": 14,
}


def load_pet_lives(config=None):
    config = config if isinstance(config, dict) else load_user_config()
    pet_lives = config.get("pet_lives", {})
    return pet_lives if isinstance(pet_lives, dict) else {}


def load_unlocked_pet_ids(config=None):
    config = config if isinstance(config, dict) else load_user_config()
    raw_ids = config.get("unlocked_pet_ids", [])
    if not isinstance(raw_ids, list):
        raw_ids = []
    valid_ids = {pet["id"] for pet in DESKTOP_PETS}
    unlocked_ids = {pet_id for pet_id in raw_ids if isinstance(pet_id, str) and pet_id in valid_ids}
    current_pet_id = config.get("desktop_pet_id")
    if isinstance(current_pet_id, str) and current_pet_id in valid_ids:
        unlocked_ids.add(current_pet_id)
    return unlocked_ids


def mark_desktop_pet_unlocked(pet_id, config=None):
    valid_ids = {pet["id"] for pet in DESKTOP_PETS}
    if pet_id not in valid_ids:
        return load_unlocked_pet_ids(config)
    config = config if isinstance(config, dict) else load_user_config()
    unlocked_ids = load_unlocked_pet_ids(config)
    if pet_id not in unlocked_ids:
        unlocked_ids.add(pet_id)
        save_user_config_fields(unlocked_pet_ids=sorted(unlocked_ids))
    return unlocked_ids


def is_desktop_pet_unlocked(pet_id, config=None):
    return pet_id in load_unlocked_pet_ids(config)


def touch_pet_life(config, pet_id, today=None):
    today = today or date.today().isoformat()
    pet_lives = dict(load_pet_lives(config))
    current = pet_lives.get(pet_id, {})
    if not isinstance(current, dict):
        current = {}
    life_days = int(current.get("life_days", 0) or 0)
    last_seen_date = current.get("last_seen_date")
    changed = last_seen_date != today
    if changed:
        life_days = max(0, life_days) + 1
        current = {"life_days": life_days, "last_seen_date": today}
        pet_lives[pet_id] = current
        save_user_config_fields(pet_lives=pet_lives)
    return life_days, changed


def get_pet_life_milestone_message(life_days, changed_today=False):
    if not changed_today:
        return None
    return PET_LIFE_MILESTONES.get(life_days)


def get_unlocked_pet_states(life_days):
    life_days = max(1, int(life_days or 1))
    unlocked = {"idle", "unhappy"}
    for state_name, required_days in PET_STATE_UNLOCK_DAYS.items():
        if life_days >= required_days:
            unlocked.add(state_name)
    return unlocked


def is_pet_state_unlocked(state_name, life_days):
    if not state_name:
        return False
    if state_name.startswith("idle"):
        return True
    return state_name in get_unlocked_pet_states(life_days)


def format_pet_life_label(pet_display_name, life_days):
    name = normalize_desktop_pet_name(pet_display_name, "桌面宠物")
    return "{} · 生命 {} 天".format(name, max(1, int(life_days or 1)))


def load_pet_moods(config=None):
    config = config if isinstance(config, dict) else load_user_config()
    pet_moods = config.get("pet_moods", {})
    return pet_moods if isinstance(pet_moods, dict) else {}


def clamp_pet_mood(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = PET_MOOD_DEFAULT
    return max(PET_MOOD_MIN, min(PET_MOOD_MAX, value))


def get_pet_mood(config, pet_id):
    moods = load_pet_moods(config)
    return clamp_pet_mood(moods.get(pet_id, PET_MOOD_DEFAULT))


def update_pet_mood(pet_id, delta, config=None):
    config = config if isinstance(config, dict) else load_user_config()
    moods = dict(load_pet_moods(config))
    mood = clamp_pet_mood(moods.get(pet_id, PET_MOOD_DEFAULT) + delta)
    moods[pet_id] = mood
    save_user_config_fields(pet_moods=moods)
    return mood


def load_pet_goal_reward_dates(config=None):
    config = config if isinstance(config, dict) else load_user_config()
    reward_dates = config.get("pet_goal_reward_dates", {})
    return reward_dates if isinstance(reward_dates, dict) else {}


def reward_current_pet_for_daily_completion(config=None, today=None):
    config = config if isinstance(config, dict) else load_user_config()
    today = today or date.today().isoformat()
    pet_id = config.get("desktop_pet_id")
    if not pet_id:
        return None, False
    reward_dates = dict(load_pet_goal_reward_dates(config))
    if reward_dates.get(pet_id) == today:
        return get_pet_mood(config, pet_id), False
    moods = dict(load_pet_moods(config))
    mood = clamp_pet_mood(moods.get(pet_id, PET_MOOD_DEFAULT) + 10)
    moods[pet_id] = mood
    reward_dates[pet_id] = today
    save_user_config_fields(pet_moods=moods, pet_goal_reward_dates=reward_dates)
    return mood, True


def load_pet_mood_recovery_dates(config=None):
    config = config if isinstance(config, dict) else load_user_config()
    recovery_dates = config.get("pet_mood_recovery_dates", {})
    return recovery_dates if isinstance(recovery_dates, dict) else {}


def recover_pet_mood_once_per_day(pet_id, config=None, today=None):
    if not pet_id:
        return PET_MOOD_DEFAULT, False
    config = config if isinstance(config, dict) else load_user_config()
    today = today or date.today().isoformat()
    recovery_dates = dict(load_pet_mood_recovery_dates(config))
    mood = get_pet_mood(config, pet_id)
    if recovery_dates.get(pet_id) == today:
        return mood, False
    recovered_mood = clamp_pet_mood(mood + 2)
    recovery_dates[pet_id] = today
    moods = dict(load_pet_moods(config))
    moods[pet_id] = recovered_mood
    save_user_config_fields(pet_moods=moods, pet_mood_recovery_dates=recovery_dates)
    return recovered_mood, recovered_mood != mood


def describe_pet_mood(mood):
    mood = clamp_pet_mood(mood)
    if mood >= 80:
        return "开心"
    if mood >= 50:
        return "平静"
    if mood >= 25:
        return "担心"
    return "低落"


def get_pet_mood_feedback(mood):
    mood_name = describe_pet_mood(mood)
    if mood_name == "开心":
        return "它开心起来了"
    if mood_name == "平静":
        return "它安心了一点"
    if mood_name == "担心":
        return "它没那么担心了"
    return "它在慢慢恢复"


def get_low_pet_mood_message(mood):
    mood = clamp_pet_mood(mood)
    if mood < 25:
        return "我有点低落，今天也想陪你慢慢恢复。"
    if mood < 50:
        return "我有点担心你，记得喝水、护眼，别一直硬撑。"
    return None


def get_pet_mood_bar_color(mood):
    mood = clamp_pet_mood(mood)
    if mood >= 80:
        return "#31a66a"
    if mood >= 50:
        return "#2f8f7b"
    if mood >= 25:
        return "#e59a3a"
    return "#6b7f99"


def format_pet_status_label(pet_display_name, life_days, mood):
    name = normalize_desktop_pet_name(pet_display_name, "桌面宠物")
    return "{} · 生命 {} 天 · {}".format(
        name,
        max(1, int(life_days or 1)),
        describe_pet_mood(mood),
    )


PET_STATE_LABELS = {
    "idle": "普通互动",
    "happy": "开心",
    "unhappy": "关心提醒",
    "sleep": "休息",
    "drink": "喝水",
    "eye": "护眼",
    "stand": "站立",
    "sport": "运动",
}


def format_pet_catalog_unlocked_states(life_days):
    life_days = int(life_days or 0)
    if life_days <= 0:
        return "未开始陪伴"
    state_order = ("idle", "unhappy", "happy", "sleep", "drink", "eye", "stand", "sport")
    unlocked = get_unlocked_pet_states(life_days)
    labels = [PET_STATE_LABELS[state_name] for state_name in state_order if state_name in unlocked]
    return "、".join(labels)


def format_pet_catalog_next_stage(life_days):
    life_days = int(life_days or 0)
    next_day = None
    for milestone_day in sorted(PET_LIFE_MILESTONES):
        if life_days < milestone_day:
            next_day = milestone_day
            break
    if next_day is None:
        return "已解锁全部基础表情"
    return "距离生命 {} 天还差 {} 天".format(next_day, next_day - life_days)


class DesktopPetWindow(tk.Toplevel):
    transparent_color = "#ff00ff"

    def __init__(
            self, master, nickname, theme_colors, pet, pet_display_name=None,
            on_redraw=None, on_rename=None, on_open_catalog=None,
            progress_summary=None, pet_life_days=1, pet_mood=PET_MOOD_DEFAULT,
            on_start_pomodoro=None, on_cancel_pomodoro=None, pomodoro_status=None,
            on_show_progress=None, on_record_health=None, on_start_eye_training=None,
            on_toggle_pause=None):
        super().__init__(master)
        self.nickname = nickname or "朋友"
        self.theme_colors = theme_colors
        self.pet = pet
        self.pet_display_name = normalize_desktop_pet_name(pet_display_name, pet["name"])
        self.pet_life_days = max(1, int(pet_life_days or 1))
        self.pet_mood = clamp_pet_mood(pet_mood)
        self.on_redraw = on_redraw
        self.on_rename = on_rename
        self.on_open_catalog = on_open_catalog
        self.progress_summary = progress_summary
        self.on_start_pomodoro = on_start_pomodoro
        self.on_cancel_pomodoro = on_cancel_pomodoro
        self.pomodoro_status = pomodoro_status
        self.on_show_progress = on_show_progress
        self.on_record_health = on_record_health
        self.on_start_eye_training = on_start_eye_training
        self.on_toggle_pause = on_toggle_pause
        self._drag_offset = (0, 0)
        self._is_docked = False
        self._dock_side = None
        self._visible_strip = 28
        self._message_index = 0
        self._click_after_id = None
        self._pose = 0
        self._sprite_frames = []
        self._state_frames = {}
        self._active_state = None
        self._current_sprite = None
        self._animation_after_id = None
        self.title("桌面宠物")
        self.geometry(self._default_geometry())
        self.resizable(False, False)
        self.overrideredirect(True)
        self.configure(bg=self.transparent_color)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", self.transparent_color)
        except tk.TclError:
            self.configure(bg="#f7fff8")
        self._build_ui()
        self.bind("<ButtonPress-1>", self._start_drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._end_drag)
        self.pet_canvas.bind("<Button-1>", self._on_click)
        self.pet_canvas.bind("<Double-Button-1>", self._on_double_click)
        self.pet_canvas.bind("<Button-3>", self._show_menu)
        self.bubble_label.bind("<Button-3>", self._show_menu)
        self.after(1500, self._cycle_message)

    def _default_geometry(self):
        width = 310
        height = 340
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, screen_w - width - 48)
        y = max(0, screen_h - height - 88)
        return "{}x{}+{}+{}".format(width, height, x, y)

    def _build_ui(self):
        self.body = tk.Frame(self, bg=self.transparent_color, padx=8, pady=8)
        self.body.pack(fill=tk.BOTH, expand=True)
        top_row = tk.Frame(self.body, bg=self.transparent_color)
        top_row.pack(fill=tk.X)
        self.name_label = tk.Label(
            top_row, text=format_pet_status_label(self.pet_display_name, self.pet_life_days, self.pet_mood), font=("微软雅黑", 10, "bold"),
            bg=self.transparent_color, fg=self.pet["color"],
        )
        self.name_label.pack(side=tk.LEFT)
        close = tk.Button(
            top_row, text="×", font=("微软雅黑", 10, "bold"),
            bg=self.transparent_color, fg="#5b6b61", bd=0, relief=tk.FLAT,
            activebackground=self.transparent_color, command=self.destroy,
        )
        close.pack(side=tk.RIGHT)
        self.pet_canvas = tk.Canvas(
            self.body, width=230, height=205, bg=self.transparent_color,
            bd=0, highlightthickness=0,
        )
        self.pet_canvas.pack(pady=(4, 8))
        self._load_pet_images()
        self._draw_pet()
        self.bubble_label = tk.Label(
            self.body, text="你抽到了{}，我是{}。".format(self.pet["name"], self.pet_display_name),
            font=("微软雅黑", 10), bg="#ffffff", fg="#123526",
            wraplength=250, justify=tk.LEFT, padx=12, pady=8,
            relief=tk.SOLID, bd=1,
            height=3,
        )
        self.bubble_label.pack(fill=tk.X)
        self.menu = tk.Menu(self, tearoff=False)
        self._refresh_menu()

    def _load_pet_images(self):
        self._sprite_frames = []
        self._state_frames = {}
        self._active_state = None
        self._current_sprite = None
        if Image is None or ImageTk is None:
            return
        pet_dir = resource_path(os.path.join("assets", "desktop_pets", self.pet["id"]))
        try:
            if os.path.isdir(pet_dir):
                frame_names = sorted(
                    (
                        name for name in os.listdir(pet_dir)
                        if self._is_idle_frame_name(name)
                    ),
                    key=self._idle_frame_sort_key,
                )
            else:
                frame_names = ()
            for frame_name in frame_names:
                frame_path = os.path.join(pet_dir, frame_name)
                if os.path.exists(frame_path):
                    image = self._prepare_pet_sprite(frame_path)
                    self._sprite_frames.append(ImageTk.PhotoImage(image))
            for state_name in ("happy", "unhappy", "sleep", "drink", "eye", "stand", "sport"):
                state_path = os.path.join(pet_dir, "{}.png".format(state_name))
                if os.path.exists(state_path):
                    image = self._prepare_pet_sprite(state_path)
                    self._state_frames[state_name] = ImageTk.PhotoImage(image)
        except Exception as e:
            log("加载桌面宠物图片异常：{}".format(e))
            self._sprite_frames = []
            self._state_frames = {}
            self._active_state = None

    def _is_idle_frame_name(self, filename):
        lower_name = filename.lower()
        if not lower_name.endswith(".png"):
            return False
        stem = lower_name[:-4]
        return (
            stem.startswith("idle_")
            or (stem.startswith("idle") and stem[4:].isdigit())
        )

    def _idle_frame_sort_key(self, filename):
        lower_name = filename.lower()
        stem = lower_name[:-4]
        if stem.startswith("idle_") and stem[5:].isdigit():
            return int(stem[5:])
        if stem.startswith("idle") and stem[4:].isdigit():
            return int(stem[4:])
        return 9999

    def _prepare_pet_sprite(self, frame_path):
        image = Image.open(frame_path).convert("RGBA").resize((196, 196), Image.LANCZOS)
        transparent_rgb = tuple(int(self.transparent_color[index:index + 2], 16) for index in (1, 3, 5))
        pixels = []
        for r, g, b, a in image.getdata():
            if a < 220:
                pixels.append((transparent_rgb[0], transparent_rgb[1], transparent_rgb[2], 255))
            else:
                pixels.append((r, g, b, 255))
        image.putdata(pixels)
        return image

    def _draw_pet(self):
        if self._sprite_frames or self._state_frames:
            c = self.pet_canvas
            c.delete("all")
            if self._active_state in self._state_frames:
                self._current_sprite = self._state_frames[self._active_state]
            elif self._sprite_frames:
                self._current_sprite = self._sprite_frames[self._pose % len(self._sprite_frames)]
            elif "happy" in self._state_frames:
                self._current_sprite = self._state_frames["happy"]
            else:
                self._current_sprite = next(iter(self._state_frames.values()))
            c.create_image(115, 101, image=self._current_sprite, anchor=tk.CENTER)
            return
        c = self.pet_canvas
        c.delete("all")
        body = self.pet["color"]
        accent = self.pet.get("accent", body)
        belly = self.pet.get("belly", "#ffffff")
        pet_id = self.pet.get("id")
        pose = self._pose % 3
        bob = -6 if pose == 1 else 0
        arm_raise = -18 if pose == 2 else 0
        eye_y = 72 + bob
        head_top = 32 + bob
        head_bottom = 122 + bob
        body_top = 102 + bob
        body_bottom = 180 + bob
        shadow_y = 190

        c.create_oval(58, shadow_y - 10, 172, shadow_y + 4, fill="#000000", outline="", stipple="gray25")

        if pet_id == "eye_cat":
            c.create_polygon(63, head_top + 10, 78, head_top - 28, 92, head_top + 12, fill=accent, outline=body, width=3)
            c.create_polygon(138, head_top + 12, 153, head_top - 28, 167, head_top + 10, fill=accent, outline=body, width=3)
        elif pet_id == "active_bear":
            c.create_oval(55, head_top - 8, 88, head_top + 25, fill=accent, outline=body, width=3)
            c.create_oval(142, head_top - 8, 175, head_top + 25, fill=accent, outline=body, width=3)
        elif pet_id == "stand_penguin":
            c.create_oval(63, head_top, 167, body_bottom, fill=body, outline="#0b3520", width=3)
        elif pet_id == "water_sprite":
            c.create_polygon(115, head_top - 28, 75, head_top + 35, 155, head_top + 35, fill=accent, outline=body, width=3)

        if pet_id != "stand_penguin":
            c.create_oval(65, body_top, 165, body_bottom, fill=body, outline="#1f3b2f", width=3)
            c.create_oval(58, head_top, 172, head_bottom, fill=body, outline="#1f3b2f", width=3)

        c.create_line(70, body_top + 18, 35, body_top + 45 + arm_raise, fill=body, width=12, capstyle=tk.ROUND)
        c.create_line(160, body_top + 18, 195, body_top + 45 - arm_raise, fill=body, width=12, capstyle=tk.ROUND)
        c.create_oval(25, body_top + 38 + arm_raise, 45, body_top + 58 + arm_raise, fill=accent, outline=body, width=2)
        c.create_oval(185, body_top + 38 - arm_raise, 205, body_top + 58 - arm_raise, fill=accent, outline=body, width=2)

        if pet_id == "stand_penguin":
            c.create_oval(83, body_top + 20, 147, body_bottom - 8, fill=belly, outline="")
        if pet_id != "stand_penguin":
            c.create_oval(88, body_top + 18, 142, body_bottom - 8, fill=belly, outline="")

        c.create_oval(78, eye_y, 93, eye_y + 15, fill="#17221d", outline="")
        c.create_oval(137, eye_y, 152, eye_y + 15, fill="#17221d", outline="")
        c.create_oval(83, eye_y + 4, 88, eye_y + 9, fill="#ffffff", outline="")
        c.create_oval(142, eye_y + 4, 147, eye_y + 9, fill="#ffffff", outline="")
        if pose == 1:
            c.create_arc(96, eye_y + 10, 134, eye_y + 36, start=200, extent=140, style=tk.ARC, width=3, outline="#17221d")
        else:
            c.create_arc(100, eye_y + 8, 130, eye_y + 28, start=200, extent=140, style=tk.ARC, width=2, outline="#17221d")
        c.create_oval(62, eye_y + 20, 82, eye_y + 34, fill="#ffb3c1", outline="")
        c.create_oval(148, eye_y + 20, 168, eye_y + 34, fill="#ffb3c1", outline="")
        c.create_oval(76, 174 + bob, 104, 194 + bob, fill=accent, outline=body, width=2)
        c.create_oval(126, 174 + bob, 154, 194 + bob, fill=accent, outline=body, width=2)
        if pet_id == "water_sprite":
            c.create_oval(138, head_top + 18, 158, head_top + 34, fill="#ffffff", outline="")
        elif pet_id == "active_bear":
            c.create_oval(108, eye_y + 16, 122, eye_y + 28, fill="#6b3d1d", outline="")
        elif pet_id == "stand_penguin":
            c.create_polygon(108, eye_y + 14, 122, eye_y + 14, 115, eye_y + 28, fill="#f2c94c", outline="")

    def _start_drag(self, event):
        if self._is_docked:
            self._expand_from_dock()
        self._drag_offset = (event.x, event.y)

    def _drag(self, event):
        self._is_docked = False
        self._dock_side = None
        x = self.winfo_x() + event.x - self._drag_offset[0]
        y = self.winfo_y() + event.y - self._drag_offset[1]
        self.geometry("+{}+{}".format(max(0, x), max(0, y)))

    def _end_drag(self, event=None):
        self._dock_if_near_edge()

    def _dock_if_near_edge(self):
        try:
            width = self.winfo_width() or 310
            height = self.winfo_height() or 340
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            x = self.winfo_x()
            y = min(max(0, self.winfo_y()), max(0, screen_h - height))
            if x <= 8:
                self._dock_to_side("left", y, width)
            elif x + width >= screen_w - 8:
                self._dock_to_side("right", y, width, screen_w)
        except tk.TclError:
            return

    def _dock_to_side(self, side, y, width=None, screen_w=None):
        width = width or self.winfo_width() or 310
        screen_w = screen_w or self.winfo_screenwidth()
        if side == "left":
            x = -(width - self._visible_strip)
        else:
            x = screen_w - self._visible_strip
        self._is_docked = True
        self._dock_side = side
        self.geometry("+{}+{}".format(x, y))
        save_user_config_fields(desktop_pet_docked=True, desktop_pet_dock_side=side)

    def _expand_from_dock(self):
        try:
            width = self.winfo_width() or 310
            screen_w = self.winfo_screenwidth()
            y = self.winfo_y()
            if self._dock_side == "left":
                x = 0
            elif self._dock_side == "right":
                x = max(0, screen_w - width)
            else:
                return
            self._is_docked = False
            self._dock_side = None
            self.geometry("+{}+{}".format(x, y))
            save_user_config_fields(desktop_pet_docked=False)
        except tk.TclError:
            return

    def _on_click(self, event=None):
        if self._is_docked:
            self._expand_from_dock()
            return
        if self._is_pomodoro_active():
            self._show_pomodoro_status()
            return
        if self._click_after_id:
            try:
                self.after_cancel(self._click_after_id)
            except tk.TclError:
                pass
        self._click_after_id = self.after(180, self._say_random)

    def _on_double_click(self, event=None):
        if self._click_after_id:
            try:
                self.after_cancel(self._click_after_id)
            except tk.TclError:
                pass
            self._click_after_id = None
        if self._is_pomodoro_active():
            self._show_pomodoro_status()
            return
        if self.progress_summary:
            self.show_state("happy", duration_ms=60 * 1000)
            self.show_message(self.progress_summary())

    def _open_pet_catalog(self):
        if self.on_open_catalog:
            self.after(10, lambda: self.on_open_catalog(self))

    def _refresh_menu(self):
        try:
            self.menu.delete(0, tk.END)
        except tk.TclError:
            return
        status = self.pomodoro_status() if self.pomodoro_status else {"active": False, "label": ""}
        if status.get("active"):
            self.menu.add_command(label=status.get("label") or "番茄时钟进行中", command=self._show_pomodoro_status)
            self.menu.add_command(label="结束番茄时钟", command=self._cancel_pomodoro)
        else:
            self.menu.add_command(label="开始番茄时钟", command=self._start_pomodoro)
        self.menu.add_separator()
        self.menu.add_command(label="查看今日进度", command=self._show_progress)
        self.menu.add_command(label="记录喝水", command=lambda: self._record_health("drink"))
        self.menu.add_command(label="开始护眼", command=self._start_eye_training)
        self.menu.add_command(label="设置免打扰", command=self._toggle_pause)
        self.menu.add_separator()
        self.menu.add_command(label="说句话", command=self._say_random)
        self.menu.add_command(label="修改名称", command=self._rename_pet)
        self.menu.add_command(label="重新抽宠物", command=self._redraw_pet)
        self.menu.add_command(label="宠物图鉴", command=self._open_pet_catalog)
        self.menu.add_command(label="关闭宠物", command=self.destroy)

    def _start_pomodoro(self):
        if self.on_start_pomodoro:
            self.after(10, self.on_start_pomodoro)

    def _cancel_pomodoro(self):
        if self.on_cancel_pomodoro:
            self.after(10, self.on_cancel_pomodoro)

    def _show_pomodoro_status(self):
        status = self.pomodoro_status() if self.pomodoro_status else {"label": "番茄时钟未开始"}
        self.show_message(status.get("label") or "番茄时钟未开始", force=True)

    def _show_progress(self):
        if self.on_show_progress:
            self.after(10, self.on_show_progress)
        elif self.progress_summary:
            self.show_message(self.progress_summary())

    def _record_health(self, key):
        if self.on_record_health:
            self.after(10, lambda: self.on_record_health(key))

    def _start_eye_training(self):
        if self.on_start_eye_training:
            self.after(10, self.on_start_eye_training)

    def _toggle_pause(self):
        if self.on_toggle_pause:
            self.after(10, self.on_toggle_pause)

    def _show_menu(self, event):
        try:
            self._refresh_menu()
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self.menu.grab_release()
            except tk.TclError:
                pass

    def _say_random(self):
        self._click_after_id = None
        if self._is_pomodoro_active():
            self._show_pomodoro_status()
            return
        self._active_state = None
        if self._sprite_frames:
            self._pose = random.randrange(len(self._sprite_frames))
        else:
            self._pose = (self._pose + 1) % 3
        self._draw_pet()
        self.show_message(self.pet["messages"][self._message_index % len(self.pet["messages"])])
        self._message_index += 1

    def _reset_pet_pose(self):
        self._animation_after_id = None
        self._active_state = None
        self._pose = 0
        self._draw_pet()

    def show_state(self, state_name, duration_ms=None, fallback_state=None):
        if self._is_pomodoro_active():
            self._show_pomodoro_status()
            return
        if not is_pet_state_unlocked(state_name, self.pet_life_days):
            self._say_random()
            return
        if state_name not in self._state_frames:
            if fallback_state in self._state_frames and is_pet_state_unlocked(fallback_state, self.pet_life_days):
                state_name = fallback_state
            elif "happy" in self._state_frames and is_pet_state_unlocked("happy", self.pet_life_days):
                state_name = "happy"
            else:
                self._say_random()
                return
        if self._animation_after_id:
            try:
                self.after_cancel(self._animation_after_id)
            except tk.TclError:
                pass
        self._active_state = state_name
        self._draw_pet()
        if duration_ms:
            self._animation_after_id = self.after(duration_ms, self._reset_pet_pose)

    def _redraw_pet(self):
        if self.on_redraw:
            self.after(10, lambda: self.on_redraw(self))

    def _rename_pet(self):
        if self.on_rename:
            self.on_rename(self)

    def update_pet_name(self, pet_display_name):
        self.pet_display_name = normalize_desktop_pet_name(pet_display_name, self.pet["name"])
        self.name_label.configure(text=format_pet_status_label(self.pet_display_name, self.pet_life_days, self.pet_mood))
        self.show_message("以后就叫我{}吧。".format(self.pet_display_name))

    def update_pet(self, pet, pet_display_name=None, pet_life_days=1, pet_mood=PET_MOOD_DEFAULT):
        self.pet = pet
        self._message_index = 0
        self._pose = 0
        self.pet_display_name = normalize_desktop_pet_name(pet_display_name, pet["name"])
        self.pet_life_days = max(1, int(pet_life_days or 1))
        self.pet_mood = clamp_pet_mood(pet_mood)
        self.name_label.configure(text=format_pet_status_label(self.pet_display_name, self.pet_life_days, self.pet_mood), fg=pet["color"])
        self._load_pet_images()
        self._draw_pet()
        self.show_message("重新抽到了{}，我是{}。".format(pet["name"], self.pet_display_name))

    def update_pet_mood_display(self, pet_mood):
        self.pet_mood = clamp_pet_mood(pet_mood)
        self.name_label.configure(text=format_pet_status_label(self.pet_display_name, self.pet_life_days, self.pet_mood))

    def _is_pomodoro_active(self):
        try:
            status = self.pomodoro_status() if self.pomodoro_status else {"active": False}
            return bool(status.get("active"))
        except Exception:
            return False

    def show_message(self, text, force=False):
        if self._is_pomodoro_active() and not force:
            status = self.pomodoro_status() if self.pomodoro_status else {}
            text = status.get("label") or "番茄专注中"
        self.bubble_label.configure(text=self._fit_bubble_text(text))

    def _fit_bubble_text(self, text):
        text = str(text or "").replace("\r", " ").strip()
        parts = [part.strip() for part in text.replace("。", "。\n").splitlines() if part.strip()]
        if not parts:
            return ""
        fitted = []
        for part in parts[:2]:
            if len(part) > 24:
                part = part[:23] + "…"
            fitted.append(part)
        return "\n".join(fitted)

    def _cycle_message(self):
        try:
            if not self.winfo_exists():
                return
            if self._is_pomodoro_active():
                self._show_pomodoro_status()
            else:
                self._say_random()
            self.after(5 * 60 * 1000, self._cycle_message)
        except tk.TclError:
            return


class HealthMainPage:
    def __init__(self, root, nickname, reminders, topmost=True, autostart=False, theme=DEFAULT_THEME, sleep_cfg=None, challenge_cfg=None):
        self.root = root
        self.root.title("健康助手")
        self.nickname = nickname
        self.reminders = reminders
        self.today = date.today().isoformat()
        self.data = self.load_data()
        self.timers = {}
        self.closing = False
        self.topmost = topmost
        self.autostart = autostart
        self.current_theme = theme
        self.challenge_cfg = normalize_challenge_config(challenge_cfg)
        self.desktop_pet_autostart = get_desktop_pet_autostart()
        self.theme_colors = get_theme_colors(theme)
        # 兼容sleep_cfg
        if sleep_cfg and "sleep_periods" in sleep_cfg:
            self.sleep_periods = [dict(p) for p in sleep_cfg["sleep_periods"]]
        else:
            self.sleep_periods = [{"start": "23:00", "end": "07:00"}]
        # 新增：合并弹窗相关变量
        self.pending_reminders = []  # 待弹提醒项
        self.reminder_popup_scheduled = False  # 是否已安排弹窗
        self.active_health_reminders = []
        self.eye_record_server = EyeRecordHttpServer()
        self.eye_record_url = self.eye_record_server.start()
        self.desktop_pet_window = None
        self.pet_pomodoro_after_id = None
        self.pet_pomodoro_end_time = None
        self.pet_pomodoro_started_at = None
        # 初始化好友网络管理器
        self.network_manager = FriendNetworkManager(
            nickname,
            self.on_friend_reminder,
            self.sleep_periods,
            is_in_any_sleep_period,
        )
        self.network_manager.start()
        self.root.bind("<Map>", self._on_root_map)
        self.root.bind("<Unmap>", self._on_root_unmap, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
        
        self.dashboard_colors = get_dashboard_colors(self.theme_colors)
        self.main_frame = tk.Frame(root, bg=self.dashboard_colors["app_bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.user_id = load_user_id()
        self.status_labels = {}
        self.buttons = {}
        self.health_cards = {}
        self.health_card_surfaces = {}
        self.card_name_labels = {}
        self.card_target_labels = {}
        self.eye_training_button = None
        self.pause_status_label = None
        self.pause_reminder_button = None
        self.pause_status_after_id = None
        self.dashboard_canvas = tk.Canvas(
            self.main_frame, bg=self.dashboard_colors["app_bg"],
            bd=0, highlightthickness=0,
        )
        self.dashboard_scrollbar = tk.Scrollbar(
            self.main_frame, orient=tk.VERTICAL,
            command=self.dashboard_canvas.yview,
        )
        self.dashboard_canvas.configure(yscrollcommand=self.dashboard_scrollbar.set)
        self.dashboard_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.dashboard_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.dashboard_shell = tk.Frame(self.dashboard_canvas, bg=self.dashboard_colors["app_bg"])
        self.dashboard_window = self.dashboard_canvas.create_window(
            22, 14, anchor="nw", window=self.dashboard_shell,
        )
        self.dashboard_shell.bind("<Configure>", self._update_dashboard_scrollregion)
        self.dashboard_canvas.bind("<Configure>", self._resize_dashboard_viewport)
        self.dashboard_shell.grid_columnconfigure(0, weight=1)
        self.dashboard_shell.grid_rowconfigure(3, weight=1)
        self.create_header_section(self.dashboard_shell)
        self.create_user_meta_section(self.dashboard_shell)
        self.create_progress_summary(self.dashboard_shell)
        self.create_health_cards(self.dashboard_shell)
        self.create_footer_actions(self.dashboard_shell)
        self.update_dashboard_state()
        self.update_pause_reminder_state(schedule_next=True)
        
        self.apply_topmost()
        self._show_main_window_on_start()
        self.start_all_reminders()
        self.check_eye_autorecord()  # 启动护眼自动打卡同步
        if self.desktop_pet_autostart:
            self.root.after(900, self.open_desktop_pet)

    def _update_dashboard_scrollregion(self, event=None):
        self.dashboard_canvas.configure(scrollregion=self.dashboard_canvas.bbox("all"))

    def _resize_dashboard_viewport(self, event):
        # Keep one responsive content column; only vertical overflow scrolls.
        viewport_width = max(1, event.width - 44)
        self.dashboard_canvas.itemconfigure(self.dashboard_window, width=viewport_width)
        self._update_dashboard_scrollregion()

    def create_header_section(self, parent):
        colors = self.dashboard_colors
        header = tk.Frame(parent, bg=colors["surface"], padx=16, pady=10, highlightbackground=colors["border"], highlightthickness=1)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        self.title_label = tk.Label(header, text="健康助手", font=("微软雅黑", 20, "bold"), bg=colors["surface"], fg=colors["text_primary"])
        self.title_label.grid(row=0, column=0, sticky="w")
        self.greeting_label = tk.Label(header, text="轻松记录，照顾好今天的自己", font=("微软雅黑", 10), bg=colors["surface"], fg=colors["text_secondary"])
        self.greeting_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.nav_frame = tk.Frame(header, bg=colors["surface"])
        self.nav_frame.grid(row=0, column=1, rowspan=2, sticky="e")
        nav_options = dict(font=("微软雅黑", 10, "bold"), bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"], relief=tk.FLAT, bd=0, padx=10, pady=6)
        self.ai_button = tk.Button(self.nav_frame, text="AI 助手", command=self.open_ai_assistant, **nav_options)
        self.friends_button = tk.Button(self.nav_frame, text="好友", command=self.open_friends, **nav_options)
        self.settings_button = tk.Button(self.nav_frame, text="设置", command=self.open_settings, **nav_options)
        for column, button in enumerate((self.ai_button, self.friends_button, self.settings_button)):
            button.grid(row=0, column=column, padx=(8 if column else 0, 0))

    def create_user_meta_section(self, parent):
        colors = self.dashboard_colors
        section = tk.Frame(parent, bg=colors["app_bg"])
        section.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        section.grid_columnconfigure(2, weight=1)
        self.nick_label = tk.Label(section, text="{}，{}".format(self.nickname, get_day_greeting(datetime.now().hour)), font=("微软雅黑", 13, "bold"), bg=colors["app_bg"], fg=colors["text_primary"])
        self.date_label = tk.Label(section, text="日期：{}".format(self.today), font=("微软雅黑", 11), bg=colors["app_bg"], fg=colors["text_secondary"])
        self.id_label = tk.Label(section, text="用户 ID：{}".format(self.user_id), font=("微软雅黑", 11), bg=colors["app_bg"], fg=colors["text_secondary"])
        self.copy_button = tk.Button(section, text="复制 ID", font=("微软雅黑", 9), bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"], relief=tk.FLAT, bd=0, padx=10, pady=6, command=self.copy_user_id)
        self.nick_label.grid(row=0, column=0, sticky="w")
        self.date_label.grid(row=0, column=1, sticky="w", padx=(18, 0))
        self.id_label.grid(row=0, column=2, sticky="w", padx=(18, 8))
        self.copy_button.grid(row=0, column=3, sticky="e")

    def create_progress_summary(self, parent):
        colors = self.dashboard_colors
        self.progress_frame = tk.Frame(parent, bg=colors["surface_alt"], highlightbackground=colors["border"], highlightthickness=1)
        self.progress_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        text_frame = tk.Frame(self.progress_frame, bg=colors["surface_alt"])
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=14, pady=8)
        self.progress_title_label = tk.Label(text_frame, text="今日进度", font=("微软雅黑", 14, "bold"), bg=colors["surface_alt"], fg=colors["text_primary"])
        self.progress_detail_label = tk.Label(text_frame, text="已完成 0 / 4 项", font=("微软雅黑", 11), bg=colors["surface_alt"], fg=colors["text_secondary"])
        self.progress_hint_label = tk.Label(text_frame, text="每一步都值得记录", font=("微软雅黑", 9), bg=colors["surface_alt"], fg=colors["text_secondary"])
        self.progress_title_label.pack(anchor="w")
        self.progress_detail_label.pack(anchor="w", pady=(2, 0))
        self.progress_hint_label.pack(anchor="w", pady=(1, 0))
        self.progress_canvas = tk.Canvas(self.progress_frame, width=68, height=68, bg=colors["surface_alt"], bd=0, highlightthickness=0)
        self.progress_canvas.pack(side=tk.RIGHT, padx=12, pady=4)
        self.progress_canvas.create_arc(8, 8, 60, 60, start=0, extent=359, style=tk.ARC, width=6, outline=colors["border"])

    def create_health_cards(self, parent):
        colors = self.dashboard_colors
        self.health_grid = tk.Frame(parent, bg=colors["app_bg"])
        self.health_grid.grid(row=3, column=0, sticky="nsew")
        for index in range(2):
            self.health_grid.grid_columnconfigure(index, weight=1, uniform="health")
            self.health_grid.grid_rowconfigure(index, weight=1, uniform="health")
        reminder_lookup = {item["key"]: item for item in self.reminders}
        target_counts = {"drink": 8, "stand": 6, "eye": 4, "sport": 2}
        today_data = self.data.get(self.today, {})
        if not isinstance(today_data, dict):
            today_data = {}
        for index, key in enumerate(("drink", "stand", "eye", "sport")):
            reminder = reminder_lookup.get(key)
            if reminder is None:
                continue
            outer = tk.Frame(self.health_grid, bg=colors["border"])
            outer.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0 if index % 2 == 0 else 6, 6 if index % 2 == 0 else 0), pady=(0 if index < 2 else 6, 6 if index < 2 else 0))
            inner = tk.Frame(outer, bg=colors["surface"], padx=12, pady=9, height=116)
            inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
            inner.grid_columnconfigure(0, weight=1)
            inner.grid_columnconfigure(1, weight=0)
            name_label = tk.Label(inner, text=reminder["name"], font=("微软雅黑", 15, "bold"), bg=colors["surface"], fg=colors["text_primary"])
            target_label = tk.Label(inner, text="目标 {} 次".format(target_counts[key]), font=("微软雅黑", 10), bg=colors["surface"], fg=colors["text_secondary"])
            count_label = tk.Label(inner, text="{} 次".format(len(today_data.get(key, []))), font=("微软雅黑", 22, "bold"), bg=colors["surface"], fg=colors["text_primary"])
            name_label.grid(row=0, column=0, sticky="w")
            target_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
            count_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))
            is_primary = key == "drink"
            action_row = tk.Frame(inner, bg=colors["surface"])
            action_button = tk.Button(action_row, text="记录{}".format(reminder["name"]), font=("微软雅黑", 10, "bold"), bg=colors["primary"] if is_primary else colors["surface_alt"], fg=colors["on_primary"] if is_primary else colors["secondary_action_text"], activebackground=colors["primary_active"], relief=tk.FLAT, bd=0, pady=6, command=lambda current_key=key: self.record_action(current_key))
            action_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
            if key == "eye":
                eye_training_button = tk.Button(action_row, text="开始护眼", font=("微软雅黑", 10, "bold"), bg=colors["primary"], fg=colors["on_primary"], activebackground=colors["primary_active"], relief=tk.FLAT, bd=0, pady=6, command=self.open_eye_training)
                eye_training_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
                self.eye_training_button = eye_training_button
            action_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
            self.health_cards[key] = outer
            self.health_card_surfaces[key] = inner
            self.card_name_labels[key] = name_label
            self.card_target_labels[key] = target_label
            self.status_labels[key] = count_label
            self.buttons[key] = action_button

    def create_footer_actions(self, parent):
        colors = self.dashboard_colors
        footer = tk.Frame(parent, bg=colors["surface"], padx=12, pady=8, highlightbackground=colors["border"], highlightthickness=1)
        footer.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        for column in range(5):
            footer.grid_columnconfigure(column, weight=1, uniform="footer")
        self.pause_status_label = tk.Label(footer, text="提醒正常", font=("微软雅黑", 10), bg=colors["surface"], fg=colors["text_secondary"])
        self.pause_reminder_button = tk.Button(footer, text="设置免打扰", font=("微软雅黑", 10), bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"], padx=10, pady=6, bd=0, relief=tk.FLAT, command=self.toggle_reminder_pause)
        self.pet_button = tk.Button(footer, text="召唤宠物", font=("微软雅黑", 10), bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"], padx=10, pady=6, bd=0, relief=tk.FLAT, command=self.open_desktop_pet)
        self.restart_button = tk.Button(footer, text="重启程序", font=("微软雅黑", 10), bg=colors["danger_muted"], fg=colors["danger_text"], activebackground=colors["danger_muted"], padx=10, pady=6, bd=0, relief=tk.FLAT, command=self.restart_reminders)
        self.quit_button = tk.Button(footer, text="退出", font=("微软雅黑", 10), bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"], padx=10, pady=6, bd=0, relief=tk.FLAT, command=self.quit_app)
        self.pause_status_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.pause_reminder_button.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.pet_button.grid(row=0, column=2, sticky="ew", padx=6)
        self.restart_button.grid(row=0, column=3, sticky="ew", padx=6)
        self.quit_button.grid(row=0, column=4, sticky="ew", padx=(6, 0))

    def open_desktop_pet(self):
        try:
            if self.desktop_pet_window is not None and self.desktop_pet_window.winfo_exists():
                self.desktop_pet_window.lift()
                return
        except tk.TclError:
            pass
        config = load_user_config()
        pet_id = config.get("desktop_pet_id")
        if not pet_id:
            pet_id = choose_desktop_pet_id()
            save_user_config_fields(desktop_pet_id=pet_id)
        mark_desktop_pet_unlocked(pet_id, config)
        pet = get_desktop_pet(pet_id)
        pet_life_days, pet_life_changed = touch_pet_life(config, pet["id"], self.today)
        pet_life_message = get_pet_life_milestone_message(pet_life_days, pet_life_changed)
        pet_mood, pet_mood_recovered = recover_pet_mood_once_per_day(pet["id"], config, self.today)
        pet_display_name = normalize_desktop_pet_name(config.get("desktop_pet_name"), pet["name"])
        if not config.get("desktop_pet_named"):
            pet_display_name = self.ask_desktop_pet_name(pet, pet_display_name)
            save_user_config_fields(desktop_pet_named=True)
        self.desktop_pet_window = DesktopPetWindow(
            self.root,
            self.nickname,
            self.dashboard_colors,
            pet,
            pet_display_name=pet_display_name,
            on_redraw=self.redraw_desktop_pet,
            on_rename=self.rename_desktop_pet,
            on_open_catalog=self.open_desktop_pet_catalog,
            progress_summary=self.get_desktop_pet_progress_summary,
            pet_life_days=pet_life_days,
            pet_mood=pet_mood,
            on_start_pomodoro=self.start_pet_pomodoro,
            on_cancel_pomodoro=self.cancel_pet_pomodoro,
            pomodoro_status=self.get_pet_pomodoro_status,
            on_show_progress=self.show_pet_today_progress,
            on_record_health=self.pet_record_health,
            on_start_eye_training=self.pet_start_eye_training,
            on_toggle_pause=self.pet_toggle_reminder_pause,
        )
        if pet_life_message:
            self.desktop_pet_window.show_message(pet_life_message)
        elif pet_mood_recovered:
            self.desktop_pet_window.show_message("今天见到你，心情恢复了一点。")
        else:
            low_mood_message = get_low_pet_mood_message(pet_mood)
            if low_mood_message:
                self.desktop_pet_window.show_message(low_mood_message)

    def open_desktop_pet_catalog(self, parent=None):
        config = load_user_config()
        pet_lives = load_pet_lives(config)
        unlocked_pet_ids = load_unlocked_pet_ids(config)
        colors = self.dashboard_colors
        pet_catalog_images = []
        catalog = tk.Toplevel(parent or self.root)
        catalog.title("宠物图鉴")
        catalog.configure(bg="#edf7f2")
        catalog.geometry("720x560")
        catalog.minsize(620, 460)
        catalog.resizable(True, True)
        try:
            catalog.transient(parent or self.root)
            catalog.lift()
        except tk.TclError:
            pass

        header = tk.Frame(catalog, bg="#2f8f7b", padx=20, pady=16)
        header.pack(fill=tk.X)
        title_row = tk.Frame(header, bg="#2f8f7b")
        title_row.pack(fill=tk.X)
        tk.Label(
            title_row, text="PET DEX", font=("微软雅黑", 10, "bold"),
            bg="#173c36", fg="#ffffff", padx=10, pady=4,
        ).pack(side=tk.LEFT)
        tk.Label(
            title_row, text="已解锁 {} / {} 只宠物".format(len(unlocked_pet_ids), len(DESKTOP_PETS)),
            font=("微软雅黑", 10), bg="#2f8f7b", fg="#eafff8",
        ).pack(side=tk.RIGHT)
        tk.Label(
            header, text="宠物图鉴", font=("微软雅黑", 24, "bold"),
            bg="#2f8f7b", fg="#ffffff",
        ).pack(anchor="w", pady=(10, 0))
        tk.Label(
            header, text="查看陪伴天数、心情、已解锁表情和下一阶段。",
            font=("微软雅黑", 11), bg="#2f8f7b", fg="#dff8ef",
        ).pack(anchor="w", pady=(4, 0))

        shell = tk.Frame(catalog, bg="#edf7f2", padx=16, pady=16)
        shell.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(shell, bg="#edf7f2", bd=0, highlightthickness=0)
        scrollbar = tk.Scrollbar(shell, orient=tk.VERTICAL, command=canvas.yview)
        list_frame = tk.Frame(canvas, bg="#edf7f2")
        canvas_window = canvas.create_window((0, 0), window=list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_scrollregion(event=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except tk.TclError:
                pass

        def resize_list_width(event):
            try:
                canvas.itemconfigure(canvas_window, width=event.width)
            except tk.TclError:
                pass

        def on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass

        list_frame.bind("<Configure>", refresh_scrollregion)
        canvas.bind("<Configure>", resize_list_width)
        catalog.bind("<MouseWheel>", on_mousewheel)

        current_pet_id = config.get("desktop_pet_id")
        ordered_pets = sorted(
            DESKTOP_PETS,
            key=lambda pet: 0 if pet.get("id") == current_pet_id else 1,
        )
        for index, pet in enumerate(ordered_pets, start=1):
            is_current_pet = pet.get("id") == current_pet_id
            is_unlocked = pet.get("id") in unlocked_pet_ids
            life_record = pet_lives.get(pet["id"], {})
            if not isinstance(life_record, dict):
                life_record = {}
            try:
                life_days = max(0, int(life_record.get("life_days", 0) or 0))
            except (TypeError, ValueError):
                life_days = 0
            if not is_unlocked:
                life_days = 0
            mood = get_pet_mood(config, pet["id"]) if is_unlocked else 0
            card_border = tk.Frame(list_frame, bg="#2f8f7b" if is_current_pet else "#d7e1f2")
            card_border.pack(fill=tk.X, pady=(0, 12))
            row = tk.Frame(card_border, bg="#ffffff", padx=14, pady=12)
            row.pack(fill=tk.X, padx=1, pady=1)
            row.grid_columnconfigure(2, weight=1)
            number_badge = tk.Label(
                row, text="#{:03d}".format(index), font=("Consolas", 12, "bold"),
                bg="#173c36", fg="#ffffff", padx=10, pady=6,
            )
            number_badge.grid(row=0, column=0, sticky="n", padx=(0, 12), rowspan=3)
            image_cell = tk.Frame(row, bg="#f3fbf7", width=78, height=78)
            image_cell.grid(row=0, column=1, sticky="n", padx=(0, 12), rowspan=4)
            image_cell.grid_propagate(False)
            image_cell.pack_propagate(False)
            pet_image_label = tk.Label(image_cell, bg="#f3fbf7")
            pet_image_label.pack(fill=tk.BOTH, expand=True)
            pet_preview = None
            if is_unlocked and Image is not None and ImageTk is not None:
                idle_path = resource_path(os.path.join("assets", "desktop_pets", pet["id"], "idle_0.png"))
                try:
                    if os.path.exists(idle_path):
                        preview_image = Image.open(idle_path).convert("RGBA")
                        preview_image.thumbnail((72, 72), Image.LANCZOS)
                        pet_preview = ImageTk.PhotoImage(preview_image)
                        pet_catalog_images.append(pet_preview)
                        pet_image_label.configure(image=pet_preview)
                except Exception as e:
                    log("加载宠物图鉴图片异常：{}".format(e))
            if pet_preview is None:
                pet_image_label.destroy()
                fallback_chip = tk.Canvas(image_cell, width=72, height=72, bg="#f3fbf7", bd=0, highlightthickness=0)
                fallback_chip.pack(fill=tk.BOTH, expand=True)
                if is_unlocked:
                    fallback_chip.create_oval(8, 8, 64, 64, fill=pet.get("color", colors["primary"]), outline="#173c36", width=2)
                    fallback_chip.create_oval(25, 25, 47, 47, fill=pet.get("belly", "#ffffff"), outline="")
                else:
                    fallback_chip.create_oval(8, 8, 64, 64, fill="#edf1f5", outline="#c3ccd6", width=2)
                    fallback_chip.create_text(36, 36, text="?", font=("微软雅黑", 26, "bold"), fill="#8b98a8")
            title_line = tk.Frame(row, bg="#ffffff")
            title_line.grid(row=0, column=2, sticky="ew")
            tk.Label(
                title_line, text=pet["name"] if is_unlocked else "？？？", font=("微软雅黑", 15, "bold"),
                bg="#ffffff", fg="#102033" if is_unlocked else "#7b8794",
            ).pack(side=tk.LEFT)
            if is_current_pet:
                tk.Label(
                    title_line, text="当前陪伴中", font=("微软雅黑", 10, "bold"),
                    bg="#2f8f7b", fg="#ffffff",
                    padx=10, pady=3,
                ).pack(side=tk.LEFT, padx=(10, 0))
            if is_unlocked:
                tk.Label(
                    title_line, text=describe_pet_mood(mood), font=("微软雅黑", 10, "bold"),
                    bg="#e8f7ef" if mood >= 50 else "#fff1e8",
                    fg="#137a4b" if mood >= 50 else "#b45309",
                    padx=10, pady=3,
                ).pack(side=tk.LEFT, padx=(10, 0))
            else:
                tk.Label(
                    title_line, text="未解锁", font=("微软雅黑", 10, "bold"),
                    bg="#eef2f6", fg="#7b8794",
                    padx=10, pady=3,
                ).pack(side=tk.LEFT, padx=(10, 0))
            tk.Label(
                row, text="生命 {} 天".format(life_days),
                font=("微软雅黑", 11), bg="#ffffff", fg="#536172",
            ).grid(row=1, column=2, sticky="w", pady=(5, 0))
            mood_bar = tk.Canvas(row, width=180, height=10, bg="#edf1f5", bd=0, highlightthickness=0)
            mood_bar.grid(row=1, column=2, sticky="e", padx=(0, 4), pady=(5, 0))
            mood_width = int(180 * clamp_pet_mood(mood) / 100) if is_unlocked else 0
            mood_bar.create_rectangle(0, 0, 180, 10, fill="#edf1f5", outline="")
            mood_bar.create_rectangle(0, 0, mood_width, 10, fill=get_pet_mood_bar_color(mood), outline="")
            tk.Label(
                row, text="已解锁：{}".format(format_pet_catalog_unlocked_states(life_days) if is_unlocked else "未解锁"),
                font=("微软雅黑", 10), bg="#ffffff", fg="#102033",
                wraplength=520, justify=tk.LEFT,
            ).grid(row=2, column=2, sticky="w", pady=(6, 0))
            tk.Label(
                row, text="下一阶段：{}".format(format_pet_catalog_next_stage(life_days) if is_unlocked else "抽到后开始陪伴"),
                font=("微软雅黑", 10), bg="#ffffff", fg="#536172",
                wraplength=520, justify=tk.LEFT,
            ).grid(row=3, column=2, sticky="w", pady=(3, 0))
            action_line = tk.Frame(row, bg="#ffffff")
            action_line.grid(row=4, column=2, sticky="ew", pady=(8, 0))
            if is_unlocked and not is_current_pet:
                tk.Button(
                    action_line, text="切换为当前宠物", font=("微软雅黑", 10, "bold"),
                    bg="#2f8f7b", fg="#ffffff", activebackground="#247363",
                    relief=tk.FLAT, bd=0, padx=12, pady=6,
                    command=lambda pet_id=pet["id"], win=catalog: self.switch_desktop_pet_from_catalog(pet_id, win),
                ).pack(side=tk.LEFT)
            elif not is_unlocked:
                tk.Label(
                    action_line, text="重新抽卡有机会获得", font=("微软雅黑", 10),
                    bg="#ffffff", fg="#7b8794",
                ).pack(side=tk.LEFT)
        try:
            catalog.pet_catalog_images = pet_catalog_images
            catalog.update_idletasks()
        except tk.TclError:
            pass

    def switch_desktop_pet_from_catalog(self, pet_id, catalog=None):
        pet = get_desktop_pet(pet_id)
        pet_display_name = pet["name"]
        save_user_config_fields(desktop_pet_id=pet_id, desktop_pet_name=pet_display_name, desktop_pet_named=True)
        config = load_user_config()
        mark_desktop_pet_unlocked(pet_id, config)
        pet_life_days, pet_life_changed = touch_pet_life(config, pet_id, self.today)
        pet_life_message = get_pet_life_milestone_message(pet_life_days, pet_life_changed)
        pet_mood = get_pet_mood(config, pet_id)
        try:
            if self.desktop_pet_window is not None and self.desktop_pet_window.winfo_exists():
                self.desktop_pet_window.update_pet(
                    pet, pet_display_name,
                    pet_life_days=pet_life_days,
                    pet_mood=pet_mood,
                )
                if pet_life_message:
                    self.desktop_pet_window.show_message(pet_life_message)
        except tk.TclError:
            pass
        try:
            if catalog is not None and catalog.winfo_exists():
                catalog.destroy()
        except tk.TclError:
            pass
        self.open_desktop_pet_catalog()

    def ask_desktop_pet_name(self, pet, current_name=None, parent=None):
        default_name = normalize_desktop_pet_name(current_name, pet["name"])
        dialog_parent = parent or self.root
        try:
            name = simpledialog.askstring(
                "给宠物取名",
                "你抽到了{}，给它取个名字吧（1-8个字）：".format(pet["name"]),
                initialvalue=default_name,
                parent=dialog_parent,
            )
        except tk.TclError:
            name = None
        pet_display_name = normalize_desktop_pet_name(name, default_name)
        save_user_config_fields(desktop_pet_name=pet_display_name, desktop_pet_named=True)
        return pet_display_name

    def rename_desktop_pet(self, pet_window=None):
        target = pet_window or self.desktop_pet_window
        if target is None:
            return
        pet_display_name = self.ask_desktop_pet_name(target.pet, target.pet_display_name, parent=target)
        try:
            if target.winfo_exists():
                target.update_pet_name(pet_display_name)
        except tk.TclError:
            pass

    def redraw_desktop_pet(self, pet_window=None):
        pet_id = choose_desktop_pet_id()
        pet = get_desktop_pet(pet_id)
        target = pet_window or self.desktop_pet_window
        pet_display_name = self.ask_desktop_pet_name(pet, pet["name"], parent=target)
        save_user_config_fields(desktop_pet_id=pet_id, desktop_pet_name=pet_display_name, desktop_pet_named=True)
        config = load_user_config()
        mark_desktop_pet_unlocked(pet_id, config)
        pet_life_days, pet_life_changed = touch_pet_life(config, pet_id, self.today)
        pet_life_message = get_pet_life_milestone_message(pet_life_days, pet_life_changed)
        pet_mood = get_pet_mood(config, pet_id)
        try:
            if target is not None and target.winfo_exists():
                target.update_pet(pet, pet_display_name, pet_life_days=pet_life_days, pet_mood=pet_mood)
                if pet_life_message:
                    target.show_message(pet_life_message)
        except tk.TclError:
            pass

    def get_desktop_pet_progress_summary(self):
        today_data = self.data.get(self.today, {})
        if not isinstance(today_data, dict):
            today_data = {}
        return "今日进度：喝水{} 站立{}\n护眼{} 运动{}".format(
            len(today_data.get("drink", [])),
            len(today_data.get("stand", [])),
            len(today_data.get("eye", [])),
            len(today_data.get("sport", [])),
        )

    def show_desktop_pet_state(self, state_name, message=None, fallback_state=None, duration_ms=None):
        target = self.desktop_pet_window
        try:
            if target is None or not target.winfo_exists():
                return
            target.show_state(state_name, duration_ms=duration_ms, fallback_state=fallback_state)
            if message:
                target.show_message(message)
        except tk.TclError:
            pass

    def show_desktop_pet_reminder_state(self, reminders):
        reminders = list(reminders or [])
        if not reminders:
            return
        if self.is_pet_pomodoro_active():
            self.update_pet_pomodoro_countdown()
            return
        self.adjust_current_pet_mood(-3)
        key = reminders[0].get("key", "unhappy")
        name = reminders[0].get("name", "健康提醒")
        self.show_desktop_pet_state(
            key,
            message="{}时间到了，我在旁边提醒你。".format(name),
            fallback_state="unhappy",
        )

    def adjust_current_pet_mood(self, delta):
        config = load_user_config()
        pet_id = config.get("desktop_pet_id")
        if not pet_id:
            return PET_MOOD_DEFAULT
        mood = update_pet_mood(pet_id, delta, config)
        target = self.desktop_pet_window
        try:
            if target is not None and target.winfo_exists() and target.pet.get("id") == pet_id:
                target.update_pet_mood_display(mood)
        except tk.TclError:
            pass
        return mood

    def get_status_text(self, key):
        today_data = self.data.get(self.today, {})
        if not isinstance(today_data, dict):
            today_data = {}
        count = len(today_data.get(key, []))
        name = next((r["name"] for r in self.reminders if r["key"] == key), key)
        return f"今天已{name}：{count} 次"
    def record_action(self, key, auto=False):
        now = datetime.now().strftime("%H:%M:%S")
        self.data.setdefault(self.today, {}).setdefault(key, []).append(now)
        self.save_data()
        self.update_dashboard_state()
        mood = self.adjust_current_pet_mood(8)
        self.show_desktop_pet_state(
            key,
            message="{}记录完成，{}。".format(
                next((r["name"] for r in self.reminders if r["key"] == key), "健康"),
                get_pet_mood_feedback(mood),
            ),
            fallback_state="happy",
        )
        if not auto:
            name = next((r["name"] for r in self.reminders if r["key"] == key), key)
            tip = get_random_health_tip(key)
            messagebox.showinfo("记录成功", f"{self.nickname or '朋友'}，{name}记录成功！\n\n健康小知识：{tip}")
        self.schedule_reminder(key)

    def update_dashboard_state(self):
        today_data = self.data.get(self.today, {})
        if not isinstance(today_data, dict):
            today_data = {}
        keys = ["drink", "stand", "eye", "sport"]
        completed = count_completed_items(today_data, keys)
        if completed >= len(keys):
            self.reward_daily_completion_if_needed()
        for key in keys:
            label = self.status_labels.get(key)
            if label is not None:
                label.configure(text="{} 次".format(len(today_data.get(key, []))))
        self.progress_detail_label.configure(text="已完成 {} / 4 项".format(completed))
        self.draw_progress_ring(completed, 4)

    def reward_daily_completion_if_needed(self):
        mood, rewarded = reward_current_pet_for_daily_completion(today=self.today)
        if not rewarded:
            return
        target = self.desktop_pet_window
        try:
            if target is not None and target.winfo_exists():
                target.update_pet_mood_display(mood)
                target.show_message("今天四项都完成了，心情增加了。")
        except tk.TclError:
            pass

    def start_pet_pomodoro(self, minutes=25):
        if self.pet_pomodoro_after_id:
            self.cancel_pet_pomodoro(show_message=False)
        if self.pending_reminders:
            self._finish_reminder_batch(list(self.pending_reminders))
            self.pending_reminders.clear()
        self.reminder_popup_scheduled = False
        self.pet_pomodoro_started_at = datetime.now()
        self.pet_pomodoro_end_time = self.pet_pomodoro_started_at + timedelta(seconds=POMODORO_FOCUS_SECONDS)
        self.update_pet_pomodoro_countdown()

    def is_pet_pomodoro_active(self):
        if not self.pet_pomodoro_end_time:
            return False
        return datetime.now() < self.pet_pomodoro_end_time

    def suppress_health_reminder_during_pomodoro(self, reminders):
        if not self.is_pet_pomodoro_active():
            return False
        self._finish_reminder_batch(reminders)
        self.update_pet_pomodoro_countdown()
        return True

    def update_pet_pomodoro_countdown(self):
        if not self.pet_pomodoro_end_time:
            return
        remaining_seconds = int((self.pet_pomodoro_end_time - datetime.now()).total_seconds())
        if remaining_seconds <= 0:
            self.finish_pet_pomodoro()
            return
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60
        target = self.desktop_pet_window
        try:
            if target is not None and target.winfo_exists():
                target.show_message("番茄专注 {:02d}:{:02d}".format(minutes, seconds), force=True)
        except tk.TclError:
            pass
        self.pet_pomodoro_after_id = self.root.after(1000, self.update_pet_pomodoro_countdown)

    def cancel_pet_pomodoro(self, show_message=True):
        if self.pet_pomodoro_after_id:
            try:
                self.root.after_cancel(self.pet_pomodoro_after_id)
            except tk.TclError:
                pass
        self.pet_pomodoro_after_id = None
        self.pet_pomodoro_end_time = None
        self.pet_pomodoro_started_at = None
        if show_message:
            self.show_desktop_pet_state("idle", message="番茄时钟已结束。")

    def get_pet_pomodoro_status(self):
        if not self.pet_pomodoro_end_time:
            return {"active": False, "label": "番茄时钟未开始"}
        remaining_seconds = int((self.pet_pomodoro_end_time - datetime.now()).total_seconds())
        if remaining_seconds <= 0:
            return {"active": True, "label": "番茄专注 00:00"}
        minutes = remaining_seconds // 60
        seconds = remaining_seconds % 60
        return {"active": True, "label": "番茄专注 {:02d}:{:02d}".format(minutes, seconds)}

    def finish_pet_pomodoro(self):
        self.pet_pomodoro_after_id = None
        self.pet_pomodoro_end_time = None
        self.pet_pomodoro_started_at = None
        mood = self.adjust_current_pet_mood(5)
        message = "番茄完成，休息 5 分钟吧。{}。".format(get_pet_mood_feedback(mood))
        target = self.desktop_pet_window
        try:
            if target is not None and target.winfo_exists():
                target.lift()
                target.attributes("-topmost", True)
                target.show_state("happy", duration_ms=60 * 1000, fallback_state="stand")
                target.show_message(message, force=True)
                return
        except tk.TclError:
            pass
        messagebox.showinfo("番茄时钟完成", message)

    def show_pet_today_progress(self):
        message = self.get_desktop_pet_progress_summary()
        self.show_desktop_pet_state("happy", message=message, fallback_state="idle")

    def pet_record_health(self, key):
        self.record_action(key)

    def pet_start_eye_training(self):
        self.show_desktop_pet_state("eye", message="开始护眼训练，眼睛休息一下。", fallback_state="happy")
        self.open_eye_training()

    def pet_toggle_reminder_pause(self):
        self.toggle_reminder_pause(parent=self.root)

    def draw_progress_ring(self, completed, total=4):
        safe_total = max(1, int(total))
        safe_completed = max(0, min(int(completed), safe_total))
        try:
            self.progress_canvas.delete("all")
            self.progress_canvas.create_arc(
                8, 8, 60, 60, start=0, extent=359, style=tk.ARC,
                width=6, outline=self.dashboard_colors["border"],
            )
            if safe_completed:
                self.progress_canvas.create_arc(
                    8, 8, 60, 60, start=90,
                    extent=-(360 * safe_completed / safe_total), style=tk.ARC,
                    width=6, outline=self.dashboard_colors["primary"],
                )
            self.progress_canvas.create_text(
                34, 34, text="{}/{}".format(safe_completed, safe_total),
                font=("微软雅黑", 11, "bold"),
                fill=self.dashboard_colors["text_primary"],
            )
        except tk.TclError:
            # The textual progress detail remains the accessible fallback.
            pass
    def open_settings(self):
        SettingsPage(
            self.root, self.nickname, self.reminders, self.topmost, self.autostart,
            self.current_theme, self.on_settings_save,
            {"sleep_periods": self.sleep_periods}, self.challenge_cfg,
            self.desktop_pet_autostart,
        )
    
    def open_friends(self):
        """打开好友管理页面"""
        FriendsPage(self.root, self.network_manager, self.theme_colors)

    def update_pause_reminder_state(self, schedule_next=False):
        clear_expired_reminder_pause()
        config = load_user_config()
        paused = is_reminder_paused(config)
        if self.pause_status_label is not None:
            self.pause_status_label.configure(text=format_reminder_pause_status(config))
        if self.pause_reminder_button is not None:
            self.pause_reminder_button.configure(text="恢复提醒" if paused else "设置免打扰")
        if schedule_next:
            if self.pause_status_after_id:
                try:
                    self.root.after_cancel(self.pause_status_after_id)
                except tk.TclError:
                    pass
            try:
                self.pause_status_after_id = self.root.after(
                    60 * 1000,
                    lambda: self.update_pause_reminder_state(schedule_next=True),
                )
            except tk.TclError:
                self.pause_status_after_id = None

    def toggle_reminder_pause(self, parent=None):
        config = load_user_config()
        if is_reminder_paused(config):
            save_user_config_fields(reminder_pause_until="")
            self.update_pause_reminder_state()
            messagebox.showinfo("提醒已恢复", "健康提醒已恢复。", parent=parent or self.root)
            return
        self.open_reminder_pause_dialog(parent=parent)

    def open_reminder_pause_dialog(self, parent=None):
        dialog_parent = parent or self.root
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass
        dialog = tk.Toplevel(dialog_parent)
        dialog.title("设置免打扰")
        apply_safe_window_geometry(dialog, 560, 560, 540, 520, height_ratio=0.82)
        dialog.resizable(True, True)
        dialog.configure(bg=self.dashboard_colors["app_bg"])
        try:
            dialog.transient(dialog_parent)
        except tk.TclError:
            pass
        dialog.lift()
        dialog.focus_force()
        dialog.grab_set()
        shell = tk.Frame(dialog, bg=self.dashboard_colors["app_bg"], padx=24, pady=22)
        shell.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(shell, bg=self.dashboard_colors["app_bg"])
        header.pack(fill=tk.X)
        tk.Label(
            header, text="设置免打扰", font=("微软雅黑", 18, "bold"),
            bg=self.dashboard_colors["app_bg"], fg=self.dashboard_colors["text_primary"],
        ).pack(anchor="w")
        tk.Label(
            header, text="暂停期间不会弹健康提醒，也不会触发答题霸屏。",
            font=("微软雅黑", 10), bg=self.dashboard_colors["app_bg"],
            fg=self.dashboard_colors["text_secondary"], wraplength=460, justify=tk.LEFT,
        ).pack(anchor="w", pady=(6, 0))

        def set_pause_until(target_time):
            save_user_config_fields(reminder_pause_until=target_time.strftime("%Y-%m-%d %H:%M:%S"))
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass
            self.update_pause_reminder_state()
            messagebox.showinfo(
                "已开启免打扰",
                "{} 后恢复提醒。".format(target_time.strftime("%H:%M")),
                parent=dialog_parent,
            )

        now = datetime.now()
        quick_section = tk.Frame(shell, bg=self.dashboard_colors["app_bg"])
        quick_section.pack(fill=tk.X, pady=(18, 0))
        tk.Label(
            quick_section, text="快捷设置", font=("微软雅黑", 11, "bold"),
            bg=self.dashboard_colors["app_bg"], fg=self.dashboard_colors["text_primary"],
        ).pack(anchor="w", pady=(0, 8))
        quick_row = tk.Frame(quick_section, bg=self.dashboard_colors["app_bg"])
        quick_row.pack(fill=tk.X)
        for column in range(3):
            quick_row.grid_columnconfigure(column, weight=1, uniform="pause_quick")
        quick_options = (
            ("30 分钟", now + timedelta(minutes=30)),
            ("1 小时", now + timedelta(hours=1)),
            ("2 小时", now + timedelta(hours=2)),
        )
        for column, (label, target_time) in enumerate(quick_options):
            tk.Button(
                quick_row, text=label, font=("微软雅黑", 11, "bold"), bg=self.dashboard_colors["surface"],
                fg=self.dashboard_colors["text_primary"], activebackground=self.dashboard_colors["surface_alt"],
                relief=tk.FLAT, bd=0, padx=12, pady=10,
                command=lambda t=target_time: set_pause_until(t),
            ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0 if column == 2 else 6))

        custom_section = tk.Frame(
            shell, bg=self.dashboard_colors["surface"],
            highlightbackground=self.dashboard_colors["border"], highlightthickness=1,
            padx=16, pady=14,
        )
        custom_section.pack(fill=tk.X, pady=(20, 0))
        tk.Label(
            custom_section, text="自定义恢复时间", font=("微软雅黑", 11, "bold"),
            bg=self.dashboard_colors["surface"], fg=self.dashboard_colors["text_primary"],
        ).pack(anchor="w")
        tk.Label(
            custom_section, text="请输入今天的恢复时间，例如 16:30；必须晚于当前时间。",
            font=("微软雅黑", 9), bg=self.dashboard_colors["surface"],
            fg=self.dashboard_colors["text_secondary"], wraplength=390, justify=tk.LEFT,
        ).pack(anchor="w", pady=(4, 8))
        input_row = tk.Frame(custom_section, bg=self.dashboard_colors["surface"])
        input_row.pack(fill=tk.X)
        input_row.grid_columnconfigure(1, weight=1)
        custom_var = tk.StringVar(value=(now + timedelta(hours=1)).strftime("%H:%M"))
        tk.Label(
            input_row, text="恢复时间", font=("微软雅黑", 10),
            bg=self.dashboard_colors["surface"], fg=self.dashboard_colors["text_secondary"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        custom_entry = tk.Entry(input_row, textvariable=custom_var, width=10, justify=tk.CENTER, font=("微软雅黑", 12))
        custom_entry.grid(row=0, column=1, sticky="ew", ipady=7)

        def submit_custom_time():
            value = custom_var.get().strip()
            try:
                hour, minute = [int(part) for part in value.split(":", 1)]
                target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            except (ValueError, TypeError):
                messagebox.showwarning("时间格式错误", "请输入 HH:MM，例如 16:30。", parent=dialog)
                return
            if target_time <= now:
                messagebox.showwarning("时间不可用", "恢复时间必须晚于当前时间。", parent=dialog)
                return
            set_pause_until(target_time)

        def close_dialog():
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass

        tk.Button(
            input_row, text="开启", font=("微软雅黑", 11, "bold"),
            bg=self.dashboard_colors["primary"], fg=self.dashboard_colors["on_primary"],
            activebackground=self.dashboard_colors["primary_active"],
            relief=tk.FLAT, bd=0, padx=12, pady=10, command=submit_custom_time,
        ).grid(row=0, column=2, sticky="e", padx=(10, 0))
        tk.Button(
            shell, text="取消", font=("微软雅黑", 10),
            bg=self.dashboard_colors["surface"], fg=self.dashboard_colors["text_primary"],
            activebackground=self.dashboard_colors["surface_alt"],
            relief=tk.FLAT, bd=0, padx=12, pady=10,
            command=close_dialog,
        ).pack(fill=tk.X, pady=(18, 0))
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        custom_entry.focus_set()
    
    def on_friend_reminder(self, friend_nickname, reminder_text):
        """收到好友提醒的回调"""
        # 检查休眠时段
        if is_in_any_sleep_period(self.sleep_periods):
            return

        # 切回 Tk 主线程，避免在网络线程里直接操作 UI。
        self.root.after(
            0,
            lambda: messagebox.showinfo(
                "好友提醒",
                f"好友{friend_nickname}提醒您：{reminder_text}",
            ),
        )
    
    def on_settings_save(self, nickname, reminders, topmost, autostart, theme, sleep_cfg, challenge_cfg):
        self.nickname = nickname
        self.reminders[:] = reminders
        self.topmost = topmost
        self.autostart = autostart
        self.current_theme = theme
        self.theme_colors = get_theme_colors(theme)
        self.challenge_cfg = normalize_challenge_config(challenge_cfg)
        self.desktop_pet_autostart = get_desktop_pet_autostart()
        if sleep_cfg and "sleep_periods" in sleep_cfg:
            self.sleep_periods = [dict(p) for p in sleep_cfg["sleep_periods"]]
        else:
            self.sleep_periods = [{"start": "23:00", "end": "07:00"}]
        # 更新界面显示
        self.nick_label.config(text="{}，{}".format(self.nickname, get_day_greeting(datetime.now().hour)))
        # 重新应用主题
        self.apply_theme()
        self.update_dashboard_state()
        self.apply_topmost()
        save_reminder_settings(self.reminders, {"sleep_periods": self.sleep_periods}, self.challenge_cfg)
        self.start_all_reminders()
    
    def apply_theme(self):
        """Refresh the dashboard by semantic role instead of widget type."""
        colors = get_dashboard_colors(self.theme_colors)
        self.dashboard_colors = colors
        self.root.configure(bg=colors["app_bg"])
        self.main_frame.configure(bg=colors["app_bg"])
        self.dashboard_canvas.configure(bg=colors["app_bg"])
        self.dashboard_scrollbar.configure(
            bg=colors["surface_alt"], activebackground=colors["primary_active"],
            troughcolor=colors["app_bg"],
        )
        self.dashboard_shell.configure(bg=colors["app_bg"])

        self.title_label.master.configure(bg=colors["surface"], highlightbackground=colors["border"])
        self.nav_frame.configure(bg=colors["surface"])
        self.nick_label.master.configure(bg=colors["app_bg"])
        for label in (self.title_label, self.nick_label):
            label.configure(fg=colors["text_primary"])
        self.title_label.configure(bg=colors["surface"])
        self.nick_label.configure(bg=colors["app_bg"])
        self.greeting_label.configure(bg=colors["surface"], fg=colors["text_secondary"])
        for label in (self.date_label, self.id_label):
            label.configure(bg=colors["app_bg"], fg=colors["text_secondary"])

        for button in (self.ai_button, self.friends_button, self.settings_button, self.copy_button):
            button.configure(bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"])

        self.progress_frame.configure(bg=colors["surface_alt"], highlightbackground=colors["border"])
        self.progress_title_label.master.configure(bg=colors["surface_alt"])
        self.progress_title_label.configure(bg=colors["surface_alt"], fg=colors["text_primary"])
        self.progress_detail_label.configure(bg=colors["surface_alt"], fg=colors["text_secondary"])
        self.progress_hint_label.configure(bg=colors["surface_alt"], fg=colors["text_secondary"])
        self.progress_canvas.configure(bg=colors["surface_alt"])

        self.health_grid.configure(bg=colors["app_bg"])
        for key, outer in self.health_cards.items():
            outer.configure(bg=colors["border"])
            surface = self.health_card_surfaces[key]
            surface.configure(bg=colors["surface"])
            self.card_name_labels[key].configure(bg=colors["surface"], fg=colors["text_primary"])
            self.card_target_labels[key].configure(bg=colors["surface"], fg=colors["text_secondary"])
            self.status_labels[key].configure(bg=colors["surface"], fg=colors["text_primary"])
            is_primary = key == "drink"
            self.buttons[key].configure(
                bg=colors["primary"] if is_primary else colors["surface_alt"],
                fg=colors["on_primary"] if is_primary else colors["secondary_action_text"],
                activebackground=colors["primary_active"],
            )
            if key == "eye" and self.eye_training_button is not None:
                self.eye_training_button.configure(
                    bg=colors["primary"],
                    fg=colors["on_primary"],
                    activebackground=colors["primary_active"],
                )

        self.quit_button.master.configure(bg=colors["surface"], highlightbackground=colors["border"])
        if self.pause_status_label is not None:
            self.pause_status_label.configure(bg=colors["surface"], fg=colors["text_secondary"])
        if self.pause_reminder_button is not None:
            self.pause_reminder_button.configure(bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"])
        self.quit_button.configure(bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"])
        self.pet_button.configure(bg=colors["surface"], fg=colors["text_primary"], activebackground=colors["surface_alt"])
        self.restart_button.configure(bg=colors["danger_muted"], fg=colors["danger_text"], activebackground=colors["danger_muted"])
        completed = count_completed_items(self.data.get(self.today, {}), ["drink", "stand", "eye", "sport"])
        self.draw_progress_ring(completed, 4)
    
    def update_widget_theme(self, parent):
        """递归更新组件主题"""
        for widget in parent.winfo_children():
            if isinstance(widget, tk.Frame):
                widget.configure(bg=self.theme_colors["bg"])
                self.update_widget_theme(widget)
            elif isinstance(widget, tk.Label):
                widget.configure(bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"])
            elif isinstance(widget, tk.Button):
                widget.configure(
                    bg=self.theme_colors["button_bg"], 
                    fg=self.theme_colors["button_fg"], 
                    activebackground=self.theme_colors["button_active"]
                )
    def apply_topmost(self):
        self.root.attributes("-topmost", self.topmost)

    def _show_main_window_on_start(self):
        """Give the packaged app an explicit visible, centered start state."""
        try:
            self.root.update_idletasks()
            self.root.minsize(720, 560)
            screen_height = self.root.winfo_screenheight()
            requested_width = max(820, self.dashboard_shell.winfo_reqwidth() + 64)
            requested_height = min(
                max(640, self.dashboard_shell.winfo_reqheight() + 36),
                max(560, screen_height - 80),
            )
            width, height, x, y = calculate_window_geometry(
                self.root.winfo_screenwidth(),
                screen_height,
                requested_width=requested_width,
                requested_height=requested_height,
            )
            self.root.geometry("{}x{}+{}+{}".format(width, height, x, y))
            self.root.state("normal")
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", self.topmost)
            # A one-file launcher can apply its inherited startup window state
            # after Tk creates the root. Correct that delayed state only during
            # startup; later user-initiated minimization remains untouched.
            self.root.after(200, self._ensure_visible_after_start)
            self.root.after(1000, self._ensure_visible_after_start)
        except tk.TclError:
            pass

    def _ensure_visible_after_start(self):
        if self.closing:
            return
        try:
            self.root.state("normal")
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", self.topmost)
        except tk.TclError:
            pass

    def restore_main_window(self):
        """Refresh window stacking after Windows has restored it normally."""
        if self.closing:
            return
        try:
            # Let Windows finish the taskbar restore transition before this
            # handler adjusts stacking for the packaged Tk window.
            if self.root.state() != "normal":
                return
            self.root.lift()
            self.root.attributes("-topmost", self.topmost)
        except tk.TclError:
            pass

    def _on_root_map(self, event):
        if not self.closing and event.widget is self.root:
            self.root.after(50, self.restore_main_window)
            self.root.after(50, self._sync_reminder_windows_for_root_state)

    def _on_root_unmap(self, event):
        if not self.closing and event.widget is self.root:
            self.root.after_idle(self._sync_reminder_windows_for_root_state)

    def _register_health_reminder(self, win):
        """Track one timed health reminder until its Tk window is destroyed."""
        if win not in self.active_health_reminders:
            self.active_health_reminders.append(win)
        try:
            if self.root.state() == "iconic":
                self.root.deiconify()
                self.root.lift()
        except tk.TclError:
            pass
        win._health_reminder_has_unmapped = False
        win._health_reminder_terminal = False
        try:
            win._health_reminder_topmost = bool(win.attributes("-topmost"))
        except tk.TclError:
            win._health_reminder_topmost = False

        def cleanup(event):
            if event.widget is win:
                self._unregister_health_reminder(win)

        def restore_root_first(event):
            if event.widget is not win or self.closing:
                return
            if not getattr(win, "_health_reminder_has_unmapped", False):
                return
            win._health_reminder_has_unmapped = False
            try:
                if self.root.state() == "iconic":
                    self.root.deiconify()
                    self.root.lift()
                    self.root.after_idle(self._sync_reminder_windows_for_root_state)
            except tk.TclError:
                pass

        def remember_unmap(event):
            if event.widget is win:
                win._health_reminder_has_unmapped = True

        win.bind("<Destroy>", cleanup, add="+")
        win.bind("<Unmap>", remember_unmap, add="+")
        win.bind("<Map>", restore_root_first, add="+")
        return win

    def _unregister_health_reminder(self, win):
        """Forget a reminder safely, including already-destroyed widgets."""
        removed = False
        try:
            self.active_health_reminders.remove(win)
            removed = True
        except ValueError:
            pass
        if (removed and self.active_health_reminders
                and not getattr(self, "_health_reminder_syncing", False)):
            try:
                self.root.after_idle(self._sync_reminder_windows_for_root_state)
            except (AttributeError, tk.TclError):
                try:
                    self._sync_reminder_windows_for_root_state()
                except (AttributeError, tk.TclError):
                    pass

    def _claim_health_reminder_terminal(self, win):
        """Atomically claim the one terminal action allowed for a reminder."""
        if getattr(win, "_health_reminder_terminal", False):
            return False
        win._health_reminder_terminal = True
        return True

    def _sync_reminder_windows_for_root_state(self):
        """Keep timed reminders visible even while the main window is minimized."""
        if self.closing:
            return
        existing = []
        self._health_reminder_syncing = True
        try:
            try:
                if self.active_health_reminders and self.root.state() == "iconic":
                    self.root.deiconify()
                    self.root.lift()
            except tk.TclError:
                return
            for win in list(self.active_health_reminders):
                try:
                    if not win.winfo_exists():
                        self._unregister_health_reminder(win)
                        continue
                    win.deiconify()
                    win.lift()
                    if getattr(win, "_health_reminder_topmost", False):
                        win.attributes("-topmost", True)
                    existing.append(win)
                except tk.TclError:
                    self._unregister_health_reminder(win)
        finally:
            self._health_reminder_syncing = False
        if not existing:
            return
        front_window = existing[-1]
        for win in existing[:-1]:
            try:
                win.grab_release()
            except tk.TclError:
                pass
        try:
            front_window.grab_set()
            front_window.focus_force()
        except tk.TclError:
            self._unregister_health_reminder(front_window)

    def _cancel_timer(self, key):
        timer_id = self.timers.pop(key, None)
        if not timer_id:
            return
        try:
            self.root.after_cancel(timer_id)
        except tk.TclError:
            # 旧定时器可能已经触发或被 Tk 清理，不应因此让程序崩溃。
            pass

    def start_all_reminders(self):
        for key in list(self.timers.keys()):
            self._cancel_timer(key)
        for r in self.reminders:
            if r["enabled"]:
                self.schedule_reminder(r["key"])
    def schedule_reminder(self, key):
        r = next((x for x in self.reminders if x["key"] == key), None)
        if not r or not r["enabled"]:
            return
        
        # 先取消该key对应的旧定时器
        self._cancel_timer(key)
        
        interval_ms = int(r["interval"]) * 60 * 1000
        self.timers[key] = self.root.after(interval_ms, lambda: self.remind(key))
    def remind(self, key):
        r = next((x for x in self.reminders if x["key"] == key), None)
        if not r:
            return
        if is_reminder_paused():
            self.schedule_reminder(key)
            self.update_pause_reminder_state()
            return
        if self.is_pet_pomodoro_active():
            self.schedule_reminder(key)
            self.update_pet_pomodoro_countdown()
            return
        # 多段休眠时段判断
        if is_in_any_sleep_period(self.sleep_periods):
            self.schedule_reminder(key)
            return
        # 合并弹窗逻辑
        self.pending_reminders.append(r)
        if not self.reminder_popup_scheduled:
            self.reminder_popup_scheduled = True
            self.root.after(1000, self.show_combined_reminder)  # 1秒合并窗口
    # 新增：合并弹窗方法
    def show_combined_reminder(self):
        if not self.pending_reminders:
            self.reminder_popup_scheduled = False
            return
        reminders = list(self.pending_reminders)
        self.pending_reminders.clear()
        self.reminder_popup_scheduled = False
        if self.suppress_health_reminder_during_pomodoro(reminders):
            return
        self._show_reminder_batch(reminders, snooze_count=0)

    def _show_reminder_batch(self, reminders, snooze_count):
        """Present one stable reminder batch without mutating the pending queue."""
        reminders = list(reminders)
        if not reminders:
            return
        if self.suppress_health_reminder_during_pomodoro(reminders):
            return
        msg = "\n".join([r["msg"].format(nickname=self.nickname or "朋友") for r in reminders])
        # 优先用第一个提醒类型的小知识
        tip_type = reminders[0]["key"]
        tip = get_random_health_tip(tip_type)
        
        # 检查是否包含护眼提醒
        has_eye = any(r["key"] == "eye" for r in reminders)
        if self.challenge_cfg["answer_required"]:
            self.show_answer_required_reminder(
                reminders, msg, tip, has_eye, snooze_count=snooze_count
            )
            return
        if has_eye:
            # 弹窗带按钮，点击打开护眼页面
            self.show_eye_reminder_with_link(msg, tip)
            self._finish_reminder_batch(reminders)
            return
        self.show_standard_health_reminder(reminders, msg, tip)

    def show_standard_health_reminder(self, reminders, msg, tip):
        """Show an owned, trackable modal for a normal timed reminder batch."""
        reminders = list(reminders)
        if self.suppress_health_reminder_during_pomodoro(reminders):
            return
        self.show_desktop_pet_reminder_state(reminders)
        win = tk.Toplevel(self.root)
        self._register_health_reminder(win)
        win.title("健康提醒")
        apply_safe_window_geometry(win, 460, 320, 420, 280, height_ratio=0.75)
        win.resizable(True, True)
        win.configure(bg=self.theme_colors["bg"])
        win.transient(self.root)

        tk.Label(
            win, text=msg, font=("微软雅黑", 14), wraplength=370,
            justify=tk.CENTER, bg=self.theme_colors["bg"],
            fg=self.theme_colors["button_bg"],
        ).pack(padx=24, pady=(28, 12), fill=tk.X)
        tk.Label(
            win, text="健康小知识：{}".format(tip), font=("微软雅黑", 11),
            wraplength=370, justify=tk.CENTER, bg=self.theme_colors["bg"],
            fg="#4caf50",
        ).pack(padx=24, pady=(0, 20), fill=tk.X)

        def close_reminder():
            if not self._claim_health_reminder_terminal(win):
                return
            self._unregister_health_reminder(win)
            try:
                win.grab_release()
            except tk.TclError:
                pass
            try:
                win.destroy()
            except tk.TclError:
                pass
            self._finish_reminder_batch(reminders)

        tk.Button(
            win, text="知道了", font=("微软雅黑", 11, "bold"),
            bg=self.theme_colors["button_bg"], fg=self.theme_colors["button_fg"],
            activebackground=self.theme_colors["button_active"],
            relief=tk.FLAT, bd=0, padx=24, pady=10,
            command=close_reminder,
        ).pack(pady=(0, 22))
        win.protocol("WM_DELETE_WINDOW", close_reminder)
        win.grab_set()
        win.lift()
        win.focus_force()

    def _finish_reminder_batch(self, reminders):
        """Resume normal cycles once for each unique key in a completed batch."""
        seen = set()
        for reminder in reminders:
            key = reminder["key"]
            if key not in seen:
                seen.add(key)
                self.schedule_reminder(key)

    def _redisplay_snoozed_batch(self, reminders, snooze_count):
        """Keep a batch suspended and redisplay it after the configured delay."""
        delay_ms = self.challenge_cfg["snooze_minutes"] * 60 * 1000
        reminder_copy = list(reminders)
        self.root.after(
            delay_ms,
            lambda: self._show_reminder_batch(reminder_copy, snooze_count),
        )

    def show_answer_required_reminder(self, reminders, msg, tip, has_eye, snooze_count=0):
        """Show a modal reminder that can only be completed with a correct answer."""
        reminders = list(reminders)
        if self.suppress_health_reminder_during_pomodoro(reminders):
            return
        win = None
        try:
            self.show_desktop_pet_reminder_state(reminders)
            expression, expected_answer = generate_math_challenge()
            win = tk.Toplevel(self.root)
            self._register_health_reminder(win)
            win.title("健康提醒")
            win.configure(bg=self.theme_colors["bg"])
            win.attributes("-fullscreen", True)
            win.attributes("-topmost", True)
            win._health_reminder_topmost = True
            win.transient(self.root)
            win.protocol("WM_DELETE_WINDOW", lambda: None)
            win.bind("<Escape>", lambda event: "break")
            win.bind("<Alt-F4>", lambda event: "break")
            win.grab_set()
            win.lift()
            win.focus_force()

            panel = tk.Frame(
                win,
                bg=self.theme_colors["bg"],
                padx=48,
                pady=40,
            )
            panel.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

            tk.Label(
                panel, text="健康提醒", font=("微软雅黑", 26, "bold"),
                bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"],
            ).pack(pady=(0, 18))
            tk.Label(
                panel, text=msg, font=("微软雅黑", 16), wraplength=760,
                justify=tk.CENTER, bg=self.theme_colors["bg"],
                fg=self.theme_colors["button_bg"],
            ).pack(pady=(0, 12))
            tk.Label(
                panel, text=f"健康小知识：{tip}", font=("微软雅黑", 12),
                wraplength=760, justify=tk.CENTER, bg=self.theme_colors["bg"],
                fg="#4caf50",
            ).pack(pady=(0, 24))
            tk.Label(
                panel, text=f"请计算：{expression}", font=("微软雅黑", 24, "bold"),
                bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"],
            ).pack(pady=(0, 14))

            answer_row = tk.Frame(panel, bg=self.theme_colors["bg"])
            answer_row.pack()
            tk.Label(
                answer_row, text="答案：", font=("微软雅黑", 14),
                bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"],
            ).pack(side=tk.LEFT, padx=(0, 8))
            answer_var = tk.StringVar()
            answer_entry = tk.Entry(
                answer_row, textvariable=answer_var, font=("微软雅黑", 18),
                width=12, justify=tk.CENTER,
            )
            answer_entry.pack(side=tk.LEFT)
            error_var = tk.StringVar()
            tk.Label(
                panel, textvariable=error_var, font=("微软雅黑", 11),
                bg=self.theme_colors["bg"], fg="#d32f2f",
            ).pack(pady=(8, 10))

            def submit_answer(event=None):
                if is_correct_answer(answer_var.get(), expected_answer):
                    self._complete_answer_reminder(win, reminders)
                    return "break"
                error_var.set("答案不正确，请重新计算")
                answer_entry.selection_range(0, tk.END)
                answer_entry.focus_set()
                return "break"

            answer_entry.bind("<Return>", submit_answer)
            actions = tk.Frame(panel, bg=self.theme_colors["bg"])
            actions.pack(pady=(8, 0))
            button_options = {
                "font": ("微软雅黑", 12, "bold"),
                "bg": self.theme_colors["button_bg"],
                "fg": self.theme_colors["button_fg"],
                "activebackground": self.theme_colors["button_active"],
                "relief": tk.FLAT,
                "height": 2,
                "padx": 18,
            }
            tk.Button(
                actions, text="完成并关闭", command=submit_answer, **button_options
            ).pack(side=tk.LEFT, padx=6)
            if has_eye:
                tk.Button(
                    actions,
                    text="护眼训练",
                    command=lambda: self._open_eye_training_from_reminder(win, reminders),
                    **button_options
                ).pack(side=tk.LEFT, padx=6)

            snooze_minutes = self.challenge_cfg["snooze_minutes"]
            max_snooze_count = self.challenge_cfg["max_snooze_count"]
            if snooze_count < max_snooze_count:
                tk.Button(
                    actions,
                    text=f"稍后提醒（{snooze_minutes} 分钟）",
                    command=lambda: self._snooze_answer_reminder(
                        win, reminders, snooze_count
                    ),
                    **button_options
                ).pack(side=tk.LEFT, padx=6)
            else:
                tk.Label(
                    panel,
                    text=f"本次提醒已延期 {max_snooze_count} 次，请完成答题",
                    font=("微软雅黑", 11), bg=self.theme_colors["bg"],
                    fg=self.theme_colors["button_bg"],
                ).pack(pady=(14, 0))
            answer_entry.focus_set()
        except Exception as exc:
            log_exception(exc)
            if win is not None:
                self._unregister_health_reminder(win)
                try:
                    win.grab_release()
                    win.destroy()
                except tk.TclError:
                    pass
            if has_eye:
                self.show_eye_reminder_with_link(msg, tip)
            else:
                self.show_standard_health_reminder(reminders, msg, tip)
                return
            self._finish_reminder_batch(reminders)

    def _complete_answer_reminder(self, win, reminders):
        """Safely close a successfully answered reminder window."""
        if not self._claim_health_reminder_terminal(win):
            return
        self._unregister_health_reminder(win)
        try:
            win.grab_release()
        except tk.TclError:
            pass
        try:
            win.destroy()
        except tk.TclError:
            pass
        self._finish_reminder_batch(reminders)

    def _snooze_answer_reminder(self, win, reminders, snooze_count):
        """Safely close the current window and retain its batch for redisplay."""
        if not self._claim_health_reminder_terminal(win):
            return
        self._unregister_health_reminder(win)
        try:
            win.grab_release()
        except tk.TclError:
            pass
        try:
            win.destroy()
        except tk.TclError:
            pass
        self._redisplay_snoozed_batch(reminders, snooze_count + 1)

    def show_eye_reminder_with_link(self, msg, tip):
        """
        弹出带"护眼训练"按钮的护眼提醒弹窗
        """
        if self.suppress_health_reminder_during_pomodoro([{"key": "eye"}]):
            return
        self.show_desktop_pet_state(
            "eye",
            message="护眼时间到了，做一次眼部放松吧。",
            fallback_state="unhappy",
        )
        # 创建自定义弹窗
        win = tk.Toplevel(self.root)
        self._register_health_reminder(win)
        win.title("健康提醒 - 护眼")
        apply_safe_window_geometry(win, 440, 300, 400, 260, height_ratio=0.75)
        win.resizable(True, True)
        win.configure(bg=self.theme_colors["bg"])
        win.transient(self.root)
        win.grab_set()
        # 提醒内容
        tk.Label(win, text=msg, font=("微软雅黑", 13), bg=self.theme_colors["bg"], fg=self.theme_colors["button_bg"], wraplength=340, justify=tk.LEFT).pack(pady=(18, 8), padx=18)
        # 健康小知识
        tk.Label(win, text=f"健康小知识：{tip}", font=("微软雅黑", 11), bg=self.theme_colors["bg"], fg="#4caf50", wraplength=340, justify=tk.LEFT).pack(pady=(0, 10), padx=18)
        # 护眼训练按钮
        open_btn = tk.Button(
            win, text="护眼训练", font=("微软雅黑", 11, "bold"),
            bg="#4caf50", fg="white", width=14, relief=tk.FLAT,
            command=lambda: self._open_eye_training_from_reminder(win, [])
        )
        open_btn.pack(pady=(0, 10))
        # 关闭按钮
        def close_eye_reminder():
            if not self._claim_health_reminder_terminal(win):
                return
            self._unregister_health_reminder(win)
            try:
                win.grab_release()
            except tk.TclError:
                pass
            try:
                win.destroy()
            except tk.TclError:
                pass

        close_btn = tk.Button(
            win, text="关闭", font=("微软雅黑", 10),
            bg="#e0e0e0", fg="#333333", relief=tk.FLAT,
            command=close_eye_reminder
        )
        close_btn.pack()
        win.protocol("WM_DELETE_WINDOW", close_eye_reminder)
        win.focus()

    def _open_eye_training_from_reminder(self, win, reminders):
        """Release the reminder window before launching eye training."""
        if not self._claim_health_reminder_terminal(win):
            return
        self._unregister_health_reminder(win)
        try:
            win.grab_release()
        except tk.TclError:
            pass
        try:
            win.destroy()
        except tk.TclError:
            pass
        self.open_eye_training()
        if reminders:
            self._finish_reminder_batch(reminders)

    def open_eye_training(self):
        """
        使用默认浏览器打开护眼训练程序，避免打包 webview/pythonnet/numpy 重依赖。
        """
        try:
            open_eye_training_in_browser(self.eye_record_url, autostart=True)
            print("[调试] 护眼训练程序已启动")
        except Exception as e:
            print(f"[调试] 启动护眼训练程序失败：{e}")
            messagebox.showerror("错误", f"启动护眼训练程序失败：\n{e}")

    def open_eye_html(self):
        """
        用默认浏览器或资源管理器打开护眼页面index.html，并增加详细日志和弹窗，便于定位问题
        """
        import os
        import tkinter.messagebox as messagebox
        html_path = os.path.join(RESOURCE_DIR, "护眼", "index.html")
        url = "file:///" + html_path.replace("\\", "/")
        # 检查文件是否存在
        if not os.path.exists(html_path):
            messagebox.showerror("错误", f"文件不存在：\n{html_path}")
            print(f"[调试] 文件不存在: {html_path}")
            return
        # 日志输出
        print(f"[调试] 尝试打开URL: {url}")
        print(f"[调试] 尝试打开本地文件: {html_path}")
        # 尝试用webbrowser
        import webbrowser
        try:
            webbrowser.open(url)
            print("[调试] webbrowser.open已调用")
        except Exception as e:
            print(f"[调试] webbrowser打开失败：{e}")
        # 兼容性更好：直接用os.startfile（仅Windows）
        try:
            os.startfile(html_path)
            print("[调试] os.startfile已调用")
        except Exception as e:
            print(f"[调试] os.startfile打开失败：{e}")

    def load_data(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                migrated, changed = migrate_drink_data(data)
                if changed:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = backup_file(DATA_FILE, f"backup_{timestamp}")
                    self.data = migrated
                    self.save_data()
                    log(f"饮水数据已迁移，原文件备份到: {backup_path}")
                return migrated
            return {}
        except Exception as e:
            log_exception(e)
            return {}
    def save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    def quit_app(self):
        if self.closing:
            return
        self.closing = True
        for key in list(self.timers.keys()):
            self._cancel_timer(key)
        if self.pause_status_after_id:
            try:
                self.root.after_cancel(self.pause_status_after_id)
            except tk.TclError:
                pass
            self.pause_status_after_id = None
        if self.pet_pomodoro_after_id:
            try:
                self.root.after_cancel(self.pet_pomodoro_after_id)
            except tk.TclError:
                pass
            self.pet_pomodoro_after_id = None
        # 停止网络服务
        if hasattr(self, 'network_manager'):
            self.network_manager.stop()
        if hasattr(self, 'eye_record_server'):
            self.eye_record_server.stop()
        self.save_data()
        self.root.destroy()

    def copy_user_id(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.user_id)
        messagebox.showinfo("已复制", "用户ID已复制到剪贴板")

    def open_ai_assistant(self):
        AIHealthAssistantDialog(self.root, self.nickname)

    def check_eye_autorecord(self):
        """定时检测eye_autorecord.txt文件并自动统计护眼次数"""
        try:
            EYE_AUTO_FILE = os.path.join(APP_DIR, "eye_autorecord.txt")
            if os.path.exists(EYE_AUTO_FILE):
                with open(EYE_AUTO_FILE, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    for _ in lines:
                        self.record_action("eye", auto=True)
                    # 清空文件
                    with open(EYE_AUTO_FILE, "w", encoding="utf-8") as f:
                        f.write("")
        except Exception as e:
            print("自动护眼同步异常：", e)
        # 10秒后再次检查
        self.root.after(10000, self.check_eye_autorecord)

    def restart_reminders(self):
        """重启整个程序"""
        # 保存当前数据
        self.save_data()
        if self.pet_pomodoro_after_id:
            try:
                self.root.after_cancel(self.pet_pomodoro_after_id)
            except tk.TclError:
                pass
            self.pet_pomodoro_after_id = None
        # 停止网络服务
        if hasattr(self, 'network_manager'):
            self.network_manager.stop()
        if hasattr(self, 'eye_record_server'):
            self.eye_record_server.stop()
        # 重启程序
        python = sys.executable
        os.execl(python, python, *sys.argv)

def start_main_app(root, nickname, reminders=None, topmost=True, autostart=False, theme=DEFAULT_THEME, sleep_cfg=None, challenge_cfg=None):
    for widget in root.winfo_children():
        widget.destroy()
    global main_app
    if reminders is None or sleep_cfg is None:
        reminders, sleep_cfg, challenge_cfg = load_reminder_settings()
    main_app = HealthMainPage(root, nickname, reminders, topmost, autostart, theme, sleep_cfg, challenge_cfg)

class FriendNetworkManager:
    """好友网络管理器"""
    def __init__(self, nickname, on_friend_reminder=None, sleep_periods=None):
        self.nickname = nickname
        self.user_id = load_user_id()
        self.on_friend_reminder = on_friend_reminder
        self.discovery_socket = None
        self.chat_socket = None
        self.running = False
        self.friends = load_friends()
        # 兼容sleep_periods
        if sleep_periods:
            self.sleep_periods = [dict(p) for p in sleep_periods]
        else:
            self.sleep_periods = [{"start": "23:00", "end": "07:00"}]

    def _reload_friends(self):
        self.friends = load_friends()
        return self.friends

    def _find_friend(self, friend_id):
        for friend in self.friends:
            if friend.get('user_id') == friend_id:
                return friend
        return None

    def _get_friend_ip(self, friend_id):
        self._reload_friends()
        friend = self._find_friend(friend_id)
        if not friend:
            return None
        return friend.get('ip')
        
    def start(self):
        """启动网络服务"""
        self.running = True
        # 启动好友发现服务
        threading.Thread(target=self._start_discovery_service, daemon=True).start()
        # 启动聊天服务
        threading.Thread(target=self._start_chat_service, daemon=True).start()
        log("好友网络服务已启动")
    
    def stop(self):
        """停止网络服务"""
        self.running = False
        if self.discovery_socket:
            self.discovery_socket.close()
        if self.chat_socket:
            self.chat_socket.close()
        log("好友网络服务已停止")
    
    def _start_discovery_service(self):
        """启动好友发现服务"""
        try:
            self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.discovery_socket.bind(('', DISCOVERY_PORT))
            while self.running:
                try:
                    data, addr = self.discovery_socket.recvfrom(1024)
                    message = json.loads(data.decode('utf-8'))
                    if message.get('type') == 'discover':
                        # 收到发现请求，回复自己的信息
                        response = {
                            'type': 'discover_response',
                            'user_id': self.user_id,
                            'nickname': self.nickname
                        }
                        self.discovery_socket.sendto(json.dumps(response).encode('utf-8'), addr)
                    elif message.get('type') == 'discover_response':
                        # 收到发现响应，更新好友状态
                        friend_id = message.get('user_id')
                        friend_nickname = message.get('nickname')
                        self._update_friend_status(friend_id, friend_nickname, True)
                except Exception as e:
                    log(f"好友发现服务异常：{e}")
        except Exception as e:
            log(f"启动好友发现服务失败：{e}")
    
    def _start_chat_service(self):
        """启动聊天服务"""
        try:
            self.chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.chat_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.chat_socket.bind(('', CHAT_PORT))
            self.chat_socket.listen(5)
            
            while self.running:
                try:
                    client_socket, addr = self.chat_socket.accept()
                    threading.Thread(target=self._handle_chat_client, args=(client_socket,), daemon=True).start()
                except Exception as e:
                    if self.running:
                        log(f"聊天服务异常：{e}")
                        
        except Exception as e:
            log(f"启动聊天服务失败：{e}")
    
    def _handle_chat_client(self, client_socket):
        """处理聊天客户端连接"""
        try:
            message = recv_json_message(client_socket)
            if message.get('type') == 'reminder':
                # 收到好友提醒
                friend_id = message.get('from_user_id')
                friend_nickname = message.get('from_nickname')
                reminder_text = message.get('text')
                # 检查休眠时段
                if is_in_any_sleep_period(self.sleep_periods):
                    response = {'type': 'reminder_response', 'status': 'sleeping'}
                else:
                    response = {'type': 'reminder_response', 'status': 'success'}
                    # 触发提醒回调
                    if self.on_friend_reminder:
                        self.on_friend_reminder(friend_nickname, reminder_text)
                send_json_message(client_socket, response)
            elif message.get('type') == 'get_data':
                # 好友请求查看数据
                friend_id = message.get('from_user_id')
                permissions = load_user_permissions()
                if permissions.get('allow_data_view'):
                    data = self._get_shareable_data()
                    response = {'type': 'data_response', 'data': data}
                else:
                    response = {'type': 'data_response', 'error': 'permission_denied'}
                send_json_message(client_socket, response)
        except Exception as e:
            log(f"处理聊天客户端异常：{e}")
        finally:
            client_socket.close()
    
    def _update_friend_status(self, friend_id, nickname, online, ip=None):
        """更新好友状态"""
        self._reload_friends()
        for friend in self.friends:
            if friend.get('user_id') == friend_id:
                friend['online'] = online
                friend['last_seen'] = datetime.now().isoformat()
                if ip:
                    friend['ip'] = ip
                # 修复：昵称同步
                if nickname and nickname != friend.get('nickname'):
                    friend['nickname'] = nickname
                save_friends(self.friends)
                return
        
        # 新好友
        self.friends.append({
            'user_id': friend_id,
            'nickname': nickname,
            'online': online,
            'last_seen': datetime.now().isoformat(),
            'ip': ip
        })
        save_friends(self.friends)
    
    def _get_shareable_data(self):
        """获取可分享的数据"""
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            log(f"获取分享数据异常：{e}")
            return {}
    
    def send_reminder(self, friend_id, text):
        """发送提醒给好友"""
        try:
            # 检查是否可以发送提醒
            if not can_send_reminder(friend_id):
                return False, "发送过于频繁，请稍后再试"
            
            # 查找好友IP
            friend_ip = self._get_friend_ip(friend_id)
            
            if not friend_ip:
                return False, "好友离线或未找到"
            
            # 发送提醒
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5)
            client_socket.connect((friend_ip, CHAT_PORT))
            
            message = {
                'type': 'reminder',
                'from_user_id': self.user_id,
                'from_nickname': self.nickname,
                'text': text
            }
            
            send_json_message(client_socket, message)
            response_data = recv_json_message(client_socket)
            client_socket.close()
            if response_data.get('status') == 'success':
                record_reminder_sent(friend_id)
                return True, "提醒发送成功"
            elif response_data.get('status') == 'sleeping':
                return False, "好友正在休眠时段"
            else:
                return False, "发送失败"
                
        except Exception as e:
            self._update_friend_status(friend_id, None, False)
            log(f"发送提醒异常：{e}")
            return False, "网络连接失败"
    
    def discover_friends(self):
        """发现好友"""
        try:
            # 发送广播发现请求
            discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            discovery_socket.settimeout(3)
            
            message = {
                'type': 'discover',
                'user_id': self.user_id,
                'nickname': self.nickname
            }
            
            discovery_socket.sendto(json.dumps(message).encode('utf-8'), (BROADCAST_ADDR, DISCOVERY_PORT))
            
            # 等待响应
            start_time = time.time()
            while time.time() - start_time < 3:
                try:
                    data, addr = discovery_socket.recvfrom(1024)
                    response = json.loads(data.decode('utf-8'))
                    
                    if response.get('type') == 'discover_response':
                        friend_id = response.get('user_id')
                        friend_nickname = response.get('nickname')
                        
                        if friend_id != self.user_id:  # 不添加自己
                            self._update_friend_status(friend_id, friend_nickname, True, addr[0])
                            
                except socket.timeout:
                    break
                except Exception as e:
                    log(f"发现好友响应异常：{e}")
            
            discovery_socket.close()
            
        except Exception as e:
            log(f"发现好友异常：{e}")
    
    def check_friend_online(self, friend_id):
        """检查好友是否在线"""
        try:
            # 查找好友IP
            friend_ip = self._get_friend_ip(friend_id)
            
            if not friend_ip:
                return False
            
            # 尝试连接
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(2)
            client_socket.connect((friend_ip, CHAT_PORT))
            client_socket.close()
            
            # 更新状态为在线
            self._update_friend_status(friend_id, None, True, friend_ip)
            return True
            
        except Exception as e:
            # 更新状态为离线
            self._update_friend_status(friend_id, None, False)
            return False

    def get_friend_data(self, friend_id):
        """获取好友数据"""
        try:
            # 查找好友IP
            friend_ip = self._get_friend_ip(friend_id)
            
            if not friend_ip:
                return None, "好友离线或未找到"
            
            # 请求数据
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5)
            client_socket.connect((friend_ip, CHAT_PORT))
            
            message = {
                'type': 'get_data',
                'from_user_id': self.user_id
            }
            
            send_json_message(client_socket, message)
            response_data = recv_json_message(client_socket)
            client_socket.close()
            if 'error' in response_data:
                return None, response_data['error']
            else:
                return response_data.get('data', {}), None
                
        except Exception as e:
            self._update_friend_status(friend_id, None, False)
            log(f"获取好友数据异常：{e}")
            return None, "网络连接失败"


FriendNetworkManager = ImportedFriendNetworkManager

class FriendsPage(tk.Toplevel):
    """好友管理页面"""
    def __init__(self, master, network_manager, theme_colors):
        super().__init__(master)
        self.title("好友管理")
        apply_safe_window_geometry(self, 560, 680, 500, 560, height_ratio=0.85)
        self.resizable(True, True)
        self.network_manager = network_manager
        self.theme_colors = theme_colors
        self.dialog_colors = get_dashboard_colors(theme_colors)
        self.configure(bg=self.dialog_colors["app_bg"])
        
        # 窗口设置
        self.transient(master)
        self.grab_set()
        self.focus()
        self.lift()
        
        self.create_widgets()
        self.refresh_friends()
    
    def create_widgets(self):
        colors = self.dialog_colors
        shell = tk.Frame(self, bg=colors["app_bg"], padx=18, pady=16)
        shell.pack(fill=tk.BOTH, expand=True)
        create_dialog_header(shell, "好友管理", "连接好友，查看健康记录，也可以发送轻量提醒。", colors)
        
        # 添加好友区域
        add_frame = create_dialog_card(shell, colors, padx=16, pady=14)
        add_frame.grid_columnconfigure(1, weight=1)
        
        tk.Label(
            add_frame, text="添加好友：", 
            font=("微软雅黑", 12), 
            bg=colors["surface"],
            fg=colors["text_primary"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        
        self.friend_id_var = tk.StringVar()
        self.friend_id_entry = tk.Entry(
            add_frame, textvariable=self.friend_id_var,
            font=("微软雅黑", 12), width=15,
            relief=tk.FLAT, bg=colors["surface"],
            fg=colors["text_primary"],
            highlightbackground=colors["border"],
            highlightcolor=colors["primary"],
            highlightthickness=1, bd=0
        )
        self.friend_id_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        
        add_btn = tk.Button(
            add_frame, text="添加", 
            command=self.add_friend,
            **dialog_button_options(colors, primary=True)
        )
        add_btn.grid(row=0, column=2, sticky="e")
        
        discover_btn = tk.Button(
            add_frame, text="发现好友", 
            command=self.discover_friends,
            **dialog_button_options(colors)
        )
        discover_btn.grid(row=1, column=1, sticky="e", padx=(0, 8), pady=(8, 0))
        self.discover_btn = discover_btn  # 保存引用
        
        refresh_btn = tk.Button(
            add_frame, text="刷新状态", 
            command=self.refresh_friend_status,
            **dialog_button_options(colors)
        )
        refresh_btn.grid(row=1, column=2, sticky="e", pady=(8, 0))
        
        # 好友列表区域
        list_frame = create_dialog_card(shell, colors, padx=14, pady=14, fill=tk.BOTH, expand=True)
        
        tk.Label(
            list_frame, text="好友列表：", 
            font=("微软雅黑", 14, "bold"), 
            bg=colors["surface"],
            fg=colors["text_primary"]
        ).pack(anchor=tk.W, pady=(0, 10))
        
        # 创建滚动框架
        canvas = tk.Canvas(list_frame, bg=colors["surface"], highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg=colors["surface"])
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 显示本机ID及复制按钮
        self.user_id = load_user_id()
        id_frame = tk.Frame(shell, bg=colors["app_bg"])
        id_frame.pack(fill=tk.X, pady=(12, 0))
        id_label = tk.Label(
            id_frame, text=f"我的ID：{self.user_id}（可复制给好友）", 
            font=("微软雅黑", 11),
            bg=colors["app_bg"], fg=colors["text_secondary"]
        )
        id_label.pack(side=tk.LEFT)
        copy_btn = tk.Button(id_frame, text="复制", command=self.copy_user_id, **dialog_button_options(colors))
        copy_btn.pack(side=tk.LEFT, padx=(8,0))
        close_btn = tk.Button(id_frame, text="关闭", command=self.destroy, **dialog_button_options(colors, primary=True))
        close_btn.pack(side=tk.RIGHT)
    
    def add_friend(self):
        """添加好友"""
        friend_id = self.friend_id_var.get().strip()
        if not friend_id:
            messagebox.showwarning("提示", "请输入好友ID")
            return
        # 检查是否已经是好友
        friends = load_friends()
        for friend in friends:
            if friend.get('user_id') == friend_id:
                messagebox.showinfo("提示", "该用户已经是您的好友")
                return
        # 检查是否是自己
        if friend_id == self.user_id:
            messagebox.showwarning("提示", "不能添加自己为好友")
            return
        # 添加好友（离线状态）
        friends.append({
            'user_id': friend_id,
            'nickname': f"用户{friend_id}",
            'online': False,
            'last_seen': datetime.now().isoformat(),
            'ip': None
        })
        save_friends(friends)
        self.friend_id_var.set("")
        self.refresh_friends()
        messagebox.showinfo("成功", f"好友 {friend_id} 添加成功！\n\n好友上线后会自动更新状态。")
    
    def discover_friends(self):
        """发现好友"""
        # 显示发现中的提示
        self.discover_btn.config(state=tk.DISABLED, text="发现中...")
        threading.Thread(target=self._discover_friends_thread, daemon=True).start()
    
    def _discover_friends_thread(self):
        """发现好友线程"""
        self.network_manager.discover_friends()
        # 在主线程中刷新界面
        self.after(100, self._discover_complete)
    
    def _discover_complete(self):
        """发现完成"""
        self.discover_btn.config(state=tk.NORMAL, text="发现好友")
        self.refresh_friends()
        
        # 显示发现结果
        friends = load_friends()
        online_count = sum(1 for f in friends if f.get('online'))
        messagebox.showinfo("发现完成", f"发现完成！\n\n当前好友：{len(friends)} 个\n在线好友：{online_count} 个")
    
    def refresh_friend_status(self):
        """刷新好友状态"""
        friends = load_friends()
        if not friends:
            return
        
        # 在新线程中检查所有好友状态
        threading.Thread(target=self._refresh_status_thread, daemon=True).start()
    
    def _refresh_status_thread(self):
        """刷新状态线程"""
        friends = load_friends()
        for friend in friends:
            friend_id = friend.get('user_id')
            if friend_id:
                self.network_manager.check_friend_online(friend_id)
        
        # 在主线程中刷新界面
        self.after(100, self.refresh_friends)
    
    def refresh_friends(self):
        """刷新好友列表"""
        # 清空现有列表
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        friends = load_friends()
        if not friends:
            # 空状态
            empty_label = tk.Label(
                self.scrollable_frame, 
                text="暂无好友\n点击'发现好友'或手动添加好友ID", 
                font=("微软雅黑", 12),
                bg=self.dialog_colors["surface"],
                fg=self.dialog_colors["text_secondary"],
                justify=tk.CENTER
            )
            empty_label.pack(pady=50)
            return
        
        for friend in friends:
            self.create_friend_item(friend)
    
    def create_friend_item(self, friend):
        """创建好友列表项"""
        colors = self.dialog_colors
        item_frame = tk.Frame(self.scrollable_frame, bg="#ffffff", bd=0, relief=tk.FLAT, 
                             highlightbackground=colors["border"], highlightthickness=1)
        item_frame.pack(pady=5, padx=2, fill=tk.X)
        
        # 好友信息
        info_frame = tk.Frame(item_frame, bg="#ffffff")
        info_frame.pack(pady=10, padx=15, fill=tk.X)
        
        # 状态指示器
        status_color = "#4caf50" if friend.get('online') else "#e0e0e0"
        status_label = tk.Label(
            info_frame, text="●", 
            font=("微软雅黑", 16),
            bg="#ffffff", fg=status_color
        )
        status_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # 好友昵称（可编辑）
        nickname = friend.get('nickname', f"用户{friend.get('user_id', '')}")
        user_id = friend.get('user_id', '')
        # 判断是否为默认昵称
        is_default_nick = nickname == f"用户{user_id}" or nickname == "未知"
        if is_default_nick:
            # 显示为可编辑Entry
            nickname_var = tk.StringVar(value=nickname)
            def save_nickname(event=None, var=nickname_var, f=friend):
                new_nick = var.get().strip()
                if new_nick and new_nick != f"用户{user_id}":
                    f['nickname'] = new_nick
                    friends = load_friends()
                    for ff in friends:
                        if ff.get('user_id') == user_id:
                            ff['nickname'] = new_nick
                    save_friends(friends)
                    self.refresh_friends()
            nickname_entry = tk.Entry(
                info_frame, textvariable=nickname_var, font=("微软雅黑", 12, "bold"),
                bg="#ffffff", fg=colors["text_primary"], width=10, relief=tk.FLAT
            )
            nickname_entry.pack(side=tk.LEFT, padx=(0, 2))
            nickname_entry.bind('<Return>', save_nickname)
            nickname_entry.bind('<FocusOut>', save_nickname)
        else:
            # 普通Label
            info_label = tk.Label(
                info_frame, 
                text=f"{nickname} ({user_id})", 
                font=("微软雅黑", 12, "bold"),
                bg="#ffffff", fg=colors["text_primary"]
            )
            info_label.pack(side=tk.LEFT, padx=(0, 2))
        
        # 状态信息
        status_text = "在线" if friend.get('online') else "离线"
        status_text_label = tk.Label(
            info_frame, text=status_text,
            font=("微软雅黑", 10),
            bg="#ffffff", fg="#888888"
        )
        status_text_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # IP地址信息
        ip_text = f"IP: {friend.get('ip', '未知')}"
        ip_label = tk.Label(
            info_frame, text=ip_text,
            font=("微软雅黑", 9),
            bg="#ffffff", fg="#aaaaaa"
        )
        ip_label.pack(side=tk.LEFT)
        
        # 操作按钮
        btn_frame = tk.Frame(item_frame, bg="#ffffff")
        btn_frame.pack(pady=(0, 10), padx=15, fill=tk.X)
        
        view_btn = tk.Button(
            btn_frame, text="查看数据", 
            command=lambda: self.view_friend_data(friend),
            **dialog_button_options(colors)
        )
        view_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        remind_btn = tk.Button(
            btn_frame, text="发送提醒", 
            command=lambda: self.send_reminder(friend),
            **dialog_button_options(colors, primary=True)
        )
        remind_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        delete_btn = tk.Button(
            btn_frame, text="删除", 
            command=lambda: self.delete_friend(friend),
            **dialog_button_options(colors, danger=True)
        )
        delete_btn.pack(side=tk.LEFT)
    
    def view_friend_data(self, friend):
        """查看好友数据"""
        if not friend.get('online'):
            messagebox.showwarning("提示", "好友离线，无法查看数据")
            return
        
        # 在新线程中获取数据
        threading.Thread(target=self._get_friend_data_thread, args=(friend,), daemon=True).start()
    
    def _get_friend_data_thread(self, friend):
        """获取好友数据线程"""
        data, error = self.network_manager.get_friend_data(friend.get('user_id'))
        
        if error:
            self.after(0, lambda: messagebox.showerror("错误", error))
        else:
            self.after(0, lambda: self.show_friend_data(friend, data))
    
    def show_friend_data(self, friend, data):
        """显示好友数据"""
        colors = self.dialog_colors
        data_window = tk.Toplevel(self)
        data_window.title(f"{friend.get('nickname')}的健康数据")
        apply_safe_window_geometry(data_window, 460, 560, 400, 460, height_ratio=0.82)
        data_window.resizable(True, True)
        data_window.configure(bg=colors["app_bg"])
        data_window.transient(self)
        data_window.grab_set()
        shell = tk.Frame(data_window, bg=colors["app_bg"], padx=18, pady=16)
        shell.pack(fill=tk.BOTH, expand=True)
        create_dialog_header(
            shell,
            f"{friend.get('nickname')}的健康数据",
            "查看好友今天同步到的健康记录。",
            colors,
        )
        data_card = create_dialog_card(shell, colors, padx=12, pady=12, fill=tk.BOTH, expand=True)
        # 数据展示
        canvas = tk.Canvas(data_card, bg=colors["surface"], highlightthickness=0)
        scrollbar = tk.Scrollbar(data_card, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=colors["surface"])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 显示数据
        today = date.today().isoformat()
        today_data = data.get(today, {})
        
        if not today_data:
            empty_label = tk.Label(
                scrollable_frame, text="今日暂无数据", 
                font=("微软雅黑", 12),
                bg=colors["surface"], fg=colors["text_secondary"]
            )
            empty_label.pack(pady=50)
        else:
            for key, times in today_data.items():
                if isinstance(times, list):
                    item_frame = tk.Frame(scrollable_frame, bg="#ffffff", bd=0, relief=tk.FLAT,
                                         highlightbackground=colors["border"], highlightthickness=1)
                    item_frame.pack(pady=5, padx=4, fill=tk.X)
                    
                    name_label = tk.Label(
                        item_frame, text=f"{key}：{len(times)}次", 
                        font=("微软雅黑", 12, "bold"),
                        bg="#ffffff", fg=colors["text_primary"]
                    )
                    name_label.pack(pady=10, padx=15, anchor=tk.W)
                    
                    if times:
                        # 优化：全部显示，自动换行，每行6个时间
                        times_per_line = 6
                        lines = []
                        for i in range(0, len(times), times_per_line):
                            lines.append("、".join(times[i:i+times_per_line]))
                        times_text = "时间：\n" + "\n".join(lines)
                        times_label = tk.Label(
                            item_frame, text=times_text, 
                            font=("微软雅黑", 10),
                            bg="#ffffff", fg="#666666",
                            wraplength=340,  # 自动换行
                            justify=tk.LEFT
                        )
                        times_label.pack(pady=(0, 10), padx=15, anchor=tk.W)
        
        canvas.pack(side="left", fill="both", expand=True, padx=(0, 5))
        scrollbar.pack(side="right", fill="y")
        
        # 发送提醒按钮
        action_row = tk.Frame(shell, bg=colors["app_bg"])
        action_row.pack(fill=tk.X, pady=(12, 0))
        remind_btn = tk.Button(
            action_row, text="发送提醒",
            command=lambda: self.send_reminder_from_data(friend, data_window),
            **dialog_button_options(colors, primary=True)
        )
        remind_btn.pack(side=tk.RIGHT)
    
    def send_reminder_from_data(self, friend, data_window):
        """从数据页面发送提醒"""
        data_window.destroy()
        self.send_reminder(friend)
    
    def send_reminder(self, friend):
        """发送提醒"""
        if not friend.get('online'):
            messagebox.showwarning("提示", "好友离线，无法发送提醒")
            return
        colors = self.dialog_colors
        # 创建提醒输入窗口
        reminder_window = tk.Toplevel(self)
        reminder_window.title("发送提醒")
        apply_safe_window_geometry(reminder_window, 460, 430, 400, 360, height_ratio=0.78)
        reminder_window.resizable(True, True)
        reminder_window.configure(bg=colors["app_bg"])
        reminder_window.transient(self)
        reminder_window.grab_set()
        reminder_window.focus()  # 确保窗口获得焦点
        shell = tk.Frame(reminder_window, bg=colors["app_bg"], padx=18, pady=16)
        shell.pack(fill=tk.BOTH, expand=True)
        create_dialog_header(
            shell,
            f"给 {friend.get('nickname')} 发送提醒",
            "输入一条简短提醒，对方在线时会收到。",
            colors,
        )
        input_card = create_dialog_card(shell, colors, padx=14, pady=14, fill=tk.BOTH, expand=True)
        # 提醒内容输入
        tk.Label(
            input_card, text="提醒内容", 
            font=("微软雅黑", 12), 
            bg=colors["surface"],
            fg=colors["text_primary"]
        ).pack(anchor=tk.W, pady=(0, 8))
        
        text_frame = tk.Frame(input_card, bg=colors["surface"])
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        reminder_text = tk.Text(
            text_frame, 
            font=("微软雅黑", 11),
            relief=tk.FLAT, bg="#ffffff", fg=colors["text_primary"],
            highlightbackground=colors["border"],
            highlightcolor=colors["primary"],
            highlightthickness=1, bd=0,
            height=8  # 设置固定高度
        )
        reminder_text.pack(fill=tk.BOTH, expand=True)
        
        # 按钮区域
        btn_frame = tk.Frame(shell, bg=colors["app_bg"])
        btn_frame.pack(pady=(12, 0), fill=tk.X)
        
        # 发送按钮
        send_btn = tk.Button(
            btn_frame, text="发送", 
            command=lambda: self._send_reminder_thread(friend, reminder_text.get("1.0", tk.END).strip(), reminder_window),
            **dialog_button_options(colors, primary=True)
        )
        send_btn.pack(side=tk.RIGHT)
        
        # 取消按钮
        cancel_btn = tk.Button(
            btn_frame, text="取消", 
            command=reminder_window.destroy,
            **dialog_button_options(colors)
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(0, 10))
        
        # 绑定回车键发送
        reminder_text.bind('<Control-Return>', lambda e: self._send_reminder_thread(friend, reminder_text.get("1.0", tk.END).strip(), reminder_window))
        
        # 设置焦点到文本框
        reminder_text.focus()
    
    def _send_reminder_thread(self, friend, text, window):
        """发送提醒线程"""
        if not text:
            messagebox.showwarning("提示", "请输入提醒内容")
            return
        
        success, message = self.network_manager.send_reminder(friend.get('user_id'), text)
        window.destroy()
        
        if success:
            messagebox.showinfo("成功", message)
        else:
            messagebox.showerror("失败", message)
    
    def delete_friend(self, friend):
        """删除好友"""
        if messagebox.askyesno("确认", f"确定要删除好友 {friend.get('nickname')} 吗？"):
            friends = load_friends()
            friends = [f for f in friends if f.get('user_id') != friend.get('user_id')]
            save_friends(friends)
            self.refresh_friends()
            messagebox.showinfo("成功", "好友已删除")

    def copy_user_id(self):
        self.clipboard_clear()
        self.clipboard_append(self.user_id)
        messagebox.showinfo("已复制", "用户ID已复制到剪贴板")

# ========== 健康知识库与AI助手 ==========
HEALTH_TIPS_FILE = os.path.join(RESOURCE_DIR, "health_tips.json")
AI_QA_FILE = os.path.join(RESOURCE_DIR, "ai_qa.json")

def load_health_tips():
    try:
        return load_json_from_resource("health_tips.json", {})
    except Exception as e:
        log(f"加载健康知识库异常：{e}")
        return {}

def get_random_health_tip(tip_type=None):
    tips_dict = load_health_tips()
    if isinstance(tips_dict, dict):
        if tip_type and tip_type in tips_dict and tips_dict[tip_type]:
            return random.choice(tips_dict[tip_type])
        # 若未指定类型或该类型无内容，则从所有场景中随机选一条
        all_tips = []
        for tips in tips_dict.values():
            all_tips.extend(tips)
        if all_tips:
            return random.choice(all_tips)
    return "保持健康，从点滴做起！"

def load_ai_qa():
    try:
        return load_json_from_resource("ai_qa.json", [])
    except Exception as e:
        log(f"加载AI问答库异常：{e}")
        return []

def ai_answer(question, nickname=None):
    """本地AI助手：关键词匹配，返回答案"""
    qa_list = load_ai_qa()
    q = question.strip().lower()
    for qa in qa_list:
        if any(kw in q for kw in qa.get("keywords", [])):
            ans = qa.get("answer", "")
            if nickname:
                ans = ans.replace("{nickname}", nickname)
            return ans
    return "暂未收录该问题，欢迎反馈！"

# ========== AI健康助手对话弹窗 ==========
class AIHealthAssistantDialog(tk.Toplevel):
    def __init__(self, master, nickname):
        super().__init__(master)
        self.title("AI健康助手")
        self.resizable(True, True)
        self._configure_window_geometry()
        self.nickname = nickname
        self.theme_colors = get_theme_colors()
        self.dialog_colors = get_dashboard_colors(self.theme_colors)
        self.configure(bg=self.dialog_colors["app_bg"])
        self.transient(master)
        self.grab_set()
        self.focus()
        self.lift()
        self.create_widgets()

    def _configure_window_geometry(self):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(680, max(460, screen_width - 80))
        height = min(560, max(400, screen_height - 120))
        min_width = min(460, width)
        min_height = min(400, height)
        self.minsize(min_width, min_height)
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def create_widgets(self):
        colors = self.dialog_colors
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        shell = tk.Frame(self, bg=colors["app_bg"], padx=18, pady=16)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        header = create_dialog_header(
            shell,
            "AI 健康助手",
            "可咨询喝水、护眼、久坐、运动、压力和饮食建议。",
            colors,
        )
        header.pack_forget()
        header.grid(row=0, column=0, sticky="ew")
        chat_card = tk.Frame(shell, bg=colors["surface"], padx=12, pady=12,
                             highlightbackground=colors["border"], highlightthickness=1)
        chat_card.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        chat_card.grid_columnconfigure(0, weight=1)
        chat_card.grid_rowconfigure(0, weight=1)
        self.text_area = tk.Text(
            chat_card, font=("微软雅黑", 11), height=14, width=56,
            bg=colors["surface"], fg=colors["text_primary"], state=tk.DISABLED,
            wrap=tk.WORD, relief=tk.FLAT, bd=0,
        )
        self.text_area.grid(row=0, column=0, sticky="nsew")
        chat_scrollbar = tk.Scrollbar(chat_card, orient=tk.VERTICAL, command=self.text_area.yview)
        chat_scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.text_area.configure(yscrollcommand=chat_scrollbar.set)
        input_frame = tk.Frame(shell, bg=colors["app_bg"])
        input_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        input_frame.grid_columnconfigure(0, weight=1)
        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            input_frame, textvariable=self.input_var, font=("微软雅黑", 12),
            relief=tk.FLAT, bd=0, bg=colors["surface"], fg=colors["text_primary"],
            highlightbackground=colors["border"], highlightcolor=colors["primary"],
            highlightthickness=1,
        )
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10), ipady=8)
        send_btn = tk.Button(input_frame, text="发送", command=self.on_send, **dialog_button_options(colors, primary=True))
        send_btn.grid(row=0, column=1, sticky="e", ipadx=8, ipady=7)
        self.input_entry.bind('<Return>', lambda e: self.on_send())
        self.input_entry.focus()
        self.append_text("AI健康助手：可以问我喝水、久坐、护眼、运动、压力、饮食相关问题。")
    def on_send(self):
        q = self.input_var.get().strip()
        if not q:
            return
        self.append_text(f"你：{q}")
        ans = ai_answer(q, self.nickname)
        self.append_text(f"AI健康助手：{ans}")
        self.input_var.set("")
    def append_text(self, text):
        self.text_area.config(state=tk.NORMAL)
        self.text_area.insert(tk.END, text + "\n")
        self.text_area.see(tk.END)
        self.text_area.config(state=tk.DISABLED)

if __name__ == "__main__":
    try:
        log("主程序启动")
        if "--launch-eye-training" in sys.argv:
            launch_eye_training_window(autostart="--autostart" in sys.argv)
            sys.exit(0)

        enable_windows_dpi_awareness()
        root = tk.Tk()
        
        # 加载用户配置
        user_config = load_user_config()
        is_first_run = user_config.get("first_run", True)
        nickname = user_config.get("nickname", "")
        theme = user_config.get("theme", DEFAULT_THEME)
        topmost = user_config.get("topmost", True)
        autostart = is_autostart_enabled()
        reminders, sleep_cfg, challenge_cfg = load_reminder_settings()
        
        if is_first_run:
            # 首次进入，弹出设置页面，设置完成后进入主页面
            def on_first_settings_save(nickname, reminders, topmost, autostart, theme, sleep_cfg, challenge_cfg):
                # 保存用户配置
                save_user_config_fields(
                    nickname=nickname,
                    first_run=False,
                    topmost=topmost,
                    theme=theme,
                    desktop_pet_autostart=get_desktop_pet_autostart(),
                )
                start_main_app(root, nickname, reminders, topmost, autostart, theme, sleep_cfg, challenge_cfg)
            SettingsPage(root, nickname, reminders, topmost, autostart, theme, on_first_settings_save, sleep_cfg, challenge_cfg, get_desktop_pet_autostart(user_config))
        else:
            # 非首次直接进入主页面
            start_main_app(root, nickname, reminders, topmost, autostart, theme, sleep_cfg, challenge_cfg)
        
        root.mainloop()
        log("主循环结束")
    except Exception as e:
        log_exception(e)
        messagebox.showerror("错误", "程序发生异常，请查看日志文件并联系开发者：\n{}".format(LOG_FILE))

