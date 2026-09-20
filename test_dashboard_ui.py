from dashboard_ui import (
    calculate_window_geometry,
    contrast_ratio,
    count_completed_items,
    get_dashboard_colors,
    get_day_greeting,
)
import inspect
import os
import tkinter as tk
from datetime import datetime
from types import SimpleNamespace
import drink_water_reminder as app


def test_dashboard_palette_has_semantic_roles():
    colors = get_dashboard_colors({
        "bg": "#e8f5e8",
        "button_bg": "#4caf50",
        "button_fg": "white",
        "button_active": "#66bb6a",
    })
    assert set(colors) == {
        "app_bg", "surface", "surface_alt", "primary", "primary_active",
        "on_primary", "secondary_action_text", "text_primary", "text_secondary", "border",
        "danger_muted", "danger_text",
    }
    assert colors["surface"] == "#ffffff"
    assert colors["primary"] == "#4caf50"
    assert colors["text_primary"] == "#123526"


def test_green_and_orange_actions_meet_text_contrast():
    for primary in ("#4caf50", "#ff9800"):
        colors = get_dashboard_colors({"button_bg": primary})
        assert contrast_ratio(colors["on_primary"], colors["primary"]) >= 4.5
        assert contrast_ratio(
            colors["secondary_action_text"], colors["surface_alt"]) >= 4.5


def test_count_completed_items_counts_nonempty_known_keys_only():
    assert count_completed_items(
        {"drink": ["08:00"], "stand": [], "eye": ["09:00"], "other": ["x"]},
        ["drink", "stand", "eye", "sport"],
    ) == 2
    assert count_completed_items([], ["drink"]) == 0


def test_day_greeting_boundaries():
    greetings = [get_day_greeting(hour) for hour in (5, 11, 13, 19)]
    assert all(isinstance(greeting, str) and greeting for greeting in greetings)
    assert len(set(greetings)) == 4


def test_window_geometry_is_centered_and_screen_bounded():
    assert calculate_window_geometry(1920, 1080) == (820, 720, 550, 180)
    width, height, x, y = calculate_window_geometry(800, 700)
    assert (width, height) == (720, 620)
    assert x == 40 and y == 40


def test_main_page_uses_confirmed_dashboard_sections():
    init_source = inspect.getsource(app.HealthMainPage.__init__)
    for method_name in (
        "create_header_section", "create_user_meta_section",
        "create_progress_summary", "create_health_cards",
        "create_footer_actions",
    ):
        assert "self.{}(".format(method_name) in init_source
        assert hasattr(app.HealthMainPage, method_name)


def test_dashboard_preserves_all_primary_commands():
    sources = "\n".join(
        inspect.getsource(method) for method in (
            app.HealthMainPage.create_header_section,
            app.HealthMainPage.create_user_meta_section,
            app.HealthMainPage.create_health_cards,
            app.HealthMainPage.create_footer_actions,
        )
    )
    for command in (
        "self.open_ai_assistant", "self.open_friends", "self.open_settings",
        "self.copy_user_id", "self.record_action", "self.quit_app",
        "self.restart_reminders", "self.open_eye_training", "self.open_desktop_pet",
        "self.toggle_reminder_pause",
    ):
        assert command in sources


def test_health_cards_expose_targets_and_large_counts():
    init_source = inspect.getsource(app.HealthMainPage.__init__)
    source = inspect.getsource(app.HealthMainPage.create_health_cards)
    assert 'target_counts = {"drink": 8, "stand": 6, "eye": 4, "sport": 2}' in source
    assert "target_counts[key]" in source
    assert '22, "bold"' in source
    assert 'row=0, column=1, rowspan=2, sticky="e"' in source
    assert "len(today_data.get(key, []))" in source
    assert "self.card_name_labels = {}" in init_source
    assert "self.card_target_labels = {}" in init_source
    assert "self.card_name_labels[key] = name_label" in source
    assert "self.card_target_labels[key] = target_label" in source


def test_record_action_refreshes_card_and_progress():
    source = inspect.getsource(app.HealthMainPage.record_action)
    assert "self.update_dashboard_state()" in source


def test_dashboard_state_uses_completed_item_helper():
    source = inspect.getsource(app.HealthMainPage.update_dashboard_state)
    assert "count_completed_items" in source
    assert "self.draw_progress_ring" in source
    assert "self.progress_detail_label.configure" in source
    assert "label.configure" in source


def test_progress_ring_has_neutral_primary_and_text_signals():
    source = inspect.getsource(app.HealthMainPage.draw_progress_ring)
    assert 'outline=self.dashboard_colors["border"]' in source
    assert 'outline=self.dashboard_colors["primary"]' in source
    assert "create_text" in source
    assert "except tk.TclError" in source


def test_theme_refresh_is_semantic_not_recursive_recoloring():
    source = inspect.getsource(app.HealthMainPage.apply_theme)
    assert "get_dashboard_colors" in source
    assert "self.health_card_surfaces" in source
    assert "self.card_name_labels" in source
    assert "self.card_target_labels" in source
    assert "update_widget_theme" not in source


def test_start_geometry_uses_dashboard_calculator_and_minimum_size():
    source = inspect.getsource(app.HealthMainPage._show_main_window_on_start)
    assert "calculate_window_geometry" in source
    assert "minsize(720, 560)" in source
    assert "screen_height - 80" in source
    assert "self.root.after(200, self._ensure_visible_after_start)" in source
    assert "self.root.after(1000, self._ensure_visible_after_start)" in source


