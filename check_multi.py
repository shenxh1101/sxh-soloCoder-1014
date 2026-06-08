import json
with open('output/multi_strategy_test2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
scenarios = data['scenarios']
print(f'方案数量: {len(scenarios)}')
for i, s in enumerate(scenarios):
    print(f'  方案{i+1}: {s["scenario_id"]} - {s["strategy_name"]}')
    print(f'    航次数量: {len(s["plans"])}')
    print(f'    检查结果数量: {len(s["check_results"])}')
print(f'\n方案ID列表: {[s["scenario_id"] for s in scenarios]}')
print(f'filters_applied: {data.get("filters_applied", {})}')
