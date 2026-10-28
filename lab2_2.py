"""Лаба 2.2 — Kanban, панели мониторинга, настройка процесса."""
from project_lib import Lab

l = Lab("mirea-test-org", "PartsUnlimited", 2)
AREA = "Unlimited Parts\\PUL-Web"
QA = "Утверждено QA"
DOD = "WIP-лимит: 1. Definition of Done: проходит **все** тесты."

new_tut = l.issue("Как клиент, я хочу просмотреть новые учебники", "Product Backlog Item")
recent = l.issue("Как клиент, я хочу видеть недавно просмотренные учебники", "Product Backlog Item")
request = l.issue("Как клиент, я хочу запрашивать новые учебные материалы", "Product Backlog Item")

print("Задача 4: Kanban")
l.label("данные", "FBCA04", "Работа с пользовательскими данными (выделяется на доске)")
l.label("ux", "C5DEF5", "Пользовательский интерфейс")
l.add_labels(new_tut, ["данные", "ux"])

# Новая колонка между Committed и Done
l.add_options("Status", [(QA, "PINK", DOD)], before="Done")
l.set(recent, Status=QA)
l.set(request, Status=QA)          # 2 элемента при лимите 1 — превышение WIP
l.close(request, closed=False)
l.comment(recent, f"Перемещено в «{QA}». В колонке 2 элемента при WIP-лимите 1 — превышение.")
l.set(recent, Status="Committed")  # возвращаем назад

# Разделение колонки на Doing / Done (pull-модель)
l.rename_option("Status", QA, f"{QA}: Doing", desc=DOD)
l.add_options("Status", [(f"{QA}: Done", "PINK", "Работа на этапе QA завершена, можно забирать в Done")], before="Done")
l.set(request, Status=f"{QA}: Doing")

# Дорожки (swimlanes)
l.create_field("Lane", "SINGLE_SELECT", [("Стандартная", "GRAY", ""), ("Ускоренная", "RED", "Приоритетная дорожка")])
l.set(recent, Status=f"{QA}: Doing", Lane="Ускоренная")
for it in (new_tut, request):
    l.set(it, Lane="Стандартная")
l.view("PUL-Web: Kanban", "BOARD_LAYOUT", f'area:"{AREA}" type:"Product Backlog Item",Bug')

print("Задача 5: панели мониторинга и запросы")
l.view("Веб-задачи", "TABLE_LAYOUT", f'type:Task area:"{AREA}"')
l.view("Обучение продукту", "TABLE_LAYOUT", f'area:"{AREA}" sprint:@current')

print("Задача 6: процесс «Мой Scrum» — поле PUL Ticket ID")
fields = l.gh.rest("GET", f"orgs/{l.org}/issue-fields")
field = next((f for f in fields if f["name"] == "PUL Ticket ID"), None)
if field is None:
    field = l.gh.rest("POST", f"orgs/{l.org}/issue-fields", {
        "name": "PUL Ticket ID", "description": "Ticket ID — внешний идентификатор тикета PartsUnlimited (группа PartsUnlimitedGroup)",
        "data_type": "text", "visibility": "organization_members_only"})
    print("  + поле организации PUL Ticket ID")
l.reload()
if "PUL Ticket ID" not in l.fields:
    l.gh.gql("mutation($p:ID!,$f:ID!){createProjectV2IssueField(input:{projectId:$p,issueFieldId:$f}){clientMutationId}}",
             p=l.project_id, f=field["node_id"])
first = l.issue("Provide related items or frequently bought together section when people browse or search", "Product Backlog Item")
l.gh.gql("""mutation($i:ID!,$f:ID!){setIssueFieldValue(input:{issueId:$i,issueFields:[{fieldId:$f,textValue:"PUL-1001"}]}){clientMutationId}}""",
         i=first["id"], f=field["node_id"])
print("OK")