def test_settings_save_refreshes_identity_theme_and_state():
    source = inspect.getsource(app.HealthMainPage.on_settings_save)
    assert "get_day_greeting(datetime.now().hour)" in source
    assert source.count("self.apply_theme()") == 1
    assert source.count("self.update_dashboard_state()") == 1
    assert source.count("self.start_all_reminders()") == 1


def test_health_grid_is_retained_and_semantically_themed():
    create_source = inspect.getsource(app.HealthMainPage.create_health_cards)
    theme_source = inspect.getsource(app.HealthMainPage.apply_theme)
    assert "self.health_grid = tk.Frame" in create_source
    assert "tk.Frame(self.health_grid" in create_source
    assert 'self.health_grid.configure(bg=colors["app_bg"])' in theme_source


def test_progress_summary_retains_encouraging_text_signal():
    create_source = inspect.getsource(app.HealthMainPage.create_progress_summary)
    theme_source = inspect.getsource(app.HealthMainPage.apply_theme)
    assert "self.progress_hint_label" in create_source
    assert "font=(\"微软雅黑\", 9)" in create_source
    assert "self.progress_hint_label.configure" in theme_source
    assert 'fg=colors["text_secondary"]' in theme_source


def test_custom_theme_registration_and_persistence_contracts():
    original = app.THEMES.get("自定义")
    palette = {
        "name": "自定义", "bg": "#123456", "button_bg": "#123456",
        "button_fg": "white", "button_active": "#123456",
    }
    try:
        assert app.restore_custom_theme({"custom_theme": palette}) is True
        assert app.THEMES["自定义"] == palette
        assert app.restore_custom_theme({"custom_theme": {"bg": "#ffffff"}}) is False
    finally:
        if original is None:
            app.THEMES.pop("自定义", None)
        else:
            app.THEMES["自定义"] = original
    custom_source = inspect.getsource(app.SettingsPage.custom_color)
    save_source = inspect.getsource(app.SettingsPage.save)
    load_source = inspect.getsource(app.load_user_config)
    assert 'THEMES["自定义"] = custom_theme' in custom_source
    assert 'custom_theme=THEMES.get("自定义")' in save_source
    assert "restore_custom_theme(config)" in load_source


def test_dashboard_actions_use_accessible_padding_and_compact_budget():
    init_source = inspect.getsource(app.HealthMainPage.__init__)
    header_source = inspect.getsource(app.HealthMainPage.create_header_section)
    meta_source = inspect.getsource(app.HealthMainPage.create_user_meta_section)
    cards_source = inspect.getsource(app.HealthMainPage.create_health_cards)
    footer_source = inspect.getsource(app.HealthMainPage.create_footer_actions)
    assert "22, 14, anchor=\"nw\"" in init_source
    assert "pady=10" in header_source
    assert "pady=(8, 6)" in meta_source
    assert "pady=9, height=116" in cards_source
    assert "highlightbackground=colors[\"border\"]" in header_source
    assert "highlightbackground=colors[\"border\"]" in footer_source
    assert "footer.grid_columnconfigure(column, weight=1" in footer_source
    assert "row=0, column=4" in footer_source
    assert "row=2" in cards_source
    assert "inner.pack_propagate(False)" not in cards_source
    assert 'action_row = tk.Frame(inner, bg=colors["surface"])' in cards_source
    assert 'action_button.pack(side=tk.LEFT, fill=tk.X, expand=True)' in cards_source
    assert "eye_training_button = tk.Button" in cards_source
    assert "command=self.open_eye_training" in cards_source
    assert 'eye_training_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))' in cards_source
    assert 'colors["secondary_action_text"]' in cards_source


def test_eye_training_button_participates_in_theme_refresh():
    init_source = inspect.getsource(app.HealthMainPage.__init__)
    theme_source = inspect.getsource(app.HealthMainPage.apply_theme)
    assert "self.eye_training_button = None" in init_source
    assert "self.eye_training_button = eye_training_button" in inspect.getsource(app.HealthMainPage.create_health_cards)
    assert 'key == "eye" and self.eye_training_button is not None' in theme_source
    assert 'self.eye_training_button.configure' in theme_source


