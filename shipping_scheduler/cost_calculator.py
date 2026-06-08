from typing import List, Dict
from datetime import timedelta
from .models import Port, Ship, Cargo, VoyagePlan, CostBreakdown, CargoType


def calculate_fuel_cost(plan: VoyagePlan, ship: Ship) -> float:
    sailing_days = (plan.voyage.arrival_date - plan.voyage.departure_date).days
    if sailing_days <= 0:
        sailing_days = 1
    fuel_consumed = sailing_days * ship.fuel_consumption
    return fuel_consumed * ship.fuel_price


def calculate_port_fees(
    plan: VoyagePlan,
    load_port: Port,
    disch_port: Port,
    cargos: List[Cargo],
) -> tuple[float, float, float, float]:
    cargo_list = [c for c in cargos if c.id in plan.voyage.cargo_ids]
    total_weight = plan.voyage.total_weight

    loading_fee = total_weight * load_port.port_fee_per_ton
    discharging_fee = total_weight * disch_port.port_fee_per_ton

    dangerous_fee = 0.0
    refrigerated_fee = 0.0

    for cargo in cargo_list:
        if cargo.cargo_type == CargoType.DANGEROUS:
            dangerous_fee += cargo.weight * (
                load_port.dangerous_cargo_fee + disch_port.dangerous_cargo_fee
            )
        if cargo.cargo_type == CargoType.REFRIGERATED:
            refrigerated_fee += cargo.weight * (
                load_port.refrigerated_fee + disch_port.refrigerated_fee
            )

    return loading_fee, discharging_fee, dangerous_fee, refrigerated_fee


def calculate_charter_cost(plan: VoyagePlan, ship: Ship) -> float:
    total_days = (plan.voyage.discharging_end - plan.voyage.loading_start).total_seconds() / 86400
    return max(1, int(total_days)) * ship.daily_charter


def calculate_demurrage(
    plan: VoyagePlan,
    load_port: Port,
    disch_port: Port,
    cargos: List[Cargo],
) -> tuple[float, str]:
    cargo_list = [c for c in cargos if c.id in plan.voyage.cargo_ids]

    allowed_loading_days = plan.voyage.total_weight / load_port.handling_rate
    actual_loading_hours = (plan.voyage.loading_end - plan.voyage.loading_start).total_seconds() / 3600
    actual_loading_days = actual_loading_hours / 24

    allowed_discharging_days = plan.voyage.total_weight / disch_port.handling_rate
    actual_discharging_hours = (plan.voyage.discharging_end - plan.voyage.discharging_start).total_seconds() / 3600
    actual_discharging_days = actual_discharging_hours / 24

    loading_demurrage_days = max(0, actual_loading_days - allowed_loading_days)
    discharging_demurrage_days = max(0, actual_discharging_days - allowed_discharging_days)
    total_demurrage_days = loading_demurrage_days + discharging_demurrage_days

    demurrage_cost = total_demurrage_days * (load_port.demurrage_rate + disch_port.demurrage_rate) / 2

    if total_demurrage_days <= 0:
        risk = "low"
    elif total_demurrage_days <= 3:
        risk = "medium"
    else:
        risk = "high"

    return demurrage_cost, risk


def calculate_voyage_cost(
    plan: VoyagePlan,
    ships: Dict[str, Ship],
    ports: Dict[str, Port],
    cargos: List[Cargo],
) -> VoyagePlan:
    ship = ships.get(plan.voyage.ship_name)
    load_port = ports.get(plan.voyage.loading_port)
    disch_port = ports.get(plan.voyage.discharging_port)

    if not ship or not load_port or not disch_port:
        plan.errors.append("缺少费用计算所需数据")
        return plan

    fuel_cost = calculate_fuel_cost(plan, ship)
    loading_fee, discharging_fee, dangerous_fee, refrigerated_fee = calculate_port_fees(
        plan, load_port, disch_port, cargos
    )
    charter_cost = calculate_charter_cost(plan, ship)
    demurrage_cost, demurrage_risk = calculate_demurrage(plan, load_port, disch_port, cargos)

    total_cost = (
        fuel_cost
        + loading_fee
        + discharging_fee
        + dangerous_fee
        + refrigerated_fee
        + charter_cost
        + demurrage_cost
    )

    plan.cost = CostBreakdown(
        fuel_cost=fuel_cost,
        port_loading_fee=loading_fee,
        port_discharging_fee=discharging_fee,
        dangerous_cargo_fee=dangerous_fee,
        refrigerated_fee=refrigerated_fee,
        charter_cost=charter_cost,
        demurrage_cost=demurrage_cost,
        total_cost=total_cost,
    )

    plan.demurrage_risk = demurrage_risk

    if demurrage_risk == "medium" and "中等滞期风险" not in plan.warnings:
        plan.warnings.append("存在中等滞期风险")
    if demurrage_risk == "high" and "高滞期风险" not in plan.errors:
        plan.errors.append("存在高滞期风险")

    return plan


def calculate_all_costs(
    plans: List[VoyagePlan],
    ships: Dict[str, Ship],
    ports: Dict[str, Port],
    cargos: List[Cargo],
) -> List[VoyagePlan]:
    return [calculate_voyage_cost(plan, ships, ports, cargos) for plan in plans]


def summarize_costs(plans: List[VoyagePlan]) -> dict:
    total_fuel = sum(p.cost.fuel_cost for p in plans)
    total_port_loading = sum(p.cost.port_loading_fee for p in plans)
    total_port_discharging = sum(p.cost.port_discharging_fee for p in plans)
    total_dangerous = sum(p.cost.dangerous_cargo_fee for p in plans)
    total_refrigerated = sum(p.cost.refrigerated_fee for p in plans)
    total_charter = sum(p.cost.charter_cost for p in plans)
    total_demurrage = sum(p.cost.demurrage_cost for p in plans)
    grand_total = sum(p.cost.total_cost for p in plans)

    total_weight = sum(p.voyage.total_weight for p in plans)
    total_days = sum(p.voyage.estimated_days for p in plans)

    cost_per_ton = grand_total / total_weight if total_weight > 0 else 0
    cost_per_day = grand_total / total_days if total_days > 0 else 0

    return {
        "voyage_count": len(plans),
        "total_weight": total_weight,
        "total_estimated_days": total_days,
        "fuel_cost": total_fuel,
        "port_loading_cost": total_port_loading,
        "port_discharging_cost": total_port_discharging,
        "dangerous_cargo_cost": total_dangerous,
        "refrigerated_cost": total_refrigerated,
        "charter_cost": total_charter,
        "demurrage_cost": total_demurrage,
        "grand_total": grand_total,
        "cost_per_ton": cost_per_ton,
        "cost_per_day": cost_per_day,
    }
