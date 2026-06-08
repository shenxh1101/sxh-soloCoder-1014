from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple, Callable
from collections import defaultdict
from .models import (
    Port, Ship, Cargo, Voyage, VoyagePlan, CostBreakdown, CargoType,
    UnassignedCargo, PlanStrategy
)
from .data_loader import get_route_distance


STRATEGY_CONFIGS = {
    PlanStrategy.LOWEST_COST: {
        "name": "最低成本",
        "description": "优先选择总成本最低的船舶和方案，适合预算敏感场景",
        "cost_weight": 1.0,
        "time_weight": 0.3,
        "priority_weight": 0.5,
        "demurrage_weight": 0.4,
    },
    PlanStrategy.FASTEST_ARRIVAL: {
        "name": "最快到港",
        "description": "优先选择航行和装卸时间最短的方案，适合紧急货物",
        "cost_weight": 0.3,
        "time_weight": 1.0,
        "priority_weight": 0.6,
        "demurrage_weight": 0.2,
    },
    PlanStrategy.PRIORITY_FIRST: {
        "name": "优先级优先",
        "description": "优先保障高优先级货物按时抵达，适合重要物资运输",
        "cost_weight": 0.4,
        "time_weight": 0.6,
        "priority_weight": 1.0,
        "demurrage_weight": 0.5,
    },
    PlanStrategy.LOW_DEMURRAGE: {
        "name": "低滞期风险",
        "description": "优先选择滞期风险最低的方案，避免港口拥堵和额外费用",
        "cost_weight": 0.5,
        "time_weight": 0.4,
        "priority_weight": 0.5,
        "demurrage_weight": 1.0,
    },
}


def calculate_sailing_days(distance: float, speed: float) -> float:
    hours = distance / speed
    return hours / 24.0


def calculate_loading_days(weight: float, handling_rate: float, working_hours: int = 10) -> float:
    tons_per_day = handling_rate * (working_hours / 24.0)
    return weight / tons_per_day


def align_to_working_hours(dt: datetime, start_hour: int, end_hour: int) -> datetime:
    working_hours_per_day = end_hour - start_hour
    if working_hours_per_day <= 0:
        return dt

    if dt.hour < start_hour:
        dt = datetime(dt.year, dt.month, dt.day, start_hour)
    elif dt.hour >= end_hour:
        dt = datetime(dt.year, dt.month, dt.day, start_hour) + timedelta(days=1)
    return dt


def add_working_days(start_dt: datetime, days: float, start_hour: int, end_hour: int) -> datetime:
    working_hours_per_day = end_hour - start_hour
    if working_hours_per_day <= 0:
        return start_dt + timedelta(days=days)

    total_working_hours_needed = days * working_hours_per_day
    result = start_dt

    while total_working_hours_needed > 0:
        if result.hour < start_hour:
            result = datetime(result.year, result.month, result.day, start_hour)
        elif result.hour >= end_hour:
            result = datetime(result.year, result.month, result.day, start_hour) + timedelta(days=1)

        hours_today = min(
            total_working_hours_needed,
            end_hour - result.hour
        )
        result = result + timedelta(hours=hours_today)
        total_working_hours_needed -= hours_today

    return result


def group_cargos_by_route(cargos: List[Cargo]) -> Dict[Tuple[str, str], List[Cargo]]:
    grouped = defaultdict(list)
    for cargo in cargos:
        key = (cargo.loading_port, cargo.discharging_port)
        grouped[key].append(cargo)
    return grouped


def sort_cargos_by_priority(cargos: List[Cargo]) -> List[Cargo]:
    return sorted(cargos, key=lambda c: (-c.priority, c.ready_date))


def sort_cargos_by_deadline(cargos: List[Cargo]) -> List[Cargo]:
    return sorted(cargos, key=lambda c: (c.deadline, -c.priority))


def sort_cargos_by_ready_date(cargos: List[Cargo]) -> List[Cargo]:
    return sorted(cargos, key=lambda c: (c.ready_date, -c.priority))


def get_sort_function(strategy: PlanStrategy) -> Callable[[List[Cargo]], List[Cargo]]:
    if strategy == PlanStrategy.FASTEST_ARRIVAL:
        return sort_cargos_by_deadline
    elif strategy == PlanStrategy.LOW_DEMURRAGE:
        return sort_cargos_by_ready_date
    else:
        return sort_cargos_by_priority