def test_desktop_pet_class_is_safe_lightweight_window():
    assert hasattr(app, "DesktopPetWindow")
    source = inspect.getsource(app.DesktopPetWindow)
    assert "grab_set" not in source
    assert 'attributes("-fullscreen"' not in source
    assert "self.overrideredirect(True)" in source
    assert 'attributes("-transparentcolor", self.transparent_color)' in source
    assert 'attributes("-topmost", True)' in source
    assert "show_message" in source
    assert "_cycle_message" in source
    assert "_redraw_pet" in source
    assert "_on_double_click" in source
    assert "self.pet_canvas = tk.Canvas" in source
    assert "create_oval" in source
    assert "create_polygon" in source
    assert "_draw_pet" in source
    assert "self._pose = 0" in source
    assert "pet_display_name" in source
    assert "normalize_desktop_pet_name" in source
    assert "_rename_pet" in source
    assert "update_pet_name" in source
    assert "_sprite_frames" in source
    assert "_state_frames" in source
    assert "_active_state" in source
    assert "_load_pet_images" in source
    assert "ImageTk.PhotoImage" in source
    assert 'assets", "desktop_pets"' in source
    assert "_is_idle_frame_name" in source
    assert "_idle_frame_sort_key" in source
    assert "_prepare_pet_sprite" in source
    assert 'stem.startswith("idle_")' in source
    assert 'stem.startswith("idle") and stem[4:].isdigit()' in source
    assert "key=self._idle_frame_sort_key" in source
    assert "if a < 220" in source
    for state_name in ("happy", "unhappy", "sleep", "drink", "eye", "stand", "sport"):
        assert state_name in source
    assert "create_image" in source
    assert "width=230, height=205" in source
    assert "wraplength=" in source
    assert "_fit_bubble_text" in source
    assert "310" in source
    assert "340" in source
    assert "arm_raise" in source
    assert "shadow_y" in source
    assert "body_bottom" in source
    assert "random.randrange(len(self._sprite_frames))" in source
    assert "show_state" in source
    assert 'self.show_state("happy", duration_ms=60 * 1000)' in source
    assert "def show_state(self, state_name, duration_ms=None, fallback_state=None)" in source
    assert "pet_life_days=1" in source
    assert "format_pet_status_label" in source
    assert "update_pet_mood_display" in source
    assert "if duration_ms:" in source
    assert "self._animation_after_id = self.after(duration_ms, self._reset_pet_pose)" in source
    assert "grab_release" in source
    assert "self.after(10, lambda: self.on_redraw(self))" in source
    assert "on_open_catalog" in source
    assert "_open_pet_catalog" in source
    assert "self.after(10, lambda: self.on_open_catalog(self))" in source
    assert "tk.Menu" in source
    assert '"<ButtonPress-1>"' in source
    assert '"<B1-Motion>"' in source
    assert '"<ButtonRelease-1>"' in source
    assert '"<Button-3>"' in source
    assert "_dock_if_near_edge" in source
    assert "_expand_from_dock" in source
    assert "desktop_pet_docked=True" in source
    assert "desktop_pet_docked=False" in source


def test_dashboard_exposes_desktop_pet_command_and_reuses_window():
    init_source = inspect.getsource(app.HealthMainPage.__init__)
    footer_source = inspect.getsource(app.HealthMainPage.create_footer_actions)
    open_source = inspect.getsource(app.HealthMainPage.open_desktop_pet)
    settings_source = inspect.getsource(app.HealthMainPage.open_settings)
    theme_source = inspect.getsource(app.HealthMainPage.apply_theme)
    assert "self.desktop_pet_window = None" in init_source
    assert "self.desktop_pet_autostart = get_desktop_pet_autostart()" in init_source
    assert "self.pause_status_label = None" in init_source
    assert "self.pause_reminder_button = None" in init_source
    assert "self.pause_status_after_id = None" in init_source
    assert "self.root.after(900, self.open_desktop_pet)" in init_source
    assert "command=self.open_desktop_pet" in footer_source
    assert "command=self.toggle_reminder_pause" in footer_source
    assert "choose_desktop_pet_id()" in open_source
    assert "save_user_config_fields(desktop_pet_id=pet_id)" in open_source
    assert "desktop_pet_name" in open_source
    assert "desktop_pet_named" in open_source
    assert "touch_pet_life(config, pet[\"id\"], self.today)" in open_source
    assert "get_pet_life_milestone_message" in open_source
    assert "pet_life_days=pet_life_days" in open_source
    assert "pet_mood=pet_mood" in open_source
    assert "on_start_pomodoro=self.start_pet_pomodoro" in open_source
    assert "on_cancel_pomodoro=self.cancel_pet_pomodoro" in open_source
    assert "pomodoro_status=self.get_pet_pomodoro_status" in open_source
    assert "on_show_progress=self.show_pet_today_progress" in open_source
    assert "on_record_health=self.pet_record_health" in open_source
    assert "on_start_eye_training=self.pet_start_eye_training" in open_source
    assert "on_toggle_pause=self.pet_toggle_reminder_pause" in open_source
    assert "ask_desktop_pet_name" in open_source
    assert "get_desktop_pet(pet_id)" in open_source
    assert "DesktopPetWindow" in open_source
    assert "on_rename=self.rename_desktop_pet" in open_source
    assert "on_open_catalog=self.open_desktop_pet_catalog" in open_source
    assert "winfo_exists()" in open_source
    assert "lift()" in open_source
    assert hasattr(app.HealthMainPage, "open_desktop_pet_catalog")
    assert "format_pet_catalog_unlocked_states" in inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    assert "format_pet_catalog_next_stage" in inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    assert "idle_0.png" in inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    assert "pet_catalog_images" in inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    assert "current_pet_id" in inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    assert "ordered_pets" in inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    assert "get_pet_mood_bar_color" in inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    assert "mood_bar.create_rectangle" in inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    assert "self.desktop_pet_autostart" in settings_source
    assert "self.pet_button.configure" in theme_source
    assert "self.pause_reminder_button.configure" in theme_source
    assert "is_reminder_paused()" in inspect.getsource(app.HealthMainPage.remind)
    assert "self.schedule_reminder(key)" in inspect.getsource(app.HealthMainPage.remind)
    pause_dialog_source = inspect.getsource(app.HealthMainPage.open_reminder_pause_dialog)
    assert "apply_safe_window_geometry(dialog" in pause_dialog_source
    assert "dialog_parent = parent or self.root" in pause_dialog_source
    assert "tk.Toplevel(dialog_parent)" in pause_dialog_source
    assert "dialog.transient(dialog_parent)" in pause_dialog_source
    assert "quick_row.grid_columnconfigure" in pause_dialog_source
    assert "input_row.grid_columnconfigure" in pause_dialog_source
    assert "dialog.resizable(True, True)" in pause_dialog_source
    assert "custom_section" in pause_dialog_source
    assert "messagebox.showwarning" in pause_dialog_source
    assert "target_time + timedelta(days=1)" not in pause_dialog_source
    assert "close_dialog" in pause_dialog_source
    assert "parent=target" in inspect.getsource(app.HealthMainPage.redraw_desktop_pet)
    assert "dialog_parent = parent or self.root" in inspect.getsource(app.HealthMainPage.ask_desktop_pet_name)
    assert "show_desktop_pet_state" in inspect.getsource(app.HealthMainPage.record_action)
    assert "show_desktop_pet_reminder_state" in inspect.getsource(app.HealthMainPage.show_standard_health_reminder)
    assert "show_desktop_pet_reminder_state" in inspect.getsource(app.HealthMainPage.show_answer_required_reminder)
    assert hasattr(app.HealthMainPage, "start_pet_pomodoro")
    assert hasattr(app.HealthMainPage, "finish_pet_pomodoro")
    assert hasattr(app.HealthMainPage, "get_pet_pomodoro_status")
    assert hasattr(app.HealthMainPage, "cancel_pet_pomodoro")
    assert hasattr(app.HealthMainPage, "show_pet_today_progress")
    assert hasattr(app.HealthMainPage, "pet_record_health")
    assert hasattr(app.HealthMainPage, "pet_start_eye_training")
    assert hasattr(app.HealthMainPage, "pet_toggle_reminder_pause")


