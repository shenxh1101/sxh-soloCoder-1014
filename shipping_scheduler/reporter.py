from typing import List, Dict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
import json
import csv
from datetime import datetime
from .models import VoyagePlan, CheckResult, Cargo
from .cost_calculator import summarize_costs


console = Console()


def format_currency(value: float) -> str:
    return f"¥{value:,.2f}"


def format_number(value: float) -> str:
    return f"{value:,.2f}"


def get_risk_color(risk: str) -> str:
    return {
        "low": "green",
        "medium": "yellow",
        "high": "red"
    }.get(risk, "white")


def print_schedule_table(plans: List[VoyagePlan], cargos: List[Cargo]):
    table = Table(title="航次调度表", box=box.ROUNDED, show_lines=True)
    table.add_column("航次号", style="cyan", no_wrap=True)
    table.add_column("船名", style="blue")
    table.add_column("航线", style="magenta")
    table.add_column("货物", style="yellow")
    table.add_column("载重(吨)", justify="right")
    table.add_column("类型", style="bold")
    table.add_column("装货时间", style="green")
    table.add_column("离港", style="cyan")
    table.add_column("到港", style="cyan")
    table.add_column("卸货完成", style="green")
    table.add_column("风险", style="bold")

    for plan in plans:
        voyage = plan.voyage
        cargo_list = [c for c in cargos if c.id in voyage.cargo_ids]
        cargo_names = ",".join([c.name[:10] for c in cargo_list])

        type_tags = []
        if voyage.is_dangerous:
            type_tags.append("[red]危险品[/red]")
        if voyage.is_refrigerated:
            type_tags.append("[blue]冷链[/blue]")
        if not type_tags:
            type_tags.append("普通")

        risk_color = get_risk_color(plan.demurrage_risk)
        risk_text = f"[{risk_color}]{plan.demurrage_risk.upper()}[/{risk_color}]"

        table.add_row(
            voyage.voyage_id,
            voyage.ship_name,
            f"{voyage.loading_port} → {voyage.discharging_port}",
            cargo_names,
            format_number(voyage.total_weight),
            " ".join(type_tags),
            voyage.loading_start.strftime("%m-%d %H:%M"),
            voyage.departure_date.strftime("%Y-%m-%d"),
            voyage.arrival_date.strftime("%Y-%m-%d"),
            voyage.discharging_end.strftime("%m-%d %H:%M"),
            risk_text
        )

    console.print(table)


def print_cost_table(plans: List[VoyagePlan]):
    table = Table(title="航次费用明细", box=box.ROUNDED, show_lines=True)
    table.add_column("航次号", style="cyan")
    table.add_column("船名", style="blue")
    table.add_column("航线", style="magenta")
    table.add_column("燃油费", justify="right", style="yellow")
    table.add_column("装港费", justify="right")
    table.add_column("卸港费", justify="right")
    table.add_column("附加费", justify="right", style="red")
    table.add_column("租金", justify="right", style="blue")
    table.add_column("滞期费", justify="right", style="red")
    table.add_column("总计", justify="right", style="bold green")

    for plan in plans:
        voyage = plan.voyage
        cost = plan.cost
        surcharges = cost.dangerous_cargo_fee + cost.refrigerated_fee

        table.add_row(
            voyage.voyage_id,
            voyage.ship_name,
            f"{voyage.loading_port}→{voyage.discharging_port}",
            format_currency(cost.fuel_cost),
            format_currency(cost.port_loading_fee),
            format_currency(cost.port_discharging_fee),
            format_currency(surcharges),
            format_currency(cost.charter_cost),
            format_currency(cost.demurrage_cost),
            format_currency(cost.total_cost)
        )

    console.print(table)


def print_cost_summary(plans: List[VoyagePlan]):
    summary = summarize_costs(plans)

    table = Table(title="费用汇总", box=box.ROUNDED, show_header=False)
    table.add_column("项目", style="bold")
    table.add_column("金额", justify="right", style="green")

    table.add_row("航次数量", str(summary["voyage_count"]))
    table.add_row("总载重吨", format_number(summary["total_weight"]))
    table.add_row("预计总天数", format_number(summary["total_estimated_days"]))
    table.add_row("─" * 20, "─" * 15)
    table.add_row("燃油费", format_currency(summary["fuel_cost"]))
    table.add_row("装港费", format_currency(summary["port_loading_cost"]))
    table.add_row("卸港费", format_currency(summary["port_discharging_cost"]))
    table.add_row("危险品附加费", format_currency(summary["dangerous_cargo_cost"]))
    table.add_row("冷链附加费", format_currency(summary["refrigerated_cost"]))
    table.add_row("船舶租金", format_currency(summary["charter_cost"]))
    table.add_row("预计滞期费", format_currency(summary["demurrage_cost"]))
    table.add_row("═" * 20, "═" * 15, style="bold")
    table.add_row("[bold]总费用[/bold]", format_currency(summary["grand_total"]), style="bold green")
    table.add_row("─" * 20, "─" * 15)
    table.add_row("单位成本(元/吨)", format_currency(summary["cost_per_ton"]))
    table.add_row("单位成本(元/天)", format_currency(summary["cost_per_day"]))

    console.print(table)


