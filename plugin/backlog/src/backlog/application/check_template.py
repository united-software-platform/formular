"""Сценарий приёмки шаблона операции.

Приёмка отвечает на вопрос, порождает ли шаблон цельный беклог при любом сочетании признаков
условных блоков. Порождение проверяет один вариант — тот, который назвал вызов; дефект ветки,
которую вызов не назвал, иначе доходит до исполнителя первым же прогоном с другим признаком.

Каждый вариант проходит тот же путь, что порождение до записи файла: рендер, разбор
и структурная проверка домена. Файла приёмка не пишет — единственный её результат есть
вердикт.

Число вариантов растёт как 2ⁿ от числа признаков, поэтому у перебора есть предел: шаблон
с большим числом признаков стоит разделить, а не перебирать.
"""

import dataclasses
import itertools

from ..domain import structure_findings

# Исходы сценария.
ACCEPTED = "accepted"
DEFECTIVE = "defective"
TOO_MANY_FLAGS = "too-many-flags"

# Предел числа признаков: при большем числе приёмка отказывает, а не перебирает.
MAX_FLAGS = 8


@dataclasses.dataclass(frozen=True)
class CheckTemplateInput:
    """Входной контракт приёмки: версия и текст шаблона, значения и перечень признаков.

    Неизменяем и логики не содержит. Значения приходят собранными: какие подстановки
    порождение заполняет само и чем заполнить прочие — забота сборки вызова.
    """

    template_version: str
    text: str
    values: dict
    flags: tuple = ()


@dataclasses.dataclass(frozen=True)
class VariantFinding:
    """Расхождение одного варианта: сочетание признаков и найденное в порождённом тексте.

    Сочетание названо рядом с расхождением, потому что дефект ветки виден только при ней:
    без сочетания вызывающему пришлось бы перебирать варианты самому.
    """

    flags: tuple
    finding: object


@dataclasses.dataclass(frozen=True)
class CheckTemplateOutput:
    """Выходной контракт приёмки: исход, число вариантов и расхождения с сочетаниями."""

    outcome: str
    variants: int = 0
    findings: tuple = ()


class CheckTemplateUseCase:
    """Приёмка шаблона операции: единственная публичная операция execute."""

    def __init__(self, render, parser):
        self._render = render
        self._parser = parser

    def execute(self, request):
        """Прогоняет шаблон по всем сочетаниям признаков и называет расхождения вариантов."""
        names = tuple(request.flags)
        if len(names) > MAX_FLAGS:
            return CheckTemplateOutput(outcome=TOO_MANY_FLAGS, variants=2 ** len(names))

        values = dict(request.values)
        values.setdefault("template_version", request.template_version)

        found = []
        variants = 0
        for states in itertools.product((True, False), repeat=len(names)):
            flags = dict(zip(names, states))
            variants += 1
            rendered = self._render(request.text, values, flags)
            for finding in structure_findings(self._parser.parse(rendered)):
                found.append(VariantFinding(flags=tuple(flags.items()), finding=finding))

        return CheckTemplateOutput(
            outcome=DEFECTIVE if found else ACCEPTED,
            variants=variants,
            findings=tuple(found),
        )