def test_desktop_pet_menu_exposes_quick_tools_without_blocking_features():
    init_source = inspect.getsource(app.DesktopPetWindow.__init__)
    click_source = inspect.getsource(app.DesktopPetWindow._on_click)
    double_click_source = inspect.getsource(app.DesktopPetWindow._on_double_click)
    random_source = inspect.getsource(app.DesktopPetWindow._say_random)
    menu_source = inspect.getsource(app.DesktopPetWindow._refresh_menu)
    pomodoro_source = inspect.getsource(app.HealthMainPage.start_pet_pomodoro)
    countdown_source = inspect.getsource(app.HealthMainPage.update_pet_pomodoro_countdown)
    status_source = inspect.getsource(app.HealthMainPage.get_pet_pomodoro_status)
    pet_window_source = inspect.getsource(app.DesktopPetWindow)
    finish_source = inspect.getsource(app.HealthMainPage.finish_pet_pomodoro)
    quick_source = "\n".join(
        inspect.getsource(method) for method in (
            app.HealthMainPage.show_pet_today_progress,
            app.HealthMainPage.pet_record_health,
            app.HealthMainPage.pet_start_eye_training,
            app.HealthMainPage.pet_toggle_reminder_pause,
        )
    )
    assert "on_start_pomodoro" in init_source
    assert "on_show_progress" in init_source
    assert "on_record_health" in init_source
    assert "on_pet_click" in init_source
    assert "reward_click=True" in click_source
    assert "_reward_click_mood()" in double_click_source
    assert "if reward_click:" in random_source
    assert "self.on_pet_click()" in inspect.getsource(app.DesktopPetWindow._reward_click_mood)
    assert "开始番茄时钟" in menu_source
    assert "结束番茄时钟" in menu_source
    assert "查看今日进度" in menu_source
    assert "记录喝水" in menu_source
    assert "开始护眼" in menu_source
    assert "设置免打扰" in menu_source
    assert app.POMODORO_FOCUS_SECONDS == 25 * 60
    assert "timedelta(seconds=POMODORO_FOCUS_SECONDS)" in pomodoro_source
    assert "self.update_pet_pomodoro_countdown()" in pomodoro_source
    assert "root.after(1000, self.update_pet_pomodoro_countdown)" in countdown_source
    assert "番茄专注 {:02d}:{:02d}" in countdown_source
    assert "番茄专注 {:02d}:{:02d}" in status_source
    assert "def _is_pomodoro_active" in pet_window_source
    assert "def show_message(self, text, force=False)" in pet_window_source
    assert "if self._is_pomodoro_active()" in pet_window_source
    assert "force=True" in inspect.getsource(app.DesktopPetWindow._show_pomodoro_status)
    assert "adjust_current_pet_mood(5)" in finish_source
    assert "messagebox.showinfo" in finish_source
    assert "get_desktop_pet_progress_summary()" in quick_source
    assert "self.record_action(key)" in quick_source
    assert "self.open_eye_training()" in quick_source
    assert "self.toggle_reminder_pause(parent=self.root)" in quick_source
    all_source = inspect.getsource(app.HealthMainPage) + inspect.getsource(app.DesktopPetWindow)
    assert "刷新题目" not in all_source
    assert "一键导出" not in all_source


