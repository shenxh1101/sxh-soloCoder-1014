from datetime import date
from typing import List, Optional
from .models import VoyagePlan


def filter_by_date_range(
    plans: List[VoyagePlan],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    date_type: str = "departure"
) -> List[VoyagePlan]:
    filtered = []
    for plan in plans:
        if date_type == "departure":
            plan_date = plan.voyage.departure_date
        elif date_type == "arrival":
            plan_date = plan.voyage.arrival_date
        else:
            plan_date = plan.voyage.departure_date

        if start_date and plan_date < start_date:
            continue
        if end_date and plan_date > end_date:
            continue
        filtered.append(plan)
    return filtered


def filter_by_ship(plans: List[VoyagePlan], ship_names: List[str]) -> List[VoyagePlan]:
    if not ship_names:
        return plans
    return [p for p in plans if p.voyage.ship_name in ship_names]


def filter_by_route(
    plans: List[VoyagePlan],
    loading_port: Optional[str] = None,
    discharging_port: Optional[str] = None,
) -> List[VoyagePlan]:
    filtered = plans
    if loading_port:
        filtered = [p for p in filtered if p.voyage.loading_port == loading_port]
    if discharging_port:
        filtered = [p for p in filtered if p.voyage.discharging_port == discharging_port]
    return filtered


def filter_by_cargo_type(
    plans: List[VoyagePlan],
    dangerous: Optional[bool] = None,
    refrigerated: Optional[bool] = None,
) -> List[VoyagePlan]:
    filtered = plans
    if dangerous is not None:
        filtered = [p for p in filtered if p.voyage.is_dangerous == dangerous]
    if refrigerated is not None:
        filtered = [p for p in filtered if p.voyage.is_refrigerated == refrigerated]
    return filtered


def filter_by_demurrage_risk(
    plans: List[VoyagePlan],
    risk_levels: List[str],
) -> List[VoyagePlan]:
    if not risk_levels:
        return plans
    return [p for p in plans if p.demurrage_risk in risk_levels]


def filter_by_weight_range(
    plans: List[VoyagePlan],
    min_weight: Optional[float] = None,
    max_weight: Optional[float] = None,
) -> List[VoyagePlan]:
    filtered = plans
    if min_weight is not None:
        filtered = [p for p in filtered if p.voyage.total_weight >= min_weight]
    if max_weight is not None:
        filtered = [p for p in filtered if p.voyage.total_weight <= max_weight]
    return filtered


def apply_filters(
    plans: List[VoyagePlan],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    date_type: str = "departure",
    ship_names: Optional[List[str]] = None,
    loading_port: Optional[str] = None,
    discharging_port: Optional[str] = None,
    dangerous: Optional[bool] = None,
    refrigerated: Optional[bool] = None,
    demurrage_risk: Optional[List[str]] = None,
    min_weight: Optional[float] = None,
    max_weight: Optional[float] = None,
) -> List[VoyagePlan]:
    filtered = filter_by_date_range(plans, start_date, end_date, date_type)
    if ship_names:
        filtered = filter_by_ship(filtered, ship_names)
    filtered = filter_by_route(filtered, loading_port, discharging_port)
    filtered = filter_by_cargo_type(filtered, dangerous, refrigerated)
    if demurrage_risk:
        filtered = filter_by_demurrage_risk(filtered, demurrage_risk)
    filtered = filter_by_weight_range(filtered, min_weight, max_weight)
    return filtered
