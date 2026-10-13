"""Проверки ядра беклога: грамматика шаблона, маркер версии, запись, проверки и выдача норм.

Проверяется то, в чём дефект тих: рендер оставит лишнюю задачу, маркер версии пропадёт,
повторная запись перезапишет состоявшийся файл, задача уйдёт в беклог без признака
«выполнено ранее», исполненная задача останется неотмеченной — и ни одно из этого
не заявит о себе само.

Исполняется стандартным unittest: зависимостей у ядра нет, и проверки их не добавляют.
"""

import contextlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "plugin" / "backlog" / "src"))

from backlog import (  # noqa: E402
    BACKLOG_EXISTS,
    BACKLOG_WRITTEN,
    Backlog,
    BacklogDocument,
    BacklogTask,
    FileBacklog,
    FileBacklogs,
    FileTemplates,
    Leftover,
    MarkdownBacklog,
    execution_findings,
    load_template,
    render,
    scalar,
    structure_findings,
    template_grammar,
)
from backlog.__main__ import _project_root, main  # noqa: E402
from backlog.application import (  # noqa: E402
    ACCEPTED,
    DEFECTIVE,
    TOO_MANY_FLAGS,
    CheckTemplateInput,
    CheckTemplateUseCase,
    CLEAN,
    EXECUTED,
    FOUND,
    GENERATED,
    INCOMPLETE,
    REJECTED,
    GenerateBacklogInput,
    GenerateBacklogUseCase,
    LintBacklogInput,
    LintBacklogUseCase,
    VerifyBacklogInput,
    VerifyBacklogUseCase,
)


class Refused(Exception):
    """Отказ прогона: в проверках он ловится, а не завершает процесс."""


def fail(message):
    raise Refused(message)


class RenderTest(unittest.TestCase):
    """Грамматика шаблона: подстановки и условные блоки."""

    def test_substitutes_values(self):
        text = render("предмет {{subject}} и {{version}}\n", {"subject": "проба", "version": "1"}, {})
        self.assertEqual(text, "предмет проба и 1\n")

    def test_keeps_block_on_flag(self):
        template = "начало\n{{#host}}\nхостовая задача\n{{/host}}\nконец\n"
        kept = render(template, {}, {"host": True})
        dropped = render(template, {}, {"host": False})
        self.assertIn("хостовая задача", kept)
        self.assertNotIn("хостовая задача", dropped)

    def test_negated_block_is_mirror(self):
        template = "{{^host}}\nхостовой части нет\n{{/^host}}\n"
        self.assertIn("хостовой части нет", render(template, {}, {"host": False}))
        self.assertNotIn("хостовой части нет", render(template, {}, {"host": True}))

    def test_leaves_substitution_without_value(self):
        """Остаток подстановки рендер не проверяет: его называет структурная проверка.

        Два носителя одного правила разошлись бы при первой правке, поэтому рендер
        оставляет остаток в тексте, а порождение отказывает по вердикту проверки.
        """
        text = render("путь {{missing}}\n", {"other": "значение"}, {})
        self.assertIn("{{missing}}", text)


class TemplateGrammarTest(unittest.TestCase):
    """Перечень подстановок и признаков шаблона: из него приёмка строит варианты."""

    def test_lists_substitutions_and_flags(self):
        template = (
            "target: {{target_scalar}}\n# {{target}} над {{subject}}\n"
            "{{#host}}\nхост {{target}}\n{{/host}}\n"
            "{{^remote}}\nбез удалённого\n{{/^remote}}\n"
            "{{#remote}}\nудалённый\n{{/remote}}\n"
        )
        grammar = template_grammar(template)
        self.assertEqual(grammar.substitutions, ("target_scalar", "target", "subject"))
        self.assertEqual(grammar.flags, ("host", "remote"))

    def test_template_without_grammar_is_empty(self):
        grammar = template_grammar("простой текст\n")
        self.assertEqual((grammar.substitutions, grammar.flags), ((), ()))


class ScalarTest(unittest.TestCase):
    """Вид значения во фронтматтере: кавычки только там, где без них неоднозначно."""

    def test_plain_value_stays_bare(self):
        self.assertEqual(scalar("проба"), "проба")

    def test_ambiguous_value_is_quoted(self):
        self.assertEqual(scalar("ключ: значение"), '"ключ: значение"')
        self.assertEqual(scalar("- список"), '"- список"')

    def test_quotes_are_escaped(self):
        self.assertEqual(scalar('он сказал "да": и ушёл'), '"он сказал \\"да\\": и ушёл"')


