import types, subprocess, actions

class DummyPopenCalls(list):
    def __call__(self, *args, **kwargs):
        self.append((args, kwargs))
        class _P:  # minimal proc stub
            def __init__(self): pass
        return _P()

def test_run_action_open_app(monkeypatch):
    calls = DummyPopenCalls()
    monkeypatch.setattr(subprocess, 'Popen', calls)
    # Force os.path.exists to False to hit -a branch
    monkeypatch.setattr(actions.os.path, 'exists', lambda p: False)
    actions.run_action('open_app Safari')
    assert calls, 'Popen not called'
    # Should call open -a Safari
    argv = calls[0][0][0]
    assert argv[0] == 'open'
    assert '-a' in argv
    assert 'Safari' in argv

def test_run_action_open_app_empty(monkeypatch):
    calls = DummyPopenCalls()
    monkeypatch.setattr(subprocess, 'Popen', calls)
    actions.run_action('open_app ')
    assert not calls, 'Should not invoke Popen for empty app name'
