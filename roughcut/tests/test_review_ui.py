"""Exercise page callbacks and their actual NiceGUI component tree."""
import asyncio
import inspect
from dataclasses import replace
from pathlib import Path

from nicegui import Client, ui
from nicegui.page import page

from smartcut.schema import Cut, CutPlan, Word
from ui import silence
from ui.review_preview import ReviewPreview


def test_analysis_opens_processed_clip_and_populates_review(monkeypatch):
    async def exercise():
        async def inline(function, *args, **kwargs):
            return function(*args, **kwargs)

        plan = CutPlan('second.mp4', 10, 'colab',
                       words=[Word(0, 1, 'Olá'), Word(3, 4, 'mundo')],
                       cuts=[Cut(1.1, 2.9, 'pausa_na_frase')])
        monkeypatch.setattr(silence.run, 'io_bound', inline)
        monkeypatch.setattr(silence, 'analyze_clip', lambda *a, **k: (plan, {'plan': Path('review.json')}))
        with Client(page('/review-test')) as client:
            silence.smartcut_page()
            button = next(e for e in client.elements.values()
                          if isinstance(e, ui.button) and e.text == 'Analisar selecionados')
            callback = inspect.getclosurevars(next(iter(button._event_listeners.values())).handler).nonlocals['callback']
            refs = inspect.getclosurevars(callback).nonlocals
            refs['normalize'].value = False
            refs['output'].value = '/tmp/review-test'
            refs['state'].update(selected='first.mp4', files=[
                dict(path='first.mp4', name='first.mp4', duration=10, selected=False, thumb_key='a'),
                dict(path='second.mp4', name='second.mp4', duration=10, selected=True, thumb_key='b'),
            ])
            await callback()
            assert refs['state']['selected'] == 'second.mp4'
            elements = list(client.elements.values())
            assert any(isinstance(e, ReviewPreview) for e in elements)
            assert any(isinstance(e, ui.echart) for e in elements)
            texts = [str(getattr(e, 'text', '')) for e in elements]
            assert '1 ativos · 0 mantidos' in texts
            assert 'Olá mundo' in texts
            assert any('review.json' in text for text in texts)
            assert refs['status'].text.startswith('Análise concluída')

            def fail(*args, **kwargs):
                raise RuntimeError('Falha de áudio de teste')

            monkeypatch.setattr(silence, 'analyze_clip', fail)
            await callback()
            assert refs['status'].text == 'Falha na análise: Falha de áudio de teste'
            assert not refs['state']['running']

    asyncio.run(exercise())


def test_switching_review_video_preserves_its_cuts_and_rules():
    async def exercise():
        plan_a = CutPlan('a.mp4', 10, 'colab', words=[Word(0, 1, 'A'), Word(3, 4, 'B')], cuts=[Cut(1.1, 2.9, 'pausa_na_frase')])
        plan_b = CutPlan('b.mp4', 10, 'colab', words=[Word(0, 1, 'C'), Word(4, 5, 'D')], cuts=[Cut(1.1, 3.9, 'pausa_na_frase')])
        with Client(page('/switch-review-test')) as client:
            silence.smartcut_page()
            analyze_button = next(e for e in client.elements.values() if isinstance(e, ui.button) and e.text == 'Analisar selecionados')
            analyze = inspect.getclosurevars(next(iter(analyze_button._event_listeners.values())).handler).nonlocals['callback']
            refs = inspect.getclosurevars(analyze).nonlocals
            select_refs = inspect.getclosurevars(refs['select']).nonlocals
            controls = inspect.getclosurevars(select_refs['set_rules_controls']).nonlocals
            first = dict(path='a.mp4', name='a.mp4', duration=10, selected=True, thumb_key='a', plan=plan_a,
                         artifacts={}, disabled_cuts={0}, rules=silence.load_rules('colab'))
            second = dict(path='b.mp4', name='b.mp4', duration=10, selected=True, thumb_key='b', plan=plan_b,
                          artifacts={}, disabled_cuts=set(), rules=silence.load_rules('colab'))
            refs['state'].update(files=[first, second], selected='a.mp4')
            refs['refresh_review_selector']()
            refs['select'](first)
            first['rules'] = replace(first['rules'], pause_within_sentence_s=1.25)
            rules_a = first['rules']
            refs['select'](second)
            assert second['disabled_cuts'] == set()
            refs['select'](first)
            assert first['disabled_cuts'] == {0}
            assert first['rules'] == rules_a
            assert controls['within'].value == 1.25
            selector = select_refs['review_select']
            assert selector.options == {'a.mp4': 'a.mp4', 'b.mp4': 'b.mp4'}

    asyncio.run(exercise())
