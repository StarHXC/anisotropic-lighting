# -*- coding: utf-8 -*-
import json
from pathlib import Path
r = json.load(open(Path(__file__).parent / 'ginput3.json', encoding='utf-8'))
for t in r['types']:
    if 'input_ok' in t:
        ok = t['input_ok']
        err = '' if ok else '  ' + str(t.get('input_err', ''))[:60]
        print(f"{t['type']:<16} input_ok={ok}{err}")
    else:
        print(f"{t['type']:<16} ERROR {str(t.get('error', ''))[:80]}")
