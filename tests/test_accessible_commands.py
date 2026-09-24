from awtui.actions import ACTIONS, footer_text, help_text
from awtui.live import build_application
from types import SimpleNamespace


def test_shared_action_map_is_visible_in_tui_footer_and_help_panel():
    app = build_application()
    footer = app.awtui_footer.text
    assert "?: Show help" in footer
    assert all(item.label in footer for item in ACTIONS)
    assert all(item.shortcut in help_text() for item in ACTIONS)

    app.awtui_state.help_visible = True
    app.awtui_state._refresh()
    assert "KEYBOARD AND ACCESSIBILITY HELP" in app.awtui_help.text


def test_help_binding_is_not_an_action_while_editing():
    app = build_application()
    app.awtui_state.input_mode = True
    binding = next(item for item in app.key_bindings.bindings if str(item.keys[0]) == "?")
    binding.handler(SimpleNamespace(app=app, key_sequence=[SimpleNamespace(key="?")]))
    assert app.awtui_state.help_visible is False


def test_tui_help_action_can_be_toggled_from_normal_mode():
    app = build_application()
    binding = next(item for item in app.key_bindings.bindings if str(item.keys[0]) == "?")
    binding.handler(SimpleNamespace(app=app, key_sequence=[SimpleNamespace(key="?")]))
    assert app.awtui_state.help_visible is True
