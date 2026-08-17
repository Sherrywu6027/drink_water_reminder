import json
import inspect
import os
import random
import tempfile

import drink_water_reminder as app

from reminder_challenge import (
    generate_math_challenge,
    is_correct_answer,
    normalize_challenge_config,
)


def test_config_defaults_and_validation():
    assert normalize_challenge_config(None) == {
        "answer_required": False,
        "snooze_minutes": 5,
        "max_snooze_count": 2,
    }
    assert normalize_challenge_config({
        "answer_required": True,
        "snooze_minutes": "bad",
        "max_snooze_count": -1,
    }) == {
        "answer_required": True,
        "snooze_minutes": 5,
        "max_snooze_count": 2,
    }
    assert normalize_challenge_config({
        "snooze_minutes": True,
        "max_snooze_count": False,
    }) == {
        "answer_required": False,
        "snooze_minutes": 5,
        "max_snooze_count": 2,
    }


def test_generated_answers_are_two_or_three_digits():
    rng = random.Random(20260803)
    for _ in range(500):
        expression, answer = generate_math_challenge(rng)
        assert isinstance(expression, str)
        assert 10 <= answer <= 999
        assert any(operator in expression for operator in ("+", "-", "×"))


def test_answer_validation():
    assert is_correct_answer(" 42 ", 42) is True
    assert is_correct_answer("41", 42) is False
    assert is_correct_answer("4.2", 42) is False
    assert is_correct_answer("", 42) is False
    assert is_correct_answer(None, 42) is False


def test_map_handler_does_not_force_restore_or_focus():
    source = inspect.getsource(app.HealthMainPage.restore_main_window)
    assert 'state() != "normal"' in source
    assert "deiconify" not in source
    assert "focus_force" not in source


def test_main_window_has_explicit_visible_start_state():
    init_source = inspect.getsource(app.HealthMainPage.__init__)
    show_source = inspect.getsource(app.HealthMainPage._show_main_window_on_start)
    assert 'title("健康助手")' in init_source
    assert "_show_main_window_on_start()" in init_source
    assert 'state("normal")' in show_source
    assert "deiconify()" in show_source
    assert "geometry(" in show_source
    assert "focus_force" not in show_source
    assert "after(200, self._ensure_visible_after_start)" in show_source
    assert "after(1000, self._ensure_visible_after_start)" in show_source
    delayed_source = inspect.getsource(app.HealthMainPage._ensure_visible_after_start)
    assert 'state("normal")' in delayed_source
    assert "deiconify()" in delayed_source
    assert "focus_force" not in delayed_source


def test_legacy_settings_default_challenge_off():
    original = app.SETTINGS_FILE
    temp_dir = tempfile.mkdtemp(prefix="reminder_challenge_settings_")
    try:
        app.SETTINGS_FILE = os.path.join(temp_dir, "reminder_settings.json")
        with open(app.SETTINGS_FILE, "w", encoding="utf-8") as handle:
            json.dump([
                {"key": "drink", "name": "喝水", "interval": 30, "enabled": True, "msg": "喝水"},
                {"sleep_periods": [{"start": "23:00", "end": "07:00"}]},
            ], handle, ensure_ascii=False)
        _, _, challenge_cfg = app.load_reminder_settings()
        assert challenge_cfg["answer_required"] is False
    finally:
        app.SETTINGS_FILE = original


def test_challenge_settings_round_trip():
    original = app.SETTINGS_FILE
    temp_dir = tempfile.mkdtemp(prefix="reminder_challenge_settings_")
    try:
        app.SETTINGS_FILE = os.path.join(temp_dir, "reminder_settings.json")
        app.save_reminder_settings([], {"sleep_periods": []}, {
            "answer_required": True,
            "snooze_minutes": 5,
            "max_snooze_count": 2,
        })
        _, _, challenge_cfg = app.load_reminder_settings()
        assert challenge_cfg == {
            "answer_required": True,
            "snooze_minutes": 5,
            "max_snooze_count": 2,
        }
    finally:
        app.SETTINGS_FILE = original


