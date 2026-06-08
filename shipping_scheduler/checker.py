from datetime import datetime
from typing import List, Dict
from .models import Port, Ship, Cargo, VoyagePlan, CheckResult, CargoType


def check_deadweight(plan: VoyagePlan, ship: Ship) -> tuple[bool, str]:
    ratio = plan.voyage.total_weight / ship.deadweight
    if ratio > 1.0:
        return False, f"超载: 载重 {plan.voyage.total_weight:.0f} 吨 > 载重吨 {ship.deadweight:.0f} 吨"
    if ratio > 0.98:
        return True, f"接近载重上限: {ratio*100:.1f}%"
    return True, f"载重率: {ratio*100:.1f}%"


def check_draft(plan: VoyagePlan, ship: Ship, load_port: Port, disch_port: Port) -> tuple[bool, str]:
    issues = []
    passed = True

    if ship.draft > load_port.max_draft:
        issues.append(f"装港吃水超限: 船舶吃水 {ship.draft}m > 港口最大吃水 {load_port.max_draft}m")
        passed = False
    if ship.draft > disch_port.max_draft:
        issues.append(f"卸港吃水超限: 船舶吃水 {ship.draft}m > 港口最大吃水 {disch_port.max_draft}m")
        passed = False

    if passed:
        load_margin = load_port.max_draft - ship.draft
        disch_margin = disch_port.max_draft - ship.draft
        return True, f"吃水富余: 装港 {load_margin:.2f}m, 卸港 {disch_margin:.2f}m"

    return passed, "; ".join(issues)


def check_cargo_compatibility(plan: VoyagePlan, ship: Ship, cargos: List[Cargo]) -> tuple[bool, str]:
    issues = []
    passed = True

    if plan.voyage.is_dangerous and not ship.carries_dangerous:
        issues.append("船舶不具备危险品运输资质")
        passed = False

    if plan.voyage.is_refrigerated and not ship.carries_refrigerated:
        issues.append("船舶不具备冷链运输能力")
        passed = False

    cargo_list = [c for c in cargos if c.id in plan.voyage.cargo_ids]
    dangerous_cargos = [c for c in cargo_list if c.cargo_type == CargoType.DANGEROUS]
    refrigerated_cargos = [c for c in cargo_list if c.cargo_type == CargoType.REFRIGERATED]

    if dangerous_cargos and refrigerated_cargos:
        issues.append("危险品与冷链货物混装存在风险")
        passed = False

    if passed:
        msg = "货物兼容"
        if plan.voyage.is_dangerous:
            msg += "，含危险品"
        if plan.voyage.is_refrigerated:
            msg += "，含冷链"
        return True, msg

    return passed, "; ".join(issues)


def check_schedule_conflict(
    plan: VoyagePlan,
    all_plans: List[VoyagePlan],
    ship_schedules: Dict[str, List[tuple[datetime, datetime]]],
) -> tuple[bool, str]:
    ship_name = plan.voyage.ship_name
    current_start = plan.voyage.loading_start
    current_end = plan.voyage.discharging_end

    if ship_name not in ship_schedules:
        return True, "无时间冲突"

    for idx, (other_start, other_end) in enumerate(ship_schedules[ship_name]):
        other_plan = None
        for p in all_plans:
            if p.voyage.ship_name == ship_name and p.voyage.loading_start == other_start:
                other_plan = p
                break

        if other_plan and other_plan.voyage.voyage_id == plan.voyage.voyage_id:
            continue

        if current_start < other_end and current_end > other_start:
            overlap_start = max(current_start, other_start)
            overlap_end = min(current_end, other_end)
            overlap_hours = (overlap_end - overlap_start).total_seconds() / 3600
            conflict_with = other_plan.voyage.voyage_id if other_plan else f"航次#{idx}"
            return False, f"与航次 {conflict_with} 时间重叠 {overlap_hours:.1f} 小时"

    return True, "无时间冲突"


