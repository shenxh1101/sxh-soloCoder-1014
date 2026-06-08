import click
import sys
from datetime import date
from typing import List
from .data_loader import load_data, parse_date
from .planner import generate_candidate_voyages
from .checker import check_all
from .cost_calculator import calculate_all_costs
from .filters import apply_filters
from .reporter import (
    print_schedule_table,
    print_cost_table,
    print_cost_summary,
    print_check_results,
    print_anomalies,
    print_cargo_manifest,
    export_to_json,
    export_to_csv,
    console,
)
from .models import VoyagePlan, CheckResult


def parse_comma_list(ctx, param, value):
    if value is None:
        return None
    return [x.strip() for x in value.split(",")]


filter_options = [
    click.option("--start-date", type=str, help="筛选开始日期 (YYYY-MM-DD)"),
    click.option("--end-date", type=str, help="筛选结束日期 (YYYY-MM-DD)"),
    click.option("--date-type", type=click.Choice(["departure", "arrival"]), default="departure",
                 help="日期筛选类型: 离港或到港"),
    click.option("--ship", "ship_names", callback=parse_comma_list, help="按船名筛选，多个用逗号分隔"),
    click.option("--load-port", type=str, help="按装货港筛选"),
    click.option("--disch-port", type=str, help="按卸货港筛选"),
    click.option("--dangerous/--no-dangerous", is_flag=True, default=None, help="筛选危险品航次"),
    click.option("--refrigerated/--no-refrigerated", is_flag=True, default=None, help="筛选冷链航次"),
    click.option("--demurrage-risk", callback=parse_comma_list,
                 type=click.Choice(["low", "medium", "high"]), help="按滞期风险筛选"),
    click.option("--min-weight", type=float, help="最小载重吨"),
    click.option("--max-weight", type=float, help="最大载重吨"),
]


def add_filter_options(func):
    for option in reversed(filter_options):
        func = option(func)
    return func


def apply_filter_options(plans: List[VoyagePlan], **kwargs) -> List[VoyagePlan]:
    start_date = parse_date(kwargs["start_date"]) if kwargs.get("start_date") else None
    end_date = parse_date(kwargs["end_date"]) if kwargs.get("end_date") else None

    return apply_filters(
        plans,
        start_date=start_date,
        end_date=end_date,
        date_type=kwargs.get("date_type", "departure"),
        ship_names=kwargs.get("ship_names"),
        loading_port=kwargs.get("load_port"),
        discharging_port=kwargs.get("disch_port"),
        dangerous=kwargs.get("dangerous"),
        refrigerated=kwargs.get("refrigerated"),
        demurrage_risk=kwargs.get("demurrage_risk"),
        min_weight=kwargs.get("min_weight"),
        max_weight=kwargs.get("max_weight"),
    )


def load_all_data(ports_file, ships_file, cargos_file, routes_file):
    try:
        ports, ships, cargos, routes = load_data(
            ports_file=ports_file,
            ships_file=ships_file,
            cargos_file=cargos_file,
            routes_file=routes_file,
        )
    except Exception as e:
        console.print(f"[red]数据加载失败: {e}[/red]")
        sys.exit(1)

    if not ports:
        console.print("[red]警告: 未加载港口数据[/red]")
    if not ships:
        console.print("[red]警告: 未加载船舶数据[/red]")
    if not cargos:
        console.print("[red]警告: 未加载货物数据[/red]")
    if not routes:
        console.print("[yellow]警告: 未加载航线数据，将使用默认距离[/yellow]")

    return ports, ships, cargos, routes


@click.group()
@click.version_option(version="1.0.0", prog_name="shipping-scheduler")
@click.option("--ports", "ports_file", type=click.Path(exists=True),
              help="港口数据文件 (CSV/JSON)")
@click.option("--ships", "ships_file", type=click.Path(exists=True),
              help="船舶数据文件 (CSV/JSON)")
@click.option("--cargos", "cargos_file", type=click.Path(exists=True),
              help="货物数据文件 (CSV/JSON)")
@click.option("--routes", "routes_file", type=click.Path(exists=True),
              help="航线数据文件 (CSV/JSON)")
@click.pass_context
def cli(ctx, ports_file, ships_file, cargos_file, routes_file):
    """水路运输调度命令行工具"""
    ctx.ensure_object(dict)
    ctx.obj["ports_file"] = ports_file
    ctx.obj["ships_file"] = ships_file
    ctx.obj["cargos_file"] = cargos_file
    ctx.obj["routes_file"] = routes_file


@cli.command()
@click.option("--max-cargos", type=int, default=5, help="每个航次最大货物数")
@click.option("--output", "output_file", type=click.Path(), help="导出结果到文件")
@click.option("--format", "output_format", type=click.Choice(["json", "csv"]),
              default="json", help="导出格式")
@click.option("--show-costs/--no-show-costs", is_flag=True, default=True,
              help="是否显示费用信息")
