import json
with open('output/multi_test.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for s in data['scenarios']:
    if s['scenario_id'] == 'S04-low_demurrage':
        print(f"方案: {s['scenario_id']}")
        p = s['plans'][0]
        print(f"\n第一个航次的 voyage 结构:")
        print(json.dumps(p['voyage'], indent=2, ensure_ascii=False))
        break