def check_port_availability(
    plan: VoyagePlan,
    load_port: Port,
    disch_port: Port,
    port_schedules: Dict[str, List[tuple[datetime, datetime, str]]],
) -> tuple[bool, str]:
    issues = []
    passed = True

    load_start = plan.voyage.loading_start
    load_end = plan.voyage.loading_end
    disch_start = plan.voyage.discharging_start
    disch_end = plan.voyage.discharging_end

    load_port_key = plan.voyage.loading_port
    if load_port_key in port_schedules:
        for (p_start, p_end, p_voyage) in port_schedules[load_port_key]:
            if p_voyage == plan.voyage.voyage_id:
                continue
            if load_start < p_end and load_end > p_start:
                overlap = (min(load_end, p_end) - max(load_start, p_start)).total_seconds() / 3600
                issues.append(f"装港泊位冲突: 与航次 {p_voyage} 重叠 {overlap:.1f} 小时")
                passed = False

    disch_port_key = plan.voyage.discharging_port
    if disch_port_key in port_schedules:
        for (p_start, p_end, p_voyage) in port_schedules[disch_port_key]:
            if p_voyage == plan.voyage.voyage_id:
                continue
            if disch_start < p_end and disch_end > p_start:
                overlap = (min(disch_end, p_end) - max(disch_start, p_start)).total_seconds() / 3600
                issues.append(f"卸港泊位冲突: 与航次 {p_voyage} 重叠 {overlap:.1f} 小时")
                passed = False

    if passed:
        return True, "港口泊位可用"
    return passed, "; ".join(issues)


def check_cargo_deadlines(plan: VoyagePlan, cargos: List[Cargo]) -> tuple[bool, str]:
    cargo_list = [c for c in cargos if c.id in plan.voyage.cargo_ids]
    issues = []
    passed = True

    for cargo in cargo_list:
        if plan.voyage.arrival_date > cargo.deadline:
            delay = (plan.voyage.arrival_date - cargo.deadline).days
            issues.append(f"货物 {cargo.id} 延迟 {delay} 天抵达")
            passed = False
        if plan.voyage.departure_date < cargo.ready_date:
            early = (cargo.ready_date - plan.voyage.departure_date).days
            issues.append(f"货物 {cargo.id} 未就绪，需等待 {early} 天")
            passed = False

    if passed:
        return True, "所有货物时间要求满足"
    return passed, "; ".join(issues)


def check_all(
    plans: List[VoyagePlan],
    ships: Dict[str, Ship],
    ports: Dict[str, Port],
    cargos: List[Cargo],
) -> List[CheckResult]:
    results = []

    ship_schedules: Dict[str, List[tuple[datetime, datetime]]] = {}
    port_schedules: Dict[str, List[tuple[datetime, datetime, str]]] = {}

    for plan in plans:
        ship_name = plan.voyage.ship_name
        if ship_name not in ship_schedules:
            ship_schedules[ship_name] = []
        ship_schedules[ship_name].append((plan.voyage.loading_start, plan.voyage.discharging_end))

        load_port = plan.voyage.loading_port
        if load_port not in port_schedules:
            port_schedules[load_port] = []
        port_schedules[load_port].append((
            plan.voyage.loading_start, plan.voyage.loading_end, plan.voyage.voyage_id
        ))

        disch_port = plan.voyage.discharging_port
        if disch_port not in port_schedules:
            port_schedules[disch_port] = []
        port_schedules[disch_port].append((
            plan.voyage.discharging_start, plan.voyage.discharging_end, plan.voyage.voyage_id
        ))

    for plan in plans:
        ship = ships.get(plan.voyage.ship_name)
        load_port = ports.get(plan.voyage.loading_port)
        disch_port = ports.get(plan.voyage.discharging_port)

        if not ship or not load_port or not disch_port:
            results.append(CheckResult(
                voyage_id=plan.voyage.voyage_id,
                passed=False,
                issues=["缺少船舶或港口数据"],
                details={}
            ))
            continue

        issues = []
        details = {}
        passed = True

        dw_ok, dw_msg = check_deadweight(plan, ship)
        details["deadweight"] = dw_msg
        if not dw_ok:
            issues.append(dw_msg)
            passed = False

        draft_ok, draft_msg = check_draft(plan, ship, load_port, disch_port)
        details["draft"] = draft_msg
        if not draft_ok:
            issues.append(draft_msg)
            passed = False

        compat_ok, compat_msg = check_cargo_compatibility(plan, ship, cargos)
        details["compatibility"] = compat_msg
        if not compat_ok:
            issues.append(compat_msg)
            passed = False

        sched_ok, sched_msg = check_schedule_conflict(plan, plans, ship_schedules)
        details["schedule"] = sched_msg
        if not sched_ok:
            issues.append(sched_msg)
            passed = False

        port_ok, port_msg = check_port_availability(plan, load_port, disch_port, port_schedules)
        details["port_availability"] = port_msg
        if not port_ok:
            issues.append(port_msg)
            passed = False

        deadline_ok, deadline_msg = check_cargo_deadlines(plan, cargos)
        details["deadlines"] = deadline_msg
        if not deadline_ok:
            issues.append(deadline_msg)
            passed = False

        results.append(CheckResult(
            voyage_id=plan.voyage.voyage_id,
            passed=passed,
            issues=issues,
            details=details
        ))

    return results
