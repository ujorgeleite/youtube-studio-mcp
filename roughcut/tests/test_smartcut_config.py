from smartcut.config import apply_glossary, list_presets, load_glossary, load_rules


def test_presets_have_the_requested_editorial_profiles():
    assert list_presets() == ["colab", "solo-emocional", "vlog"]
    assert load_rules("solo-emocional").pause_within_sentence_s > load_rules("vlog").pause_within_sentence_s


def test_glossary_applies_channel_terms():
    glossary = load_glossary()
    assert apply_glossary("eindoven e chimarao", glossary["corrections"]) == "Eindhoven e chimarrão"