class TemplateVersionTest(unittest.TestCase):
    """Маркер версии шаблона: он живёт в шаблоне и в беклог не попадает."""

    def test_reads_version_and_strips_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "sample.md"
            path.write_text("<!-- template_version: 1.2.3 -->\nтело шаблона\n", encoding="utf-8")
            version, text = load_template(path, fail)
        self.assertEqual(version, "1.2.3")
        self.assertEqual(text, "тело шаблона\n")

    def test_refuses_template_without_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "sample.md"
            path.write_text("тело без маркера\n", encoding="utf-8")
            with self.assertRaises(Refused):
                load_template(path, fail)

    def test_refuses_missing_template(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Refused):
                load_template(pathlib.Path(directory) / "нет.md", fail)


class FileBacklogsTest(unittest.TestCase):
    """Каталог следа: адрес из пары и запрет перезаписи состоявшегося файла."""

    def test_address_is_operation_and_subject(self):
        with tempfile.TemporaryDirectory() as directory:
            backlogs = FileBacklogs(pathlib.Path(directory), fail)
            path = backlogs.path_of("sample-operation", "20261008120000")
        self.assertEqual(path.parts[-3:], ("sample-operation", "20261008120000", "tasks.md"))

    def test_second_write_keeps_first_file(self):
        """Порождённое не правится: повторная запись отвечает исходом, а файл остаётся прежним."""
        with tempfile.TemporaryDirectory() as directory:
            backlogs = FileBacklogs(pathlib.Path(directory), fail)
            backlog = Backlog(
                operation="sample-operation",
                subject="20261008120000",
                template_version="1.0.0",
                values={},
            )
            self.assertEqual(backlogs.add(backlog, "первый\n"), BACKLOG_WRITTEN)
            self.assertEqual(backlogs.add(backlog, "второй\n"), BACKLOG_EXISTS)
            self.assertEqual(
                backlogs.path_of(*backlog.address).read_text(encoding="utf-8"), "первый\n"
            )

    def test_exists_answers_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            backlogs = FileBacklogs(pathlib.Path(directory), fail)
            self.assertFalse(backlogs.exists("sample-operation", "20261008120000"))
            backlogs.add(
                Backlog("sample-operation", "20261008120000", "1.0.0", {}), "тело\n"
            )
            self.assertTrue(backlogs.exists("sample-operation", "20261008120000"))


# Беклог, отвечающий структуре целиком: от него отступают проверки структурных правил.
WHOLE_BACKLOG = """---
template_version: "1.1.0"
runner: "/backlog:backlog-run"
confirmed:
  irreversible_step: null
---

# Операция над предметом

Значения несёт фронтматтер ([BKL-005](../rules.md#самодостаточность-значений)), порядок
исполнения — [BKL-006](../rules.md#признак-исполнения), [BKL-007](../rules.md#стоп-знак-необратимой-задачи)
и [BKL-008](../rules.md#передача-исполнения).

- [ ] 1.1 Первая задача: прочитать `/backlog:backlog-run`
  - Проверка: состояние названо
  - Выполнено ранее: состояние уже таково
- [ ] 1.2 Прогнать `backlog lint` по этому беклогу
  - Проверка: код возврата 0
  - Выполнено ранее: проверка состояния
- [ ] 2.1 **Стоп-знак.** Необратимый шаг, подтверждение в `confirmed.irreversible_step`
  - Проверка: шаг исполнен
  - Выполнено ранее: состояние несёт результат шага

## Версионирование

| Версия | Дата | Задача | Агент | Модель | Описание изменений |
|--------|------|--------|-------|--------|--------------------|
| 1.0.0 | 2026-10-12 | проба | backlog | — | Беклог порождён |
"""


def executed(text):
    """Тот же беклог, но исполненный: отметки закрыты, подтверждение заполнено."""
    return text.replace("- [ ]", "- [x]").replace(
        "irreversible_step: null", 'irreversible_step: "владелец подтвердил"'
    )


RUNNER = "/backlog:backlog-run"
NORM_CODES = ("BKL-005", "BKL-006", "BKL-007", "BKL-008")


def coded(text):
    """Тот же беклог, но нормы названы кодом и вызовом входа, без ссылок на файл норм."""
    for code, anchor in zip(
        NORM_CODES,
        (
            "самодостаточность-значений",
            "признак-исполнения",
            "стоп-знак-необратимой-задачи",
            "передача-исполнения",
        ),
    ):
        text = text.replace(
            f"[{code}](../rules.md#{anchor})", f"{code} (`backlog norms --rule {code}`)"
        )
    return text
SELF_CHECK_TASK = BacklogTask(
    number="1.2",
    line=13,
    marked=False,
    has_check=True,
    has_completion_marker=True,
    text="1.2 Прогнать `backlog lint <путь этого беклога>`",
)