def calculate_strategy_score(
    plan: VoyagePlan,
    ship: Ship,
    batch: List[Cargo],
    sailing_days: float,
    total_days: float,
    estimated_cost: float,
    start_delay: int,
    strategy: PlanStrategy,
) -> float:
    config = STRATEGY_CONFIGS.get(strategy, STRATEGY_CONFIGS[PlanStrategy.LOWEST_COST])

    max_priority = max(c.priority for c in batch)
    avg_priority = sum(c.priority for c in batch) / len(batch)
    priority_penalty = (5 - avg_priority) * 10000 * config["priority_weight"]

    deadline_delays = []
    for c in batch:
        if plan.voyage.arrival_date > c.deadline:
            delay = (plan.voyage.arrival_date - c.deadline).days
            deadline_delays.append(delay)
    deadline_penalty = sum(deadline_delays) * 5000 * config["time_weight"]

    demurrage_penalty = 0
    if plan.demurrage_risk == "medium":
        demurrage_penalty = 50000 * config["demurrage_weight"]
    elif plan.demurrage_risk == "high":
        demurrage_penalty = 200000 * config["demurrage_weight"]

    error_penalty = len(plan.errors) * 100000
    warning_penalty = len(plan.warnings) * 10000
    delay_penalty = start_delay * ship.daily_charter * 2 * config["time_weight"]
    cost_component = estimated_cost * config["cost_weight"]
    time_component = total_days * 2000 * config["time_weight"]

    return (
        cost_component +
        time_component +
        priority_penalty +
        deadline_penalty +
        demurrage_penalty +
        error_penalty +
        warning_penalty +
        delay_penalty
    )


def get_unassigned_reason(
    cargo: Cargo,
    ships: Dict[str, Ship],
    ports: Dict[str, Port],
) -> str:
    reasons = []
    load_port = ports.get(cargo.loading_port)
    disch_port = ports.get(cargo.discharging_port)

    if not load_port:
        reasons.append(f"装货港 {cargo.loading_port} 不存在")
    if not disch_port:
        reasons.append(f"卸货港 {cargo.discharging_port} 不存在")

    if load_port and disch_port:
        suitable_ships = []
        for ship in ships.values():
            if ship.deadweight < cargo.weight * 0.9:
                continue
            if ship.draft > load_port.max_draft or ship.draft > disch_port.max_draft:
                continue
            if cargo.cargo_type == CargoType.DANGEROUS and not ship.carries_dangerous:
                continue
            if cargo.cargo_type == CargoType.REFRIGERATED and not ship.carries_refrigerated:
                continue
            suitable_ships.append(ship)

        if not suitable_ships:
            ship_reasons = []
            if cargo.weight > max((s.deadweight for s in ships.values()), default=0):
                ship_reasons.append("货物重量超过所有船舶载重")
            if cargo.cargo_type == CargoType.DANGEROUS and not any(s.carries_dangerous for s in ships.values()):
                ship_reasons.append("无危险品运输资质船舶")
            if cargo.cargo_type == CargoType.REFRIGERATED and not any(s.carries_refrigerated for s in ships.values()):
                ship_reasons.append("无冷链运输能力船舶")
            if load_port.max_draft < min((s.draft for s in ships.values()), default=999):
                ship_reasons.append("港口吃水限制")
            if disch_port.max_draft < min((s.draft for s in ships.values()), default=999):
                ship_reasons.append("卸港吃水限制")
            if not ship_reasons:
                ship_reasons.append("无合适船舶")
            reasons.extend(ship_reasons)

    if not reasons:
        reasons.append("船舶档期冲突或其他原因")

    return "; ".join(reasons)


def find_compatible_ships(
    cargos: List[Cargo],
    ships: Dict[str, Ship],
    ports: Dict[str, Port],
    routes: Dict,
    is_dangerous: bool,
    is_refrigerated: bool,
    total_weight: float,
) -> List[Ship]:
    compatible = []
    load_port = ports.get(cargos[0].loading_port)
    disch_port = ports.get(cargos[0].discharging_port)

    if not load_port or not disch_port:
        return []

    for ship in ships.values():
        if ship.deadweight < total_weight * 0.9:
            continue

        if ship.draft > load_port.max_draft or ship.draft > disch_port.max_draft:
            continue

        if is_dangerous and not ship.carries_dangerous:
            continue

        if is_refrigerated and not ship.carries_refrigerated:
            continue

        compatible.append(ship)

    return compatible


