"""Lightweight publication guard. Inspect working files AND every reachable git blob.

This is a guardrail, not proof that arbitrary text cannot contain a secret.
Never print a matching secret; report only artifact path and pattern label.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    'private-key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'github-token':r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
    'provider-key':r'\bsk-(?:proj-|ant-api\d+-)?[A-Za-z0-9_-]{32,}\b',
    'cloudflare-token':r'\bv1\.0-[A-Za-z0-9_-]{40,}\b',
    'personal-tailnet-host':r'\b[a-zA-Z0-9.-]+\.ts\.net\b',
    'absolute-user-home':r'/home/[a-zA-Z0-9_.-]+/',
    'literal-email':r'\b[A-Za-z0-9._%+-]+@(?!example\.(?:test|com)\b|users\.noreply\.github\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
}


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args],stderr=subprocess.DEVNULL)


def scan(label, data):
    if b'\0' in data:
        return []
    text=data.decode('utf-8','replace')
    return [(label,name) for name,pattern in RULES.items() if re.search(pattern,text)]


def main():
    problems=[]
    files=git('ls-files','--cached','--others','--exclude-standard','-z').decode().split('\0')
    files=[f for f in files if f]
    for rel in files:
        p=ROOT/rel
        if p.is_file():
            problems.extend(scan('working:'+rel,p.read_bytes()))
    history=[]
    if subprocess.run(['git','-C',str(ROOT),'rev-parse','--verify','HEAD'],capture_output=True).returncode==0:
        for row in git('rev-list','--objects','--all').decode().splitlines():
            oid,_,name=row.partition(' ')
            if git('cat-file','-t',oid).strip()==b'blob':
                history.append(oid)
                problems.extend(scan('history:'+name,git('cat-file','blob',oid)))
        # Commit identity/body can also leak personal data, not just source blobs.
        for oid in git('rev-list','--all').decode().splitlines():
            problems.extend(scan('commit:'+oid,git('cat-file','commit',oid)))
    js=(ROOT/'hsuh/static/app.js').read_text()
    if any(bad in js for bad in ['.innerHTML', 'localStorage.', 'sessionStorage.', 'indexedDB.']):
        problems.append(('browser','unsafe DOM or persistence API'))
    if 'shell=True' in ''.join(p.read_text() for p in (ROOT/'hsuh').glob('*.py')):
        problems.append(('backend','shell invocation'))
    if problems:
        print('Publication guard FAILED:')
        for path,name in problems: print(f'  {path}: {name}')
        return 1
    print(f'Publication guard passed: {len(files)} working files, {len(set(history))} reachable history blobs; no matching secrets/personal data patterns.')
    print('Limit: heuristic scan and static boundary checks, not an independent security-review approval.')
    return 0


if __name__=='__main__':
    sys.exit(main())