class StructureRulesTest(unittest.TestCase):
    """Структурные правила домена: чем беклог обязан быть."""

    def document(self, **changed):
        base = dict(
            frontmatter_parsed=True,
            frontmatter={"template_version": "1.1.0", "runner": RUNNER},
            template_version="1.1.0",
            tasks=(
                BacklogTask(
                    number="1.1",
                    line=10,
                    marked=False,
                    has_check=True,
                    has_completion_marker=True,
                    text=f"1.1 Прочитать носитель {RUNNER}",
                ),
                SELF_CHECK_TASK,
            ),
            runner_pointer=True,
            version_table=True,
            rule_codes=NORM_CODES,
        )
        base.update(changed)
        return BacklogDocument(**base)

    def messages(self, document):
        return [finding.message for finding in structure_findings(document)]

    def test_whole_backlog_has_no_findings(self):
        self.assertEqual(self.messages(self.document()), [])

    def test_names_every_finding_at_once(self):
        """Перечень отвечает одним прогоном: исправление по одному нарушению за прогон дорого."""
        document = self.document(
            frontmatter_parsed=False,
            runner_pointer=False,
            version_table=False,
            tasks=(
                BacklogTask(
                    number="1.1",
                    line=10,
                    marked=False,
                    has_check=False,
                    has_completion_marker=False,
                    text=f"1.1 Прочитать {RUNNER}",
                ),
                SELF_CHECK_TASK,
            ),
        )
        self.assertEqual(len(structure_findings(document)), 5)

    def test_task_without_check_is_named(self):
        document = self.document(
            tasks=(
                BacklogTask(
                    number="1.2",
                    line=14,
                    marked=False,
                    has_check=False,
                    has_completion_marker=True,
                    text=f"1.2 Прочитать {RUNNER}",
                ),
                SELF_CHECK_TASK,
            )
        )
        self.assertEqual(self.messages(document), ["задача 1.2 не несёт строки проверки"])

    def test_task_without_completion_marker_is_named(self):
        document = self.document(
            tasks=(
                BacklogTask(
                    number="1.3",
                    line=18,
                    marked=False,
                    has_check=True,
                    has_completion_marker=False,
                    text=f"1.3 Прочитать {RUNNER}",
                ),
                SELF_CHECK_TASK,
            )
        )
        self.assertEqual(
            self.messages(document), ["задача 1.3 не несёт признака «выполнено ранее»"]
        )

    def test_leftover_substitution_is_named(self):
        document = self.document(leftovers=(Leftover(line=7, text="{{target}}"),))
        self.assertIn("{{target}}", self.messages(document)[0])

    def test_frontmatter_without_template_version_is_named(self):
        document = self.document(frontmatter={}, template_version="")
        self.assertIn("template_version", self.messages(document)[0])

    def test_runner_pointer_is_required(self):
        """Указатель носителя порядка: без него исполнение идёт без порядка."""
        document = self.document(runner_pointer=False)
        self.assertEqual(
            self.messages(document),
            ["беклог не называет носителя порядка исполнения указателем"],
        )


    def test_backlog_without_self_check_is_named(self):
        """Вторая задача не называет `backlog lint`: беклог без самопроверки."""
        document = self.document(
            tasks=(
                self.document().tasks[0],
                BacklogTask(
                    number="1.2",
                    line=13,
                    marked=False,
                    has_check=True,
                    has_completion_marker=True,
                    text="1.2 Убедиться, что предмет существует",
                ),
            )
        )
        messages = self.messages(document)
        self.assertEqual(len(messages), 1)
        self.assertIn("backlog lint", messages[0])

    def test_backlog_without_stop_sign_norm_is_named(self):
        codes = tuple(code for code in NORM_CODES if code != "BKL-007")
        messages = self.messages(self.document(rule_codes=codes))
        self.assertEqual(len(messages), 1)
        self.assertIn("BKL-007", messages[0])
        self.assertIn("стоп-знак", messages[0])

    def test_norm_named_by_code_without_link(self):
        """Беклог называет нормы кодом и вызовом входа: ссылок на файл норм нет."""
        text = coded(WHOLE_BACKLOG)
        self.assertNotIn("rules.md", text)
        self.assertEqual(structure_findings(MarkdownBacklog().parse(text)), ())

    def test_norm_named_by_code_in_link_of_former_kind(self):
        """Прежний беклог несёт коды текстом ссылок, и файла по ссылке нет: адрес не сверяется."""
        self.assertIn("](../rules.md#признак-исполнения)", WHOLE_BACKLOG)
        self.assertEqual(structure_findings(MarkdownBacklog().parse(WHOLE_BACKLOG)), ())

    def test_backlog_without_any_norm_code_is_named(self):
        text = coded(WHOLE_BACKLOG).replace("BKL-007", "норма стоп-знака")
        messages = [
            finding.message
            for finding in structure_findings(MarkdownBacklog().parse(text))
        ]
        self.assertEqual(len(messages), 1)
        self.assertIn("BKL-007", messages[0])

    def test_first_task_without_runner_is_named(self):
        document = self.document(
            tasks=(
                BacklogTask(
                    number="1.1",
                    line=10,
                    marked=False,
                    has_check=True,
                    has_completion_marker=True,
                    text="1.1 Убедиться, что предмет существует",
                ),
                SELF_CHECK_TASK,
            )
        )
        messages = self.messages(document)
        self.assertEqual(len(messages), 1)
        self.assertIn("носитель порядка исполнения", messages[0])

    def test_skeleton_in_other_words_has_no_findings(self):
        """Каркас проверяется по смыслу, а не дословным совпадением с образцом."""
        document = self.document(
            tasks=(
                BacklogTask(
                    number="1",
                    line=10,
                    marked=False,
                    has_check=True,
                    has_completion_marker=True,
                    text=f"1 Перед работой открыть {RUNNER} и следовать ему",
                ),
                BacklogTask(
                    number="2",
                    line=13,
                    marked=False,
                    has_check=True,
                    has_completion_marker=True,
                    text="2 Убедиться, что `backlog lint` по файлу молчит",
                ),
            )
        )
        self.assertEqual(self.messages(document), [])


