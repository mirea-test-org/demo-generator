"""GitHub Demo Generator — аналог Azure DevOps Services Demo Generator для GitHub.

Создаёт в организации GitHub проект, наполненный тестовыми данными из шаблона
Azure DevOps Demo Generator (Gen-PartsUnlimited):

  * репозиторий с исходным кодом (импорт из Azure Repos) и демонстрационными PR;
  * типы задач Epic / Feature / Product Backlog Item / Task / Bug;
  * GitHub Project со спринтами (поле Iteration), областями, состояниями,
    оценками (Effort, Remaining Work), активностями и приоритетом;
  * issues с иерархией через sub-issues (Epic → Feature → PBI/Bug);
  * команды организации (аналог Teams) и сохранённые представления (аналог Queries).

Запуск:  python generator.py            — интерактивно, как ADOGenerator
         python generator.py --help     — параметры командной строки
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import tempfile

from gh_api import GitHub

HERE = pathlib.Path(__file__).parent
TEMPLATES = HERE / "templates"
MARK = re.compile(r"<!-- ado-id: (\d+) -->")

TYPES = {
    "Epic": ("Крупная бизнес-инициатива", "ORANGE"),
    "Feature": ("Функциональность системы", "PURPLE"),
    "Product Backlog Item": ("Элемент бэклога продукта (PBI)", "BLUE"),
    "Task": ("Конкретная задача", "YELLOW"),
    "Bug": ("Ошибка", "RED"),
}
STATES = [
    ("New", "GRAY"), ("Approved", "BLUE"), ("Committed", "PURPLE"),
    ("To Do", "GRAY"), ("In Progress", "YELLOW"), ("Done", "GREEN"),
]
ACTIVITIES = ["Deployment", "Design", "Development", "Documentation", "Requirements", "Testing"]
PRIORITIES = ["1", "2", "3", "4"]


def ask(prompt, default=None, choices=None):
    if choices:
        for i, c in enumerate(choices, 1):
            print(f"  {i}. {c}")
    while True:
        v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip() or (default or "")
        if not choices:
            if v:
                return v
            continue
        if v.isdigit() and 1 <= int(v) <= len(choices):
            return choices[int(v) - 1]
        if v in choices:
            return v


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class Generator:
    def __init__(self, gh: GitHub, org, project, repo, template, sprint_start, sprint_days, team_prefix):
        self.gh, self.org, self.project_title, self.repo = gh, org, project, repo
        self.tpl = TEMPLATES / template
        self.sprint_start, self.sprint_days = sprint_start, sprint_days
        self.team_prefix = team_prefix
        self.fields = {}
        self.resume = False

    # ---------- организация, репозиторий ----------
    def org_ids(self):
        d = self.gh.gql("query($o:String!){organization(login:$o){id} viewer{login id}}", o=self.org)
        self.org_id, self.viewer = d["organization"]["id"], d["viewer"]["login"]

    def ensure_repo(self, source_url):
        info = self.gh.rest("GET", f"repos/{self.org}/{self.repo}", ok404=True)
        if info is None:
            print(f"• Создаю приватный репозиторий {self.org}/{self.repo} и импортирую код из {source_url}")
            self.gh.rest("POST", f"orgs/{self.org}/repos", {
                "name": self.repo, "private": True,
                "description": f"{self.project_title} — демонстрационный проект (GitHub Demo Generator)",
            })
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(["git", "clone", "--mirror", "-q", source_url, tmp], check=True)
                token = self.gh.s.headers["Authorization"].split()[1]
                dst = f"https://x-access-token:{token}@github.com/{self.org}/{self.repo}.git"
                subprocess.run(["git", "-C", tmp, "push", "-q", dst, "refs/heads/*:refs/heads/*", "refs/tags/*:refs/tags/*"],
                               check=True)
            self.gh.rest("PATCH", f"repos/{self.org}/{self.repo}", {"default_branch": "master"})
        else:
            print(f"• Репозиторий {self.org}/{self.repo} уже существует — пропускаю импорт")
        r = self.gh.gql("query($o:String!,$n:String!){repository(owner:$o,name:$n){id}}", o=self.org, n=self.repo)
        self.repo_id = r["repository"]["id"]

    # ---------- типы задач ----------
    def ensure_issue_types(self):
        existing = {t["name"]: t for t in self.gh.rest("GET", f"orgs/{self.org}/issue-types")}
        self.type_ids = {}
        for name, (desc, color) in TYPES.items():
            if name not in existing:
                print(f"• Создаю тип задач «{name}»")
                t = self.gh.rest("POST", f"orgs/{self.org}/issue-types",
                                 {"name": name, "description": desc, "color": color.lower(), "is_enabled": True})
            else:
                t = existing[name]
            self.type_ids[name] = t["node_id"]

    # ---------- проект и поля ----------
    def ensure_project(self):
        q = """query($o:String!){organization(login:$o){projectsV2(first:50){nodes{id number title url}}}}"""
        for p in self.gh.gql(q, o=self.org)["organization"]["projectsV2"]["nodes"]:
            if p["title"] == self.project_title:
                self.project = p
                print(f"• Проект «{self.project_title}» уже существует: {p['url']}")
                break
        else:
            print(f"• Создаю GitHub Project «{self.project_title}»")
            self.project = self.gh.gql(
                """mutation($o:ID!,$t:String!,$r:ID!){createProjectV2(input:{ownerId:$o,title:$t,repositoryId:$r})
                   {projectV2{id number title url}}}""", o=self.org_id, t=self.project_title, r=self.repo_id
            )["createProjectV2"]["projectV2"]
        self.gh.gql("""mutation($p:ID!,$d:String!,$r:String!){updateProjectV2(input:{projectId:$p,
                       shortDescription:$d, readme:$r}){projectV2{id}}}""",
                    p=self.project["id"], d=f"Демо-проект {self.project_title}: бэклог, спринты, доски",
                    r=(self.tpl / "README.md").read_text(encoding="utf-8") if (self.tpl / "README.md").exists() else "")
        self.load_fields()

    def load_fields(self):
        q = """query($p:ID!){node(id:$p){... on ProjectV2{fields(first:50){nodes{
                 ... on ProjectV2FieldCommon{id name dataType}
                 ... on ProjectV2SingleSelectField{options{id name}}
                 ... on ProjectV2IterationField{configuration{iterations{id title startDate duration}
                                                              completedIterations{id title startDate duration}}}}}}}}"""
        self.fields = {f["name"]: f for f in self.gh.gql(q, p=self.project["id"])["node"]["fields"]["nodes"] if f}

    def single_select(self, name, options, replace=False):
        f = self.fields.get(name)
        opts = [{"name": n, "color": c, "description": ""} for n, c in options]
        if f is None:
            print(f"• Поле «{name}» (выбор из списка)")
            self.gh.gql("""mutation($p:ID!,$n:String!,$o:[ProjectV2SingleSelectFieldOptionInput!]){createProjectV2Field(
                           input:{projectId:$p,dataType:SINGLE_SELECT,name:$n,singleSelectOptions:$o}){clientMutationId}}""",
                        p=self.project["id"], n=name, o=opts)
        elif replace and [o["name"] for o in f["options"]] != [n for n, _ in options]:
            print(f"• Обновляю варианты поля «{name}»")
            self.gh.gql("""mutation($f:ID!,$o:[ProjectV2SingleSelectFieldOptionInput!]){updateProjectV2Field(
                           input:{fieldId:$f,singleSelectOptions:$o}){clientMutationId}}""", f=f["id"], o=opts)

    def simple_field(self, name, dtype):
        if name not in self.fields:
            print(f"• Поле «{name}» ({dtype})")
            self.gh.gql("""mutation($p:ID!,$n:String!,$t:ProjectV2CustomFieldType!){createProjectV2Field(
                           input:{projectId:$p,dataType:$t,name:$n}){clientMutationId}}""",
                        p=self.project["id"], n=name, t=dtype)

    def iterations(self):
        spec = load(self.tpl / "Iterations.json")
        sprints = [c["name"] for c in spec["children"]]
        its = [{"title": s, "startDate": (self.sprint_start + dt.timedelta(days=i * self.sprint_days)).isoformat(),
                "duration": self.sprint_days} for i, s in enumerate(sprints)]
        if "Sprint" not in self.fields:
            print(f"• Поле-итерация «Sprint»: {', '.join(sprints)} по {self.sprint_days} дн. с {self.sprint_start}")
            self.gh.gql("""mutation($p:ID!,$c:ProjectV2IterationFieldConfigurationInput!){createProjectV2Field(
                           input:{projectId:$p,dataType:ITERATION,name:"Sprint",iterationConfiguration:$c}){clientMutationId}}""",
                        p=self.project["id"],
                        c={"startDate": its[0]["startDate"], "duration": self.sprint_days, "iterations": its})

    def ensure_fields(self, areas):
        self.single_select("Status", STATES, replace=True)
        self.single_select("Area", [(a, "GRAY") for a in areas])
        self.single_select("Activity", [(a, "GRAY") for a in ACTIVITIES])
        self.single_select("Priority", [(p, c) for p, c in zip(PRIORITIES, ["RED", "ORANGE", "YELLOW", "GRAY"])])
        self.simple_field("Effort", "NUMBER")
        self.simple_field("Remaining Work", "NUMBER")
        self.iterations()
        self.load_fields()

    # ---------- команды ----------
    def ensure_teams(self):
        teams = load(self.tpl / "Teams" / "Teams.json")
        existing = {t["name"]: t for t in self.gh.rest("GET", f"orgs/{self.org}/teams?per_page=100")}
        areas = [self.project_title]
        for t in teams:
            name = t["name"].replace("PartsUnlimited-tc", self.project_title)
            if t.get("isDefault") == "true":
                areas_name = self.project_title
            else:
                areas_name = f"{self.project_title}\\{name}"
                areas.append(areas_name)
            if name not in existing:
                print(f"• Команда «{name}»")
                team = self.gh.rest("POST", f"orgs/{self.org}/teams",
                                    {"name": name, "description": t["description"], "privacy": "closed"})
            else:
                team = existing[name]
            self.gh.rest("PUT", f"orgs/{self.org}/teams/{team['slug']}/repos/{self.org}/{self.repo}", {"permission": "push"})
            self.gh.gql("mutation($p:ID!,$t:ID!){linkProjectV2ToTeam(input:{projectId:$p,teamId:$t}){clientMutationId}}",
                        p=self.project["id"], t=team["node_id"])
        return areas

    # ---------- рабочие элементы ----------
    def existing_issues(self):
        found, page = {}, 1
        while True:
            batch = self.gh.rest("GET", f"repos/{self.org}/{self.repo}/issues?state=all&per_page=100&page={page}")
            for i in batch:
                m = MARK.search(i.get("body") or "")
                if m and "pull_request" not in i:
                    found[int(m.group(1))] = i
            if len(batch) < 100:
                return found
            page += 1

    def work_items(self):
        order = ["Epic", "Feature", "Product Backlog Item", "Bug", "Task"]
        items = []
        for t in order:
            items += load(self.tpl / "WorkItems" / f"{t}.json")["value"]
        existing = self.existing_issues()
        sprint_ids = {i["title"]: i["id"] for i in self.fields["Sprint"]["configuration"]["iterations"]
                      + self.fields["Sprint"]["configuration"]["completedIterations"]}
        opt = lambda field, name: next(o["id"] for o in self.fields[field]["options"] if o["name"] == name)
        nodes = {}
        print(f"• Рабочие элементы: {len(items)} шт. (уже есть: {len(existing)})")
        for n, w in enumerate(items, 1):
            f, wid = w["fields"], w["id"]
            wtype, title, state = f["System.WorkItemType"], f["System.Title"], f["System.State"]
            if wid in existing:
                issue = existing[wid]
                node_id, number = issue["node_id"], issue["number"]
            else:
                desc = f.get("System.Description") or ""
                body = f"{desc}\n\n---\n_Импортировано из шаблона Parts Unlimited (Azure DevOps #{wid})_\n<!-- ado-id: {wid} -->"
                r = self.gh.gql("""mutation($r:ID!,$t:String!,$b:String!,$ty:ID!){createIssue(input:{repositoryId:$r,
                                   title:$t,body:$b,issueTypeId:$ty}){issue{id number}}}""",
                                r=self.repo_id, t=title, b=body, ty=self.type_ids[wtype])["createIssue"]["issue"]
                node_id, number = r["id"], r["number"]
                print(f"  [{n}/{len(items)}] #{number} {wtype}: {title[:70]}")
            nodes[wid] = node_id
            item_id = self.gh.gql("""mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}""",
                                  p=self.project["id"], c=node_id)["addProjectV2ItemById"]["item"]["id"]
            values = {"Status": {"singleSelectOptionId": opt("Status", state)},
                      "Area": {"singleSelectOptionId": opt("Area", self.project_title)}}
            sprint = (f.get("System.IterationPath") or "").split("\\")[-1]
            if sprint in sprint_ids:
                values["Sprint"] = {"iterationId": sprint_ids[sprint]}
            if f.get("Microsoft.VSTS.Scheduling.Effort"):
                values["Effort"] = {"number": float(f["Microsoft.VSTS.Scheduling.Effort"])}
            if f.get("Microsoft.VSTS.Scheduling.RemainingWork"):
                values["Remaining Work"] = {"number": float(f["Microsoft.VSTS.Scheduling.RemainingWork"])}
            if f.get("Microsoft.VSTS.Common.Priority"):
                values["Priority"] = {"singleSelectOptionId": opt("Priority", str(int(float(f["Microsoft.VSTS.Common.Priority"]))))}
            if f.get("Microsoft.VSTS.Common.Activity") in ACTIVITIES:
                values["Activity"] = {"singleSelectOptionId": opt("Activity", f["Microsoft.VSTS.Common.Activity"])}
            if wid not in existing or self.resume:
                for name, value in values.items():
                    self.gh.gql("""mutation($p:ID!,$i:ID!,$f:ID!,$v:ProjectV2FieldValue!){updateProjectV2ItemFieldValue(
                                   input:{projectId:$p,itemId:$i,fieldId:$f,value:$v}){clientMutationId}}""",
                                p=self.project["id"], i=item_id, f=self.fields[name]["id"], v=value)
                if state == "Done":
                    self.gh.rest("PATCH", f"repos/{self.org}/{self.repo}/issues/{number}",
                                 {"state": "closed", "state_reason": "completed"})
        # иерархия (Hierarchy-Forward = дочерний элемент)
        print("• Связи родитель → потомок (sub-issues)")
        for w in items:
            for rel in w.get("relations") or []:
                if rel["rel"] == "System.LinkTypes.Hierarchy-Forward":
                    child = int(rel["url"].rsplit("/", 1)[1])
                    if child in nodes:
                        try:
                            self.gh.gql("""mutation($i:ID!,$s:ID!){addSubIssue(input:{issueId:$i,subIssueId:$s,replaceParent:true})
                                           {clientMutationId}}""", i=nodes[w["id"]], s=nodes[child])
                        except RuntimeError as e:
                            if "already" not in str(e).lower():
                                raise

    # ---------- представления (аналог Queries / досок) ----------
    def views(self):
        q = """query($p:ID!){node(id:$p){... on ProjectV2{views(first:50){nodes{id name}}}}}"""
        have = {v["name"]: v["id"] for v in self.gh.gql(q, p=self.project["id"])["node"]["views"]["nodes"]}
        wanted = [
            ("Backlog items", "BOARD_LAYOUT", 'type:"Product Backlog Item",Bug'),
            ("Features", "BOARD_LAYOUT", "type:Feature"),
            ("Epics", "BOARD_LAYOUT", "type:Epic"),
            ("Current sprint", "BOARD_LAYOUT", "sprint:@current"),
            ("All Items", "TABLE_LAYOUT", ""),
            ("User Stories", "TABLE_LAYOUT", 'type:"Product Backlog Item"'),
            ("Critical Bugs", "TABLE_LAYOUT", "type:Bug -status:Done priority:1"),
            ("Work in Progress", "TABLE_LAYOUT", 'type:Task status:"In Progress" sprint:@current'),
            ("Roadmap", "ROADMAP_LAYOUT", "-type:Task"),
        ]
        for name, layout, flt in wanted:
            if name in have:
                continue
            print(f"• Представление «{name}»")
            vid = self.gh.gql("""mutation($p:ID!,$n:String!,$l:ProjectV2ViewLayout!){createProjectV2View(
                                 input:{projectId:$p,name:$n,layout:$l}){projectV2View{id}}}""",
                              p=self.project["id"], n=name, l=layout)["createProjectV2View"]["projectV2View"]["id"]
            if flt:
                self.gh.gql("""mutation($v:ID!,$f:String!){updateProjectV2View(input:{viewId:$v,filter:$f}){clientMutationId}}""",
                            v=vid, f=flt)

    # ---------- pull requests ----------
    def pull_requests(self):
        existing = {p["head"]["ref"] for p in self.gh.rest("GET", f"repos/{self.org}/{self.repo}/pulls?state=all&per_page=100")}
        for i in (1, 2):
            pr = load(self.tpl / "PullRequests" / f"PullRequest{i}.json")
            head = pr["sourceRefName"].removeprefix("refs/heads/")
            if head in existing:
                continue
            print(f"• Pull request «{pr['title']}»")
            created = self.gh.rest("POST", f"repos/{self.org}/{self.repo}/pulls", {
                "title": pr["title"], "body": pr["description"], "head": head,
                "base": pr["targetRefName"].removeprefix("refs/heads/")})
            comments = self.tpl / "PullRequests" / "Comments" / f"PullRequest{i}.json"
            if comments.exists():
                for thread in load(comments)["value"]:
                    for c in thread["comments"] + thread.get("Replies", []):
                        self.gh.rest("POST", f"repos/{self.org}/{self.repo}/issues/{created['number']}/comments",
                                     {"body": c["content"]})

    def run(self, source_url):
        self.org_ids()
        self.ensure_repo(source_url)
        self.ensure_issue_types()
        self.ensure_project()
        areas = self.ensure_teams()
        self.ensure_fields(areas)
        self.work_items()
        self.views()
        self.pull_requests()
        print(f"\nГотово: {self.project['url']}\n        https://github.com/{self.org}/{self.repo}")


def main():
    templates = sorted(p.name for p in TEMPLATES.iterdir() if p.is_dir())
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--org")
    p.add_argument("--project")
    p.add_argument("--repo", default="PartsUnlimited")
    p.add_argument("--template", choices=templates)
    p.add_argument("--token", help="Personal Access Token (по умолчанию — токен gh auth)")
    p.add_argument("--source", default="https://dev.azure.com/vstsdemodata/PartsUnlimited/_git/PartsUnlimited")
    p.add_argument("--sprint-days", type=int, default=14)
    p.add_argument("--resume", action="store_true", help="повторно проставить поля у уже созданных issues")
    p.add_argument("--current-sprint", type=int, default=2,
                   help="какой спринт сделать текущим (как в Demo Generator: часть работ уже в прошлом)")
    a = p.parse_args()

    print("GitHub Demo Generator\n")
    if not a.template:
        print("Выберите шаблон:")
        a.template = ask("Шаблон", choices=templates)
    if not a.token and not a.org:
        print("Способ авторизации:")
        if ask("Авторизация", choices=["gh auth (текущий вход gh)", "Personal Access Token (PAT)"]).startswith("Personal"):
            a.token = ask("PAT")
    a.org = a.org or ask("Организация GitHub")
    a.project = a.project or ask("Имя создаваемого проекта", default="Unlimited Parts")

    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    start = monday - dt.timedelta(days=a.sprint_days * (a.current_sprint - 1))
    g = Generator(GitHub(a.token), a.org, a.project, a.repo, a.template, start, a.sprint_days, a.project)
    g.resume = a.resume
    g.run(a.source)


if __name__ == "__main__":
    sys.exit(main())
