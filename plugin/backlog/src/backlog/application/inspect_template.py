"""Сценарий интроспекции шаблона операции.

Интроспекция отвечает на вопрос, из чего шаблон собирается в вызов порождения: какие
подстановки порождение заполняет само, какие требуют значения вызова и какие признаки
условных блоков шаблон несёт. Навык порождения берёт этот состав вызовом входа, а не чтением
шаблона глазами: грамматика принадлежит ядру, и второй её носитель разошёлся бы при первой
же правке.

Разбиение на группы — знание сценария, а не входа: вход печатает группы, но не решает,
какая подстановка куда попадает. Перечень выводимых имён приходит готовым — его знает
порождение, и интроспекция его лишь потребляет.
"""

import dataclasses

# Суффикс парной подстановки: значение того же ключа в виде, пригодном фронтматтером.
SCALAR_SUFFIX = "_scalar"


@dataclasses.dataclass(frozen=True)
class InspectTemplateInput:
    """Входной контракт интроспекции: версия шаблона, его грамматика и выводимые имена.

    Неизменяем и логики не содержит. Грамматика приходит разобранной, перечень выводимых
    имён — собранным порождением: интроспекция делит готовый состав, а не добывает его.
    """

    template_version: str
    substitutions: tuple
    flags: tuple = ()
    derived: tuple = ()


@dataclasses.dataclass(frozen=True)
class InspectTemplateOutput:
    """Выходной контракт интроспекции: три группы состава шаблона.

    Выводимые имена ограничены встречающимися в шаблоне: перечень порождения шире, и лишние
    имена читателю состава ничего не сообщали бы.
    """

    template_version: str
    derived: tuple = ()
    values: tuple = ()
    flags: tuple = ()


class InspectTemplateUseCase:
    """Интроспекция шаблона операции: единственная публичная операция execute."""

    def execute(self, request):
        """Делит подстановки шаблона на выводимые порождением и требующие значения."""
        known = set(request.derived)
        derived = []
        required = []
        for name in request.substitutions:
            if name in known:
                derived.append(name)
                continue
            # Парная подстановка значением своего ключа: значения вызова ключ даёт сразу
            # обоим видам, и отдельного вопроса владельцу пара не рождает.
            base = name[: -len(SCALAR_SUFFIX)] if name.endswith(SCALAR_SUFFIX) else name
            if base not in required:
                required.append(base)
        return InspectTemplateOutput(
            template_version=request.template_version,
            derived=tuple(derived),
            values=tuple(required),
            flags=tuple(request.flags),
        )