class ExecutionRulesTest(unittest.TestCase):
    """Правила полноты исполнения: отметки и подтверждения владельца."""

    def test_unmarked_task_is_named(self):
        document = MarkdownBacklog().parse(WHOLE_BACKLOG)
        messages = [finding.message for finding in execution_findings(document)]
        self.assertEqual(
            messages,
            ["задача 1.1 не отмечена", "задача 1.2 не отмечена", "задача 2.1 не отмечена"],
        )

    def test_executed_backlog_has_no_findings(self):
        document = MarkdownBacklog().parse(executed(WHOLE_BACKLOG))
        self.assertEqual(execution_findings(document), ())

    def test_stop_sign_without_confirmation_is_named(self):
        """Отметка утверждает исполнение, а следа подтверждения владельца в беклоге нет."""
        text = WHOLE_BACKLOG.replace("- [ ]", "- [x]")
        document = MarkdownBacklog().parse(text)
        messages = [finding.message for finding in execution_findings(document)]
        self.assertEqual(len(messages), 1)
        self.assertIn("confirmed.irreversible_step", messages[0])

    def test_completion_marker_is_not_checked(self):
        """Признак «выполнено ранее» описан прозой: его сверка остаётся исполняющему."""
        document = MarkdownBacklog().parse(executed(WHOLE_BACKLOG))
        self.assertTrue(all(task.has_completion_marker for task in document.tasks))
        self.assertEqual(execution_findings(document), ())


class MarkdownBacklogTest(unittest.TestCase):
    """Разбор порождённого беклога: разметка остаётся здесь, а не в домене."""

    def setUp(self):
        self.document = MarkdownBacklog().parse(WHOLE_BACKLOG)

    def test_reads_frontmatter_with_one_nesting_level(self):
        self.assertTrue(self.document.frontmatter_parsed)
        self.assertEqual(self.document.template_version, "1.1.0")
        self.assertEqual(
            self.document.frontmatter["confirmed.irreversible_step"], "null"
        )

    def test_reads_tasks_with_place_in_file(self):
        numbers = [(task.number, task.line) for task in self.document.tasks]
        self.assertEqual(numbers, [("1.1", 14), ("1.2", 17), ("2.1", 20)])

    def test_reads_stop_sign_and_confirmation_key(self):
        stop = self.document.tasks[2]
        self.assertTrue(stop.stop_sign)
        self.assertEqual(stop.confirmation, "confirmed.irreversible_step")

    def test_reads_runner_pointer_from_frontmatter(self):
        self.assertTrue(self.document.runner_pointer)

    def test_backlog_without_frontmatter_is_not_parsed(self):
        document = MarkdownBacklog().parse("# Беклог без фронтматтера\n")
        self.assertFalse(document.frontmatter_parsed)

    def test_reads_leftover_with_place_in_file(self):
        document = MarkdownBacklog().parse(
            WHOLE_BACKLOG.replace("Первая задача", "Задача над {{target}}")
        )
        self.assertEqual(
            [(item.line, item.text) for item in document.leftovers], [(14, "{{target}}")]
        )


class SampleParseTest(unittest.TestCase):
    """Разбор порождённого образца: слова задачи и якоря ссылок на нормы."""

    def setUp(self):
        _, text = load_template(DELIVERY_TEMPLATES / f"{SAMPLE_OPERATION}.md", fail)
        self.document = MarkdownBacklog().parse(
            render(text, _sample_values(), {"host-part": True})
        )

    def test_task_text_has_no_mark_markup(self):
        first = self.document.tasks[0]
        self.assertTrue(first.text.startswith("1.1 Прочитать носитель"), first.text)
        self.assertNotIn("- [ ]", first.text)
        self.assertIn("/backlog:backlog-run", first.text)
        self.assertIn("backlog lint", self.document.tasks[1].text)

    def test_reads_rule_codes(self):
        for code in NORM_CODES:
            self.assertIn(code, self.document.rule_codes)

    def test_names_norms_by_call_without_rules_file(self):
        _, text = load_template(DELIVERY_TEMPLATES / f"{SAMPLE_OPERATION}.md", fail)
        self.assertNotIn("{{rules}}", text)
        for code in NORM_CODES:
            self.assertIn(f"backlog norms --rule {code}", text)


