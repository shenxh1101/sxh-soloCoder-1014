import click
import sys
from datetime import date
from typing import List, Optional
from .data_loader import load_data, parse_date
from .planner import generate_candidate_voyages, generate_multi_scenario, STRATEGY_CONFIGS
from .checker import check_all
from .cost_calculator import calculate_all_costs
from .filters import apply_filters
from .plan_storage import (
    load_plan, save_plan, create_schedule_plan, add_scenario,
    get_scenario_for_operation
)
from .reporter import (
    print_schedule_table,
    print_cost_table,
    print_cost_summary,
    print_check_results,
    print_anomalies,
    print_cargo_manifest,
    print_unassigned_cargos,
    print_scenario_comparison,
    export_to_json,
    export_to_csv,
    export_scenario_comparison,
    format_currency,
    console,
)
from .models import (
    VoyagePlan, CheckResult, PlanStrategy, SchedulePlan, UnassignedCargo,
    PlanScenario
)


VALID_RISK_VALUES = ["low", "medium", "high"]


def parse_comma_list(ctx, param, value):
    if value is None:
        return None
    return [x.strip() for x in value.split(",")]


def parse_demurrage_risk(ctx, param, value):
    if value is None:
        return None

    values = [x.strip().lower() for x in value.split(",")]
    invalid_values = [v for v in values if v not in VALID_RISK_VALUES]

    if invalid_values:
        console.print(
            f"[red]错误: 滞期风险参数值无效: {', '.join(invalid_values)}[/red]\n"
            f"[yellow]可用值: {', '.join(VALID_RISK_VALUES)}[/yellow]\n"
            f"[dim]用法示例: --demurrage-risk medium,high 或 --demurrage-risk high[/dim]"
        )
        sys.exit(1)

    return values


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
    click.option("--demurrage-risk", callback=parse_demurrage_risk,
                 help=f"按滞期风险筛选，多个用逗号分隔 (可用值: {', '.join(VALID_RISK_VALUES)})"),
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


def process_strategy_arg(ctx, param, value):
    if value is None:
        return None
    try:
        return PlanStrategy(value.lower())
    except ValueError:
        available = [s.value for s in PlanStrategy]
        console.print(
            f"[red]错误: 无效的调度策略 '{value}'[/red]\n"
            f"[yellow]可用策略: {', '.join(available)}[/yellow]"
        )
        sys.exit(1)


def process_multi_strategies(ctx, param, value):
    if not value:
        return None
    strategies = []
    available = [s.value for s in PlanStrategy]
    for v in value:
        v = v.lower()
        if v not in available:
            console.print(
                f"[red]错误: 无效的调度策略 '{v}'[/red]\n"
                f"[yellow]可用策略: {', '.join(available)}[/yellow]"
            )
            sys.exit(1)
        strategies.append(PlanStrategy(v))
    return strategies


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
@click.option("--plan-file", type=click.Path(exists=True),
              help="从已保存的计划文件加载（无需重复指定原始数据文件）")
@click.pass_context
def cli(ctx, ports_file, ships_file, cargos_file, routes_file, plan_file):
    """水路运输调度命令行工具"""
    ctx.ensure_object(dict)
    ctx.obj["ports_file"] = ports_file
    ctx.obj["ships_file"] = ships_file
    ctx.obj["cargos_file"] = cargos_file
    ctx.obj["routes_file"] = routes_file
    ctx.obj["plan_file"] = plan_file

    if plan_file:
        try:
            loaded_plan = load_plan(plan_file)
            ctx.obj["loaded_plan"] = loaded_plan
            console.print(f"[green]✓ 已加载计划: {loaded_plan.name}[/green]")
            console.print(f"  [dim]计划ID: {loaded_plan.plan_id}[/dim]")
            console.print(f"  [dim]生成时间: {loaded_plan.generated_at.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            console.print(f"  [dim]方案数量: {len(loaded_plan.scenarios)}[/dim]\n")
        except Exception as e:
            console.print(f"[red]加载计划文件失败: {e}[/red]")
            sys.exit(1)


def get_or_create_data(ctx):
    loaded_plan = ctx.obj.get("loaded_plan")
    if loaded_plan:
        ports_file = ctx.obj.get("ports_file")
        ships_file = ctx.obj.get("ships_file")
        cargos_file = ctx.obj.get("cargos_file")
        routes_file = ctx.obj.get("routes_file")

        ports = None
        ships = None
        cargos = None
        routes = None

        try:
            if ports_file or ships_file or cargos_file or routes_file:
                ports, ships, cargos, routes = load_data(
                    ports_file=ports_file,
                    ships_file=ships_file,
                    cargos_file=cargos_file,
                    routes_file=routes_file,
                )
        except Exception as e:
            console.print(f"[yellow]警告: 加载原始数据失败: {e}[/yellow]")

        return ports, ships, cargos, routes, loaded_plan

    ports_file = ctx.obj.get("ports_file")
    ships_file = ctx.obj.get("ships_file")
    cargos_file = ctx.obj.get("cargos_file")
    routes_file = ctx.obj.get("routes_file")

    if not (ports_file and ships_file and cargos_file):
        console.print(
            "[red]错误: 请提供原始数据文件 (--ports, --ships, --cargos) "
            "或使用 --plan-file 加载已保存的计划[/red]"
        )
        sys.exit(1)

    ports, ships, cargos, routes = load_all_data(ports_file, ships_file, cargos_file, routes_file)
    return ports, ships, cargos, routes, None


def get_active_scenario(ctx, scenario_id: str = None):
    loaded_plan = ctx.obj.get("loaded_plan")
    if loaded_plan:
        try:
            scenario, filters = get_scenario_for_operation(loaded_plan, scenario_id)
            return scenario.plans, scenario.check_results, scenario.unassigned_cargos, loaded_plan
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)
    return None, None, None, None


