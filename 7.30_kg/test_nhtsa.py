#!/usr/bin/env python3
"""离线测试：NHTSA 车辆安全风险工作台
用法：
    python test_nhtsa.py                    # 完整演示：规则 + 统计 + Top 10 + 关系分布
    python test_nhtsa.py --top 10           # Top 10 高优先级风险
    python test_nhtsa.py --vehicle "toyota|rav4|2022"  # 查询车型
    python test_nhtsa.py --component BRAKE  # 按部件查询
    python test_nhtsa.py --rules            # 展示风险分类规则
    python test_nhtsa.py --fetch            # 从 NHTSA API 重新采集数据（需要网络）
    python test_nhtsa.py --all              # 全部：采集 + 评分 + 测试用例生成
"""
import sys, os, argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pandas as pd

DATA = ROOT / "nhtsa_data"

# ── NHTSA 流水线架构 ──
# nhtsa_mvp.py:         ① NHTSA API 采集 (SafetyRatings/Recalls/Complaints)
# build_kg_and_tests.py: ② 评分 + KG 三元组构建 + 测试用例生成 + 报告

# ── 采集覆盖的 14 款车型 ──
VEHICLES_DEMO = [
    ("Tesla",     "Model 3",        2022, "EV"),
    ("Tesla",     "Model Y",        2022, "EV"),
    ("Ford",      "Mustang Mach-E", 2022, "EV"),
    ("Hyundai",   "Ioniq 5",        2022, "EV"),
    ("Kia",       "EV6",            2022, "EV"),
    ("Volkswagen","ID.4",           2022, "EV"),
    ("Porsche",   "Taycan",         2022, "EV"),
    ("Rivian",    "R1T",            2022, "EV"),
    ("Lucid",     "Air",            2022, "EV"),
    ("Toyota",    "RAV4",           2022, "ICE"),
    ("Honda",     "CR-V",           2022, "ICE"),
    ("Subaru",    "Outback",        2022, "ICE"),
    ("Volkswagen","Tiguan",         2022, "ICE"),
    ("Hyundai",   "Tucson",         2022, "ICE"),
]

# ── 17 种风险场景分类（来自 nhtsa_mvp.py）──
RISK_SCENARIOS = {
    "braking_failure_or_abnormal_braking":  "制动失效/异常制动",
    "steering_failure_or_loss_of_control":  "转向失效/失控",
    "adas_malfunction":                     "ADAS 故障/误触发",
    "electrical_or_battery_failure":        "电气/电池系统故障",
    "airbag_problem":                       "安全气囊问题",
    "vehicle_fire_risk":                    "车辆起火风险",
    "seatbelt_or_restraint_issue":          "安全带/约束系统问题",
    "visibility_or_lighting_issue":         "能见度/灯光/雨刮问题",
    "suspension_or_wheel_issue":            "悬挂/车轮/轮胎问题",
    "software_or_display_failure":          "软件/显示屏故障",
    "door_lock_or_latch_failure":           "门锁/闩锁故障",
    "powertrain_or_drive_unit_failure":     "动力总成/驱动单元故障",
    "vehicle_stall_or_loss_of_power":       "熄火/动力丢失",
    "unexpected_acceleration":              "非预期加速",
    "camera_or_sensor_failure":             "摄像头/传感器故障",
    "body_structure_issue":                 "车身结构问题",
    "charging_failure":                     "充电系统故障",
}

# ── 6 种 KG 关系类型 ──
KG_RELATIONS = [
    ("HAS_RISK_SCENARIO",  "车辆 → 存在风险场景"),
    ("AFFECTS_COMPONENT",  "风险场景 → 影响部件"),
    ("GENERATES_TEST_CASE","风险场景 → 生成测试用例"),
    ("HAS_RECALL",         "车辆 → 有召回记录"),
    ("HAS_COMPLAINT",      "车辆 → 有投诉记录"),
    ("INDICATES_RISK",     "召回/投诉 → 指向风险"),
]