def generate_voyage_plan(
    ship: Ship,
    cargos: List[Cargo],
    ports: Dict[str, Port],
    routes: Dict,
    voyage_counter: int,
    last_end_time: datetime = None,
) -> VoyagePlan:
    load_port = ports[cargos[0].loading_port]
    disch_port = ports[cargos[0].discharging_port]
    total_weight = sum(c.weight for c in cargos)
    is_dangerous = any(c.cargo_type == CargoType.DANGEROUS for c in cargos)
    is_refrigerated = any(c.cargo_type == CargoType.REFRIGERATED for c in cargos)

    try:
        distance = get_route_distance(routes, cargos[0].loading_port, cargos[0].discharging_port)
    except ValueError:
        distance = 500.0

    sailing_days = calculate_sailing_days(distance, ship.speed)
    loading_days = calculate_loading_days(
        total_weight, load_port.handling_rate,
        load_port.working_hours_end - load_port.working_hours_start
    )
    discharging_days = calculate_loading_days(
        total_weight, disch_port.handling_rate,
        disch_port.working_hours_end - disch_port.working_hours_start
    )

    earliest_ready = max(c.ready_date for c in cargos)
    available_date = ship.available_from
    start_date = max(earliest_ready, available_date)
    if last_end_time:
        start_date = max(start_date, last_end_time.date())

    loading_start = datetime(start_date.year, start_date.month, start_date.day,
                             load_port.working_hours_start)
    loading_start = align_to_working_hours(loading_start, load_port.working_hours_start,
                                           load_port.working_hours_end)
    loading_end = add_working_days(loading_start, loading_days,
                                   load_port.working_hours_start, load_port.working_hours_end)

    departure_date = loading_end.date()
    sailing_time = timedelta(days=sailing_days)
    arrival_date = departure_date + sailing_time
    arrival_dt = datetime(arrival_date.year, arrival_date.month, arrival_date.day, 8)

    discharging_start = align_to_working_hours(arrival_dt, disch_port.working_hours_start,
                                               disch_port.working_hours_end)
    discharging_end = add_working_days(discharging_start, discharging_days,
                                       disch_port.working_hours_start, disch_port.working_hours_end)

    voyage = Voyage(
        voyage_id=f"V{voyage_counter:04d}",
        ship_name=ship.name,
        cargo_ids=[c.id for c in cargos],
        loading_port=cargos[0].loading_port,
        discharging_port=cargos[0].discharging_port,
        departure_date=departure_date,
        arrival_date=arrival_date,
        loading_start=loading_start,
        loading_end=loading_end,
        discharging_start=discharging_start,
        discharging_end=discharging_end,
        total_weight=total_weight,
        is_dangerous=is_dangerous,
        is_refrigerated=is_refrigerated,
        estimated_fuel=sailing_days * ship.fuel_consumption,
        estimated_days=sailing_days + loading_days + discharging_days,
    )

    cost = CostBreakdown()
    warnings = []
    errors = []

    latest_deadline = min(c.deadline for c in cargos)
    if arrival_date > latest_deadline:
        delay_days = (arrival_date - latest_deadline).days
        warnings.append(f"预计抵达时间超出货物期限 {delay_days} 天")

    deadweight_ratio = total_weight / ship.deadweight
    if deadweight_ratio < 0.5:
        warnings.append(f"船舶载重率较低: {deadweight_ratio*100:.1f}%")
    elif deadweight_ratio > 0.95:
        warnings.append(f"船舶载重率较高，请注意配载: {deadweight_ratio*100:.1f}%")

    demurrage_risk = "low"
    if (discharging_end.date() - arrival_date).days > 3:
        demurrage_risk = "medium"
        warnings.append("存在中等滞期风险")
    if (discharging_end.date() - arrival_date).days > 7:
        demurrage_risk = "high"
        errors.append("存在高滞期风险")

    return VoyagePlan(
        voyage=voyage,
        cost=cost,
        warnings=warnings,
        errors=errors,
        demurrage_risk=demurrage_risk,
    )


