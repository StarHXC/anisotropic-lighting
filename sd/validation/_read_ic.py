# -*- coding: utf-8 -*-
import json
from pathlib import Path
r = json.load(open(Path(__file__).parent / 'ic_props.json', encoding='utf-8'))
for p in r['props']:
    print(f"  {p['cat']:<6} {p['id']:<16} {p['type']:<30} usage={p['usage']}")
print('fail:', (r.get('fail') or 'none')[:150])