def test_desktop_pet_catalog_and_interaction_helpers_exist():
    assert len(app.DESKTOP_PETS) >= 4
    ids = {pet["id"] for pet in app.DESKTOP_PETS}
    image_pet_ids = {"eye_duck_pet_ready", "dog_XB_white_pet_ready", "dog_XTM", "dog_XJM_pet_ready", "capybara_pet_ready"}
    assert image_pet_ids.issubset(ids)
    for pet in app.DESKTOP_PETS:
        assert "color" in pet
        assert "accent" in pet
        assert "belly" in pet
        if pet["id"] not in image_pet_ids:
            continue
        pet_dir = app.resource_path("assets/desktop_pets/{}".format(pet["id"]))
        assert os.path.exists(os.path.join(pet_dir, "idle_0.png"))
        assert os.path.exists(os.path.join(pet_dir, "idle_1.png"))
        assert os.path.exists(os.path.join(pet_dir, "happy.png"))
    helper_source = inspect.getsource(app.get_desktop_pet)
    redraw_source = inspect.getsource(app.HealthMainPage.redraw_desktop_pet)
    show_state_source = inspect.getsource(app.DesktopPetWindow.show_state)
    summary_source = inspect.getsource(app.HealthMainPage.get_desktop_pet_progress_summary)
    assert app.get_desktop_pet_autostart({"desktop_pet_autostart": True}) is True
    assert app.get_desktop_pet_autostart({"desktop_pet_autostart": False}) is False
    assert app.is_reminder_paused({"reminder_pause_until": "2026-08-13 16:30:00"}, datetime(2026, 8, 13, 16, 0)) is True
    assert app.is_reminder_paused({"reminder_pause_until": "2026-08-13 16:30:00"}, datetime(2026, 8, 13, 17, 0)) is False
    assert app.parse_reminder_pause_until({"reminder_pause_until": "bad"}) is None
    assert app.format_reminder_pause_status({"reminder_pause_until": "2026-08-13 16:30:00"}, datetime(2026, 8, 13, 16, 0))
    assert app.load_pet_lives({"pet_lives": {"pet": {"life_days": 2}}}) == {"pet": {"life_days": 2}}
    assert app.load_pet_lives({"pet_lives": []}) == {}
    assert app.load_unlocked_pet_ids({"unlocked_pet_ids": ["eye_duck_pet_ready"]}) == {"eye_duck_pet_ready"}
    assert app.load_unlocked_pet_ids({"unlocked_pet_ids": [], "desktop_pet_id": "dog_XB_white_pet_ready"}) == {"dog_XB_white_pet_ready"}
    assert app.is_desktop_pet_unlocked("eye_duck_pet_ready", {"unlocked_pet_ids": ["eye_duck_pet_ready"]}) is True
    assert app.is_desktop_pet_unlocked("capybara_pet_ready", {"unlocked_pet_ids": ["eye_duck_pet_ready"]}) is False
    assert app.load_pet_moods({"pet_moods": {"pet": 80}}) == {"pet": 80}
    assert app.load_pet_moods({"pet_moods": []}) == {}
    assert app.load_pet_mood_recovery_dates({"pet_mood_recovery_dates": {"pet": "2026-08-13"}}) == {"pet": "2026-08-13"}
    assert app.load_pet_mood_recovery_dates({"pet_mood_recovery_dates": []}) == {}
    assert app.clamp_pet_mood(-5) == 0
    assert app.clamp_pet_mood(105) == 100
    assert app.describe_pet_mood(85)
    assert app.describe_pet_mood(55)
    assert app.describe_pet_mood(35)
    assert app.describe_pet_mood(10)
    assert app.get_pet_mood({"pet_moods": {"pet": 80}}, "pet") == 80
    assert app.get_pet_mood_feedback(85)
    rule_text = app.format_pet_mood_rule_summary_text()
    assert "定时健康提醒弹出一次：-3" in rule_text
    assert "完成一次健康记录：+8" in rule_text
    assert "番茄时钟完成：+5" in rule_text
    assert "当天四项目标全部完成：+10" in rule_text
    assert "每天首次陪伴恢复：+2" in rule_text
    assert app.get_pet_mood_bar_color(85)
    assert app.get_pet_mood_bar_color(55)
    assert app.get_pet_mood_bar_color(35)
    assert app.get_pet_mood_bar_color(10)
    assert app.get_pet_life_milestone_message(3, True) is not None
    assert app.get_pet_life_milestone_message(3, False) is None
    assert app.is_pet_state_unlocked("idle_0", 1) is True
    assert app.is_pet_state_unlocked("happy", 2) is False
    assert app.is_pet_state_unlocked("happy", 3) is True
    assert app.is_pet_state_unlocked("sleep", 6) is False
    assert app.is_pet_state_unlocked("sleep", 7) is True
    assert app.is_pet_state_unlocked("drink", 13) is False
    assert app.is_pet_state_unlocked("drink", 14) is True
    assert "happy" in app.get_unlocked_pet_states(3)
    assert "sleep" not in app.get_unlocked_pet_states(3)
    assert "drink" in app.get_unlocked_pet_states(14)
    assert app.format_pet_status_label("pet", 2, 60)
    assert app.format_pet_catalog_unlocked_states(0)
    assert "happy" not in app.format_pet_catalog_unlocked_states(2)
    assert app.format_pet_catalog_unlocked_states(3)
    assert app.format_pet_catalog_next_stage(0)
    assert app.format_pet_catalog_next_stage(30)
    assert "random.choice(DESKTOP_PETS)" in helper_source
    assert "save_user_config_fields(desktop_pet_id=pet_id, desktop_pet_name=pet_display_name, desktop_pet_named=True)" in redraw_source
    assert "mark_desktop_pet_unlocked(pet_id" in redraw_source
    assert "mark_desktop_pet_unlocked(pet_id" in inspect.getsource(app.HealthMainPage.open_desktop_pet)
    catalog_source = inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    open_pet_source = inspect.getsource(app.HealthMainPage.open_desktop_pet)
    pet_restore_source = inspect.getsource(app.DesktopPetWindow.restore_to_screen)
    assert "restore_to_screen()" in open_pet_source
    assert "self._is_docked = False" in pet_restore_source
    assert "desktop_pet_docked=False" in pet_restore_source
    assert "self.deiconify()" in pet_restore_source
    assert "unlocked_pet_ids = load_unlocked_pet_ids(config)" in catalog_source
    assert "is_unlocked = pet.get(\"id\") in unlocked_pet_ids" in catalog_source
    assert 'text=pet["name"] if is_unlocked else "？？？"' in catalog_source
    assert 'text="未解锁"' in catalog_source
    assert 'create_text(36, 36, text="?"' in catalog_source
    assert '"抽到后开始陪伴"' in catalog_source
    assert "心情说明" in catalog_source
    assert "show_mood_rules_tooltip" in catalog_source
    assert "open_mood_rules_dialog" in catalog_source
    assert "format_pet_mood_rule_summary_text()" in catalog_source
    assert "_fit_bubble_text" in inspect.getsource(app.DesktopPetWindow.show_message)
    assert "target.update_pet(pet, pet_display_name, pet_life_days=pet_life_days, pet_mood=pet_mood)" in redraw_source
    assert "is_pet_state_unlocked(state_name, self.pet_life_days)" in show_state_source
    assert hasattr(app.HealthMainPage, "rename_desktop_pet")
    assert hasattr(app.HealthMainPage, "ask_desktop_pet_name")
    assert app.normalize_desktop_pet_name("  abc  ", "fallback") == "abc"
    assert app.normalize_desktop_pet_name("123456789", "fallback") == "12345678"
    assert app.normalize_desktop_pet_name("", "fallback") == "fallback"
    assert summary_source


