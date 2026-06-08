import sys
sys.path.insert(0, '.')
from shipping_scheduler.plan_storage import load_plan
from shipping_scheduler.cli import filter_check_results_by_plans, merge_filters, apply_filter_options

# 加载计划
plan = load_plan('output/multi_test.json')
print(f"计划: {plan.plan_id}")
print(f"方案数量: {len(plan.scenarios)}")

# 获取 S04-low_demurrage 方案
scenario = plan.get_scenario('S04-low_demurrage')
print(f"\n方案: {scenario.scenario_id}")
print(f"航次数量: {len(scenario.plans)}")
p = scenario.plans[0]
print(f"\n第一个航次结构:")
print(f"  VoyagePlan 字段: {p.model_fields.keys()}")
print(f"  Voyage 字段: {p.voyage.model_fields.keys()}")
print(f"  voyage_id: {p.voyage.voyage_id}")
print(f"  departure_date: {p.voyage.departure_date}")
print(f"  demurrage_risk: {p.demurrage_risk if hasattr(p, 'demurrage_risk') else 'N/A'}")

# 查看所有航次的离港日期
print("\n所有航次的离港日期:")
for p in scenario.plans:
    risk = p.demurrage_risk if hasattr(p, 'demurrage_risk') else 'N/A'
    print(f"  {p.voyage.voyage_id}: departure={p.voyage.departure_date}, risk={risk}")

# 应用筛选
saved_filters = plan.filters_applied or {}
user_filters = {'start_date': '2026-06-15', 'end_date': '2026-06-30', 'date_type': 'departure'}
merged = merge_filters(saved_filters, user_filters)
print(f"\n合并后的筛选条件: {merged}")

plans_filtered = apply_filter_options(scenario.plans, **merged)
print(f"\n筛选后航次数量: {len(plans_filtered)}")
for p in plans_filtered:
    risk = p.demurrage_risk if hasattr(p, 'demurrage_risk') else 'N/A'
    print(f"  {p.voyage.voyage_id}: departure={p.voyage.departure_date}, risk={risk}")

# 筛选 check_results
check_results_filtered = filter_check_results_by_plans(scenario.check_results, plans_filtered)
print(f"\n筛选后 check_results 中的航次:")
check_voyage_ids = sorted(set(cr.voyage_id for cr in check_results_filtered))
print(f"  {check_voyage_ids}")
print(f"  数量: {len(check_results_filtered)}")
