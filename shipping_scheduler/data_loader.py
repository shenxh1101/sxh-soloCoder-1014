import csv
import json
import os
from datetime import date
from typing import List, Tuple, Dict
from .models import Port, Ship, Cargo, Route, CargoType


def parse_date(date_str: str) -> date:
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"]:
        try:
            return date.fromisoformat(date_str) if fmt == "%Y-%m-%d" else date.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {date_str}")


def load_ports_from_csv(file_path: str) -> List[Port]:
    ports = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            port = Port(
                code=row["code"],
                name=row["name"],
                max_draft=float(row["max_draft"]),
                handling_rate=float(row["handling_rate"]),
                port_fee_per_ton=float(row["port_fee_per_ton"]),
                dangerous_cargo_fee=float(row.get("dangerous_cargo_fee", 50.0)),
                refrigerated_fee=float(row.get("refrigerated_fee", 30.0)),
                working_hours_start=int(row.get("working_hours_start", 8)),
                working_hours_end=int(row.get("working_hours_end", 18)),
                demurrage_rate=float(row.get("demurrage_rate", 10000.0)),
            )
            ports.append(port)
    return ports


def load_ports_from_json(file_path: str) -> List[Port]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Port(**item) for item in data]


def load_ships_from_csv(file_path: str) -> List[Ship]:
    ships = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ship = Ship(
                name=row["name"],
                imo=row["imo"],
                deadweight=float(row["deadweight"]),
                draft=float(row["draft"]),
                speed=float(row["speed"]),
                fuel_consumption=float(row["fuel_consumption"]),
                fuel_price=float(row.get("fuel_price", 4500.0)),
                daily_charter=float(row["daily_charter"]),
                carries_dangerous=row.get("carries_dangerous", "false").lower() == "true",
                carries_refrigerated=row.get("carries_refrigerated", "false").lower() == "true",
                available_from=parse_date(row["available_from"]),
            )
            ships.append(ship)
    return ships


def load_ships_from_json(file_path: str) -> List[Ship]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for item in data:
        if isinstance(item["available_from"], str):
            item["available_from"] = parse_date(item["available_from"])
    return [Ship(**item) for item in data]


def load_cargos_from_csv(file_path: str) -> List[Cargo]:
    cargos = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cargo = Cargo(
                id=row["id"],
                name=row["name"],
                cargo_type=CargoType(row["cargo_type"].lower()),
                weight=float(row["weight"]),
                loading_port=row["loading_port"],
                discharging_port=row["discharging_port"],
                ready_date=parse_date(row["ready_date"]),
                deadline=parse_date(row["deadline"]),
                priority=int(row.get("priority", 1)),
                handling_instructions=row.get("handling_instructions"),
            )
            cargos.append(cargo)
    return cargos


def load_cargos_from_json(file_path: str) -> List[Cargo]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for item in data:
        if isinstance(item["ready_date"], str):
            item["ready_date"] = parse_date(item["ready_date"])
        if isinstance(item["deadline"], str):
            item["deadline"] = parse_date(item["deadline"])
        if isinstance(item["cargo_type"], str):
            item["cargo_type"] = CargoType(item["cargo_type"].lower())
    return [Cargo(**item) for item in data]


def load_routes_from_csv(file_path: str) -> List[Route]:
    routes = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            route = Route(
                from_port=row["from_port"],
                to_port=row["to_port"],
                distance=float(row["distance"]),
            )
            routes.append(route)
    return routes


def load_routes_from_json(file_path: str) -> List[Route]:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Route(**item) for item in data]


def load_data(
    ports_file: str = None,
    ships_file: str = None,
    cargos_file: str = None,
    routes_file: str = None,
) -> Tuple[Dict[str, Port], Dict[str, Ship], List[Cargo], Dict[str, Route]]:
    ports = {}
    ships = {}
    cargos = []
    routes = {}

    if ports_file:
        ext = os.path.splitext(ports_file)[1].lower()
        port_list = load_ports_from_csv(ports_file) if ext == ".csv" else load_ports_from_json(ports_file)
        ports = {p.code: p for p in port_list}

    if ships_file:
        ext = os.path.splitext(ships_file)[1].lower()
        ship_list = load_ships_from_csv(ships_file) if ext == ".csv" else load_ships_from_json(ships_file)
        ships = {s.name: s for s in ship_list}

    if cargos_file:
        ext = os.path.splitext(cargos_file)[1].lower()
        cargos = load_cargos_from_csv(cargos_file) if ext == ".csv" else load_cargos_from_json(cargos_file)

    if routes_file:
        ext = os.path.splitext(routes_file)[1].lower()
        route_list = load_routes_from_csv(routes_file) if ext == ".csv" else load_routes_from_json(routes_file)
        for r in route_list:
            key = f"{r.from_port}->{r.to_port}"
            routes[key] = r

    return ports, ships, cargos, routes


def get_route_distance(routes: Dict[str, Route], from_port: str, to_port: str) -> float:
    key = f"{from_port}->{to_port}"
    reverse_key = f"{to_port}->{from_port}"
    if key in routes:
        return routes[key].distance
    if reverse_key in routes:
        return routes[reverse_key].distance
    raise ValueError(f"未找到航线: {from_port} -> {to_port}")
