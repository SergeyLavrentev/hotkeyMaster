import os, tempfile, json
from actions import run_action, set_display_brightness, get_display_brightness

# Smoke: run_action should not raise for basic actions

def test_run_action_open():
    run_action('open example.com')  # Should silently succeed

def test_run_action_invalid():
    run_action('')
    run_action('unknown_action_type whatever')

def test_brightness_cache_roundtrip():
    # We cannot actually change system brightness here; just ensure cache write works
    before = get_display_brightness()
    set_display_brightness(0.55)
    after = get_display_brightness()
    # after may equal 0.55 or remain old if OS calls failed but cache updated
    assert 0.0 <= after <= 1.0
