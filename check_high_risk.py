import json
with open('output/plan_high_risk.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
scenario = data['scenarios'][0]
plans = scenario['plans']
check_results = scenario['check_results']
voyage_ids = [p['voyage']['voyage_id'] for p in plans]
check_voyage_ids = [cr['voyage_id'] for cr in check_results]
print(f'计划文件中的航次数量: {len(plans)}')
print(f'航次ID列表: {sorted(voyage_ids)}')
print(f'检查结果中的航次数量: {len(check_results)}')
print(f'检查结果中的航次ID: {sorted(set(check_voyage_ids))}')
print(f'V0008 是否在 plans 中: {"V0008" in voyage_ids}')
print(f'filters_applied: {data.get("filters_applied", {})}')
print(f'总费用: {sum(p["cost"]["total_cost"] for p in plans):,.2f}')
print(f'异常数量: {len(check_results)}')
