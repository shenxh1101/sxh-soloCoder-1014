import sys
sys.path.insert(0, '.')
from shipping_scheduler.data_loader import load_all_data
from shipping_scheduler.planner import generate_multi_scenario
from shipping_scheduler.cost_calculator import calculate_all_costs
from shipping_scheduler.filters import apply_filter_options
from shipping_scheduler.models import PlanStrategy

# 加载数据
ports, ships, cargos, routes = load_all_data(
    'sample_data/ports.csv',
    'sample_data/ships.csv',
    'sample_data/cargos.csv',
    'sample_data/routes.csv'
)

# 生成 S04-low_demurrage 方案
strategies = [PlanStrategy.LOW_DEMURRAGE]
multi_results = generate_multi_scenario(ports, ships, cargos, routes, strategies, 100)
plans, unassigned = multi_results[PlanStrategy.LOW_DEMURRAGE]
plans = calculate_all_costs(plans, ships, ports, cargos)

print(f"全量航次数量: {len(plans)}")
for p in plans:
    print(f"  {p.voyage.voyage_id}: departure={p.voyage.departure_date}, risk={p.voyage.demurrage_risk}")

# 应用日期筛选
print("\n应用日期筛选: 2026-06-15 ~ 2026-06-30")
filtered = apply_filter_options(plans, start_date='2026-06-15', end_date='2026-06-30', date_type='departure')
print(f"筛选后航次数量: {len(filtered)}")
for p in filtered:
    print(f"  {p.voyage.voyage_id}: departure={p.voyage.departure_date}, risk={p.voyage.demurrage_risk}")
