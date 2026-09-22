from smartcut.preprocess import _loudnorm_stats


def test_loudnorm_stats_extracts_the_final_json_object():
    stats = _loudnorm_stats('noise\n{ "input_i": "-20.0", "input_lra": "4.0", "input_tp": "-2.0", "input_thresh": "-30.0", "target_offset": "0.2" }\n')
    assert stats["input_i"] == "-20.0"