def generate_candidate_voyages(
    ports: Dict[str, Port],
    ships: Dict[str, Ship],
    cargos: List[Cargo],
    routes: Dict,
    max_cargos_per_voyage: int = 5,
    strategy: PlanStrategy = PlanStrategy.LOWEST_COST,
) -> Tuple[List[VoyagePlan], List[UnassignedCargo]]:
    plans = []
    unassigned: List[UnassignedCargo] = []
    voyage_counter = 1

    grouped_cargos = group_cargos_by_route(cargos)
    ship_schedules: Dict[str, datetime] = {}
    sort_func = get_sort_function(strategy)

    for (load_port_code, disch_port_code), route_cargos in grouped_cargos.items():
        sorted_cargos = sort_func(route_cargos)

        i = 0
        while i < len(sorted_cargos):
            batch = []
            batch_weight = 0.0
            batch_dangerous = False
            batch_refrigerated = False
            start_i = i

            while len(batch) < max_cargos_per_voyage and i < len(sorted_cargos):
                cargo = sorted_cargos[i]

                if cargo.cargo_type == CargoType.DANGEROUS and batch_refrigerated:
                    break
                if cargo.cargo_type == CargoType.REFRIGERATED and batch_dangerous:
                    break

                new_weight = batch_weight + cargo.weight
                new_dangerous = batch_dangerous or (cargo.cargo_type == CargoType.DANGEROUS)
                new_refrigerated = batch_refrigerated or (cargo.cargo_type == CargoType.REFRIGERATED)

                compatible_ships = find_compatible_ships(
                    [*batch, cargo], ships, ports, routes,
                    new_dangerous, new_refrigerated, new_weight
                )

                if not compatible_ships:
                    if not batch:
                        reason = get_unassigned_reason(cargo, ships, ports)
                        unassigned.append(UnassignedCargo(
                            cargo_id=cargo.id,
                            cargo_name=cargo.name,
                            loading_port=cargo.loading_port,
                            discharging_port=cargo.discharging_port,
                            weight=cargo.weight,
                            cargo_type=cargo.cargo_type.value,
                            reason=reason
                        ))
                        i += 1
                    break

                batch.append(cargo)
                batch_weight = new_weight
                batch_dangerous = new_dangerous
                batch_refrigerated = new_refrigerated
                i += 1

            if not batch and i == start_i:
                i += 1
                continue

            if batch:
                compatible_ships = find_compatible_ships(
                    batch, ships, ports, routes,
                    batch_dangerous, batch_refrigerated, batch_weight
                )

                if not compatible_ships:
                    for cargo in batch:
                        reason = get_unassigned_reason(cargo, ships, ports)
                        unassigned.append(UnassignedCargo(
                            cargo_id=cargo.id,
                            cargo_name=cargo.name,
                            loading_port=cargo.loading_port,
                            discharging_port=cargo.discharging_port,
                            weight=cargo.weight,
                            cargo_type=cargo.cargo_type.value,
                            reason=reason
                        ))
                    continue

                best_ship = None
                best_plan = None
                best_score = float("inf")

                for ship in compatible_ships:
                    last_end = ship_schedules.get(ship.name)
                    plan = generate_voyage_plan(
                        ship, batch, ports, routes, voyage_counter, last_end
                    )

                    load_port = ports[batch[0].loading_port]
                    disch_port = ports[batch[0].discharging_port]
                    try:
                        distance = get_route_distance(routes, batch[0].loading_port, batch[0].discharging_port)
                    except ValueError:
                        distance = 500.0

                    sailing_days = calculate_sailing_days(distance, ship.speed)
                    loading_days = calculate_loading_days(
                        plan.voyage.total_weight, load_port.handling_rate,
                        load_port.working_hours_end - load_port.working_hours_start
                    )
                    discharging_days = calculate_loading_days(
                        plan.voyage.total_weight, disch_port.handling_rate,
                        disch_port.working_hours_end - disch_port.working_hours_start
                    )
                    total_days = sailing_days + loading_days + discharging_days

                    estimated_cost = (
                        sailing_days * ship.fuel_consumption * ship.fuel_price +
                        plan.voyage.total_weight * (load_port.port_fee_per_ton + disch_port.port_fee_per_ton) +
                        max(1, int(total_days)) * ship.daily_charter
                    )

                    start_delay = 0
                    if last_end:
                        earliest_start = max(max(c.ready_date for c in batch), ship.available_from)
                        if last_end.date() > earliest_start:
                            start_delay = (last_end.date() - earliest_start).days

                    score = calculate_strategy_score(
                        plan, ship, batch, sailing_days, total_days,
                        estimated_cost, start_delay, strategy
                    )

                    if score < best_score:
                        best_score = score
                        best_ship = ship
                        best_plan = plan

                if best_plan:
                    plans.append(best_plan)
                    ship_schedules[best_ship.name] = best_plan.voyage.discharging_end
                    voyage_counter += 1
                else:
                    for cargo in batch:
                        reason = get_unassigned_reason(cargo, ships, ports)
                        unassigned.append(UnassignedCargo(
                            cargo_id=cargo.id,
                            cargo_name=cargo.name,
                            loading_port=cargo.loading_port,
                            discharging_port=cargo.discharging_port,
                            weight=cargo.weight,
                            cargo_type=cargo.cargo_type.value,
                            reason="无法找到合适船舶完成此批货物运输"
                        ))

    return plans, unassigned


def generate_multi_scenario(
    ports: Dict[str, Port],
    ships: Dict[str, Ship],
    cargos: List[Cargo],
    routes: Dict,
    strategies: List[PlanStrategy] = None,
    max_cargos_per_voyage: int = 5,
) -> Dict[PlanStrategy, Tuple[List[VoyagePlan], List[UnassignedCargo]]]:
    if strategies is None:
        strategies = list(PlanStrategy)

    results = {}
    for strategy in strategies:
        plans, unassigned = generate_candidate_voyages(
            ports, ships, cargos, routes, max_cargos_per_voyage, strategy
        )
        results[strategy] = (plans, unassigned)

    return results
