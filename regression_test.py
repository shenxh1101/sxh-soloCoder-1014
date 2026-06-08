import subprocess
import json
import os
import sys

def run_cmd(cmd, cwd='.'):
    print(f"\n{'='*60}")
    print(f"执行命令: {cmd}")
    print('='*60)
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, encoding='utf-8', env=env)
    if result.returncode != 0:
        print(f"❌ 命令失败，退出码: {result.returncode}")
        if result.stderr:
            print(f"错误输出:\n{result.stderr[:500]}")
        return False, result.stdout, result.stderr
    print(f"✅ 命令成功")
    return True, result.stdout, result.stderr

def check_plan_file(filepath, expected_voyage_count, expected_filters=None):
    print(f"\n检查计划文件: {filepath}")
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在")
        return False
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    scenario = data['scenarios'][0]
    plans = scenario['plans']
    check_results = scenario['check_results']
    voyage_ids = [p['voyage']['voyage_id'] for p in plans]
    
    actual_count = len(plans)
    print(f"  航次数量: {actual_count} (期望: {expected_voyage_count})")
    if actual_count != expected_voyage_count:
        print(f"❌ 航次数量不匹配")
        return False
    
    if 'V0008' in voyage_ids and expected_voyage_count < 14:
        print(f"❌ V0008 不应出现在筛选后的结果中")
        return False
    
    if expected_filters:
        actual_filters = data.get('filters_applied', {})
        print(f"  filters_applied: {actual_filters}")
        print(f"  期望: {expected_filters}")
        for k, v in expected_filters.items():
            if k not in actual_filters or actual_filters[k] != v:
                print(f"❌ filters_applied 不匹配")
                return False
    
    total_cost = sum(p['cost']['total_cost'] for p in plans)
    print(f"  总费用: {total_cost:,.2f}")
    print(f"  航次ID: {sorted(voyage_ids)}")
    print(f"✅ 计划文件检查通过")
    return True

def check_multi_plan_file(filepath, expected_scenario_count=4):
    print(f"\n检查多方案计划文件: {filepath}")
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在")
        return False
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    scenarios = data['scenarios']
    actual_count = len(scenarios)
    print(f"  方案数量: {actual_count} (期望: {expected_scenario_count})")
    if actual_count != expected_scenario_count:
        print(f"❌ 方案数量不匹配")
        return False
    
    scenario_ids = [s['scenario_id'] for s in scenarios]
    print(f"  方案ID: {scenario_ids}")
    
    seen = set()
    for sid in scenario_ids:
        if sid in seen:
            print(f"❌ 方案ID重复: {sid}")
            return False
        seen.add(sid)
    
    expected_ids = ['S01-lowest_cost', 'S02-fastest_arrival', 'S03-priority_first', 'S04-low_demurrage']
    for eid in expected_ids:
        if eid not in scenario_ids:
            print(f"❌ 缺少方案: {eid}")
            return False
    
    print(f"✅ 多方案计划文件检查通过")
    return True

def check_output_for_metrics(output, expected_voyage_count=None, expected_total_cost=None, expected_anomaly_count=None):
    print(f"\n检查终端输出指标:")
    checks_passed = True
    
    if expected_voyage_count is not None:
        import re
        pattern = r"航次数量\s*│\s*" + str(expected_voyage_count) + r"\s*│"
        if re.search(pattern, output):
            print(f"✅ 航次数量匹配: {expected_voyage_count}")
        else:
            # 尝试更宽松的匹配
            if f"航次数量" in output and str(expected_voyage_count) in output:
                lines = output.split('\n')
                for line in lines:
                    if "航次数量" in line and str(expected_voyage_count) in line:
                        print(f"✅ 航次数量匹配: {expected_voyage_count} (行: {line.strip()})")
                        break
                else:
                    print(f"❌ 航次数量不匹配，期望: {expected_voyage_count}")
                    # 打印包含航次数量的行以便调试
                    for line in lines:
                        if "航次数量" in line:
                            print(f"  实际行: {line.strip()}")
                    checks_passed = False
            else:
                print(f"❌ 航次数量不匹配，期望: {expected_voyage_count}")
                checks_passed = False
    
    if expected_total_cost is not None:
        if expected_total_cost in output:
            print(f"✅ 总费用匹配: {expected_total_cost}")
        else:
            print(f"❌ 总费用不匹配，期望: {expected_total_cost}")
            checks_passed = False
    
    if expected_anomaly_count is not None:
        anomaly_str = f"发现 {expected_anomaly_count} 项异常"
        if anomaly_str in output:
            print(f"✅ 异常数量匹配: {expected_anomaly_count}")
        else:
            print(f"❌ 异常数量不匹配，期望: {expected_anomaly_count}")
            checks_passed = False
    
    return checks_passed

