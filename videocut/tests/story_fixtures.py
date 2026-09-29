"""Inventário do exemplo do wireframe: passeio no parque e conversa sobre adaptação."""

from analysis.inventory import build_inventory
from analysis.speech import group_sentences
from core.schema import Take, Transcript, VisualObservation, Word


def _words(text: str, start: float, step: float = 0.4) -> list[Word]:
    return [Word(round(start + i * step, 2), round(start + i * step + step * 0.8, 2), token) for i, token in enumerate(text.split())]


def _transcript(take_id: str, *phrases: tuple[float, str]) -> Transcript:
    words = [word for start, text in phrases for word in _words(text, start)]
    return Transcript(take_id, words=words, sentences=group_sentences(words))


def example_inventory():
    takes = [
        Take("T01", "/raw/saida.mp4", "saida.mp4", 72),
        Take("T02", "/raw/caminho.mp4", "caminho.mp4", 48),
        Take("T03", "/raw/impressao.mp4", "impressao.mp4", 126),
        Take("T04", "/raw/parque.mp4", "parque.mp4", 94),
        Take("T05", "/raw/conversa.mp4", "conversa.mp4", 198),
        Take("T06", "/raw/detalhes.mp4", "detalhes.mp4", 54),
    ]
    transcripts = {
        "T01": _transcript("T01", (10, "Hoje a gente vai aproveitar o parque aqui perto de casa.")),
        "T03": _transcript("T03", (18, "É nessas coisas pequenas que a gente percebe a mudança.")),
        "T05": _transcript("T05", (40, "A gente achava que adaptar era resolver tudo."),
                           (46, "Mas também é conseguir aproveitar um dia simples."),
                           (150, "E no fim do dia a gente voltou mais leve.")),
    }
    observations = {
        "T01": [VisualObservation("T01", 0, 40, "porta de casa", setting="casa")],
        "T02": [VisualObservation("T02", 0, 24, "rua do bairro", usable_as_broll=True, interest=.5),
                VisualObservation("T02", 24, 48, "imagem escura", issues=["escuro"], interest=.1)],
        "T03": [VisualObservation("T03", 0, 60, "pessoa em close no parque", shot="close")],
        "T04": [VisualObservation("T04", 22, 72, "crianças no parque", action="crianças brincam no balanço", interest=.9)],
        "T05": [VisualObservation("T05", 30, 200, "casal sentado conversando")],
        "T06": [VisualObservation("T06", 5, 21, "flores e árvores do parque", usable_as_broll=True, interest=.6)],
    }
    return build_inventory(takes, transcripts, observations)


def moment_id(inventory, take_id: str, kind: str, index: int = 0) -> str:
    return [m.id for m in inventory.moments if m.take_id == take_id and m.kind == kind][index]