def test_answer_window_has_safety_controls():
    source = inspect.getsource(app.HealthMainPage.show_answer_required_reminder)
    assert 'attributes("-fullscreen", True)' in source
    assert 'attributes("-topmost", True)' in source
    assert 'protocol("WM_DELETE_WINDOW"' in source
    assert 'bind("<Escape>"' in source
    assert 'bind("<Alt-F4>"' in source
    assert "完成并关闭" in source
    assert "稍后提醒" in source
    assert "答案不正确，请重新计算" in source
    assert "_open_eye_training_from_reminder(win, reminders)" in source


def test_answer_window_cleanup_guards():
    complete = inspect.getsource(app.HealthMainPage._complete_answer_reminder)
    snooze = inspect.getsource(app.HealthMainPage._snooze_answer_reminder)
    for source in (complete, snooze):
        assert "grab_release" in source
        assert "except tk.TclError" in source
        assert "destroy" in source


class FakeRoot:
    def __init__(self):
        self.calls = []

    def after(self, delay, callback):
        self.calls.append((delay, callback))
        return f"after-{len(self.calls)}"


def test_snooze_uses_five_minutes_without_rescheduling_normal_cycle():
    page = object.__new__(app.HealthMainPage)
    page.root = FakeRoot()
    page.challenge_cfg = {
        "answer_required": True,
        "snooze_minutes": 5,
        "max_snooze_count": 2,
    }
    reminders = [{"key": "drink", "enabled": True, "interval": 30}]
    page._redisplay_snoozed_batch(reminders, 1)
    assert page.root.calls[0][0] == 5 * 60 * 1000


def test_finish_batch_reschedules_each_unique_key_once():
    page = object.__new__(app.HealthMainPage)
    scheduled = []
    page.schedule_reminder = scheduled.append
    page._finish_reminder_batch([
        {"key": "drink"}, {"key": "drink"}, {"key": "eye"}
    ])
    assert scheduled == ["drink", "eye"]


def test_pomodoro_suppresses_health_reminders_and_reschedules_next_cycle():
    page = object.__new__(app.HealthMainPage)
    page.root = FakeRoot()
    page.desktop_pet_window = None
    page.pet_pomodoro_after_id = None
    page.pet_pomodoro_end_time = app.datetime.now() + app.timedelta(seconds=60)
    scheduled = []
    page.schedule_reminder = scheduled.append

    reminders = [{"key": "drink"}, {"key": "drink"}, {"key": "eye"}]
    assert page.suppress_health_reminder_during_pomodoro(reminders) is True
    assert scheduled == ["drink", "eye"]
    assert page.root.calls[0][0] == 1000


def test_health_reminder_window_lifecycle_contracts():
    init_source = inspect.getsource(app.HealthMainPage.__init__)
    assert "self.active_health_reminders = []" in init_source
    assert 'self.root.bind("<Unmap>", self._on_root_unmap, add="+")' in init_source
    for method_name in (
        "_register_health_reminder", "_unregister_health_reminder",
        "_sync_reminder_windows_for_root_state", "show_standard_health_reminder",
    ):
        assert hasattr(app.HealthMainPage, method_name)

    batch_source = inspect.getsource(app.HealthMainPage._show_reminder_batch)
    remind_source = inspect.getsource(app.HealthMainPage.remind)
    standard_source = inspect.getsource(app.HealthMainPage.show_standard_health_reminder)
    assert "self.show_standard_health_reminder(" in batch_source
    assert "self.suppress_health_reminder_during_pomodoro(reminders)" in batch_source
    assert "self.is_pet_pomodoro_active()" in remind_source
    assert "self.suppress_health_reminder_during_pomodoro(reminders)" in standard_source
    assert 'messagebox.showinfo("健康提醒"' not in batch_source
    answer_source = inspect.getsource(app.HealthMainPage.show_answer_required_reminder)
    eye_source = inspect.getsource(app.HealthMainPage.show_eye_reminder_with_link)
    assert "self._register_health_reminder(win)" in answer_source
    assert "self._register_health_reminder(win)" in eye_source
    assert "self.suppress_health_reminder_during_pomodoro(reminders)" in answer_source
    assert "self.suppress_health_reminder_during_pomodoro([{\"key\": \"eye\"}])" in eye_source
    assert "self.show_standard_health_reminder(reminders, msg, tip)" in answer_source


