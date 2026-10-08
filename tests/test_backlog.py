"""Проверки ядра беклога: грамматика шаблона, маркер версии, идемпотентность записи.

Проверяется то, в чём дефект тих: рендер оставит лишнюю задачу, маркер версии пропадёт,
повторная запись перезапишет состоявшийся файл — и ни одно из трёх не заявит о себе само.
Исполняется стандартным unittest: зависимостей у ядра нет, и проверки их не добавляют.
"""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from backlog import (  # noqa: E402
    BACKLOG_EXISTS,
    BACKLOG_WRITTEN,
    Backlog,
    FileBacklogs,
    load_template,
    render,
    scalar,
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