def load_csv(name):
    p = DATA / name
    return pd.read_csv(p) if p.exists() else None


def print_rules():
    """展示 NHTSA 流水线的核心规则。"""
    print(f"\n{'='*60}")
    print(f"  NHTSA 风险分类规则（来自 nhtsa_mvp.py）")
    print(f"{'='*60}")
    print(f"\n  部件优先级匹配规则（17 组）：")
    print(f"  {'部件关键词':<40s} {'风险场景'}")
    print(f"  {'-'*40} {'-'*35}")
    priority_pairs = [
        ("BRAKE/SERVICE BRAKES/PARKING BRAKE", "braking_failure_or_abnormal_braking"),
        ("STEERING",                            "steering_failure_or_loss_of_control"),
        ("AIR BAG/AIRBAG",                      "airbag_problem"),
        ("ELECTRICAL SYSTEM/BATTERY/HV",        "electrical_or_battery_failure"),
        ("AEB/ADAS/LANE DEPARTURE/AUTOPILOT",   "adas_malfunction"),
        ("FIRE/BURN/SMOKE/THERMAL",             "vehicle_fire_risk"),
        ("SEAT BELT/SEATBELT/RESTRAINT",        "seatbelt_or_restraint_issue"),
        ("VISIBILITY/WIPER/HEADLIGHT",          "visibility_or_lighting_issue"),
        ("SUSPENSION/WHEEL/TIRE",               "suspension_or_wheel_issue"),
        ("SOFTWARE/DISPLAY/INFOTAINMENT",       "software_or_display_failure"),
        ("LATCH/LOCK/DOOR LATCH/DOORS",         "door_lock_or_latch_failure"),
        ("POWER TRAIN/POWERTRAIN/TRANSMISSION", "powertrain_or_drive_unit_failure"),
        ("STALL/LOSS OF POWER/SHUT DOWN",       "vehicle_stall_or_loss_of_power"),
        ("UNINTENDED/SUDDEN ACCELERATION",      "unexpected_acceleration"),
        ("CAMERA/SENSOR/ULTRASONIC/RADAR/LIDAR","camera_or_sensor_failure"),
        ("STRUCTURE/FRAME/CORROSION/RUST",      "body_structure_issue"),
        ("CHARGING/CHARGE PORT/CHARGER",        "charging_failure"),
    ]
    for kw, scenario in priority_pairs:
        print(f"  {kw:<40s} {scenario}")

    print(f"\n  评分公式：")
    print(f"    frequency_score = log(1 + evidence_count) 归一化到 0-10")
    print(f"    severity_score  = risk_weight + crash*2 + fire*3 + injury*4 + recall*3")
    print(f"    priority_score  = 0.5 * frequency + 0.5 * severity")


def print_vehicles():
    print(f"\n{'='*60}")
    print(f"  数据采集覆盖车型（14 款）")
    print(f"{'='*60}")
    evs = [v for v in VEHICLES_DEMO if v[3] == "EV"]
    ices = [v for v in VEHICLES_DEMO if v[3] == "ICE"]
    print(f"\n  纯电 EV × {len(evs)}：")
    for make, model, year, _ in evs:
        print(f"    {make} {model} ({year})")
    print(f"\n  燃油/混动 × {len(ices)}：")
    for make, model, year, _ in ices:
        print(f"    {make} {model} ({year})")


def print_kg_relations():
    print(f"\n{'='*60}")
    print(f"  KG 关系类型（6 种）")
    print(f"{'='*60}")
    for rel, desc in KG_RELATIONS:
        print(f"  {rel:<25s} {desc}")


