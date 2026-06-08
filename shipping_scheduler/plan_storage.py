import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from .models import (
    SchedulePlan, PlanScenario, InputSummary, UnassignedCargo,
    VoyagePlan, CheckResult, Port, Ship, Cargo, Route, PlanStrategy
)


def generate_plan_id() -> str:
    return f"PLAN-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def generate_scenario_id(strategy: PlanStrategy, index: int) -> str:
    return f"S{index:02d}-{strategy.value}"


def create_input_summary(
    ports: Dict[str, Port],
    ships: Dict[str, Ship],
    cargos: List[Cargo],
    routes: Dict[str, Route],
    data_sources: Dict[str, str] = None,
) -> InputSummary:
    return InputSummary(
        port_count=len(ports),
        ship_count=len(ships),
        cargo_count=len(cargos),
        route_count=len(routes),
        total_cargo_weight=sum(c.weight for c in cargos),
        ports=list(ports.keys()),
        ships=list(ships.keys()),
        data_sources=data_sources or {},
    )


def create_schedule_plan(
    name: str,
    ports: Dict[str, Port],
    ships: Dict[str, Ship],
    cargos: List[Cargo],
    routes: Dict[str, Route],
    data_sources: Dict[str, str] = None,
    notes: str = None,
) -> SchedulePlan:
    return SchedulePlan(
        plan_id=generate_plan_id(),
        name=name,
        generated_at=datetime.now(),
        input_summary=create_input_summary(ports, ships, cargos, routes, data_sources),
        scenarios=[],
        notes=notes,
    )


def add_scenario(
    schedule_plan: SchedulePlan,
    strategy: PlanStrategy,
    strategy_name: str,
    description: str,
    plans: List[VoyagePlan],
    check_results: List[CheckResult],
    unassigned_cargos: List[UnassignedCargo] = None,
) -> PlanScenario:
    scenario = PlanScenario(
        scenario_id=generate_scenario_id(strategy, len(schedule_plan.scenarios) + 1),
        strategy=strategy,
        strategy_name=strategy_name,
        description=description,
        plans=plans,
        check_results=check_results,
        unassigned_cargos=unassigned_cargos or [],
    )
    schedule_plan.scenarios.append(scenario)
    return scenario


def save_plan(plan: SchedulePlan, filepath: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

    data = plan.model_dump(mode="json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


def load_plan(filepath: str) -> SchedulePlan:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"计划文件不存在: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return SchedulePlan(**data)


def list_plan_files(directory: str) -> List[str]:
    if not os.path.exists(directory):
        return []

    plan_files = []
    for filename in os.listdir(directory):
        if filename.endswith(".json"):
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "plan_id" in data and "scenarios" in data:
                        plan_files.append(filepath)
            except Exception:
                continue
    return plan_files


def get_scenario_for_operation(
    plan: SchedulePlan,
    scenario_id: Optional[str] = None,
) -> Tuple[PlanScenario, Dict[str, any]]:
    if scenario_id:
        scenario = plan.get_scenario(scenario_id)
        if not scenario:
            raise ValueError(f"方案不存在: {scenario_id}")
    else:
        scenario = plan.latest_scenario
        if not scenario:
            raise ValueError("计划中没有可用方案")

    filters = plan.filters_applied or {}
    return scenario, filters
