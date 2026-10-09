"""Сценарий установки норм беклога в дерево целевого проекта.

Нормы попадают в контекст агента только подключением из дерева проекта: файл, лежащий
в каталоге поставки, подключить нельзя — каталог несёт версию и переписывается обновлением.
Поэтому состав поставки копируется в проект, а связь копии с источником держит манифест:
версия поставки, время установки и слепок каждого установленного файла.

Слепок и решает, что делать с лежащим файлом. Совпал со слепком источника — установлено,
делать нечего. Совпал с записанным в манифест, а источник ушёл вперёд — обновляется.
Не совпал ни с тем, ни с другим — файл правил потребитель, и перезапись уничтожила бы
правку, о которой поставка не знает: расхождение называется, а решение остаётся владельцу.

Расхождение прочих файлов не останавливает: наполовину установленный состав хуже обоих
определённых исходов, поэтому прогон доводит доводимое и перечисляет оставшееся.
"""

import dataclasses

# Исходы по файлу.
INSTALLED = "installed"
ALREADY_INSTALLED = "already-installed"
UPDATED = "updated"
CONFLICT = "conflict"

# Исходы по строке подключения: она дописывается однажды и повторно не удваивается.
LINE_ADDED = "line-added"
LINE_PRESENT = "line-present"


@dataclasses.dataclass(frozen=True)
class InstallRulesInput:
    """Входной контракт установки: версия поставки и строки подключения.

    Неизменяем и логики не содержит. Состав копируемого сценарий не перечисляет — его
    называет сама поставка: перечень, записанный здесь, разошёлся бы с её содержимым.
    """

    delivery_version: str
    installed_at: str
    lines: tuple = ()


@dataclasses.dataclass(frozen=True)
class Installed:
    """Установленное прежде: версия поставки и слепки файлов по путям."""

    version: str = ""
    files: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class FileOutcome:
    """Исход по одному файлу состава: путь в проекте и что с ним стало."""

    path: str
    outcome: str


@dataclasses.dataclass(frozen=True)
class LineOutcome:
    """Исход по одной строке подключения: файл, строка и что с ней стало."""

    path: str
    line: str
    outcome: str


@dataclasses.dataclass(frozen=True)
class InstallRulesOutput:
    """Выходной контракт установки: исходы по файлам и по строкам подключения."""

    files: tuple = ()
    lines: tuple = ()

    @property
    def conflicts(self):
        """Файлы, которых прогон не коснулся: их правил потребитель."""
        return tuple(item for item in self.files if item.outcome == CONFLICT)


class InstallRulesUseCase:
    """Установка состава поставки в дерево проекта: единственная операция execute."""

    def __init__(self, delivery, project, manifest):
        self._delivery = delivery
        self._project = project
        self._manifest = manifest

    def execute(self, request):
        """Устанавливает состав поставки и ведёт манифест установленного."""
        recorded = self._manifest.read()
        files = []
        installed = {}

        for item in self._delivery.items():
            remembered = recorded.files.get(item.path)
            outcome = self._install(item, remembered)
            files.append(FileOutcome(path=item.path, outcome=outcome))
            if outcome != CONFLICT:
                installed[item.path] = item.digest
            elif remembered is not None:
                # Запись расхождения сохраняется: ею прогон помнит, чем ставил файл сам.
                # Потеряв её, он уже не отличит возвращённую потребителем копию от чужого
                # файла и обновить состав никогда не сможет.
                installed[item.path] = remembered

        lines = tuple(
            LineOutcome(
                path=line.path,
                line=line.text,
                outcome=(
                    LINE_PRESENT
                    if self._project.has_line(line.path, line.text)
                    else self._add_line(line)
                ),
            )
            for line in request.lines
        )

        # Манифест переписывается только при действительном изменении: время установки,
        # переписанное на прогоне, который ничего не сделал, выглядело бы правкой состояния
        # там, где состояние не менялось.
        if (
            installed != recorded.files
            or request.delivery_version != recorded.version
        ):
            self._manifest.write(
                version=request.delivery_version,
                installed_at=request.installed_at,
                files=installed,
            )
        return InstallRulesOutput(files=tuple(files), lines=lines)

    def _install(self, item, remembered):
        """Решает судьбу одного файла состава по его слепку."""
        present = self._project.digest_of(item.path)

        if present is None:
            self._project.write(item.path, item.text)
            return INSTALLED
        if present == item.digest:
            return ALREADY_INSTALLED
        if remembered is not None and present == remembered:
            self._project.write(item.path, item.text)
            return UPDATED
        return CONFLICT

    def _add_line(self, line):
        """Дописывает строку подключения, которой в файле проекта нет."""
        self._project.add_line(line.path, line.text, line.after)
        return LINE_ADDED
