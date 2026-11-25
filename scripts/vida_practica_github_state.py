"""Persistencia del estado de Vida Practica en una rama GitHub dedicada."""
import argparse, base64, json, os, sys
import requests
try:
    from .vida_practica_state import initial_state, reserve, mark_published
except ImportError:
    from vida_practica_state import initial_state, reserve, mark_published

API="https://api.github.com"
BRANCH="vida-practica-state"
STATE_PATH="vida-practica-state.json"

class GitHubState:
    def __init__(self, repo, token):
        self.repo=repo
        self.headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
        self.base=f"{API}/repos/{repo}"
    def request(self, method, url, **kwargs):
        r=requests.request(method,url,headers=self.headers,timeout=(15,45),**kwargs)
        if not r.ok:
            try: detail=r.json().get("message","")
            except Exception: detail=""
            raise RuntimeError(f"GitHub API {method} {url.rsplit('/',1)[-1]}: HTTP {r.status_code} {detail}")
        return r.json() if r.content else {}
    def ensure_branch(self):
        ref_url=f"{self.base}/git/ref/heads/{BRANCH}"
        r=requests.get(ref_url,headers=self.headers,timeout=(15,45))
        if r.status_code==200: return
        if r.status_code!=404: raise RuntimeError(f"No se pudo consultar la rama de estado (HTTP {r.status_code}).")
        main=self.request("GET",f"{self.base}/git/ref/heads/main")
        created=requests.post(f"{self.base}/git/refs",headers=self.headers,json={"ref":f"refs/heads/{BRANCH}","sha":main["object"]["sha"]},timeout=(15,45))
        if created.status_code not in (201,422):
            raise RuntimeError(f"No se pudo inicializar la rama de estado (HTTP {created.status_code}).")
    def load(self):
        branch=requests.get(f"{self.base}/git/ref/heads/{BRANCH}",headers=self.headers,timeout=(15,45))
        if branch.status_code==404: return initial_state(),None
        if not branch.ok: raise RuntimeError(f"No se pudo consultar la rama de estado (HTTP {branch.status_code}).")
        r=requests.get(f"{self.base}/contents/{STATE_PATH}",headers=self.headers,params={"ref":BRANCH},timeout=(15,45))
        if r.status_code==404: return initial_state(),None
        if not r.ok: raise RuntimeError(f"No se pudo leer el historial remoto (HTTP {r.status_code}).")
        item=r.json()
        state=json.loads(base64.b64decode(item["content"]).decode("utf-8"))
        if state.get("schema_version")!=1: raise RuntimeError("Estado remoto incompatible; publicación bloqueada.")
        return state,item["sha"]
    def save(self,state,sha):
        self.ensure_branch()
        content=base64.b64encode((json.dumps(state,ensure_ascii=False,indent=2)+"\n").encode()).decode()
        payload={"message":"Vida Practica: actualizar historial de publicaciones","content":content,"branch":BRANCH}
        if sha: payload["sha"]=sha
        self.request("PUT",f"{self.base}/contents/{STATE_PATH}",json=payload)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("operation",choices=["inspect","initialize","reserve","finalize"])
    p.add_argument("--repo",default=os.environ.get("GITHUB_REPOSITORY",""))
    p.add_argument("--date"); p.add_argument("--slot"); p.add_argument("--kind")
    p.add_argument("--asset-index",type=int); p.add_argument("--asset-json"); p.add_argument("--media-id")
    a=p.parse_args()
    token=os.environ.get("GITHUB_TOKEN","")
    if not token or not a.repo: raise SystemExit("Falta GITHUB_TOKEN o GITHUB_REPOSITORY.")
    store=GitHubState(a.repo,token); state,sha=store.load()
    if a.operation=="inspect":
        print(json.dumps(state,ensure_ascii=False,indent=2)); return
    if a.operation=="initialize":
        if sha is not None:
            print("El historial persistente ya existe; no se sobrescribe.")
            print(json.dumps(state,ensure_ascii=False,indent=2)); return
        store.save(state,sha)
        print("HISTORIAL PERSISTENTE INICIALIZADO. No se publicó contenido.")
        print(json.dumps(state,ensure_ascii=False,indent=2)); return
    if a.operation=="reserve":
        required=[a.date,a.slot,a.kind,a.asset_json]
        if any(x is None for x in required) or a.asset_index is None: raise SystemExit("Faltan datos para reservar.")
        reservation=reserve(state,date=a.date,slot=a.slot,kind=a.kind,asset_index=a.asset_index,asset=json.loads(a.asset_json))
        store.save(state,sha); print("RESERVA GUARDADA ANTES DE PUBLICAR: "+reservation["key"]); return
    if not a.date or not a.slot or not a.media_id: raise SystemExit("Finalize requiere --date, --slot y --media-id.")
    key=f"{a.date}:{a.slot}"; mark_published(state,key,a.media_id); store.save(state,sha)
    print("PUBLICACION REGISTRADA: "+key)

if __name__=="__main__": main()