class StoredBacklog:
    """Заглушка чтения проверяемого беклога: текст без файла на диске."""

    def __init__(self, text):
        self._text = text
        self.asked = []

    def read(self, path):
        self.asked.append(path)
        return self._text


class LintBacklogTest(unittest.TestCase):
    """Сценарий структурной проверки."""

    def test_whole_backlog_is_clean(self):
        use_case = LintBacklogUseCase(
            backlogs=StoredBacklog(WHOLE_BACKLOG), parser=MarkdownBacklog()
        )
        result = use_case.execute(LintBacklogInput(path="путь/tasks.md"))
        self.assertEqual(result.outcome, CLEAN)
        self.assertEqual(result.findings, ())

    def test_defect_is_found(self):
        text = WHOLE_BACKLOG.replace("  - Выполнено ранее: состояние уже таково\n", "")
        use_case = LintBacklogUseCase(
            backlogs=StoredBacklog(text), parser=MarkdownBacklog()
        )
        result = use_case.execute(LintBacklogInput(path="путь/tasks.md"))
        self.assertEqual(result.outcome, FOUND)
        self.assertIn("«выполнено ранее»", result.findings[0].message)

    def test_path_comes_from_the_call(self):
        """Адрес проверка не складывает: путь приходит значением вызова."""
        backlogs = StoredBacklog(WHOLE_BACKLOG)
        use_case = LintBacklogUseCase(backlogs=backlogs, parser=MarkdownBacklog())
        use_case.execute(LintBacklogInput(path="след/операция/предмет/tasks.md"))
        self.assertEqual(backlogs.asked, ["след/операция/предмет/tasks.md"])


class VerifyBacklogTest(unittest.TestCase):
    """Сценарий проверки полноты исполнения."""

    def verify(self, text):
        use_case = VerifyBacklogUseCase(
            backlogs=StoredBacklog(text), parser=MarkdownBacklog()
        )
        return use_case.execute(VerifyBacklogInput(path="путь/tasks.md"))

    def test_executed_backlog_is_whole(self):
        result = self.verify(executed(WHOLE_BACKLOG))
        self.assertEqual(result.outcome, EXECUTED)
        self.assertEqual(result.findings, ())

    def test_unmarked_task_makes_it_incomplete(self):
        result = self.verify(WHOLE_BACKLOG)
        self.assertEqual(result.outcome, INCOMPLETE)
        self.assertEqual(result.structure, ())
        self.assertEqual(len(result.execution), 3)

    def test_structure_findings_come_first(self):
        """Вердикт о полноте отметок осмыслен только на файле с целой грамматикой."""
        text = executed(WHOLE_BACKLOG).replace('runner: "/backlog:backlog-run"\n', "")
        result = self.verify(text)
        self.assertEqual(result.outcome, INCOMPLETE)
        self.assertIn("носителя порядка", result.findings[0].message)


class GenerateRejectsDefectTest(unittest.TestCase):
    """Структурная проверка внутри порождения: отказ до записи файла."""

    class Templates:
        def __init__(self, text):
            self._text = text

        def read(self, operation):
            return "1.1.0", self._text

    class Backlogs:
        def __init__(self):
            self.written = []

        def exists(self, operation, subject):
            return False

        def add(self, backlog, text):
            self.written.append(backlog.address)
            return BACKLOG_WRITTEN

    def generate(self, template_text):
        self.backlogs = self.Backlogs()
        use_case = GenerateBacklogUseCase(
            templates=self.Templates(template_text),
            backlogs=self.backlogs,
            render=render,
            parser=MarkdownBacklog(),
        )
        return use_case.execute(
            GenerateBacklogInput(operation="проба", subject="20261012000000", values={})
        )

    def test_defect_refuses_before_write(self):
        """У неудачи результата быть не должно: файл не заводится."""
        text = WHOLE_BACKLOG.replace("  - Проверка: состояние названо\n", "")
        result = self.generate(text)
        self.assertEqual(result.outcome, REJECTED)
        self.assertIn("не несёт строки проверки", result.findings[0].message)
        self.assertEqual(self.backlogs.written, [])

    def test_leftover_substitution_refuses_generation(self):
        """Остаток подстановки ловит структурная проверка, а не рендер."""
        result = self.generate(WHOLE_BACKLOG.replace("предметом", "{{subject}}"))
        self.assertEqual(result.outcome, REJECTED)
        self.assertIn("{{subject}}", result.findings[0].message)
        self.assertEqual(self.backlogs.written, [])

    def test_whole_template_is_written(self):
        result = self.generate(WHOLE_BACKLOG)
        self.assertEqual(self.backlogs.written, [("проба", "20261012000000")])