def test_health_reminder_cleanup_preserves_answer_and_snooze_paths():
    complete = inspect.getsource(app.HealthMainPage._complete_answer_reminder)
    snooze = inspect.getsource(app.HealthMainPage._snooze_answer_reminder)
    for source in (complete, snooze):
        assert "self._unregister_health_reminder(win)" in source
        assert "win.destroy()" in source
    register = inspect.getsource(app.HealthMainPage._register_health_reminder)
    unregister = inspect.getsource(app.HealthMainPage._unregister_health_reminder)
    sync = inspect.getsource(app.HealthMainPage._sync_reminder_windows_for_root_state)
    assert 'win.bind("<Destroy>"' in register
    assert 'win.bind("<Map>"' in register
    assert "self.active_health_reminders.remove(win)" in unregister
    assert "win.deiconify()" in sync
    assert "win.lift()" in sync
    assert "win.iconify()" not in sync


class FakeReminderWindow:
    def __init__(self, name):
        self.name = name
        self.bindings = {}
        self.calls = []
        self.exists = True
        self.topmost = False

    def bind(self, event_name, callback, add=None):
        self.bindings[event_name] = callback

    def attributes(self, name, value=None):
        if value is not None:
            self.topmost = bool(value)
        return self.topmost

    def winfo_exists(self):
        return self.exists

    def iconify(self): self.calls.append("iconify")
    def deiconify(self): self.calls.append("deiconify")
    def lift(self): self.calls.append("lift")
    def grab_set(self): self.calls.append("grab_set")
    def grab_release(self): self.calls.append("grab_release")
    def focus_force(self): self.calls.append("focus_force")
    def destroy(self):
        self.calls.append("destroy")
        self.exists = False


class FakeLifecycleRoot:
    def __init__(self, state="normal"):
        self.current_state = state
        self.calls = []

    def state(self): return self.current_state
    def deiconify(self):
        self.calls.append("deiconify")
        self.current_state = "normal"
    def lift(self): self.calls.append("lift")
    def after_idle(self, callback): callback()


def test_register_restores_minimized_root_before_reminder_is_shown():
    page = object.__new__(app.HealthMainPage)
    page.root = FakeLifecycleRoot("iconic")
    page.closing = False
    page.active_health_reminders = []
    win = FakeReminderWindow("A")
    page._register_health_reminder(win)
    assert page.root.calls[:2] == ["deiconify", "lift"]
    event = type("Event", (), {"widget": win})()
    win.bindings["<Map>"](event)
    assert page.root.calls == ["deiconify", "lift"]


def test_sync_restores_all_but_focuses_latest_reminder_only():
    page = object.__new__(app.HealthMainPage)
    page.root = FakeLifecycleRoot("normal")
    page.closing = False
    first = FakeReminderWindow("A")
    latest = FakeReminderWindow("B")
    page.active_health_reminders = [first, latest]
    page._sync_reminder_windows_for_root_state()
    page._sync_reminder_windows_for_root_state()
    assert first.calls.count("deiconify") == 2
    assert latest.calls.count("deiconify") == 2
    assert first.calls.count("grab_set") == 0
    assert first.calls.count("focus_force") == 0
    assert latest.calls.count("grab_set") == 2
    assert latest.calls.count("focus_force") == 2


