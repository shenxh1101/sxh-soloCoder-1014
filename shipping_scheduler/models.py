from datetime import datetime, date
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class CargoType(str, Enum):
    NORMAL = "normal"
    DANGEROUS = "dangerous"
    REFRIGERATED = "refrigerated"
    BULK = "bulk"
    LIQUID = "liquid"


class Port(BaseModel):
    code: str
    name: str
    max_draft: float = Field(description="最大吃水深度(米)")
    handling_rate: float = Field(description="装卸效率(吨/天)")
    port_fee_per_ton: float = Field(description="港杂费(元/吨)")
    dangerous_cargo_fee: float = Field(default=50.0, description="危险品附加费(元/吨)")
    refrigerated_fee: float = Field(default=30.0, description="冷链附加费(元/吨)")
    working_hours_start: int = Field(default=8, description="作业开始时间")
    working_hours_end: int = Field(default=18, description="作业结束时间")
    demurrage_rate: float = Field(default=10000.0, description="滞期费率(元/天)")


class Ship(BaseModel):
    name: str
    imo: str
    deadweight: float = Field(description="载重吨(DWT)")
    draft: float = Field(description="满载吃水(米)")
    speed: float = Field(description="航行速度(节)")
    fuel_consumption: float = Field(description="燃油消耗(吨/天)")
    fuel_price: float = Field(default=4500.0, description="燃油价格(元/吨)")
    daily_charter: float = Field(description="日租金(元/天)")
    carries_dangerous: bool = Field(default=False, description="是否可载危险品")
    carries_refrigerated: bool = Field(default=False, description="是否可载冷链")
    available_from: date = Field(description="船舶可用日期")


class Cargo(BaseModel):
    id: str
    name: str
    cargo_type: CargoType
    weight: float = Field(description="重量(吨)")
    loading_port: str
    discharging_port: str
    ready_date: date = Field(description="货物就绪日期")
    deadline: date = Field(description="要求抵达日期")
    priority: int = Field(default=1, ge=1, le=5, description="优先级(1-5, 5最高)")
    handling_instructions: Optional[str] = None


class Route(BaseModel):
    from_port: str
    to_port: str
    distance: float = Field(description="航程(海里)")


class Voyage(BaseModel):
    voyage_id: str
    ship_name: str
    cargo_ids: List[str]
    loading_port: str
    discharging_port: str
    departure_date: date
    arrival_date: date
    loading_start: datetime
    loading_end: datetime
    discharging_start: datetime
    discharging_end: datetime
    total_weight: float
    is_dangerous: bool = False
    is_refrigerated: bool = False
    estimated_fuel: float = 0.0
    estimated_days: float = 0.0


class CostBreakdown(BaseModel):
    fuel_cost: float = 0.0
    port_loading_fee: float = 0.0
    port_discharging_fee: float = 0.0
    dangerous_cargo_fee: float = 0.0
    refrigerated_fee: float = 0.0
    charter_cost: float = 0.0
    demurrage_cost: float = 0.0
    total_cost: float = 0.0


class VoyagePlan(BaseModel):
    voyage: Voyage
    cost: CostBreakdown
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    demurrage_risk: str = Field(default="low", description="滞期风险: low/medium/high")


class CheckResult(BaseModel):
    voyage_id: str
    passed: bool
    issues: List[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)