class CheckTemplateTest(unittest.TestCase):
    """Приёмка шаблона: перебор сочетаний признаков без записи файла."""

    def check(self, text, flags=()):
        use_case = CheckTemplateUseCase(render=render, parser=MarkdownBacklog())
        return use_case.execute(
            CheckTemplateInput(template_version="1.0.0", text=text, values={}, flags=flags)
        )

    def test_defect_only_when_flag_lowered_is_named_with_combination(self):
        text = WHOLE_BACKLOG.replace(
            "- [ ] 2.1",
            "{{#host}}\n- [ ] 3.1 Хостовая задача\n  - Проверка: сделано\n"
            "  - Выполнено ранее: сделано\n{{/host}}\n"
            "{{^host}}\n- [ ] 3.1 Хостовой части нет\n  - Проверка: прочитано\n"
            "{{/^host}}\n- [ ] 2.1",
        )
        result = self.check(text, flags=("host",))
        self.assertEqual(result.outcome, DEFECTIVE)
        self.assertEqual(result.variants, 2)
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0].flags, (("host", False),))
        self.assertIn("«выполнено ранее»", result.findings[0].finding.message)

    def test_template_without_flags_runs_once(self):
        result = self.check(WHOLE_BACKLOG)
        self.assertEqual(result.outcome, ACCEPTED)
        self.assertEqual(result.variants, 1)
        self.assertEqual(result.findings, ())

    def test_more_than_eight_flags_is_refused(self):
        flags = tuple(f"f{number}" for number in range(9))
        result = self.check(WHOLE_BACKLOG, flags=flags)
        self.assertEqual(result.outcome, TOO_MANY_FLAGS)
        self.assertEqual(result.findings, ())


class FileBacklogTest(unittest.TestCase):
    """Чтение проверяемого беклога: отсутствие файла — ошибка вызова."""

    def test_reads_lying_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / "tasks.md"
            target.write_text(WHOLE_BACKLOG, encoding="utf-8")
            self.assertEqual(FileBacklog(fail).read(target), WHOLE_BACKLOG)

    def test_refuses_absent_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Refused) as refusal:
                FileBacklog(fail).read(pathlib.Path(directory) / "нет.md")
            self.assertIn("не найден", str(refusal.exception))


# Каталоги поставки: образцовый шаблон лежит в поставке, а не в дереве проверок.
DELIVERY_TEMPLATES = (
    pathlib.Path(__file__).resolve().parents[1] / "plugin" / "backlog" / "templates"
)
SAMPLE_OPERATION = "sample-operation"

# Каталог проверок репозитория поставки: в проекте-потребителе его нет, и задача образца
# называть его не вправе.
DELIVERY_ONLY_DIR = "tests"


def _sample_values():
    """Значения вызова порождения по образцовому шаблону: тот же состав, что у входа.

    Версии шаблона среди них нет: её ставит сценарий маркером шаблона, и названная вызовом
    она подменила бы собой то, чем беклог порождён.
    """
    return {
        "date": "2026-10-12",
        "run_stamp": "20261012000000",
        "operation": SAMPLE_OPERATION,
        "subject": "проба",
        "runner": "/backlog:backlog-run",
        "target": "предмет операции",
        "target_scalar": scalar("предмет операции"),
    }


def _sample_task_blocks():
    """Блоки задач образцового шаблона: строка задачи и строки под ней.

    Текст задачи собирается из шаблона, а не из разобранного беклога: разобранная задача
    несёт номер и признаки, но не свои слова, а требование говорит именно о словах.
    """
    lines = (DELIVERY_TEMPLATES / f"{SAMPLE_OPERATION}.md").read_text(
        encoding="utf-8"
    ).splitlines()
    blocks = []
    current = None
    for line in lines:
        if line.startswith("- ["):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None:
            if line.startswith(("#", "---", "|")):
                blocks.append("\n".join(current))
                current = None
            else:
                current.append(line)
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


