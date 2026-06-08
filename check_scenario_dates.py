import json
with open('output/multi_test.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 找到 S04-low_demurrage 方案
for s in data['scenarios']:
    if s['scenario_id'] == 'S04-low_demurrage':
        print(f"方案: {s['scenario_id']}")
        print(f"航次数量: {len(s['plans'])}")
        print("\n航次离港时间:")
        for p in s['plans']:
            vid = p['voyage']['voyage_id']
            dep = p['voyage']['departure_time']
            risk = p['voyage']['demurrage_risk']
            print(f"  {vid}: {dep} (风险: {risk})")
        
        # 测试日期筛选
        print("\n日期范围: 2026-06-15 ~ 2026-06-30")
        from datetime import datetime
        start = datetime(2026, 6, 15)
        end = datetime(2026, 6, 30)
        
        filtered = []
        for p in s['plans']:
            dep_time = datetime.fromisoformat(p['voyage']['departure_time'])
            if start <= dep_time <= end:
                filtered.append(p['voyage']['voyage_id'])
        
        print(f"筛选后的航次 ({len(filtered)}个): {sorted(filtered)}")
        break