def test_sync_restores_root_and_reminder_when_root_is_minimized():
    page = object.__new__(app.HealthMainPage)
    page.root = FakeLifecycleRoot("iconic")
    page.closing = False
    reminder = FakeReminderWindow("answer")
    page.active_health_reminders = [reminder]

    page._sync_reminder_windows_for_root_state()

    assert page.root.current_state == "normal"
    assert page.root.calls[:2] == ["deiconify", "lift"]
    assert "iconify" not in reminder.calls
    assert reminder.calls[:2] == ["deiconify", "lift"]
    assert reminder.calls[-2:] == ["grab_set", "focus_force"]


def test_answer_terminal_actions_are_once_only_and_mutually_exclusive():
    page = object.__new__(app.HealthMainPage)
    page.active_health_reminders = []
    completed = []
    snoozed = []
    page._finish_reminder_batch = lambda reminders: completed.append(reminders)
    page._redisplay_snoozed_batch = lambda reminders, count: snoozed.append((reminders, count))
    reminders = [{"key": "drink"}]
    win = FakeReminderWindow("answer")
    page.active_health_reminders.append(win)
    page._complete_answer_reminder(win, reminders)
    page._complete_answer_reminder(win, reminders)
    page._snooze_answer_reminder(win, reminders, 0)
    assert len(completed) == 1
    assert snoozed == []

    second = FakeReminderWindow("snooze")
    page.active_health_reminders.append(second)
    page._snooze_answer_reminder(second, reminders, 0)
    page._complete_answer_reminder(second, reminders)
    page._snooze_answer_reminder(second, reminders, 0)
    assert len(completed) == 1
    assert len(snoozed) == 1


def test_eye_training_button_releases_reminder_before_launching():
    page = object.__new__(app.HealthMainPage)
    page.active_health_reminders = []
    launched = []
    completed = []
    page.open_eye_training = lambda: launched.append(True)
    page._finish_reminder_batch = lambda reminders: completed.append(reminders)
    reminders = [{"key": "eye"}]
    win = FakeReminderWindow("eye")
    page.active_health_reminders.append(win)

    page._open_eye_training_from_reminder(win, reminders)
    page._open_eye_training_from_reminder(win, reminders)

    assert launched == [True]
    assert completed == [reminders]
    assert "grab_release" in win.calls
    assert "destroy" in win.calls


def test_eye_buttons_use_release_wrapper_instead_of_direct_launch():
    answer_source = inspect.getsource(app.HealthMainPage.show_answer_required_reminder)
    eye_source = inspect.getsource(app.HealthMainPage.show_eye_reminder_with_link)
    wrapper_source = inspect.getsource(app.HealthMainPage._open_eye_training_from_reminder)
    assert "_open_eye_training_from_reminder(win, reminders)" in answer_source
    assert "_open_eye_training_from_reminder(win, [])" in eye_source
    assert "grab_release" in wrapper_source
    assert "win.destroy()" in wrapper_source
    assert "self.open_eye_training()" in wrapper_source


def test_packaged_eye_training_uses_browser_fallback_without_subprocess():
    open_source = inspect.getsource(app.HealthMainPage.open_eye_training)
    launch_source = inspect.getsource(app.launch_eye_training_window)
    browser_source = inspect.getsource(app.open_eye_training_in_browser)
    assert "open_eye_training_in_browser(self.eye_record_url, autostart=True)" in open_source
    assert "[sys.executable, \"--launch-eye-training\"" not in open_source
    assert "return open_eye_training_in_browser(autostart=autostart)" in launch_source
    assert 'import webview' not in launch_source
    assert "build_eye_training_url(record_url)" in browser_source
    assert "autostart=1" in browser_source
    assert "log_exception(exc)" not in launch_source