def print_check_results(check_results: List[CheckResult]):
    table = Table(title="检查结果", box=box.ROUNDED, show_lines=True)
    table.add_column("航次号", style="cyan")
    table.add_column("状态", style="bold")
    table.add_column("载重", style="yellow")
    table.add_column("吃水", style="blue")
    table.add_column("兼容性", style="magenta")
    table.add_column("船期", style="green")
    table.add_column("港口", style="green")
    table.add_column("期限", style="red")
    table.add_column("问题", style="red", overflow="fold")

    for result in check_results:
        status = "[green]✓ 通过[/green]" if result.passed else "[red]✗ 失败[/red]"
        d = result.details

        def get_detail(key: str) -> str:
            val = d.get(key, "")
            if "超限" in val or "冲突" in val or "延迟" in val:
                return f"[red]{val}[/red]"
            return val

        issues = "\n".join(result.issues) if result.issues else "-"

        table.add_row(
            result.voyage_id,
            status,
            get_detail("deadweight"),
            get_detail("draft"),
            get_detail("compatibility"),
            get_detail("schedule"),
            get_detail("port_availability"),
            get_detail("deadlines"),
            issues
        )

    console.print(table)

    passed = sum(1 for r in check_results if r.passed)
    total = len(check_results)
    console.print(f"\n[bold]检查摘要:[/bold] {passed}/{total} 项通过")


def print_anomalies(plans: List[VoyagePlan], check_results: List[CheckResult]):
    anomalies = []

    for plan in plans:
        for warning in plan.warnings:
            anomalies.append(("警告", plan.voyage.voyage_id, warning))
        for error in plan.errors:
            anomalies.append(("错误", plan.voyage.voyage_id, error))

    for result in check_results:
        for issue in result.issues:
            anomalies.append(("冲突", result.voyage_id, issue))

    if not anomalies:
        console.print(Panel("[green]✓ 没有发现异常[/green]", title="异常清单", border_style="green"))
        return

    table = Table(title="异常清单", box=box.ROUNDED)
    table.add_column("类型", style="bold")
    table.add_column("航次号", style="cyan")
    table.add_column("描述", style="red", overflow="fold")

    for typ, vid, desc in anomalies:
        color = "yellow" if typ == "警告" else "red"
        table.add_row(f"[{color}]{typ}[/{color}]", vid, desc)

    console.print(table)
    console.print(f"\n[bold red]发现 {len(anomalies)} 项异常[/bold red]")


def print_cargo_manifest(plans: List[VoyagePlan], cargos: List[Cargo]):
    table = Table(title="货物配载清单", box=box.ROUNDED, show_lines=True)
    table.add_column("航次号", style="cyan")
    table.add_column("船名", style="blue")
    table.add_column("货物ID", style="yellow")
    table.add_column("货物名称", style="bold")
    table.add_column("类型", style="magenta")
    table.add_column("重量(吨)", justify="right")
    table.add_column("优先级", justify="center")
    table.add_column("就绪日期", style="green")
    table.add_column("要求抵达", style="red")

    for plan in plans:
        voyage = plan.voyage
        cargo_list = [c for c in cargos if c.id in voyage.cargo_ids]
        for cargo in cargo_list:
            type_color = {
                "normal": "white",
                "dangerous": "red",
                "refrigerated": "blue",
                "bulk": "yellow",
                "liquid": "magenta"
            }.get(cargo.cargo_type.value, "white")

            priority_stars = "★" * cargo.priority + "☆" * (5 - cargo.priority)

            deadline_color = "red" if voyage.arrival_date > cargo.deadline else "green"

            table.add_row(
                voyage.voyage_id,
                voyage.ship_name,
                cargo.id,
                cargo.name,
                f"[{type_color}]{cargo.cargo_type.value}[/{type_color}]",
                format_number(cargo.weight),
                f"[yellow]{priority_stars}[/yellow]",
                cargo.ready_date.strftime("%Y-%m-%d"),
                f"[{deadline_color}]{cargo.deadline.strftime('%Y-%m-%d')}[/{deadline_color}]"
            )

    console.print(table)


def export_to_json(plans: List[VoyagePlan], check_results: List[CheckResult], filepath: str):
    data = {
        "export_time": datetime.now().isoformat(),
        "voyages": [],
        "check_results": []
    }

    for plan in plans:
        voyage_data = plan.model_dump(mode="json")
        data["voyages"].append(voyage_data)

    for result in check_results:
        result_data = result.model_dump(mode="json")
        data["check_results"].append(result_data)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    console.print(f"[green]已导出到 {filepath}[/green]")


def export_to_csv(plans: List[VoyagePlan], filepath: str):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "航次号", "船名", "装港", "卸港", "载重(吨)",
            "危险品", "冷链", "离港日期", "到港日期",
            "预计燃油(吨)", "预计天数", "滞期风险",
            "燃油费", "装港费", "卸港费", "附加费",
            "租金", "滞期费", "总费用"
        ])

        for plan in plans:
            v = plan.voyage
            c = plan.cost
            surcharges = c.dangerous_cargo_fee + c.refrigerated_fee
            writer.writerow([
                v.voyage_id, v.ship_name, v.loading_port, v.discharging_port,
                v.total_weight, v.is_dangerous, v.is_refrigerated,
                v.departure_date, v.arrival_date,
                f"{v.estimated_fuel:.2f}", f"{v.estimated_days:.2f}",
                plan.demurrage_risk,
                c.fuel_cost, c.port_loading_fee, c.port_discharging_fee,
                surcharges, c.charter_cost, c.demurrage_cost, c.total_cost
            ])

    console.print(f"[green]已导出到 {filepath}[/green]")
