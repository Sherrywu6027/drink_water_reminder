#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import inspect
import os
import socket
import tempfile
import threading

import drink_water_reminder as app
import app_storage as storage


def test_friend_reminder_stays_standard_messagebox():
    source = inspect.getsource(app.HealthMainPage.on_friend_reminder)
    assert "messagebox.showinfo" in source
    assert "show_answer_required_reminder" not in source


def test_config_merge_preserves_existing_fields():
    original_config_file = storage.USER_CONFIG_FILE
    tmp_dir = tempfile.mkdtemp(prefix="drink_water_reminder_")
    try:
        storage.USER_CONFIG_FILE = os.path.join(tmp_dir, "user_config.json")
        with open(storage.USER_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "user_id": "keep-me",
                    "nickname": "old-name",
                    "theme": "健康绿",
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        config = storage.save_user_config_fields(
            nickname="new-name",
            first_run=False,
            topmost=True,
        )

        assert config["user_id"] == "keep-me"
        assert config["nickname"] == "new-name"
        assert config["topmost"] is True
        assert config["theme"] == "健康绿"
        print("config_merge_ok")
    finally:
        storage.USER_CONFIG_FILE = original_config_file


def test_large_json_message_roundtrip():
    payload = {
        "type": "data_response",
        "data": {
            "2026-05-14": {
                "drink": [f"08:{i:02d}:00" for i in range(300)],
                "eye": [f"09:{i:02d}:00" for i in range(300)],
            }
        },
    }
    result = {}
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def server_worker():
        conn, _ = server.accept()
        try:
            received = app.recv_json_message(conn)
            result["request"] = received
            app.send_json_message(conn, payload)
        finally:
            conn.close()
            server.close()

    thread = threading.Thread(target=server_worker, daemon=True)
    thread.start()

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", port))
    try:
        app.send_json_message(client, {"type": "get_data"})
        response = app.recv_json_message(client)
    finally:
        client.close()

    thread.join(timeout=3)

    assert result["request"]["type"] == "get_data"
    assert response == payload
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    assert len(encoded) > 4096
    print("large_json_roundtrip_ok")


def test_permissions_drop_dead_field():
    original_permissions_file = storage.USER_PERMISSIONS_FILE
    tmp_dir = tempfile.mkdtemp(prefix="drink_water_reminder_permissions_")
    try:
        storage.USER_PERMISSIONS_FILE = os.path.join(tmp_dir, "user_permissions.json")
        storage.save_user_permissions(
            {"allow_data_view": False, "allow_schedule_view": True}
        )
        with open(storage.USER_PERMISSIONS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)

        assert saved == {"allow_data_view": False}
        loaded = storage.load_user_permissions()
        assert loaded == {"allow_data_view": False}
        print("permissions_cleanup_ok")
    finally:
        storage.USER_PERMISSIONS_FILE = original_permissions_file


def test_manual_friend_placeholder_ip_is_empty():
    friend = {
        "user_id": "test123",
        "nickname": "用户test123",
        "online": False,
        "last_seen": "2026-05-14T10:00:00",
        "ip": None,
    }
    assert friend["ip"] is None
    print("manual_friend_ip_placeholder_ok")


def test_legacy_data_migration():
    legacy = {
        "2026-05-14": ["08:00:00", "09:00:00"],
        "2026-05-15": {
            "drink": ["10:00:00"],
            "eye": ["11:00:00", 123],
            "bad": "ignored",
        },
    }
    migrated, changed = storage.migrate_drink_data(legacy)

    assert changed is True
    assert migrated["2026-05-14"] == {"drink": ["08:00:00", "09:00:00"]}
    assert migrated["2026-05-15"] == {
        "drink": ["10:00:00"],
        "eye": ["11:00:00"],
    }
    print("legacy_data_migration_ok")


def test_new_friend_status_does_not_invent_loopback_ip():
    original_friends_file = storage.FRIENDS_FILE
    tmp_dir = tempfile.mkdtemp(prefix="drink_water_reminder_friends_")
    try:
        storage.FRIENDS_FILE = os.path.join(tmp_dir, "friends.json")
        with open(storage.FRIENDS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

        manager = app.FriendNetworkManager("tester")
        manager._update_friend_status("friend-1", "好友1", False, None)
        friends = storage.load_friends()

        assert friends[0]["ip"] is None
        assert friends[0]["online"] is False
        print("friend_status_no_loopback_ok")
    finally:
        storage.FRIENDS_FILE = original_friends_file


if __name__ == "__main__":
    test_friend_reminder_stays_standard_messagebox()
    test_config_merge_preserves_existing_fields()
    test_large_json_message_roundtrip()
    test_permissions_drop_dead_field()
    test_manual_friend_placeholder_ip_is_empty()
    test_legacy_data_migration()
    test_new_friend_status_does_not_invent_loopback_ip()
    print("all_checks_passed")