def main():
    parser = argparse.ArgumentParser(description="NHTSA 车辆安全风险工作台 — 离线测试")
    parser.add_argument("--top", type=int, default=0, help="显示 Top N 风险场景")
    parser.add_argument("--vehicle", help="查询车型（如 toyota|rav4|2022）")
    parser.add_argument("--component", help="按部件名称模糊查询（如 BRAKE, ADAS, BATTERY）")
    parser.add_argument("--rules", action="store_true", help="展示风险分类规则")
    parser.add_argument("--fetch", action="store_true", help="从 NHTSA API 重新采集数据")
    parser.add_argument("--all", action="store_true", help="完整流程：采集 + KG 构建 + 查询")
    parser.add_argument("--summary", action="store_true", help="仅显示汇总统计")
    args = parser.parse_args()

    no_specific = not any([args.top, args.vehicle, args.component, args.rules, args.fetch, args.all, args.summary])

    # ── 流水线架构 + 规则 + 车型 ──
    if no_specific or args.rules:
        print(f"\n{'='*60}")
        print(f"  NHTSA 车辆安全风险数据工作台 — 离线测试")
        print(f"{'='*60}")
        print(f"")
        print(f"  流水线架构：")
        print(f"    nhtsa_mvp.py           ① 从 NHTSA API 采集数据")
        print(f"      - SafetyRatings      安全评级")
        print(f"      - recallsByVehicle   召回记录")
        print(f"      - complaintsByVehicle 投诉记录")
        print(f"      → vehicles.csv / ratings.csv / recalls.csv / complaints.csv")
        print(f"")
        print(f"    build_kg_and_tests.py   ② 构建 KG + 测试用例")
        print(f"      - 非技术投诉过滤（排除质保/服务/商业类）")
        print(f"      - 部件细化（UNKNOWN → 反推具体分类）")
        print(f"      - 风险场景评分（frequency + severity → priority）")
        print(f"      - 知识图谱三元组（6 种关系类型）")
        print(f"      - 工程化测试用例（16 套行业标准模板）")
        print(f"      → risk_scenarios.csv / kg_triples.csv / test_cases.csv / demo_report.md")

    if no_specific or args.rules:
        print_rules()

    if no_specific:
        print_vehicles()
        print_kg_relations()

    # ── 数据采集 ──
    if args.fetch or args.all:
        print(f"\n{'='*60}")
        print(f"  Step 1: 从 NHTSA API 采集数据")
        print(f"{'='*60}")
        nhtsa_path = ROOT.parent / "nhtsa_mvp.py"
        if nhtsa_path.exists():
            print(f"  执行: python {nhtsa_path}")
            print(f"  [INFO] 请手动运行: cd .. && python nhtsa_mvp.py")
        else:
            print(f"  [INFO] nhtsa_mvp.py 在项目根目录，请 cd .. 后执行")

    if args.all:
        print(f"\n{'='*60}")
        print(f"  Step 2: 构建 KG + 测试用例 + 报告")
        print(f"{'='*60}")
        build_path = ROOT.parent / "build_kg_and_tests.py"
        if build_path.exists():
            print(f"  执行: python {build_path}")
            print(f"  [INFO] 请手动运行: cd .. && python build_kg_and_tests.py")
        else:
            print(f"  [INFO] build_kg_and_tests.py 在项目根目录，请 cd .. 后执行")

    # ── 数据统计 ──
    rs = load_csv("risk_scenarios.csv")
    kg = load_csv("kg_triples.csv")
    tc = load_csv("test_cases.csv")
    veh = load_csv("vehicles.csv")
    comp = load_csv("complaints.csv")
    rec = load_csv("recalls.csv")

    if rs is None:
        if args.fetch or args.all:
            print("\n[INFO] 数据尚未生成，请先运行 nhtsa_mvp.py 和 build_kg_and_tests.py")
        else:
            print("\n[WARN] NHTSA 数据文件未找到。请先运行: cd .. && python nhtsa_mvp.py && python build_kg_and_tests.py")
        return

    print(f"\n{'='*60}")
    print(f"  本地数据统计")
    print(f"{'='*60}")
    print(f"  车型覆盖:   {veh['vehicle_key'].nunique() if veh is not None else 'N/A'}")
    print(f"  风险场景:   {len(rs)} 条")
    print(f"  KG 三元组:  {len(kg) if kg is not None else 'N/A'} 条")
    print(f"  测试用例:   {len(tc) if tc is not None else 'N/A'} 条")
    print(f"  投诉记录:   {len(comp) if comp is not None else 'N/A':,} 条")
    print(f"  召回记录:   {len(rec) if rec is not None else 'N/A':,} 条")

    # ── 风险场景分布 ──
    if no_specific:
        print(f"\n  风险场景分布（Top 10）：")
        for scenario, cnt in rs["risk_scenario"].value_counts().head(10).items():
            label = RISK_SCENARIOS.get(scenario, scenario)
            bar = "#" * min(cnt // 5, 50) if cnt >= 5 else ""
            print(f"    {label:<30s} {cnt:>4d}  {bar}")

    # ── Top N ──
    if args.top > 0:
        print(f"\n  Top {args.top} 高优先级风险场景:")
        for i, (_, r) in enumerate(rs.head(args.top).iterrows(), 1):
            scenario_cn = RISK_SCENARIOS.get(r['risk_scenario'], r['risk_scenario'])
            print(f"  {i:2d}. [{r['priority_score']:.1f}] {scenario_cn:<30s} | {r['vehicle_key'][:28]} | {r.get('refined_component', r.get('component',''))}")

    # ── 车型查询 ──
    if args.vehicle:
        sub = rs[rs["vehicle_key"] == args.vehicle]
        if sub.empty:
            print(f"\n  未找到车型: {args.vehicle}")
            print(f"  可用车型 (前 10):")
            for v in sorted(rs["vehicle_key"].unique())[:10]:
                print(f"    {v}")
        else:
            print(f"\n  车型: {args.vehicle}")
            print(f"  场景数: {len(sub)} | 总证据: {sub['evidence_count'].sum()}")
            for _, r in sub.head(5).iterrows():
                scenario_cn = RISK_SCENARIOS.get(r['risk_scenario'], r['risk_scenario'])
                print(f"    [{r['priority_score']:.1f}] {scenario_cn} | {r.get('refined_component','')}")

    # ── 部件查询 ──
    if args.component:
        comp_upper = args.component.upper()
        sub = rs[rs["refined_component"].str.upper().str.contains(comp_upper, na=False)]
        if sub.empty:
            print(f"\n  未找到部件: {args.component}")
            print(f"  可用部件 Top 15:")
            for c, cnt in rs["refined_component"].value_counts().head(15).items():
                print(f"    {c} ({cnt})")
        else:
            print(f"\n  部件: {args.component} → {len(sub)} 个风险场景, {sub['evidence_count'].sum()} 条证据")
            for vk, grp in sub.groupby("vehicle_key"):
                print(f"    {vk}: {len(grp)} 场景")
            for _, r in sub.head(5).iterrows():
                scenario_cn = RISK_SCENARIOS.get(r['risk_scenario'], r['risk_scenario'])
                print(f"    [{r['priority_score']:.1f}] {scenario_cn} | {r.get('refined_component','')} | {r['vehicle_key']}")

    # ── 关系分布 ──
    if kg is not None and (no_specific or args.summary):
        print(f"\n  KG 关系类型分布:")
        for rel, cnt in kg["relation"].value_counts().items():
            bar = "#" * min(cnt // 100, 40)
            print(f"    {rel:25s} {cnt:>6d}  {bar}")

    # ── 测试用例预览 ──
    if args.summary and tc is not None:
        print(f"\n  测试用例预览 (前 3 条):")
        for i, (_, row) in enumerate(tc.head(3).iterrows(), 1):
            print(f"  {i}. [{row['priority_score']}] {row['test_case_title']}")
            print(f"     车型: {row['vehicle_key']} | 风险: {row['risk_scenario']}")
            print(f"     环境: {row['test_environment']}")

    print()


if __name__ == "__main__":
    main()