class DeliveredSampleTest(unittest.TestCase):
    """Пригодность приносимого образца: он порождается и исполним у потребителя.

    Проверка держит то, в чём дефект тих: образец поставки может не отвечать проверке
    этой же поставки, и порождение у потребителя откажет на первом же вызове — но ни один
    прогон репозитория поставки об этом не скажет.
    """

    def test_delivered_sample_generates_and_passes_structure(self):
        """Порождение по поставляемому образцу заводит файл, и структура расхождений не несёт."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            backlogs = FileBacklogs(root, fail)
            use_case = GenerateBacklogUseCase(
                templates=FileTemplates(DELIVERY_TEMPLATES, fail),
                backlogs=backlogs,
                render=render,
                parser=MarkdownBacklog(),
            )
            result = use_case.execute(
                GenerateBacklogInput(
                    operation=SAMPLE_OPERATION,
                    subject="проба",
                    values=_sample_values(),
                    flags={"host-part": False},
                )
            )
            self.assertEqual(result.outcome, GENERATED, result.findings)

            path = backlogs.path_of(SAMPLE_OPERATION, "проба")
            lint = LintBacklogUseCase(
                backlogs=FileBacklog(fail), parser=MarkdownBacklog()
            )
            verdict = lint.execute(LintBacklogInput(path=path))
            self.assertEqual(verdict.findings, ())
            self.assertEqual(verdict.outcome, CLEAN)

    def test_delivered_sample_names_no_delivery_only_directory(self):
        """Задача образца зовёт только то, что есть у потребителя."""
        blocks = _sample_task_blocks()
        self.assertTrue(blocks, "задач в образцовом шаблоне не нашлось")
        for block in blocks:
            self.assertNotIn(DELIVERY_ONLY_DIR, block, block)


class CheckTemplateEntryTest(unittest.TestCase):
    """Вход приёмки: коды возврата и отсутствие следа."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = pathlib.Path(self.temporary.name)
        self.root = self.base / "след"
        self.root.mkdir()

    def run_entry(self, *argv):
        """Исполняет вход; отказ входа завершает его SystemExit — код берётся из него."""
        environment = {"BACKLOG_ROOT": str(self.root), "CLAUDE_PROJECT_DIR": str(self.base)}
        with mock.patch.dict(os.environ, environment), contextlib.redirect_stdout(
            io.StringIO()
        ) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                code = main(list(argv))
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue() + err.getvalue()

    def test_sample_is_accepted_and_leaves_no_trace(self):
        code, output = self.run_entry(
            "check-template", str(DELIVERY_TEMPLATES / f"{SAMPLE_OPERATION}.md")
        )
        self.assertEqual(code, 0, output)
        self.assertIn("вариантов 2, расхождений 0", output.splitlines()[-1])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_absent_file_is_environment_error(self):
        code, _ = self.run_entry("check-template", str(self.base / "нет.md"))
        self.assertEqual(code, 2)

    def test_template_without_version_marker_is_environment_error(self):
        draft = self.base / "черновик.md"
        draft.write_text(WHOLE_BACKLOG, encoding="utf-8")
        code, output = self.run_entry("check-template", str(draft))
        self.assertEqual(code, 2)
        self.assertIn("маркера версии", output)

    def test_defect_is_named_with_combination(self):
        text = (DELIVERY_TEMPLATES / f"{SAMPLE_OPERATION}.md").read_text(encoding="utf-8")
        text = text.replace("  - Выполнено ранее: решение названо в этом сеансе\n", "")
        draft = self.base / "черновик.md"
        draft.write_text(text, encoding="utf-8")
        code, output = self.run_entry("check-template", str(draft))
        self.assertEqual(code, 1, output)
        self.assertIn("[host-part снят]", output)
        self.assertIn("расхождений 1", output.splitlines()[-1])
        self.assertEqual(list(self.root.iterdir()), [])


# Каталог поставки и её вход: вход запускается так же, как его запускает платформа.
DELIVERY_ROOT = DELIVERY_TEMPLATES.parent
DELIVERY_ENTRY = DELIVERY_ROOT / "bin" / "backlog"
RULE_CODES = tuple(f"BKL-{number:03d}" for number in range(1, 11))


