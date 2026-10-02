"""Textos editáveis enviados aos modelos e regras do app, com padrão e histórico.

O padrão fica no repositório (`prompts/`, `config/`). Edições feitas pela área
de Configurações ficam em `.state/ajustes/` e têm prioridade; cada salvamento
guarda a versão anterior em `.state/ajustes/historico/`.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES = ROOT / ".state" / "ajustes"
HISTORY = OVERRIDES / "historico"
PROMPT, YAML = "prompt", "yaml"
VISION, STORIES, SPEECH, SCENES, RUN = "visao", "historias", "transcricao", "cenas", "execucao"
IMPACT = {
    VISION: "Refaz a descrição visual de todos os takes na próxima análise (a transcrição é mantida).",
    STORIES: "Vale ao clicar em “Refazer histórias”; transcrição e visão são reaproveitadas.",
    SPEECH: "Refaz a transcrição na próxima análise.",
    SCENES: "Vale ao refazer as histórias; nada é analisado de novo.",
    RUN: "Vale na próxima análise ou render.",
}


@dataclass(frozen=True)
class Editable:
    key: str
    label: str
    group: str
    kind: str
    default: Path
    description: str
    affects: str
    required: tuple[str, ...] = ()

    @property
    def override(self) -> Path:
        return OVERRIDES / self.default.name


EDITABLES = (
    Editable("visao_ampla", "Descrição dos frames", "Visão", PROMPT, ROOT / "prompts" / "visao_ampla.md",
             "Enviado com 4 frames de cada trecho do take. Define o que o modelo descreve e o JSON de resposta.",
             VISION, ("instantes", "arquivo", "fala")),
    Editable("visao_detalhe", "Sequência de ação", "Visão", PROMPT, ROOT / "prompts" / "visao_detalhe.md",
             "Enviado com 6 frames em momentos de ação ou ambíguos para detalhar o que acontece do início ao fim.",
             VISION, ("instantes", "arquivo", "fala", "anterior", "total")),
    Editable("capitulos", "Capítulos do vídeo", "Planejador", PROMPT, ROOT / "prompts" / "capitulos.md",
             "Primeiro pedido do planejador: vê todos os takes em ordem e divide o dia em capítulos, escolhe o gancho.",
             STORIES, ("canal", "regras", "intencao", "formato", "duracao", "takes", "skills")),
    Editable("capitulo", "Blocos de cada capítulo", "Planejador", PROMPT, ROOT / "prompts" / "capitulo.md",
             "Um pedido por capítulo: escolhe falas, descarta o fraco e indica imagens de apoio.",
             STORIES, ("video", "numero", "total", "capitulo", "papel", "duracao", "regras", "momentos", "skills")),
    Editable("canal", "Regras do canal e formatos", "Regras", YAML, ROOT / "config" / "canal.yaml",
             "Público, regras editoriais e formatos. Entra nos dois pedidos do planejador.", STORIES),
    Editable("estilo", "Estilo de cena", "Regras", YAML, ROOT / "config" / "estilo.yaml",
             "Regras aplicadas sem modelo depois do planejador: juntar trechos, tamanho mínimo, papéis.", SCENES),
    Editable("glossario", "Glossário do Whisper", "Transcrição", YAML, ROOT / "config" / "glossario.yaml",
             "Nomes e lugares que o Whisper deve reconhecer e correções automáticas.", SPEECH),
    Editable("modelos", "Modelos e amostragem", "Execução", YAML, ROOT / "config" / "modelos.yaml",
             "Modelos locais, memória necessária, frames por trecho e passagem detalhada.", VISION),
    Editable("execucao", "Limites térmicos", "Execução", YAML, ROOT / "config" / "execucao.yaml",
             "Quando pausar e retomar no modo de cargas longas.", RUN),
)
BY_KEY = {item.key: item for item in EDITABLES}
BY_FILE = {item.default.name: item for item in EDITABLES}


def editable(key: str) -> Editable:
    return BY_KEY[key]


def resolve(file_name: str, folder: Path) -> Path:
    """Caminho efetivo de um arquivo de `prompts/` ou `config/`: a edição, se houver."""
    item = BY_FILE.get(file_name)
    if item is not None and item.override.is_file():
        return item.override
    return folder / file_name


def read(key: str) -> str:
    item = editable(key)
    return (item.override if item.override.is_file() else item.default).read_text(encoding="utf-8")


def read_default(key: str) -> str:
    return editable(key).default.read_text(encoding="utf-8")


def is_customized(key: str) -> bool:
    return editable(key).override.is_file()


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def validate(key: str, text: str) -> list[str]:
    item = editable(key)
    if item.kind == YAML:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as error:
            return [f"YAML inválido: {str(error).splitlines()[0]}"]
        return [] if isinstance(data, dict) else ["O arquivo precisa ser um mapa (chave: valor)."]
    try:
        found = placeholders(text)
        text.format(**{name: "" for name in found})
    except (ValueError, IndexError, KeyError) as error:
        return [f"Chaves {{ }} inválidas: {error}. Para escrever uma chave literal no JSON, use {{{{ e }}}}."]
    errors = [f"Falta a variável {{{name}}}: sem ela o modelo não recebe esses dados." for name in item.required if name not in found]
    errors += [f"Variável desconhecida {{{name}}}: o app não sabe preencher." for name in sorted(found - set(item.required))]
    return errors


def _snapshot(item: Editable, text: str) -> Path:
    folder = HISTORY / item.key
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{item.default.suffix}"
    target.write_text(text, encoding="utf-8")
    return target


def save(key: str, text: str) -> list[str]:
    errors = validate(key, text)
    if errors:
        return errors
    item = editable(key)
    _snapshot(item, read(key))
    item.override.parent.mkdir(parents=True, exist_ok=True)
    item.override.write_text(text, encoding="utf-8")
    _reload()
    return []


def restore_default(key: str) -> None:
    """A edição vai para o histórico e o padrão do repositório volta a valer."""
    item = editable(key)
    if item.override.is_file():
        _snapshot(item, item.override.read_text(encoding="utf-8"))
        item.override.unlink()
    _reload()


def history(key: str) -> list[Path]:
    folder = HISTORY / editable(key).key
    return sorted(folder.glob("*"), reverse=True) if folder.is_dir() else []


def estimate_tokens(text: str) -> int:
    return round(len(text) / 3.6)


def _reload() -> None:
    from .config import load_yaml
    load_yaml.cache_clear()