def test_pet_mood_recovers_once_per_day():
    saved_fields = []
    original_save_user_config_fields = app.save_user_config_fields
    try:
        app.save_user_config_fields = lambda **fields: saved_fields.append(fields)
        mood, changed = app.recover_pet_mood_once_per_day(
            "pet",
            {"pet_moods": {"pet": 60}, "pet_mood_recovery_dates": {}},
            "2026-08-13",
        )
        assert mood == 62
        assert changed is True
        assert saved_fields[-1]["pet_moods"]["pet"] == 62
        assert saved_fields[-1]["pet_mood_recovery_dates"]["pet"] == "2026-08-13"

        mood, changed = app.recover_pet_mood_once_per_day(
            "pet",
            {"pet_moods": {"pet": 60}, "pet_mood_recovery_dates": {"pet": "2026-08-13"}},
            "2026-08-13",
        )
        assert mood == 60
        assert changed is False

        mood, changed = app.recover_pet_mood_once_per_day(
            "pet",
            {"pet_moods": {"pet": 100}, "pet_mood_recovery_dates": {}},
            "2026-08-13",
        )
        assert mood == 100
        assert changed is False
    finally:
        app.save_user_config_fields = original_save_user_config_fields


def test_pet_click_mood_adds_one_point():
    page = object.__new__(app.HealthMainPage)
    deltas = []
    page.adjust_current_pet_mood = deltas.append
    page.pet_click_mood()
    assert deltas == [1]


def test_pet_goal_reward_and_low_mood_helpers():
    saved_fields = []
    original_save_user_config_fields = app.save_user_config_fields
    try:
        app.save_user_config_fields = lambda **fields: saved_fields.append(fields)
        mood, rewarded = app.reward_current_pet_for_daily_completion(
            {
                "desktop_pet_id": "eye_duck_pet_ready",
                "pet_moods": {"eye_duck_pet_ready": 55},
                "pet_goal_reward_dates": {},
            },
            "2026-08-14",
        )
        assert mood == 65
        assert rewarded is True
        assert saved_fields[-1]["pet_goal_reward_dates"]["eye_duck_pet_ready"] == "2026-08-14"

        mood, rewarded = app.reward_current_pet_for_daily_completion(
            {
                "desktop_pet_id": "eye_duck_pet_ready",
                "pet_moods": {"eye_duck_pet_ready": 55},
                "pet_goal_reward_dates": {"eye_duck_pet_ready": "2026-08-14"},
            },
            "2026-08-14",
        )
        assert mood == 55
        assert rewarded is False
        assert app.load_pet_goal_reward_dates({"pet_goal_reward_dates": []}) == {}
        assert app.get_low_pet_mood_message(20)
        assert app.get_low_pet_mood_message(40)
        assert app.get_low_pet_mood_message(60) is None
    finally:
        app.save_user_config_fields = original_save_user_config_fields


def test_version_support_and_catalog_switch_contracts():
    assert app.APP_VERSION == "v0.5.0"
    assert os.path.exists(os.path.join(os.path.dirname(app.__file__), "CHANGELOG.md"))
    assert hasattr(app, "open_path_with_default_app")
    personal_source = inspect.getsource(app.SettingsPage.create_personal_settings)
    assert '"当前版本：{}".format(APP_VERSION)' in personal_source
    assert "打开日志文件" in personal_source
    assert "打开程序目录" in personal_source
    assert hasattr(app.SettingsPage, "open_log_file")
    assert hasattr(app.SettingsPage, "open_app_folder")
    catalog_source = inspect.getsource(app.HealthMainPage.open_desktop_pet_catalog)
    switch_source = inspect.getsource(app.HealthMainPage.switch_desktop_pet_from_catalog)
    dashboard_source = inspect.getsource(app.HealthMainPage.update_dashboard_state)
    open_pet_source = inspect.getsource(app.HealthMainPage.open_desktop_pet)
    assert "切换为当前宠物" in catalog_source
    assert "重新抽卡有机会获得" in catalog_source
    assert "switch_desktop_pet_from_catalog" in catalog_source
    assert "save_user_config_fields(desktop_pet_id=pet_id" in switch_source
    assert "update_pet(" in switch_source
    assert "reward_daily_completion_if_needed" in dashboard_source
    assert "get_low_pet_mood_message" in open_pet_source


