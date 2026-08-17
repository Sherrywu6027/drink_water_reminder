import json
import socket
import threading
import time
from datetime import datetime

from app_storage import (
    CHAT_PORT,
    BROADCAST_ADDR,
    DISCOVERY_PORT,
    can_send_reminder,
    load_friends,
    load_shareable_data,
    load_user_id,
    load_user_permissions,
    log,
    record_reminder_sent,
    save_friends,
)
from protocol_helpers import recv_json_message, send_json_message


class FriendNetworkManager:
    """好友网络管理器"""

    def __init__(
        self,
        nickname,
        on_friend_reminder=None,
        sleep_periods=None,
        is_sleeping_func=None,
    ):
        self.nickname = nickname
        self.user_id = load_user_id()
        self.on_friend_reminder = on_friend_reminder
        self.is_sleeping_func = is_sleeping_func or (lambda periods: False)
        self.discovery_socket = None
        self.chat_socket = None
        self.running = False
        self.friends = load_friends()
        if sleep_periods:
            self.sleep_periods = [dict(p) for p in sleep_periods]
        else:
            self.sleep_periods = [{"start": "23:00", "end": "07:00"}]

    def _reload_friends(self):
        self.friends = load_friends()
        return self.friends

    def _find_friend(self, friend_id):
        for friend in self.friends:
            if friend.get("user_id") == friend_id:
                return friend
        return None

    def _get_friend_ip(self, friend_id):
        self._reload_friends()
        friend = self._find_friend(friend_id)
        if not friend:
            return None
        return friend.get("ip")

    def start(self):
        self.running = True
        threading.Thread(target=self._start_discovery_service, daemon=True).start()
        threading.Thread(target=self._start_chat_service, daemon=True).start()
        log("好友网络服务已启动")

    def stop(self):
        self.running = False
        if self.discovery_socket:
            self.discovery_socket.close()
        if self.chat_socket:
            self.chat_socket.close()
        log("好友网络服务已停止")

    def _start_discovery_service(self):
        try:
            self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.discovery_socket.bind(("", DISCOVERY_PORT))
            while self.running:
                try:
                    data, addr = self.discovery_socket.recvfrom(1024)
                    message = json.loads(data.decode("utf-8"))
                    if message.get("type") == "discover":
                        response = {
                            "type": "discover_response",
                            "user_id": self.user_id,
                            "nickname": self.nickname,
                        }
                        self.discovery_socket.sendto(
                            json.dumps(response).encode("utf-8"), addr
                        )
                    elif message.get("type") == "discover_response":
                        friend_id = message.get("user_id")
                        friend_nickname = message.get("nickname")
                        self._update_friend_status(friend_id, friend_nickname, True)
                except Exception as e:
                    log(f"好友发现服务异常：{e}")
        except Exception as e:
            log(f"启动好友发现服务失败：{e}")

    def _start_chat_service(self):
        try:
            self.chat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.chat_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.chat_socket.bind(("", CHAT_PORT))
            self.chat_socket.listen(5)
            while self.running:
                try:
                    client_socket, _ = self.chat_socket.accept()
                    threading.Thread(
                        target=self._handle_chat_client,
                        args=(client_socket,),
                        daemon=True,
                    ).start()
                except Exception as e:
                    if self.running:
                        log(f"聊天服务异常：{e}")
        except Exception as e:
            log(f"启动聊天服务失败：{e}")

    def _handle_chat_client(self, client_socket):
        try:
            message = recv_json_message(client_socket)
            if message.get("type") == "reminder":
                friend_nickname = message.get("from_nickname")
                reminder_text = message.get("text")
                if self.is_sleeping_func(self.sleep_periods):
                    response = {"type": "reminder_response", "status": "sleeping"}
                else:
                    response = {"type": "reminder_response", "status": "success"}
                    if self.on_friend_reminder:
                        self.on_friend_reminder(friend_nickname, reminder_text)
                send_json_message(client_socket, response)
            elif message.get("type") == "get_data":
                permissions = load_user_permissions()
                if permissions.get("allow_data_view"):
                    response = {
                        "type": "data_response",
                        "data": load_shareable_data(),
                    }
                else:
                    response = {
                        "type": "data_response",
                        "error": "permission_denied",
                    }
                send_json_message(client_socket, response)
        except Exception as e:
            log(f"处理聊天客户端异常：{e}")
        finally:
            client_socket.close()

    def _update_friend_status(self, friend_id, nickname, online, ip=None):
        self._reload_friends()
        for friend in self.friends:
            if friend.get("user_id") == friend_id:
                friend["online"] = online
                friend["last_seen"] = datetime.now().isoformat()
                if ip:
                    friend["ip"] = ip
                if nickname and nickname != friend.get("nickname"):
                    friend["nickname"] = nickname
                save_friends(self.friends)
                return

        self.friends.append(
            {
                "user_id": friend_id,
                "nickname": nickname,
                "online": online,
                "last_seen": datetime.now().isoformat(),
                "ip": ip,
            }
        )
        save_friends(self.friends)

    def send_reminder(self, friend_id, text):
        try:
            if not can_send_reminder(friend_id):
                return False, "发送过于频繁，请稍后再试"

            friend_ip = self._get_friend_ip(friend_id)
            if not friend_ip:
                return False, "好友离线或未找到"

            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5)
            client_socket.connect((friend_ip, CHAT_PORT))
            message = {
                "type": "reminder",
                "from_user_id": self.user_id,
                "from_nickname": self.nickname,
                "text": text,
            }
            send_json_message(client_socket, message)
            response_data = recv_json_message(client_socket)
            client_socket.close()
            if response_data.get("status") == "success":
                record_reminder_sent(friend_id)
                return True, "提醒发送成功"
            if response_data.get("status") == "sleeping":
                return False, "好友正在休眠时段"
            return False, "发送失败"
        except Exception as e:
            self._update_friend_status(friend_id, None, False)
            log(f"发送提醒异常：{e}")
            return False, "网络连接失败"

    def discover_friends(self):
        try:
            discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            discovery_socket.settimeout(3)
            message = {
                "type": "discover",
                "user_id": self.user_id,
                "nickname": self.nickname,
            }
            discovery_socket.sendto(
                json.dumps(message).encode("utf-8"),
                (BROADCAST_ADDR, DISCOVERY_PORT),
            )
            start_time = time.time()
            while time.time() - start_time < 3:
                try:
                    data, addr = discovery_socket.recvfrom(1024)
                    response = json.loads(data.decode("utf-8"))
                    if response.get("type") == "discover_response":
                        friend_id = response.get("user_id")
                        friend_nickname = response.get("nickname")
                        if friend_id != self.user_id:
                            self._update_friend_status(
                                friend_id, friend_nickname, True, addr[0]
                            )
                except socket.timeout:
                    break
                except Exception as e:
                    log(f"发现好友响应异常：{e}")
            discovery_socket.close()
        except Exception as e:
            log(f"发现好友异常：{e}")

    def check_friend_online(self, friend_id):
        try:
            friend_ip = self._get_friend_ip(friend_id)
            if not friend_ip:
                return False
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(2)
            client_socket.connect((friend_ip, CHAT_PORT))
            client_socket.close()
            self._update_friend_status(friend_id, None, True, friend_ip)
            return True
        except Exception:
            self._update_friend_status(friend_id, None, False)
            return False

    def get_friend_data(self, friend_id):
        try:
            friend_ip = self._get_friend_ip(friend_id)
            if not friend_ip:
                return None, "好友离线或未找到"
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5)
            client_socket.connect((friend_ip, CHAT_PORT))
            message = {"type": "get_data", "from_user_id": self.user_id}
            send_json_message(client_socket, message)
            response_data = recv_json_message(client_socket)
            client_socket.close()
            if "error" in response_data:
                return None, response_data["error"]
            return response_data.get("data", {}), None
        except Exception as e:
            self._update_friend_status(friend_id, None, False)
            log(f"获取好友数据异常：{e}")
            return None, "网络连接失败"
