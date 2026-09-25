from smartcut.export import write_fcpxml, write_review_report, write_srt
from smartcut.schema import Cut, Word


def test_exports_are_reviewable_and_reference_the_original(tmp_path):
    words = [Word(0, 1, "Oi"), Word(3, 4, "Mundo")]
    cuts = [Cut(1.1, 2.9, "pausa_na_frase")]
    srt = write_srt(words, cuts, tmp_path / "fala.srt")
    xml = write_fcpxml(tmp_path / "original.mp4", 4, cuts, tmp_path / "timeline.fcpxml")
    report = write_review_report(cuts, [], tmp_path / "revisao.md")
    assert "Oi" in srt.read_text()
    assert "asset-clip" in xml.read_text()
    assert "pausa_na_frase" in report.read_text()