def test_eye_training_record_server_and_url_contracts():
    url_source = inspect.getsource(app.build_eye_training_url)
    server_source = inspect.getsource(app.EyeRecordHttpServer)
    append_source = inspect.getsource(app.append_eye_autorecord)
    assert "autorecord=" in url_source
    assert "urllib.parse.quote" in url_source
    assert "http.server.HTTPServer" in server_source
    assert '("127.0.0.1", 0)' in server_source
    assert 'self.url = f"http://127.0.0.1:{port}/eye-record"' in server_source
    assert "Access-Control-Allow-Origin" in server_source
    assert "if duration < 60:" in append_source
    assert 'eye_autorecord.txt' in append_source


def test_eye_training_js_posts_only_after_sixty_seconds():
    js_path = os.path.join(app.RESOURCE_DIR, "护眼", "main.js")
    with open(js_path, "r", encoding="utf-8") as handle:
        source = handle.read()
    assert "function writeAutoRecordSignal(totalSec)" in source
    assert "if (totalSec < 60) return;" in source
    assert "new URLSearchParams(window.location.search)" in source
    assert "params.get('autorecord')" in source
    assert "fetch(recordUrl" in source
    assert "method: 'POST'" in source
    assert "writeAutoRecordSignal(totalSec);" in source


def test_unregister_latest_transfers_focus_to_remaining_latest():
    page = object.__new__(app.HealthMainPage)
    page.root = FakeLifecycleRoot("normal")
    page.closing = False
    first = FakeReminderWindow("A")
    latest = FakeReminderWindow("B")
    page.active_health_reminders = [first, latest]
    page._unregister_health_reminder(latest)
    assert page.active_health_reminders == [first]
    assert first.calls.count("grab_set") == 1
    assert first.calls.count("focus_force") == 1


def test_failed_restore_window_never_becomes_front_window():
    class BrokenReminderWindow(FakeReminderWindow):
        def deiconify(self):
            self.calls.append("deiconify")
            raise app.tk.TclError("restore failed")

    page = object.__new__(app.HealthMainPage)
    page.root = FakeLifecycleRoot("normal")
    page.closing = False
    good = FakeReminderWindow("good")
    broken = BrokenReminderWindow("broken")
    page.active_health_reminders = [good, broken]
    page._sync_reminder_windows_for_root_state()
    assert good.calls.count("grab_set") == 1
    assert good.calls.count("focus_force") == 1
    assert broken not in page.active_health_reminders


if __name__ == "__main__":
    test_config_defaults_and_validation()
    test_generated_answers_are_two_or_three_digits()
    test_answer_validation()
    test_map_handler_does_not_force_restore_or_focus()
    test_main_window_has_explicit_visible_start_state()
    test_legacy_settings_default_challenge_off()
    test_challenge_settings_round_trip()
    test_answer_window_has_safety_controls()
    test_answer_window_cleanup_guards()
    test_snooze_uses_five_minutes_without_rescheduling_normal_cycle()
    test_finish_batch_reschedules_each_unique_key_once()
    test_pomodoro_suppresses_health_reminders_and_reschedules_next_cycle()
    test_health_reminder_window_lifecycle_contracts()
    test_health_reminder_cleanup_preserves_answer_and_snooze_paths()
    test_register_restores_minimized_root_before_reminder_is_shown()
    test_sync_restores_all_but_focuses_latest_reminder_only()
    test_sync_restores_root_and_reminder_when_root_is_minimized()
    test_answer_terminal_actions_are_once_only_and_mutually_exclusive()
    test_eye_training_button_releases_reminder_before_launching()
    test_eye_buttons_use_release_wrapper_instead_of_direct_launch()
    test_packaged_eye_training_uses_browser_fallback_without_subprocess()
    test_eye_training_record_server_and_url_contracts()
    test_eye_training_js_posts_only_after_sixty_seconds()
    test_unregister_latest_transfers_focus_to_remaining_latest()
    test_failed_restore_window_never_becomes_front_window()
    print("reminder_challenge_checks_passed")
