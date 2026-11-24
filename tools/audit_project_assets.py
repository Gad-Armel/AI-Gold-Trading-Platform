"""Inventory assets and protected Advisor 1 dependencies; never auto-delete source."""
import ast
import hashlib
import json
import sys
import zipfile
from collections import Counter, deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.audit_python_reachability import module_index, imports


def main():
    index=module_index()
    protected={ROOT/'run_gold_advisor.py'}; pending=deque(protected)
    while pending:
        for dependency in imports(pending.popleft(),index):
            if dependency not in protected:
                protected.add(dependency);pending.append(dependency)
    inventory=[];zips={}
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or any(part in {'.git','.agents','.codex','.claude','.mt5-validation'} for part in p.relative_to(ROOT).parts):continue
        relative=p.relative_to(ROOT).as_posix()
        category=('protected_advisor1' if p in protected else 'regenerable_bytecode' if '__pycache__' in p.parts or p.suffix=='.pyc' else
                  'retired_v6_archive' if p.name.startswith('AI_Gold_Economic_Advisor_V6') and p.suffix=='.zip' else
                  'research_or_execution_evidence' if relative.startswith(('data/','logs/')) else 'project_asset')
        item=dict(path=relative,bytes=p.stat().st_size,category=category)
        if p in protected:item['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        inventory.append(item)
        if p.suffix=='.zip':
            with zipfile.ZipFile(p) as archive:zips[relative]=archive.namelist()
    result=dict(files=inventory,archives=zips,counts=dict(Counter(i['category'] for i in inventory)),
                protected_paths=[p.relative_to(ROOT).as_posix() for p in sorted(protected)])
    out=ROOT/'data/research/project_cleanup';out.mkdir(parents=True,exist_ok=True)
    (out/'inventory_before.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(counts=result['counts'],protected=result['protected_paths'],
        largest=sorted(inventory,key=lambda x:x['bytes'],reverse=True)[:12],archives=zips),indent=2))


if __name__=='__main__':main()
