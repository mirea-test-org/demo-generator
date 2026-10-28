"""Лаба 3 — планы поставок (Delivery Plans) на роадмапе GitHub Projects."""
from project_lib import Lab

l = Lab("mirea-test-org", "PartsUnlimited", 2)
EXT = "Unlimited Parts\\External integrations"

print("Задача 2: план поставки")
l.view("Поставка Веб-приложения", "ROADMAP_LAYOUT", 'type:"Product Backlog Item" -status:Done')
# Маркер на последнюю пятницу месяца -> веха (milestone) с датой
l.milestone("Команда в отпуске", "2026-10-30", "Маркер плана поставки: команда в отпуске")

print("Задача 3: внешняя команда и её итерации")
l.team("External integrations", "Интеграция с внешними сервисами (погода, банковские платежи, доставка)", [l.me])
l.add_options("Area", [(EXT, "ORANGE", "Команда External integrations")])
# Итерация 50: сегодня (ср 28.10) — третья пятница (13.11) = 17 дней
# Итерация 51: пн после окончания (16.11) — третья пятница после начала (04.12) = 19 дней
l.add_iterations([("Итерация 50", "2026-10-28", 17), ("Итерация 51", "2026-11-16", 19)])

print("Задача 4: решения о поставке")
weather = l.issue("Интеграция с метеорологической службой", "Product Backlog Item", "Получение прогнозов погоды от внешнего сервиса.")
l.set(weather, Area=EXT, Sprint="Итерация 50", Status="New")
shipping = l.issue("Интеграция с корпоративными данными доставок", "Product Backlog Item", "Интеграция с данными службы доставки компании.")
l.set(shipping, Area=EXT, Sprint="Итерация 51", Status="New")

# Зависимость обнаружена: отслеживание посылок не может быть готово раньше интеграции с данными доставок.
# Меняем итерации местами у внешней команды...
l.set(shipping, Sprint="Итерация 50")
l.set(weather, Sprint="Итерация 51")
# ...и переносим элемент основной команды из Sprint 1 в Sprint 4
tracking = l.issue("Provide customers the ability to track status of the package", "Product Backlog Item")
l.close(tracking, closed=False)
l.set(tracking, Sprint="Sprint 4", Status="Committed")
try:
    l.gh.rest("POST", f"repos/{l.org}/{l.repo}/issues/{tracking['number']}/dependencies/blocked_by",
              {"issue_id": l.gh.rest("GET", f"repos/{l.org}/{l.repo}/issues/{shipping['number']}")["id"]})
except RuntimeError as e:
    if "already" not in str(e).lower():
        raise
l.comment(tracking, f"Перенесено из Sprint 1 в Sprint 4: зависит от #{shipping['number']} "
                    "(команда External integrations, Итерация 50).")
l.view("План поставки: команды", "ROADMAP_LAYOUT", f'type:"Product Backlog Item" -status:Done')
print("OK")