class EntryCase(unittest.TestCase):
    """Вход в изолированном проекте: корень проекта, каталог шаблонов и каталог следа."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = pathlib.Path(self.temporary.name)
        self.templates = self.base / "templates"
        self.templates.mkdir()
        self.root = self.base / "backlog"

    def run_entry(self, *argv):
        """Исполняет вход; отказ входа завершает его SystemExit — код берётся из него."""
        environment = {
            "CLAUDE_PROJECT_DIR": str(self.base),
            "BACKLOG_TEMPLATES": str(self.templates),
            "BACKLOG_ROOT": str(self.root),
        }
        with mock.patch.dict(os.environ, environment), contextlib.redirect_stdout(
            io.StringIO()
        ) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            try:
                code = main(list(argv))
            except SystemExit as exit_:
                code = exit_.code
        self.out, self.err = out.getvalue(), err.getvalue()
        return code


class NormsEntryTest(EntryCase):
    """Выдача норм, глоссария и образца входом: канал внешнего вызова."""

    def test_norms_carry_rules_and_glossary(self):
        self.assertEqual(self.run_entry("norms"), 0, self.err)
        self.assertIn("# Правила беклога операции", self.out)
        self.assertIn("# Глоссарий понятий проекта", self.out)
        self.assertLess(
            self.out.index("# Правила беклога операции"),
            self.out.index("# Глоссарий понятий проекта"),
        )

    def test_each_rule_is_given_alone(self):
        for code in RULE_CODES:
            with self.subTest(code=code):
                self.assertEqual(self.run_entry("norms", "--rule", code), 0, self.err)
                self.assertIn(f"**[{code}]**", self.out)
                self.assertTrue(self.out.startswith("## "), self.out[:40])
                others = [
                    other for other in RULE_CODES
                    if other != code and f"**[{other}]**" in self.out
                ]
                self.assertEqual(others, [])
                self.assertNotIn("## Версионирование", self.out)

    def test_unknown_rule_is_refused(self):
        self.assertEqual(self.run_entry("norms", "--rule", "BKL-999"), 2)
        self.assertIn("BKL-999", self.err)
        self.assertEqual(self.out, "")

    def test_sample_starts_with_version_marker_and_is_accepted(self):
        self.assertEqual(self.run_entry("sample"), 0, self.err)
        self.assertTrue(self.out.startswith("<!-- template_version: "), self.out[:40])

        written = self.templates / f"{SAMPLE_OPERATION}.md"
        written.write_text(self.out, encoding="utf-8")
        self.assertEqual(self.run_entry("check-template", str(written)), 0, self.err)
        self.assertIn("расхождений 0", self.out)

    def test_help_names_norms_sample_and_ignore_advice(self):
        result = subprocess.run(
            ["sh", str(DELIVERY_ENTRY), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for word in ("norms", "sample", "--rule", ".gitignore", "backlog/*"):
            self.assertIn(word, result.stdout)
        self.assertNotIn("install", result.stdout)


class GenerateEntryTest(EntryCase):
    """Вход порождения: подстановка без значения, рекомендация для .gitignore."""

    def write_sample(self, text=None):
        source = DELIVERY_TEMPLATES / f"{SAMPLE_OPERATION}.md"
        target = self.templates / f"{SAMPLE_OPERATION}.md"
        target.write_text(
            text if text is not None else source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def generate(self, subject="проба"):
        return self.run_entry(
            "generate", "--operation", SAMPLE_OPERATION, "--subject", subject,
            "--value", "target=предмет", "--no-flag", "host-part",
        )

    def test_rules_substitution_is_refused(self):
        """Прежняя подстановка ссылки на нормы значения не получает: порождение отказывает."""
        text = (DELIVERY_TEMPLATES / f"{SAMPLE_OPERATION}.md").read_text(encoding="utf-8")
        self.write_sample(text.replace("по порядку.", "по порядку ({{rules}}).", 1))
        self.assertEqual(self.generate(), 2)
        self.assertIn("{{rules}}", self.err)
        self.assertFalse(self.root.exists())

    def test_fresh_root_prints_ignore_advice(self):
        gitignore = self.base / ".gitignore"
        gitignore.write_text("__pycache__/\n", encoding="utf-8")
        self.write_sample()
        self.assertEqual(self.generate(), 0, self.err)
        self.assertTrue((self.root / SAMPLE_OPERATION / "проба" / "tasks.md").is_file())
        self.assertIn(".gitignore", self.err)
        self.assertIn("`backlog/*`", self.err)
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "__pycache__/\n")

    def test_lying_root_prints_no_advice(self):
        self.root.mkdir()
        self.write_sample()
        self.assertEqual(self.generate(), 0, self.err)
        self.assertNotIn(".gitignore", self.err)
        self.assertFalse((self.base / ".gitignore").exists())


class ProjectRootTest(unittest.TestCase):
    """Корень проекта: маркер системы контроля версий, найденный вверх от рабочего каталога."""

    def test_root_is_found_by_git_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory).resolve()
            (base / ".git").mkdir()
            nested = base / "a" / "b"
            nested.mkdir(parents=True)
            previous = os.getcwd()
            environment = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
            try:
                os.chdir(nested)
                with mock.patch.dict(os.environ, environment, clear=True):
                    self.assertEqual(_project_root(), base)
            finally:
                os.chdir(previous)


class DeliveryEntryTest(unittest.TestCase):
    """Вход поставки: носитель порядка по умолчанию — навык плагина."""

    def test_generated_backlog_names_plugin_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            (base / "templates").mkdir()
            (base / "templates" / f"{SAMPLE_OPERATION}.md").write_text(
                (DELIVERY_TEMPLATES / f"{SAMPLE_OPERATION}.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            environment = {
                k: v for k, v in os.environ.items()
                if not k.startswith("BACKLOG_") and k != "CLAUDE_PROJECT_DIR"
            }
            environment["CLAUDE_PROJECT_DIR"] = str(base)
            result = subprocess.run(
                [
                    "sh", str(DELIVERY_ENTRY), "generate", "--operation", SAMPLE_OPERATION,
                    "--subject", "проба", "--value", "target=предмет", "--flag", "host-part",
                ],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            text = (base / "backlog" / SAMPLE_OPERATION / "проба" / "tasks.md").read_text(
                encoding="utf-8"
            )
            self.assertIn('runner: "/backlog:backlog-run"', text)


if __name__ == "__main__":
    unittest.main()
