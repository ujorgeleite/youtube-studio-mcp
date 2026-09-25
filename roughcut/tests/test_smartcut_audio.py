from smartcut.audio import room_tone_region
from smartcut.schema import SpeechRegion


def test_room_tone_uses_the_largest_gap_without_voice():
    region = room_tone_region(30, [SpeechRegion(2, 5), SpeechRegion(8, 11), SpeechRegion(25, 30)])
    assert region == SpeechRegion(11, 21)
