"""Проверки ядра беклога: грамматика шаблона, маркер версии, запись, проверки и установка.

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
    FileDelivery,
    FileManifest,
    FileProject,
    FileTemplates,
    ImportLine,
    Leftover,
    MarkdownBacklog,
    execution_findings,
    load_template,
    render,
    scalar,
    structure_findings,
    template_grammar,
)
from backlog.__main__ import main  # noqa: E402
from backlog.application import (  # noqa: E402
    ACCEPTED,
    ALREADY_INSTALLED,
    DEFECTIVE,
    TOO_MANY_FLAGS,
    CheckTemplateInput,
    CheckTemplateUseCase,
    CLEAN,
    CONFLICT,
    EXECUTED,
    FOUND,
    GENERATED,
    INCOMPLETE,
    INSTALLED,
    LINE_ADDED,
    LINE_PRESENT,
    REJECTED,
    UPDATED,
    GenerateBacklogInput,
    GenerateBacklogUseCase,
    InstallRulesInput,
    InstallRulesUseCase,
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


if __name__ == "__main__":
    unittest.main()


class InstallRulesTest(unittest.TestCase):
    """Установка состава поставки: идемпотентность, расхождение и строки подключения.

    Проверяется то, в чём дефект тих: повторный прогон перепишет манифест временем
    установки, расхождение потеряет запись о том, чем файл ставился, строка подключения
    удвоится — ни одно из трёх не заявит о себе само.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.temporary.name)
        self.share = base / "share"
        self.project = base / "project"
        (self.share / "rules").mkdir(parents=True)
        (self.share / "rules" / "norm.md").write_text("норма\n", encoding="utf-8")
        self.project.mkdir()
        self.addCleanup(self.temporary.cleanup)

    def _run(self, version="1.0.0", installed_at="2026-10-09T00:00:00Z", lines=()):
        use_case = InstallRulesUseCase(
            delivery=FileDelivery(self.share, fail=fail),
            project=FileProject(self.project, fail),
            manifest=FileManifest(self.project, fail),
        )
        return use_case.execute(
            InstallRulesInput(
                delivery_version=version, installed_at=installed_at, lines=lines
            )
        )

    def test_installs_absent_file(self):
        result = self._run()
        self.assertEqual([item.outcome for item in result.files], [INSTALLED])
        self.assertEqual(
            (self.project / "rules" / "norm.md").read_text(encoding="utf-8"), "норма\n"
        )

    def test_repeated_run_leaves_state_untouched(self):
        self._run()
        manifest = self.project / FileManifest(self.project, fail).path.name
        before = manifest.read_text(encoding="utf-8")

        result = self._run(installed_at="2026-12-31T23:59:59Z")

        self.assertEqual([item.outcome for item in result.files], [ALREADY_INSTALLED])
        self.assertEqual(manifest.read_text(encoding="utf-8"), before)

    def test_updates_file_left_as_installed(self):
        self._run()
        (self.share / "rules" / "norm.md").write_text("норма, правленная поставкой\n", encoding="utf-8")

        result = self._run()

        self.assertEqual([item.outcome for item in result.files], [UPDATED])
        self.assertEqual(
            (self.project / "rules" / "norm.md").read_text(encoding="utf-8"),
            "норма, правленная поставкой\n",
        )

    def test_consumer_edit_is_not_overwritten(self):
        self._run()
        edited = self.project / "rules" / "norm.md"
        edited.write_text("норма, правленная потребителем\n", encoding="utf-8")

        result = self._run()

        self.assertEqual([item.outcome for item in result.files], [CONFLICT])
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(
            edited.read_text(encoding="utf-8"), "норма, правленная потребителем\n"
        )

    def test_conflict_keeps_manifest_record(self):
        self._run()
        remembered = FileManifest(self.project, fail).read().files["rules/norm.md"]
        (self.project / "rules" / "norm.md").write_text("правка потребителя\n", encoding="utf-8")

        self._run()

        kept = FileManifest(self.project, fail).read().files["rules/norm.md"]
        self.assertEqual(kept, remembered)

    def test_import_line_is_added_once(self):
        line = ImportLine(path="CLAUDE.md", text="@rules/norm.md")

        first = self._run(lines=(line,))
        second = self._run(lines=(line,))

        self.assertEqual([item.outcome for item in first.lines], [LINE_ADDED])
        self.assertEqual([item.outcome for item in second.lines], [LINE_PRESENT])
        self.assertEqual(
            (self.project / "CLAUDE.md").read_text(encoding="utf-8").count("@rules/norm.md"), 1
        )

    def test_import_line_goes_after_named_line(self):
        (self.project / "CLAUDE.md").write_text("@rules/a.md\n@rules/b.md\n", encoding="utf-8")
        line = ImportLine(path="CLAUDE.md", text="@rules/norm.md", after="@rules/a.md")

        self._run(lines=(line,))

        self.assertEqual(
            (self.project / "CLAUDE.md").read_text(encoding="utf-8").splitlines(),
            ["@rules/a.md", "@rules/norm.md", "@rules/b.md"],
        )


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
NORM_ANCHORS = (
    "самодостаточность-значений",
    "признак-исполнения",
    "стоп-знак-необратимой-задачи",
    "передача-исполнения",
)
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
            rule_anchors=NORM_ANCHORS,
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
        anchors = tuple(a for a in NORM_ANCHORS if a != "стоп-знак-необратимой-задачи")
        messages = self.messages(self.document(rule_anchors=anchors))
        self.assertEqual(len(messages), 1)
        self.assertIn("#стоп-знак-необратимой-задачи", messages[0])

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

    def test_reads_rule_anchors(self):
        for anchor in NORM_ANCHORS:
            self.assertIn(anchor, self.document.rule_anchors)


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
        "rules": "../../../rules/operation-backlog-rules.md",
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