def main():
    base_dir = 'd:/code/TraeProjects/1014'
    output_dir = os.path.join(base_dir, 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    all_passed = True
    results = []
    
    # 1. 测试入口帮助
    print("\n" + "="*60)
    print("测试1: 入口帮助命令")
    print("="*60)
    for cmd in [
        "python main.py --help",
        "python main.py plan --help",
        "python main.py check --help",
        "python main.py cost --help",
        "python main.py report --help",
    ]:
        success, _, _ = run_cmd(cmd, cwd=base_dir)
        results.append((cmd, success))
        all_passed = all_passed and success
    
    # 2. 测试 --demurrage-risk medium,high 单方案保存
    print("\n" + "="*60)
    print("测试2: --demurrage-risk medium,high 单方案保存")
    print("="*60)
    cmd = "python main.py --ports sample_data/ports.csv --ships sample_data/ships.csv --cargos sample_data/cargos.csv --routes sample_data/routes.csv plan --strategy lowest_cost --demurrage-risk medium,high --save output/plan_medium_high.json"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    if success:
        # 检查终端输出
        all_passed = check_output_for_metrics(stdout, 
            expected_voyage_count=13, 
            expected_total_cost="¥22,802,833.33",
            expected_anomaly_count=69) and all_passed
        
        # 检查保存文件
        all_passed = check_plan_file(
            os.path.join(base_dir, 'output/plan_medium_high.json'),
            expected_voyage_count=13,
            expected_filters={'demurrage_risk': ['medium', 'high'], 'date_type': 'departure'}
        ) and all_passed
    
    # 3. 测试从计划文件读取 plan
    print("\n" + "="*60)
    print("测试3: 从计划文件读取 plan")
    print("="*60)
    cmd = "python main.py --plan-file output/plan_medium_high.json plan"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    if success:
        all_passed = check_output_for_metrics(stdout,
            expected_voyage_count=13,
            expected_total_cost="¥22,802,833.33",
            expected_anomaly_count=69) and all_passed
    
    # 4. 测试从计划文件读取 check
    print("\n" + "="*60)
    print("测试4: 从计划文件读取 check")
    print("="*60)
    cmd = "python main.py --plan-file output/plan_medium_high.json check"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    # 5. 测试从计划文件读取 cost
    print("\n" + "="*60)
    print("测试5: 从计划文件读取 cost")
    print("="*60)
    cmd = "python main.py --plan-file output/plan_medium_high.json cost"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    if success:
        all_passed = check_output_for_metrics(stdout,
            expected_voyage_count=13,
            expected_total_cost="¥22,802,833.33") and all_passed
    
    # 6. 测试 --demurrage-risk high 单方案保存
    print("\n" + "="*60)
    print("测试6: --demurrage-risk high 单方案保存")
    print("="*60)
    cmd = "python main.py --ports sample_data/ports.csv --ships sample_data/ships.csv --cargos sample_data/cargos.csv --routes sample_data/routes.csv plan --strategy lowest_cost --demurrage-risk high --save output/plan_high.json"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    if success:
        all_passed = check_output_for_metrics(stdout,
            expected_voyage_count=6,
            expected_total_cost="¥17,275,125.00",
            expected_anomaly_count=36) and all_passed
        
        all_passed = check_plan_file(
            os.path.join(base_dir, 'output/plan_high.json'),
            expected_voyage_count=6,
            expected_filters={'demurrage_risk': ['high'], 'date_type': 'departure'}
        ) and all_passed
    
    # 7. 测试从 high 计划文件读取
    print("\n" + "="*60)
    print("测试7: 从 high 计划文件读取 plan")
    print("="*60)
    cmd = "python main.py --plan-file output/plan_high.json plan"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    if success:
        all_passed = check_output_for_metrics(stdout,
            expected_voyage_count=6,
            expected_total_cost="¥17,275,125.00",
            expected_anomaly_count=36) and all_passed
    
    # 8. 测试多方案保存
    print("\n" + "="*60)
    print("测试8: 多方案保存 (--all-strategies)")
    print("="*60)
    cmd = "python main.py --ports sample_data/ports.csv --ships sample_data/ships.csv --cargos sample_data/cargos.csv --routes sample_data/routes.csv plan --all-strategies --save output/multi_test.json"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    if success:
        all_passed = check_multi_plan_file(
            os.path.join(base_dir, 'output/multi_test.json'),
            expected_scenario_count=4
        ) and all_passed
    
    # 9. 测试多方案 report compare
    print("\n" + "="*60)
    print("测试9: 多方案 report compare")
    print("="*60)
    cmd = "python main.py --plan-file output/multi_test.json report --type compare --compare-all"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    if success:
        # 检查对比表中没有重复方案
        scenario_ids = ['S01-lowest_cost', 'S02-fastest_arrival', 'S03-priority_first', 'S04-low_demurrage']
        for sid in scenario_ids:
            count = stdout.count(sid.split('-')[0])  # 只统计 S01, S02 等前缀
            print(f"  {sid.split('-')[0]} 出现次数: {count}")
            if count != 1:
                print(f"❌ {sid} 出现 {count} 次，期望1次")
                all_passed = False
    
    # 10. 测试多方案日期筛选 check
    print("\n" + "="*60)
    print("测试10: 多方案日期筛选 check")
    print("="*60)
    cmd = "python main.py --plan-file output/multi_test.json check --scenario S04-low_demurrage --start-date 2026-06-15 --end-date 2026-06-30"
    success, stdout, _ = run_cmd(cmd, cwd=base_dir)
    results.append((cmd, success))
    all_passed = all_passed and success
    
    if success:
        all_passed = check_output_for_metrics(stdout,
            expected_voyage_count=10,
            expected_anomaly_count=51) and all_passed
    
    # 11. 测试无效值提示
    print("\n" + "="*60)
    print("测试11: --demurrage-risk 无效值提示")
    print("="*60)
    cmd = "python main.py --ports sample_data/ports.csv --ships sample_data/ships.csv --cargos sample_data/cargos.csv --routes sample_data/routes.csv plan --demurrage-risk invalid,test"
    success, stdout, stderr = run_cmd(cmd, cwd=base_dir)
    # 这个命令应该失败（退出码1），但要有友好提示
    if not success and ("无效的滞期风险值" in stdout or "无效的滞期风险值" in stderr):
        print("✅ 无效值友好提示正常")
        results.append((cmd, True))
    else:
        print(f"❌ 无效值处理不正确，退出码: {0 if success else 1}")
        results.append((cmd, False))
        all_passed = False
    
    # 总结
    print("\n" + "="*60)
    print("回归测试总结")
    print("="*60)
    passed = sum(1 for _, s in results if s)
    total = len(results)
    print(f"通过: {passed}/{total}")
    
    for cmd, success in results:
        status = "✅" if success else "❌"
        short_cmd = cmd if len(cmd) < 80 else cmd[:77] + "..."
        print(f"{status} {short_cmd}")
    
    if all_passed:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