@cli.command()
@click.option("--max-cargos", type=int, default=5, help="每个航次最大货物数")
@click.option("--strategy", type=str, callback=process_strategy_arg,
              default="lowest_cost",
              help=f"调度策略: {', '.join([s.value for s in PlanStrategy])}")
@click.option("--multi", "multi_strategies", type=str, multiple=True,
              callback=process_multi_strategies,
              help="生成多个方案进行对比，可多次指定，如 --multi lowest_cost --multi fastest_arrival")
@click.option("--all-strategies", is_flag=True, default=False,
              help="使用全部4种策略生成方案")
@click.option("--name", "plan_name", type=str, default="调度计划",
              help="计划名称，用于保存")
@click.option("--save", "save_file", type=click.Path(),
              help="保存计划到文件（可后续直接加载）")
@click.option("--output", "output_file", type=click.Path(), help="导出结果到文件")
@click.option("--format", "output_format", type=click.Choice(["json", "csv"]),
              default="json", help="导出格式")
@click.option("--show-costs/--no-show-costs", is_flag=True, default=True,
              help="是否显示费用信息")
@click.option("--scenario", type=str,
              help="加载已保存计划时指定方案ID")
@add_filter_options
@click.pass_context
def plan(ctx, max_cargos, strategy, multi_strategies, all_strategies, plan_name,
         save_file, output_file, output_format, show_costs, scenario, **filter_kwargs):
    """生成航次计划，支持多策略方案对比"""
    ports, ships, cargos, routes, loaded_plan = get_or_create_data(ctx)

    if loaded_plan:
        if not multi_strategies and not all_strategies:
            plans, check_results, unassigned, _ = get_active_scenario(ctx, scenario)
            if plans is not None:
                plans = apply_filter_options(plans, **filter_kwargs)
                console.print(f"[green]从计划文件加载: {len(plans)} 个航次[/green]\n")
                _print_plan_results(plans, check_results, unassigned, cargos, show_costs,
                                  output_file, output_format, **filter_kwargs)
                return

    if ports is None or ships is None or cargos is None:
        console.print("[red]缺少必要数据，无法生成计划[/red]")
        return

    console.print(f"[bold]生成航次计划中...[/bold] 船舶: {len(ships)}艘, 货物: {len(cargos)}批\n")

    data_sources = {
        "ports": ctx.obj.get("ports_file", ""),
        "ships": ctx.obj.get("ships_file", ""),
        "cargos": ctx.obj.get("cargos_file", ""),
        "routes": ctx.obj.get("routes_file", ""),
    }

    if save_file:
        schedule_plan = create_schedule_plan(plan_name, ports, ships, cargos, routes, data_sources)
    else:
        schedule_plan = None

    if all_strategies:
        strategies = list(PlanStrategy)
    elif multi_strategies:
        strategies = multi_strategies
    else:
        strategies = [strategy]

    multi_results = generate_multi_scenario(ports, ships, cargos, routes, strategies, max_cargos)

    for strat in strategies:
        config = STRATEGY_CONFIGS[strat]
        console.print(f"[bold cyan]━━━ 方案: {config['name']} ━━━[/bold cyan]")
        console.print(f"[dim]{config['description']}[/dim]\n")

        plans, unassigned = multi_results[strat]
        plans = calculate_all_costs(plans, ships, ports, cargos)
        plans_filtered = apply_filter_options(plans, **filter_kwargs)
        check_results = check_all(plans_filtered, ships, ports, cargos)

        if schedule_plan is not None:
            add_scenario(
                schedule_plan, strat, config["name"], config["description"],
                plans, check_results, unassigned
            )

        if len(strategies) == 1:
            if not plans_filtered:
                console.print("[yellow]未生成符合条件的航次计划[/yellow]")
            else:
                console.print(f"[green]已生成 {len(plans_filtered)} 个航次计划[/green]\n")
                _print_plan_results(plans_filtered, check_results, unassigned, cargos,
                                  show_costs, output_file, output_format, **filter_kwargs)
        else:
            console.print(f"  航次数: {len(plans)}, 未安排: {len(unassigned)}, "
                         f"总费用: {format_currency(sum(p.cost.total_cost for p in plans))}\n")

        ctx.obj[f"plans_{strat.value}"] = plans
        ctx.obj[f"check_{strat.value}"] = check_results
        ctx.obj[f"unassigned_{strat.value}"] = unassigned

    if len(strategies) > 1:
        scenarios_list = []
        for strat in strategies:
            config = STRATEGY_CONFIGS[strat]
            plans = ctx.obj.get(f"plans_{strat.value}", [])
            unassigned = ctx.obj.get(f"unassigned_{strat.value}", [])
            check_results = ctx.obj.get(f"check_{strat.value}", [])
            scenarios_list.append(PlanScenario(
                scenario_id=f"S{strat.value}",
                strategy=strat,
                strategy_name=config["name"],
                description=config["description"],
                plans=plans,
                check_results=check_results,
                unassigned_cargos=unassigned,
            ))

        console.print("\n" + "=" * 60)
        print_scenario_comparison(scenarios_list)

        if output_file:
            export_scenario_comparison(scenarios_list, output_file)

    if save_file and schedule_plan:
        schedule_plan.filters_applied = {
            k: v for k, v in filter_kwargs.items() if v is not None
        }
        save_plan(schedule_plan, save_file)
        console.print(f"\n[green]✓ 计划已保存到: {save_file}[/green]")
        console.print(f"  [dim]计划ID: {schedule_plan.plan_id}[/dim]")


