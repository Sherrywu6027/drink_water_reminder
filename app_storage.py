import json
import logging
import os
import shutil
import sys
import uuid
from datetime import datetime, timedelta


if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = APP_DIR
DATA_FILE = os.path.join(APP_DIR, "drink_data.json")
USER_CONFIG_FILE = os.path.join(APP_DIR, "user_config.json")
SETTINGS_FILE = os.path.join(APP_DIR, "reminder_settings.json")
FRIENDS_FILE = os.path.join(APP_DIR, "friends.json")
FRIEND_REMINDERS_FILE = os.path.join(APP_DIR, "friend_reminders.json")
USER_PERMISSIONS_FILE = os.path.join(APP_DIR, "user_permissions.json")
APP_NAME = "HealthAssistant"
DISCOVERY_PORT = 8888
CHAT_PORT = 8889
BROADCAST_ADDR = "255.255.255.255"
LOG_FILE = os.path.join(APP_DIR, "error.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def log(msg):
    print(f"[LOG] {msg}")


def log_exception(e):
    logging.error("Exception occurred", exc_info=e)


def resource_path(*parts):
    return os.path.join(RESOURCE_DIR, *parts)


def load_json_file(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log(f"加载JSON文件异常 {path}: {e}")
    return default


def load_json_from_resource(filename, default):
    path = resource_path(filename)
    return load_json_file(path, default)


def save_user_config_fields(**updates):
    config = load_json_file(USER_CONFIG_FILE, {})
    if not isinstance(config, dict):
        config = {}
    config.update(updates)
    with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return config


def backup_file(path, suffix):
    if not os.path.exists(path):
        return None
    backup_path = f"{path}.{suffix}"
    shutil.copy2(path, backup_path)
    return backup_path


def normalize_day_data(day_value):
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


def generate_user_id():
    return str(uuid.uuid4())[:8]


def load_user_id(load_user_config_func=None):
    try:
        if os.path.exists(USER_CONFIG_FILE):
            with open(USER_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                if "user_id" in config:
                    return config["user_id"]
    except Exception as e:
        log(f"加载用户ID异常：{e}")

    user_id = generate_user_id()
    try:
        if load_user_config_func:
            config = load_user_config_func()
            if not isinstance(config, dict):
                config = {}
            config["user_id"] = user_id
            with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        else:
            save_user_config_fields(user_id=user_id)
    except Exception as e:
        log(f"保存用户ID异常：{e}")

    return user_id


def load_friends():
    try:
        if os.path.exists(FRIENDS_FILE):
            with open(FRIENDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except Exception as e:
        log(f"加载好友列表异常：{e}")
        return []


def save_friends(friends):
    try:
        with open(FRIENDS_FILE, "w", encoding="utf-8") as f:
            json.dump(friends, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"保存好友列表异常：{e}")


def load_friend_reminders():
    try:
        if os.path.exists(FRIEND_REMINDERS_FILE):
            with open(FRIEND_REMINDERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        log(f"加载好友提醒记录异常：{e}")
        return {}


def save_friend_reminders(reminders):
    try:
        with open(FRIEND_REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(reminders, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"保存好友提醒记录异常：{e}")


def load_user_permissions():
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
    reminders = load_friend_reminders()
    user_id = load_user_id()
    key = f"{user_id}_{friend_id}"
    if key in reminders:
        last_time = datetime.fromisoformat(reminders[key])
        if datetime.now() - last_time < timedelta(minutes=10):
            return False
    return True


def record_reminder_sent(friend_id):
    reminders = load_friend_reminders()
    user_id = load_user_id()
    key = f"{user_id}_{friend_id}"
    reminders[key] = datetime.now().isoformat()
    save_friend_reminders(reminders)


def load_shareable_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"获取分享数据异常：{e}")
        return {}
