"""Минимальный клиент GitHub REST/GraphQL с обработкой rate limit."""
import json
import os
import subprocess
import time

import requests


def _token():
    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


class GitHub:
    def __init__(self, token=None, pause=0.7):
        self.pause = pause
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"bearer {token or _token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _send(self, method, url, payload):
        r = None
        for attempt in range(10):
            try:
                r = self.s.request(method, url, json=payload, timeout=60)
            except requests.exceptions.RequestException as e:
                print(f"    … сетевая ошибка ({type(e).__name__}), повтор через 15 c")
                time.sleep(15)
                continue
            limited = r.status_code in (429, 502, 503) or (
                r.status_code == 403 and "rate limit" in r.text.lower()
            ) or (r.status_code == 200 and '"RATE_LIMITED"' in r.text)
            if not limited:
                time.sleep(self.pause)
                return r
            wait = int(r.headers.get("retry-after") or 0) or min(60 * (attempt + 1), 300)
            print(f"    … лимит запросов GitHub ({r.status_code}), жду {wait} c")
            time.sleep(wait)
        raise RuntimeError(f"Превышено число попыток: {getattr(r, 'status_code', None)} {getattr(r, 'text', '')}")

    def gql(self, query, **variables):
        r = self._send("POST", "https://api.github.com/graphql", {"query": query, "variables": variables})
        data = r.json()
        if data.get("errors"):
            raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))
        return data["data"]

    def rest(self, method, path, body=None, ok404=False):
        r = self._send(method, "https://api.github.com/" + path.lstrip("/"), body)
        if ok404 and r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path}: {r.status_code} {r.text}")
        return r.json() if r.text else None
