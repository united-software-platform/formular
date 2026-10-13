# Tasks

## 1. Выдача норм и образца входом

- [x] 1.1 Добавить подкоманду `backlog norms`: нормы из `share/rules/operation-backlog-rules.md`, за ними глоссарий из `share/docs/glossary.md`; проверить тестом в `tests/test_backlog.py`, что вывод несёт оба документа и код `0`
- [x] 1.2 Добавить ключ `--rule BKL-NNN` с выдачей одного раздела и отказом кодом `2` на неизвестный код; проверить тестом по каждому коду `BKL-001`..`BKL-010` и по `BKL-999`
- [x] 1.3 Добавить подкоманду `backlog sample`, печатающую `templates/sample-operation.md` поставки; проверить тестом, что вывод начинается маркером версии и принимается `check-template`
- [x] 1.4 Описать `norms` и `sample` в справке входа и в комментарии `bin/backlog`; проверить, что `backlog --help` их перечисляет

## 2. Беклог называет нормы кодом

- [x] 2.1 Перевести каркас структурной проверки с якорей `EXECUTION_NORM_ANCHORS` на коды `BKL-005`..`BKL-008` в тексте беклога; проверить тестами сценарии «Норма названа кодом без ссылки», «Норма названа кодом со ссылкой прежнего вида», «Беклог без ссылки на норму исполнения»
- [x] 2.2 Удалить подстановку `rules` из выводимых значений порождения и `_rules_link`; проверить тестом, что шаблон с `{{rules}}` отказывает порождением кодом `2`
- [x] 2.3 Перевести `plugin/backlog/templates/sample-operation.md` с `{{rules}}` на «код (`backlog norms --rule …`)» и поднять версию шаблона; проверить `backlog check-template plugin/backlog/templates/sample-operation.md` — код `0` (`BKL-009`)

## 3. Удаление установки и вендоренной поставки

- [x] 3.1 Удалить подкоманду `install`, `application/install_rules.py`, их контракты и адаптеры (`FileDelivery`, `FileProject`, `FileManifest`, `ImportLine`), `IMPORT_LINES`, `IGNORE_LINES`; удалить `InstallRulesTest`; проверить `python3 -m unittest discover -s tests` — без ошибок
- [x] 3.2 Убрать `.backlog-manifest.json` из маркеров корня проекта; проверить тестом, что корень находится по `.git` из подкаталога
- [x] 3.3 Удалить ветку вендоренной поставки в `bin/backlog`, оставив умолчание `BACKLOG_RUNNER=/backlog:backlog-run` и переопределение переменной; проверить, что порождённый беклог несёт `runner: "/backlog:backlog-run"`

## 4. Рекомендация для `.gitignore`

- [x] 4.1 В `generate` печатать в поток ошибок рекомендацию для `.gitignore`, когда корень следа заводится впервые, и не печатать, когда он уже лежит; проверить тестами оба сценария и то, что `.gitignore` не меняется
- [x] 4.2 Добавить ту же рекомендацию в справку входа; проверить `backlog --help`

## 5. Нормы и навыки поставки

- [x] 5.1 Перенести в `BKL-002` сведения `share/backlog/README.md`, которых в норме нет (ключ `--root`, рекомендация для `.gitignore`), удалить `share/backlog/README.md`; проверить, что в поставке нет ссылок на удалённый файл
- [x] 5.2 Переформулировать `BKL-008` (норма называется кодом правила и вызовом `backlog norms --rule`) и `BKL-010` (каркас — коды норм исполнения), обновить таблицу правил и таблицу версий документа; проверить, что `--rule BKL-008` и `--rule BKL-010` выдают новый текст
- [x] 5.3 Перевести навыки `backlog-run` и `backlog-template` с `${CLAUDE_PROJECT_DIR}/…` на `${CLAUDE_PLUGIN_ROOT}/share/…` и `${CLAUDE_PLUGIN_ROOT}/templates/…`, ссылку на `backlog/README.md` — на `BKL-002`; в `backlog-template` назвать `backlog norms` и `backlog sample` для внешнего вызова; проверить поиском, что `${CLAUDE_PROJECT_DIR}/rules` и `backlog/README.md` в навыках не встречаются
- [x] 5.4 Поднять версию в `plugin/backlog/.claude-plugin/plugin.json` до `1.3.0`; проверить, что `backlog norms` идёт без ошибки версии поставки

## 6. Репозиторий formular

- [x] 6.1 Перевести шаблоны `templates/*.md` (кроме копии образца) с `{{rules}}` на коды с вызовом и поднять их версии; проверить `backlog check-template` по каждому — код `0`
- [x] 6.2 Удалить корневые `rules/operation-backlog-rules.md`, `docs/glossary.md`, `backlog/README.md`, `templates/sample-operation.md`, `.backlog-manifest.json`; убрать `!backlog/README.md` из `.gitignore`, оставив `backlog/*`; проверить `git status`
- [x] 6.3 В `CLAUDE.md` перевести `@`-импорты на `@plugin/backlog/share/rules/operation-backlog-rules.md` и `@plugin/backlog/share/docs/glossary.md`, ссылки раздела «Понятия» и перечня правил — на источник, удалить абзац о установленной копии и `backlog install`, дописать строку версии; проверить, что все относительные ссылки файла разрешаются
- [x] 6.4 Обновить `README.md`, `CONTRIBUTING.md`, `AGENTS.md`: убрать `backlog install` и манифест, назвать `norms`/`sample`, ограничение claude.ai и Cowork, нормы — ссылкой на источник; проверить поиском, что `backlog install`, `.backlog-manifest.json` и ссылки на удалённые корневые файлы не встречаются

## 7. Подключение плагина в formular и сквозная проверка

- [x] 7.1 Прочитать `.claude-plugin/marketplace.json` и убедиться, что источник плагина — относительный путь; проверить вызовом навыка, что `${CLAUDE_PLUGIN_ROOT}` подставляется в `plugin/backlog/` репозитория
- [x] 7.2 Проверить относительный путь маркетплейса в `.claude/settings.json` вместо `/app`; заменить, если платформа его принимает, иначе записать ограничение в `README.md`
- [x] 7.3 Сквозная проверка во временном каталоге с `git init`: `backlog sample` в `templates/`, `backlog generate --operation sample-operation …`, `backlog lint` по беклогу — коды `0`, а в дереве нет файлов, кроме шаблона и беклога, и `.gitignore`/`CLAUDE.md` не созданы
- [x] 7.4 Прогнать `python3 -m unittest discover -s tests` и `openspec validate deliver-norms-via-plugin --strict` — без ошибок

## Workflow follow-up

- Код, номер и описание задачи для коммитов уточнить у пользователя (`GIT-010`).
- При архивации удалить каталог спецификации `openspec/specs/backlog/rules-installation/`, оставшийся без требований.