def test_desktop_pet_catalog_window_renders_pet_rows():
    root = tk.Tk()
    root.withdraw()
    original_load_user_config = app.load_user_config
    try:
        app.load_user_config = lambda: {"desktop_pet_id": "capybara_pet_ready"}
        fake_page = SimpleNamespace(root=root, dashboard_colors=app.get_dashboard_colors({}))
        app.HealthMainPage.open_desktop_pet_catalog(fake_page)
        root.update_idletasks()
        label_texts = []

        def collect_labels(widget):
            for child in widget.winfo_children():
                if child.winfo_class() == "Label":
                    label_texts.append(child.cget("text"))
                collect_labels(child)

        collect_labels(root)
        current_pet = app.get_desktop_pet("capybara_pet_ready")
        assert current_pet["name"] in label_texts
        assert "？？？" in label_texts
        assert "未解锁" in label_texts
        assert any("重新抽卡有机会获得" in text for text in label_texts)
        assert not any(
            pet["name"] in label_texts
            for pet in app.DESKTOP_PETS
            if pet["id"] != "capybara_pet_ready"
        )
        assert any("life" not in text.lower() and text for text in label_texts)
    finally:
        app.load_user_config = original_load_user_config
        root.destroy()

def test_windows_dpi_awareness_is_safe_and_precedes_tk_root():
    helper_source = inspect.getsource(app.enable_windows_dpi_awareness)
    assert 'if sys.platform != "win32"' in helper_source
    assert "SetProcessDpiAwareness(1)" in helper_source
    assert "SetProcessDPIAware()" in helper_source
    assert helper_source.count("except Exception") == 2
    with open(app.__file__, "r", encoding="utf-8") as source_file:
        module_source = source_file.read()
    main_source = module_source[module_source.index('if __name__ == "__main__":'):]
    assert main_source.index("enable_windows_dpi_awareness()") < main_source.index("root = tk.Tk()")


def test_safe_dialog_layout_helpers_and_high_risk_dialogs_use_them():
    assert hasattr(app, "bounded_window_geometry")
    assert hasattr(app, "apply_safe_window_geometry")
    assert hasattr(app, "create_scrollable_body")
    assert hasattr(app, "create_dialog_header")
    assert hasattr(app, "create_dialog_card")
    assert hasattr(app, "dialog_button_options")
    assert "create_window" in inspect.getsource(app.create_scrollable_body)
    assert "scrollregion" in inspect.getsource(app.create_scrollable_body)
    assert "apply_safe_window_geometry(win" in inspect.getsource(app.HealthMainPage.show_standard_health_reminder)
    assert "apply_safe_window_geometry(win" in inspect.getsource(app.HealthMainPage.show_eye_reminder_with_link)
    assert "apply_safe_window_geometry(self" in inspect.getsource(app.FriendsPage.__init__)
    assert "apply_safe_window_geometry(data_window" in inspect.getsource(app.FriendsPage.show_friend_data)
    assert "apply_safe_window_geometry(reminder_window" in inspect.getsource(app.FriendsPage.send_reminder)
    assert "create_dialog_header(" in inspect.getsource(app.FriendsPage.show_friend_data)
    assert "create_dialog_card(" in inspect.getsource(app.FriendsPage.send_reminder)
    assert "resizable(True, True)" in inspect.getsource(app.FriendsPage.__init__)


def test_dashboard_shell_scrolls_vertically_and_follows_viewport_width():
    init_source = inspect.getsource(app.HealthMainPage.__init__)
    scroll_source = inspect.getsource(app.HealthMainPage._update_dashboard_scrollregion)
    resize_source = inspect.getsource(app.HealthMainPage._resize_dashboard_viewport)
    assert "self.dashboard_canvas = tk.Canvas" in init_source
    assert "self.dashboard_scrollbar = tk.Scrollbar" in init_source
    assert "orient=tk.VERTICAL" in init_source
    assert "self.dashboard_window = self.dashboard_canvas.create_window" in init_source
    assert 'scrollregion=self.dashboard_canvas.bbox("all")' in scroll_source
    assert "event.width - 44" in resize_source
    assert "itemconfigure(self.dashboard_window, width=viewport_width)" in resize_source
    assert "xview" not in init_source


def test_start_geometry_uses_real_content_request_and_short_nav_copy():
    geometry_source = inspect.getsource(app.HealthMainPage._show_main_window_on_start)
    header_source = inspect.getsource(app.HealthMainPage.create_header_section)
    assert "self.dashboard_shell.winfo_reqwidth() + 64" in geometry_source
    assert "self.dashboard_shell.winfo_reqheight() + 36" in geometry_source
    assert "requested_width=requested_width" in geometry_source
    assert "requested_height=requested_height" in geometry_source
    assert "command=self.open_ai_assistant" in header_source


