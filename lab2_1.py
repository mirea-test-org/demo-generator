"""Лаба 2.1 — гибкое планирование (Scrum) в GitHub Projects."""
from project_lib import Lab

l = Lab("mirea-test-org", "PartsUnlimited", 2)
AREA = "Unlimited Parts\\PUL-Web"

print("Задача 1: команда, области, итерации")
l.team("PUL-Web", "Parts Unlimited Web. Итерации: Sprint 1–3. Область: Unlimited Parts\\PUL-Web (с подобластями)", [l.me])
l.add_options("Area", [(AREA, "BLUE", "Команда PUL-Web")])
l.view("PUL-Web: бэклог", "BOARD_LAYOUT", f'area:"{AREA}" sprint:"Sprint 1","Sprint 2","Sprint 3"')

print("Задача 2: рабочие элементы")
epic = l.issue("Обучение продуктам", "Epic", "Раздел обучения использованию продукции на сайте Parts Unlimited.")
l.assign(epic)
l.set(epic, Area=AREA, Sprint="Sprint 2", Status="New")

feature = l.issue("Осваиваем дашборды", "Feature", "Учебные материалы по работе с дашбордами.", parent=epic)
l.assign(feature)
l.set(feature, Area=AREA, Sprint="Sprint 2", Status="New")

pbis = []
for title in ("Как клиент, я хочу просмотреть новые учебники",
              "Как клиент, я хочу видеть недавно просмотренные учебники",
              "Как клиент, я хочу запрашивать новые учебные материалы"):
    p = l.issue(title, "Product Backlog Item", "", parent=feature)
    l.set(p, Area=AREA, Sprint="Sprint 2")
    pbis.append(p)

# перетаскивание по доске: Approved / Committed / Done
l.set(pbis[0], Status="Approved")
l.assign(pbis[0])
l.set(pbis[1], Status="Committed")
l.set(pbis[2], Status="Done")
l.close(pbis[2])

t1 = l.issue("Добавить страницу для самых последних учебников", "Task", "", parent=pbis[0])
l.set(t1, Area=AREA, Sprint="Sprint 2", Status="To Do", Remaining_Work=5, Activity="Development")
t2 = l.issue("Оптимизация запроса к данным для последних учебников", "Task", "", parent=pbis[0])
l.set(t2, Area=AREA, Sprint="Sprint 2", Status="To Do", Remaining_Work=3, Activity="Design")

print("Задача 3: спринт и ёмкость")
l.assign(t1)
# Ёмкость (в GitHub нет отдельной вкладки Capacity — фиксируем в status update проекта):
# 1 ч/день, 10 рабочих дней спринта, отпуск 5 рабочих дней -> 5 ч
l.set(t1, Remaining_Work=8)  # оценка пересмотрена: 5 -> 8 ч
l.status_update(
    "**Sprint 2 (PUL-Web) — ёмкость превышена.**\n\n"
    "| Участник | Активность | Ёмкость/день | Дней в спринте | Отпуск | Доступно | Назначено |\n"
    "|---|---|---|---|---|---|---|\n"
    f"| @{l.me} | Development | 1 ч | 10 | 5 дн. (02.11–06.11) | 5 ч | 8 ч |\n\n"
    "Задача «Добавить страницу для самых последних учебников» переоценена с 5 до 8 ч. "
    "Всего по спринту 11 ч при ёмкости команды 5 ч → перегрузка на 6 ч. "
    "Решение (перенос в Sprint 3) пока не принимаем.",
    "AT_RISK", start="2026-10-26", target="2026-11-06")

# Правило стиля: Development — зелёный (цвет варианта Activity отображается на карточках)
l.set_options("Activity", [(o["name"], "GREEN" if o["name"] == "Development" else o["color"],
                            "Разработка" if o["name"] == "Development" else o["description"])
                           for o in l.fields["Activity"]["options"]])

l.view("Sprint 2: Taskboard", "BOARD_LAYOUT", f'sprint:"Sprint 2" area:"{AREA}"')
l.view("Sprint 2: по людям", "TABLE_LAYOUT", f'sprint:"Sprint 2" area:"{AREA}" type:Task')
l.view("Ёмкость спринта", "TABLE_LAYOUT", f'sprint:@current assignee:{l.me} type:Task')
print("OK", l.project_url)
