# GitHub Demo Generator

Аналог [Azure DevOps Services Demo Generator](https://github.com/microsoft/AzDevOpsDemoGenerator) для GitHub.
Создаёт в организации проект **Parts Unlimited** с тестовыми данными из шаблона `Gen-PartsUnlimited`
оригинального генератора.

| Azure DevOps | GitHub |
|---|---|
| Azure Repos (импорт PartsUnlimited) | Приватный репозиторий со всеми ветками и тегами |
| Work items: Epic / Feature / PBI / Task / Bug | Issues с типами (issue types) |
| Иерархия Parent/Child | Sub-issues |
| Iterations (Sprint 1–6) | Поле-итерация `Sprint` в GitHub Project |
| Area, State, Effort, Remaining Work, Priority, Activity | Поля проекта |
| Teams | Команды организации, связанные с проектом |
| Queries / Boards | Представления (views) проекта |
| Pull requests с комментариями | Pull requests с комментариями |

## Запуск

```bash
pip install requests
gh auth login            # или PAT со scope: repo, project, admin:org, workflow
python generator.py      # интерактивно: шаблон → авторизация → организация → имя проекта
# или
python generator.py --org mirea-test-org --project "Unlimited Parts" --template PartsUnlimited
```

Скрипт идемпотентен: повторный запуск досоздаёт недостающее (`--resume` заново проставит поля).

Скрипты `lab2_1.py`, `lab2_2.py`, `lab3.py` воспроизводят шаги лабораторных 2.1, 2.2 и 3 на созданном проекте.