def _print_plan_results(plans, check_results, unassigned, cargos, show_costs,
                       output_file, output_format, **filter_kwargs):
    print_schedule_table(plans, cargos)
    print_cargo_manifest(plans, cargos)

    if show_costs:
        print_cost_table(plans)
        print_cost_summary(plans)

    if unassigned is not None:
        print_unassigned_cargos(unassigned)
    print_anomalies(plans, check_results)

    if output_file:
        if output_format == "json":
            export_to_json(plans, check_results, output_file)
        else:
            export_to_csv(plans, output_file)


@cli.command()
@click.option("--output", "output_file", type=click.Path(), help="导出检查结果到JSON")
@click.option("--scenario", type=str,
              help="加载已保存计划时指定方案ID")
@add_filter_options
@click.pass_context
def check(ctx, output_file, scenario, **filter_kwargs):
    """检查航次冲突和约束"""
    ports, ships, cargos, routes, loaded_plan = get_or_create_data(ctx)

    plans = None
    check_results = None
    unassigned = []

    if loaded_plan:
        plans, check_results, unassigned, _ = get_active_scenario(ctx, scenario)
        if plans is None:
            console.print("[red]计划文件中没有可用的航次数据[/red]")
            return

    if plans is None:
        plans = ctx.obj.get("last_plans")
        if not plans:
            if not ships or not cargos:
                console.print("[red]缺少必要数据[/red]")
                return
            plans, unassigned = generate_candidate_voyages(ports, ships, cargos, routes)
            plans = calculate_all_costs(plans, ships, ports, cargos)

    plans = apply_filter_options(plans, **filter_kwargs)
    if check_results is None or len(check_results) != len(plans):
        if ships and ports:
            check_results = check_all(plans, ships, ports, cargos)
        else:
            console.print("[yellow]警告: 缺少船舶/港口原始数据，将使用计划中已保存的检查结果[/yellow]")
            check_results = []

    print_schedule_table(plans, cargos)
    if check_results:
        print_check_results(check_results)
    if unassigned is not None:
        print_unassigned_cargos(unassigned)
    print_anomalies(plans, check_results)

    if output_file:
        export_to_json(plans, check_results, output_file)

    ctx.obj["last_plans"] = plans
    ctx.obj["last_check_results"] = check_results


