# -*- coding: utf-8 -*-
import json
from pathlib import Path
r = json.load(open(Path(__file__).parent / 'bmp_props.json', encoding='utf-8'))
print('--- node props ---')
for p in r['node_props']:
    print(f"  {p['cat']:<5} {p['id']:<20} {p['type']}")
print('--- resource props ---')
for p in r['resource_props']:
    print(f"  {p['cat']:<12} {p['id']:<24} {p['type']}")
print('fail:', (r.get('fail') or 'none')[:200])