@add_filter_options
@click.pass_context
def plan(ctx, max_cargos, output_file, output_format, show_costs, **filter_kwargs):
    """生成航次计划"""
    ports, ships, cargos, routes = load_all_data(
        ctx.obj["ports_file"], ctx.obj["ships_file"],
        ctx.obj["cargos_file"], ctx.obj["routes_file"]
    )

    if not ships or not cargos:
        console.print("[red]缺少必要数据，无法生成计划[/red]")
        return

    console.print(f"[bold]生成航次计划中...[/bold] 船舶: {len(ships)}艘, 货物: {len(cargos)}批")

    plans = generate_candidate_voyages(ports, ships, cargos, routes, max_cargos)
    plans = calculate_all_costs(plans, ships, ports, cargos)
    plans = apply_filter_options(plans, **filter_kwargs)
    check_results = check_all(plans, ships, ports, cargos)

    if not plans:
        console.print("[yellow]未生成符合条件的航次计划[/yellow]")
        return

    console.print(f"[green]已生成 {len(plans)} 个航次计划[/green]\n")
    print_schedule_table(plans, cargos)
    print_cargo_manifest(plans, cargos)

    if show_costs:
        print_cost_table(plans)
        print_cost_summary(plans)

    print_anomalies(plans, check_results)

    if output_file:
        if output_format == "json":
            export_to_json(plans, check_results, output_file)
        else:
            export_to_csv(plans, output_file)

    ctx.obj["last_plans"] = plans
    ctx.obj["last_check_results"] = check_results


@cli.command()
@click.option("--output", "output_file", type=click.Path(), help="导出检查结果到JSON")
@add_filter_options
@click.pass_context
def check(ctx, output_file, **filter_kwargs):
    """检查航次冲突和约束"""
    ports, ships, cargos, routes = load_all_data(
        ctx.obj["ports_file"], ctx.obj["ships_file"],
        ctx.obj["cargos_file"], ctx.obj["routes_file"]
    )

    plans = ctx.obj.get("last_plans")
    if not plans:
        if not ships or not cargos:
            console.print("[red]缺少必要数据[/red]")
            return
        plans = generate_candidate_voyages(ports, ships, cargos, routes)
        plans = calculate_all_costs(plans, ships, ports, cargos)

    plans = apply_filter_options(plans, **filter_kwargs)
    check_results = check_all(plans, ships, ports, cargos)

    print_schedule_table(plans, cargos)
    print_check_results(check_results)
    print_anomalies(plans, check_results)

    if output_file:
        export_to_json(plans, check_results, output_file)

    ctx.obj["last_plans"] = plans
    ctx.obj["last_check_results"] = check_results


@cli.command()
@click.option("--detail/--summary", default=False, help="显示明细或仅汇总")
@click.option("--output", "output_file", type=click.Path(), help="导出费用表到CSV")
@add_filter_options
@click.pass_context
def cost(ctx, detail, output_file, **filter_kwargs):
    """计算航次费用"""
    ports, ships, cargos, routes = load_all_data(
        ctx.obj["ports_file"], ctx.obj["ships_file"],
        ctx.obj["cargos_file"], ctx.obj["routes_file"]
    )

    plans = ctx.obj.get("last_plans")
    if not plans:
        if not ships or not cargos:
            console.print("[red]缺少必要数据[/red]")
            return
        plans = generate_candidate_voyages(ports, ships, cargos, routes)

    plans = calculate_all_costs(plans, ships, ports, cargos)
    plans = apply_filter_options(plans, **filter_kwargs)
    check_results = check_all(plans, ships, ports, cargos)

    if detail:
        print_cost_table(plans)
    print_cost_summary(plans)
    print_anomalies(plans, check_results)

    if output_file:
        export_to_csv(plans, output_file)

    ctx.obj["last_plans"] = plans
    ctx.obj["last_check_results"] = check_results


@cli.command()
@click.option("--type", "report_type",
              type=click.Choice(["schedule", "cost", "cargo", "anomaly", "all"]),
              default="all", help="报告类型")
@click.option("--output", "output_file", type=click.Path(), help="导出报告")
@click.option("--format", "output_format", type=click.Choice(["json", "csv"]),
              default="json", help="导出格式")
@add_filter_options
@click.pass_context
def report(ctx, report_type, output_file, output_format, **filter_kwargs):
    """生成调度报告"""
    ports, ships, cargos, routes = load_all_data(
        ctx.obj["ports_file"], ctx.obj["ships_file"],
        ctx.obj["cargos_file"], ctx.obj["routes_file"]
    )

    plans = ctx.obj.get("last_plans")
    if not plans:
        if not ships or not cargos:
            console.print("[red]缺少必要数据[/red]")
            return
        plans = generate_candidate_voyages(ports, ships, cargos, routes)
        plans = calculate_all_costs(plans, ships, ports, cargos)

    plans = apply_filter_options(plans, **filter_kwargs)
    check_results = check_all(plans, ships, ports, cargos)

    if report_type in ["schedule", "all"]:
        print_schedule_table(plans, cargos)

    if report_type in ["cargo", "all"]:
        print_cargo_manifest(plans, cargos)

    if report_type in ["cost", "all"]:
        print_cost_table(plans)
        print_cost_summary(plans)

    if report_type in ["anomaly", "all"]:
        print_check_results(check_results)
        print_anomalies(plans, check_results)

    if output_file:
        if output_format == "json":
            export_to_json(plans, check_results, output_file)
        else:
            export_to_csv(plans, output_file)

    ctx.obj["last_plans"] = plans
    ctx.obj["last_check_results"] = check_results


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
