import signal
from unittest.mock import Mock

import pytest

from bonus.device_player import Speaker


def test_speaker_applies_play_pause_resume_stop_without_shell(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    spawn = Mock(return_value=process)
    monkeypatch.setattr("bonus.device_player.subprocess.Popen", spawn)
    speaker = Speaker()
    state = {
        "action": "play",
        "track": {"preview_url": "https://cdnt-preview.dzcdn.net/preview.mp3"},
    }
    speaker.apply(state)
    speaker.apply({"action": "pause"})
    process.send_signal.assert_called_with(signal.SIGSTOP)
    speaker.apply(state)
    process.send_signal.assert_called_with(signal.SIGCONT)
    assert spawn.call_count == 1
    assert spawn.call_args.args[0][0] == "ffplay"
    assert not spawn.call_args.kwargs.get("shell")
    speaker.stop()
    process.terminate.assert_called_once()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/private",
        "https://evil.example/audio",
        "https://cdnt-preview.dzcdn.net.evil.example/audio",
    ],
)
def test_speaker_rejects_untrusted_audio(url):
    with pytest.raises(ValueError):
        Speaker().apply({"action": "play", "track": {"preview_url": url}})