def test_friends_page_actions_use_two_row_responsive_grid():
    source = inspect.getsource(app.FriendsPage.create_widgets)
    assert "create_dialog_header(shell" in source
    assert "add_frame = create_dialog_card(shell" in source
    assert "list_frame = create_dialog_card(shell" in source
    assert "add_frame.grid_columnconfigure(1, weight=1)" in source
    assert ').grid(row=0, column=0, sticky="w", padx=(0, 8))' in source
    assert 'self.friend_id_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))' in source
    assert 'add_btn.grid(row=0, column=2, sticky="e")' in source
    assert 'discover_btn.grid(row=1, column=1, sticky="e", padx=(0, 8), pady=(8, 0))' in source
    assert 'refresh_btn.grid(row=1, column=2, sticky="e", pady=(8, 0))' in source
    assert "dialog_button_options(colors, primary=True)" in source
    assert "command=self.add_friend" in source
    assert "command=self.discover_friends" in source
    assert "command=self.refresh_friend_status" in source


def test_ai_assistant_dialog_uses_responsive_layout():
    init_source = inspect.getsource(app.AIHealthAssistantDialog.__init__)
    geometry_source = inspect.getsource(
        app.AIHealthAssistantDialog._configure_window_geometry
    )
    widgets_source = inspect.getsource(
        app.AIHealthAssistantDialog.create_widgets
    )

    assert "self.resizable(True, True)" in init_source
    assert "self.dialog_colors = get_dashboard_colors" in init_source
    assert "self.minsize(" in geometry_source
    assert "self.winfo_screenwidth()" in geometry_source
    assert "self.winfo_screenheight()" in geometry_source
    assert 'self.geometry(f"{width}x{height}+{x}+{y}")' in geometry_source
    assert "self.grid_rowconfigure(0, weight=1)" in widgets_source
    assert "self.grid_columnconfigure(0, weight=1)" in widgets_source
    assert "create_dialog_header(" in widgets_source
    assert "chat_card.grid(row=1, column=0, sticky=\"nsew\"" in widgets_source
    assert "input_frame.grid(row=2, column=0, sticky=\"ew\"" in widgets_source
    assert "dialog_button_options(colors, primary=True)" in widgets_source
    assert 'sticky="nsew"' in widgets_source
    assert 'sticky="ew"' in widgets_source
    assert "input_frame.grid_columnconfigure(0, weight=1)" in widgets_source


def test_settings_dialog_uses_screen_bounded_responsive_layout():
    init_source = inspect.getsource(app.SettingsPage.__init__)
    geometry_source = inspect.getsource(app.SettingsPage._configure_window_geometry)
    widgets_source = inspect.getsource(app.SettingsPage.create_widgets)

    assert "self.resizable(True, True)" in init_source
    assert "self.dialog_colors = get_dashboard_colors" in init_source
    assert "self.winfo_screenwidth()" in geometry_source
    assert "self.winfo_screenheight()" in geometry_source
    assert "self.minsize(" in geometry_source
    assert 'self.geometry(f"{width}x{height}+{x}+{y}")' in geometry_source
    assert "canvas.itemconfigure(" in widgets_source
    assert "self.settings_canvas_window, width=event.width" in widgets_source
    assert "self.center_frame.pack(fill=tk.X, expand=True" in widgets_source
    assert "create_dialog_header(" in widgets_source
    assert "content_card = create_dialog_card(" in widgets_source
    assert "dialog_button_options(colors, primary=True)" in widgets_source
    assert 'self.bind("<MouseWheel>"' in widgets_source
    assert "bind_all" not in widgets_source


if __name__ == "__main__":
    test_dashboard_palette_has_semantic_roles()
    test_green_and_orange_actions_meet_text_contrast()
    test_count_completed_items_counts_nonempty_known_keys_only()
    test_day_greeting_boundaries()
    test_window_geometry_is_centered_and_screen_bounded()
    test_main_page_uses_confirmed_dashboard_sections()
    test_dashboard_preserves_all_primary_commands()
    test_health_cards_expose_targets_and_large_counts()
    test_record_action_refreshes_card_and_progress()
    test_dashboard_state_uses_completed_item_helper()
    test_progress_ring_has_neutral_primary_and_text_signals()
    test_theme_refresh_is_semantic_not_recursive_recoloring()
    test_start_geometry_uses_dashboard_calculator_and_minimum_size()
    test_settings_save_refreshes_identity_theme_and_state()
    test_health_grid_is_retained_and_semantically_themed()
    test_progress_summary_retains_encouraging_text_signal()
    test_custom_theme_registration_and_persistence_contracts()
    test_dashboard_actions_use_accessible_padding_and_compact_budget()
    test_desktop_pet_class_is_safe_lightweight_window()
    test_dashboard_exposes_desktop_pet_command_and_reuses_window()
    test_desktop_pet_menu_exposes_quick_tools_without_blocking_features()
    test_desktop_pet_catalog_and_interaction_helpers_exist()
    test_pet_goal_reward_and_low_mood_helpers()
    test_version_support_and_catalog_switch_contracts()
    test_windows_dpi_awareness_is_safe_and_precedes_tk_root()
    test_safe_dialog_layout_helpers_and_high_risk_dialogs_use_them()
    test_dashboard_shell_scrolls_vertically_and_follows_viewport_width()
    test_start_geometry_uses_real_content_request_and_short_nav_copy()
    test_friends_page_actions_use_two_row_responsive_grid()
    test_ai_assistant_dialog_uses_responsive_layout()
    test_settings_dialog_uses_screen_bounded_responsive_layout()
    print("dashboard_ui_checks_passed")
