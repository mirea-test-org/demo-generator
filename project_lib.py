"""Помощники для работы с GitHub Project (v2) и issues в рамках лабораторных."""
import json
import pathlib

from gh_api import GitHub

CACHE = pathlib.Path(__file__).with_name(".issues-cache.json")

FIELDS_Q = """query($p:ID!){node(id:$p){... on ProjectV2{fields(first:50){nodes{
  ... on ProjectV2FieldCommon{id name dataType}
  ... on ProjectV2SingleSelectField{options{id name color description}}
  ... on ProjectV2IterationField{configuration{duration
      iterations{id title startDate duration} completedIterations{id title startDate duration}}}}}}}}"""


class Lab:
    def __init__(self, org, repo, project_number):
        self.gh = GitHub()
        self.org, self.repo = org, repo
        d = self.gh.gql("""query($o:String!,$r:String!,$n:Int!){organization(login:$o){id projectV2(number:$n){id url}}
                           repository(owner:$o,name:$r){id} viewer{id login}}""", o=org, r=repo, n=project_number)
        self.org_id = d["organization"]["id"]
        self.project_id = d["organization"]["projectV2"]["id"]
        self.project_url = d["organization"]["projectV2"]["url"]
        self.repo_id = d["repository"]["id"]
        self.me_id, self.me = d["viewer"]["id"], d["viewer"]["login"]
        self.types = {t["name"]: t["node_id"] for t in self.gh.rest("GET", f"orgs/{org}/issue-types")}
        self.cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
        self.reload()

    # ---------- поля ----------
    def reload(self):
        self.fields = {f["name"]: f for f in self.gh.gql(FIELDS_Q, p=self.project_id)["node"]["fields"]["nodes"] if f}

    def option(self, field, name):
        return next(o["id"] for o in self.fields[field]["options"] if o["name"] == name)

    def set_options(self, field, options):
        """options: [(name, color, description)]; существующие варианты сохраняют id (и значения у элементов)."""
        have = {o["name"]: o for o in self.fields[field]["options"]}
        payload = []
        for name, color, desc in options:
            o = {"name": name, "color": color, "description": desc or ""}
            if name in have:
                o["id"] = have[name]["id"]
            payload.append(o)
        self.gh.gql("""mutation($f:ID!,$o:[ProjectV2SingleSelectFieldOptionInput!]){updateProjectV2Field(
                       input:{fieldId:$f,singleSelectOptions:$o}){clientMutationId}}""",
                    f=self.fields[field]["id"], o=payload)
        self.reload()

    def rename_option(self, field, old, new, color=None, desc=None):
        opts = []
        for o in self.fields[field]["options"]:
            x = {"id": o["id"], "name": o["name"], "color": o["color"], "description": o["description"] or ""}
            if o["name"] == old:
                x["name"] = new
                x["color"] = color or x["color"]
                x["description"] = desc if desc is not None else x["description"]
            opts.append(x)
        self.gh.gql("""mutation($f:ID!,$o:[ProjectV2SingleSelectFieldOptionInput!]){updateProjectV2Field(
                       input:{fieldId:$f,singleSelectOptions:$o}){clientMutationId}}""",
                    f=self.fields[field]["id"], o=opts)
        self.reload()

    def add_options(self, field, new, before=None):
        """Добавляет варианты (name, color, desc), сохраняя существующие; before — имя варианта, перед которым вставить."""
        cur = [(o["name"], o["color"], o["description"]) for o in self.fields[field]["options"]]
        names = [c[0] for c in cur]
        new = [n for n in new if n[0] not in names]
        if not new:
            return
        idx = names.index(before) if before in names else len(cur)
        self.set_options(field, cur[:idx] + new + cur[idx:])

    def iterations(self, field="Sprint"):
        c = self.fields[field]["configuration"]
        return c["completedIterations"] + c["iterations"]

    def iteration_id(self, title, field="Sprint"):
        return next(i["id"] for i in self.iterations(field) if i["title"] == title)

    def add_iterations(self, new, field="Sprint"):
        """new: [(title, startDate, duration)] — добавляет итерации, сохраняя существующие (их id и значения)."""
        cur = self.iterations(field)
        titles = {i["title"] for i in cur}
        its = [{"id": i["id"], "title": i["title"], "startDate": i["startDate"], "duration": i["duration"]} for i in cur]
        its += [{"title": t, "startDate": s, "duration": d} for t, s, d in new if t not in titles]
        if len(its) == len(cur):
            return
        its.sort(key=lambda i: i["startDate"])
        c = self.fields[field]["configuration"]
        self.gh.gql("""mutation($f:ID!,$c:ProjectV2IterationFieldConfigurationInput!){updateProjectV2Field(
                       input:{fieldId:$f,iterationConfiguration:$c}){clientMutationId}}""",
                    f=self.fields[field]["id"],
                    c={"startDate": its[0]["startDate"], "duration": c["duration"], "iterations": its})
        self.reload()

    def create_field(self, name, dtype, options=None):
        if name in self.fields:
            return
        extra = ""
        args = {"p": self.project_id, "n": name, "t": dtype}
        if options:
            extra, args["o"] = ",singleSelectOptions:$o", [{"name": n, "color": c, "description": d or ""} for n, c, d in options]
        self.gh.gql(f"""mutation($p:ID!,$n:String!,$t:ProjectV2CustomFieldType!{',$o:[ProjectV2SingleSelectFieldOptionInput!]' if options else ''})
                        {{createProjectV2Field(input:{{projectId:$p,dataType:$t,name:$n{extra}}}){{clientMutationId}}}}""", **args)
        self.reload()

    # ---------- issues ----------
    def find_issue(self, title):
        q = f'repo:{self.org}/{self.repo} is:issue in:title "{title}"'
        for n in self.gh.gql("""query($q:String!){search(query:$q,type:ISSUE,first:20){nodes{... on Issue{id number title}}}}""",
                             q=q)["search"]["nodes"]:
            if n and n["title"] == title:
                return n
        return None

    def issue(self, title, type_, body="", parent=None):
        """Находит или создаёт issue и добавляет его в проект. Возвращает dict(id, number, item)."""
        found = self.cache.get(title) or self.find_issue(title)
        if not found:
            found = self.gh.gql("""mutation($r:ID!,$t:String!,$b:String!,$ty:ID!){createIssue(input:{repositoryId:$r,title:$t,
                                   body:$b,issueTypeId:$ty}){issue{id number title}}}""",
                                r=self.repo_id, t=title, b=body, ty=self.types[type_])["createIssue"]["issue"]
            print(f"  + #{found['number']} [{type_}] {title}")
        self.cache[title] = {k: found[k] for k in ("id", "number", "title")}
        CACHE.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
        if parent:
            try:
                self.gh.gql("mutation($i:ID!,$s:ID!){addSubIssue(input:{issueId:$i,subIssueId:$s,replaceParent:true}){clientMutationId}}",
                            i=parent["id"], s=found["id"])
            except RuntimeError as e:
                if "already" not in str(e).lower() and "duplicate" not in str(e).lower():
                    raise
        found["item"] = self.item_of(found["id"])
        return found

    def item_of(self, content_id):
        for attempt in range(5):
            try:
                return self.gh.gql("mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}",
                                   p=self.project_id, c=content_id)["addProjectV2ItemById"]["item"]["id"]
            except RuntimeError as e:
                if "already exists" not in str(e):
                    raise
            items = self.gh.gql("""query($c:ID!){node(id:$c){... on Issue{projectItems(first:20,includeArchived:true){
                                   nodes{id project{id}}}}}}""", c=content_id)["node"]["projectItems"]["nodes"]
            for it in items:
                if it["project"]["id"] == self.project_id:
                    return it["id"]
            import time
            time.sleep(3)
        raise RuntimeError(f"Не удалось получить элемент проекта для {content_id}")

    def set(self, issue, **values):
        """Устанавливает поля проекта: Status=..., Area=..., Sprint=..., Effort=1.0 и т. п. (подчёркивание = пробел)."""
        for key, val in values.items():
            name = key.replace("_", " ")
            f = self.fields[name]
            if val is None:
                self.gh.gql("mutation($p:ID!,$i:ID!,$f:ID!){clearProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f}){clientMutationId}}",
                            p=self.project_id, i=issue["item"], f=f["id"])
                continue
            if f["dataType"] == "SINGLE_SELECT":
                v = {"singleSelectOptionId": self.option(name, val)}
            elif f["dataType"] == "ITERATION":
                v = {"iterationId": self.iteration_id(val, name)}
            elif f["dataType"] == "NUMBER":
                v = {"number": float(val)}
            elif f["dataType"] == "DATE":
                v = {"date": val}
            else:
                v = {"text": str(val)}
            self.gh.gql("""mutation($p:ID!,$i:ID!,$f:ID!,$v:ProjectV2FieldValue!){updateProjectV2ItemFieldValue(
                           input:{projectId:$p,itemId:$i,fieldId:$f,value:$v}){clientMutationId}}""",
                        p=self.project_id, i=issue["item"], f=f["id"], v=v)

    def assign(self, issue, login=None):
        self.gh.rest("POST", f"repos/{self.org}/{self.repo}/issues/{issue['number']}/assignees",
                     {"assignees": [login or self.me]})

    def unassign(self, issue, login=None):
        self.gh.rest("DELETE", f"repos/{self.org}/{self.repo}/issues/{issue['number']}/assignees",
                     {"assignees": [login or self.me]})

    def close(self, issue, closed=True):
        body = {"state": "closed", "state_reason": "completed"} if closed else {"state": "open"}
        self.gh.rest("PATCH", f"repos/{self.org}/{self.repo}/issues/{issue['number']}", body)

    def comment(self, issue, text):
        self.gh.rest("POST", f"repos/{self.org}/{self.repo}/issues/{issue['number']}/comments", {"body": text})

    def label(self, name, color, desc=""):
        if self.gh.rest("GET", f"repos/{self.org}/{self.repo}/labels/{name}", ok404=True) is None:
            self.gh.rest("POST", f"repos/{self.org}/{self.repo}/labels", {"name": name, "color": color, "description": desc})

    def add_labels(self, issue, labels):
        self.gh.rest("POST", f"repos/{self.org}/{self.repo}/issues/{issue['number']}/labels", {"labels": labels})

    # ---------- команды ----------
    def team(self, name, description, members=()):
        slug = name.lower().replace(" ", "-")
        t = self.gh.rest("GET", f"orgs/{self.org}/teams/{slug}", ok404=True)
        if t is None:
            t = self.gh.rest("POST", f"orgs/{self.org}/teams", {"name": name, "description": description, "privacy": "closed"})
            print(f"  + команда {name}")
        for m in members:
            self.gh.rest("PUT", f"orgs/{self.org}/teams/{t['slug']}/memberships/{m}", {"role": "maintainer" if m == self.me else "member"})
        self.gh.rest("PUT", f"orgs/{self.org}/teams/{t['slug']}/repos/{self.org}/{self.repo}", {"permission": "push"})
        self.gh.gql("mutation($p:ID!,$t:ID!){linkProjectV2ToTeam(input:{projectId:$p,teamId:$t}){clientMutationId}}",
                    p=self.project_id, t=t["node_id"])
        return t

    # ---------- представления ----------
    def views(self):
        q = "query($p:ID!){node(id:$p){... on ProjectV2{views(first:50){nodes{id name number}}}}}"
        return {v["name"]: v for v in self.gh.gql(q, p=self.project_id)["node"]["views"]["nodes"]}

    def view(self, name, layout, flt=""):
        v = self.views().get(name)
        if v is None:
            v = self.gh.gql("""mutation($p:ID!,$n:String!,$l:ProjectV2ViewLayout!){createProjectV2View(
                               input:{projectId:$p,name:$n,layout:$l}){projectV2View{id name number}}}""",
                            p=self.project_id, n=name, l=layout)["createProjectV2View"]["projectV2View"]
            print(f"  + представление «{name}»")
        if flt:
            self.gh.gql("mutation($v:ID!,$f:String!){updateProjectV2View(input:{viewId:$v,filter:$f}){clientMutationId}}",
                        v=v["id"], f=flt)
        return v

    def milestone(self, title, due, desc=""):
        for m in self.gh.rest("GET", f"repos/{self.org}/{self.repo}/milestones?state=all&per_page=100"):
            if m["title"] == title:
                return m
        return self.gh.rest("POST", f"repos/{self.org}/{self.repo}/milestones",
                            {"title": title, "due_on": f"{due}T12:00:00Z", "description": desc})

    def status_update(self, body, status, start=None, target=None):
        args = {"p": self.project_id, "b": body, "s": status}
        extra = ""
        if start:
            extra += ",startDate:$sd"
            args["sd"] = start
        if target:
            extra += ",targetDate:$td"
            args["td"] = target
        self.gh.gql(f"""mutation($p:ID!,$b:String!,$s:ProjectV2StatusUpdateStatus!{',$sd:Date' if start else ''}{',$td:Date' if target else ''})
                        {{createProjectV2StatusUpdate(input:{{projectId:$p,body:$b,status:$s{extra}}}){{clientMutationId}}}}""", **args)