@cli.command()
@click.option("--detail/--summary", default=False, help="显示明细或仅汇总")
@click.option("--output", "output_file", type=click.Path(), help="导出费用表到CSV")
@click.option("--scenario", type=str,
              help="加载已保存计划时指定方案ID")
@add_filter_options
@click.pass_context
def cost(ctx, detail, output_file, scenario, **filter_kwargs):
    """计算航次费用"""
    ports, ships, cargos, routes, loaded_plan = get_or_create_data(ctx)

    plans = None
    check_results = None
    unassigned = []

    if loaded_plan:
        plans, check_results, unassigned, _ = get_active_scenario(ctx, scenario)
        if plans is None:
            console.print("[red]计划文件中没有可用的航次数据[/red]")
            return

    if plans is None:
        plans = ctx.obj.get("last_plans")
        if not plans:
            if not ships or not cargos:
                console.print("[red]缺少必要数据[/red]")
                return
            plans, unassigned = generate_candidate_voyages(ports, ships, cargos, routes)

    has_cost_data = all(hasattr(p, 'cost') and p.cost and p.cost.total_cost > 0 for p in plans) if plans else False
    if not has_cost_data and ships and ports and cargos:
        plans = calculate_all_costs(plans, ships, ports, cargos)
    elif not has_cost_data:
        console.print("[yellow]警告: 缺少船舶/港口/货物原始数据，无法重新计算费用，将使用计划中已保存的数据[/yellow]")

    plans = apply_filter_options(plans, **filter_kwargs)
    if check_results is None or len(check_results) != len(plans):
        if ships and ports:
            check_results = check_all(plans, ships, ports, cargos)
        else:
            check_results = []

    if detail:
        print_cost_table(plans)
    print_cost_summary(plans)
    if unassigned is not None:
        print_unassigned_cargos(unassigned)
    print_anomalies(plans, check_results)

    if output_file:
        export_to_csv(plans, output_file)

    ctx.obj["last_plans"] = plans
    ctx.obj["last_check_results"] = check_results


@cli.command()
@click.option("--type", "report_type",
              type=click.Choice(["schedule", "cost", "cargo", "anomaly", "compare", "all"]),
              default="all", help="报告类型: compare=多方案对比")
@click.option("--output", "output_file", type=click.Path(), help="导出报告")
@click.option("--format", "output_format", type=click.Choice(["json", "csv"]),
              default="json", help="导出格式")
@click.option("--scenario", type=str,
              help="加载已保存计划时指定方案ID")
@click.option("--compare-all", is_flag=True, default=False,
              help="对比计划中的所有方案")
@add_filter_options
@click.pass_context
def report(ctx, report_type, output_file, output_format, scenario, compare_all, **filter_kwargs):
    """生成调度报告，支持多方案对比导出"""
    ports, ships, cargos, routes, loaded_plan = get_or_create_data(ctx)

    plans = None
    check_results = None
    unassigned = []

    if loaded_plan:
        if report_type == "compare" or compare_all:
            if len(loaded_plan.scenarios) < 2:
                console.print("[yellow]计划中只有1个方案，无法进行对比[/yellow]")
            else:
                print_scenario_comparison(loaded_plan.scenarios)
                if output_file:
                    export_scenario_comparison(loaded_plan.scenarios, output_file)
            return

        plans, check_results, unassigned, _ = get_active_scenario(ctx, scenario)
        if plans is None:
            console.print("[red]计划文件中没有可用的航次数据[/red]")
            return

    if plans is None:
        plans = ctx.obj.get("last_plans")
        if not plans:
            if not ships or not cargos:
                console.print("[red]缺少必要数据[/red]")
                return
            plans, unassigned = generate_candidate_voyages(ports, ships, cargos, routes)
            plans = calculate_all_costs(plans, ships, ports, cargos)

    plans = apply_filter_options(plans, **filter_kwargs)
    if check_results is None or len(check_results) != len(plans):
        if ships and ports:
            check_results = check_all(plans, ships, ports, cargos)
        else:
            check_results = []

    if report_type in ["schedule", "all"]:
        print_schedule_table(plans, cargos)

    if report_type in ["cargo", "all"]:
        print_cargo_manifest(plans, cargos)
        if unassigned is not None:
            print_unassigned_cargos(unassigned)

    if report_type in ["cost", "all"]:
        print_cost_table(plans)
        print_cost_summary(plans)

    if report_type in ["anomaly", "all"]:
        if check_results:
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
