"""Проверки ядра беклога: грамматика шаблона, маркер версии, запись и установка состава.

Проверяется то, в чём дефект тих: рендер оставит лишнюю задачу, маркер версии пропадёт,
повторная запись перезапишет состоявшийся файл — и ни одно из трёх не заявит о себе само.
Исполняется стандартным unittest: зависимостей у ядра нет, и проверки их не добавляют.
"""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "plugin" / "backlog" / "src"))

from backlog import (  # noqa: E402
    BACKLOG_EXISTS,
    BACKLOG_WRITTEN,
    Backlog,
    FileBacklogs,
    FileDelivery,
    FileManifest,
    FileProject,
    ImportLine,
    load_template,
    render,
    scalar,
)
from backlog.application import (  # noqa: E402
    ALREADY_INSTALLED,
    CONFLICT,
    INSTALLED,
    LINE_ADDED,
    LINE_PRESENT,
    UPDATED,
    InstallRulesInput,
    InstallRulesUseCase,
)


class Refused(Exception):
    """Отказ прогона: в проверках он ловится, а не завершает процесс."""


def fail(message):
    raise Refused(message)


class RenderTest(unittest.TestCase):
    """Грамматика шаблона: подстановки и условные блоки."""

    def test_substitutes_values(self):
        text = render("предмет {{subject}} и {{version}}\n", {"subject": "проба", "version": "1"}, {}, fail)
        self.assertEqual(text, "предмет проба и 1\n")

    def test_keeps_block_on_flag(self):
        template = "начало\n{{#host}}\nхостовая задача\n{{/host}}\nконец\n"
        kept = render(template, {}, {"host": True}, fail)
        dropped = render(template, {}, {"host": False}, fail)
        self.assertIn("хостовая задача", kept)
        self.assertNotIn("хостовая задача", dropped)

    def test_negated_block_is_mirror(self):
        template = "{{^host}}\nхостовой части нет\n{{/^host}}\n"
        self.assertIn("хостовой части нет", render(template, {}, {"host": False}, fail))
        self.assertNotIn("хостовой части нет", render(template, {}, {"host": True}, fail))

    def test_refuses_substitution_without_value(self):
        """Подстановка без значения — дефект шаблона, и он виден порождению, а не исполнителю."""
        with self.assertRaises(Refused) as refusal:
            render("путь {{missing}}\n", {"other": "значение"}, {}, fail)
        self.assertIn("{{missing}}", str(refusal.exception))


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
