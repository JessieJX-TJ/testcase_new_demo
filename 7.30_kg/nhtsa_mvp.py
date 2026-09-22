#!/usr/bin/env python3
"""NHTSA MVP — fetch safety ratings, recalls, complaints and generate test case candidates."""

import csv
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("请先安装 requests: pip install requests")

try:
    import pandas as pd
except ImportError:
    sys.exit("请先安装 pandas: pip install pandas")


# ---------------------------------------------------------------------------
# 1. 输入车型列表
# ---------------------------------------------------------------------------
VEHICLES = [
    # ====== 纯电 EV ======
    {"make": "Tesla", "model": "Model 3", "year": 2022},
    {"make": "Tesla", "model": "Model Y", "year": 2022},
    {"make": "Ford", "model": "Mustang Mach-E", "year": 2022},
    {"make": "Hyundai", "model": "Ioniq 5", "year": 2022},
    {"make": "Kia", "model": "EV6", "year": 2022},
    {"make": "Volkswagen", "model": "ID.4", "year": 2022},
    {"make": "Porsche", "model": "Taycan", "year": 2022},
    {"make": "Rivian", "model": "R1T", "year": 2022},
    {"make": "Lucid", "model": "Air", "year": 2022},
    # ====== 燃油 / 混动 ======
    {"make": "Toyota", "model": "RAV4", "year": 2022},
    {"make": "Honda", "model": "CR-V", "year": 2022},
    {"make": "Subaru", "model": "Outback", "year": 2022},
    {"make": "Volkswagen", "model": "Tiguan", "year": 2022},
    {"make": "Hyundai", "model": "Tucson", "year": 2022},
]

BASE_URL = "https://api.nhtsa.gov"
DATA_DIR = "data"
TIMEOUT = 30
DELAY = 0.3  # 礼貌性延迟，避免打爆 API


# ---------------------------------------------------------------------------
# 2. 工具函数
# ---------------------------------------------------------------------------
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_get(url: str) -> dict | None:
    """带超时和异常保护的 GET 请求，失败返回 None。"""
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"  [WARN] 请求失败: {url}\n         {exc}")
        return None


def vehicle_key(make: str, model: str, year: int) -> str:
    """生成稳定的 vehicle_key。"""
    raw = f"{make}|{model}|{year}".lower().replace(" ", "_")
    return raw


# ---------------------------------------------------------------------------
# 3. 风险场景规则
# ---------------------------------------------------------------------------
# 格式: (keywords, scenario, component_priority)
# component_priority: 如果该关键词出现在 component 字段中，优先匹配（不分大小写）
COMPONENT_PRIORITY_RULES = [
    # ---- 制动 ----
    (["BRAKE", "SERVICE BRAKES", "PARKING BRAKE", "BRAKING"],
     "braking_failure_or_abnormal_braking"),
    # ---- 转向 ----
    (["STEERING"],
     "steering_failure_or_loss_of_control"),
    # ---- 气囊 ----
    (["AIR BAG", "AIRBAG", "AIR BAGS"],
     "airbag_problem"),
    # ---- 电气 / 电池 ----
    (["ELECTRICAL SYSTEM", "BATTERY", "HIGH VOLTAGE", "HV BATTERY",
      "PROPULSION SYSTEM", "ELECTRIC POWERTRAIN", "CHARGING"],
     "electrical_or_battery_failure"),
    # ---- ADAS ----
    (["FORWARD COLLISION AVOIDANCE", "AEB", "ADAS", "LANE DEPARTURE",
      "LANE KEEPING", "AUTONOMOUS", "SELF DRIVING", "AUTOPILOT",
      "ADAPTIVE CRUISE", "BLIND SPOT", "PARKING ASSIST", "TRAFFIC AWARE"],
     "adas_malfunction"),
    # ---- 火 ----
    (["FIRE", "BURN", "SMOKE", "THERMAL", "OVERHEAT"],
     "vehicle_fire_risk"),
    # ---- 安全带 / 约束 ----
    (["SEAT BELT", "SEATBELT", "RESTRAINT", "SEAT BELTS", "BUCKLE",
      "PRETENSIONER", "OCCUPANT PROTECTION"],
     "seatbelt_or_restraint_issue"),
    # ---- 能见度 / 灯光 / 雨刮 ----
    (["VISIBILITY", "WIPER", "WINDSHIELD", "LIGHTING", "DEFROST",
      "HEADLIGHT", "TAILLIGHT", "TURN SIGNAL", "REARVIEW", "GLASS",
      "WINDSHIELD/WIPER"],
     "visibility_or_lighting_issue"),
    # ---- 悬挂 / 车轮 / 轮胎 ----
    (["SUSPENSION", "WHEEL", "TIRE", "TYRE", "WHEELS", "TIRES",
      "HUB", "AXLE", "LINKAGE"],
     "suspension_or_wheel_issue"),
    # ---- 软件 / 显示 ----
    (["SOFTWARE", "DISPLAY", "INFOTAINMENT", "SCREEN", "FIRMWARE",
      "CPU", "TOUCHSCREEN", "INSTRUMENT CLUSTER", "NAVIGATION"],
     "software_or_display_failure"),
    # ---- 门锁 / 闩锁 ----
    (["LATCH", "LOCK", "DOOR LATCH", "DOOR LOCK", "TRUNK LID",
      "DOORS", "LATCHES", "LOCKS", "CLOSURE"],
     "door_lock_or_latch_failure"),
    # ---- 动力总成 / 驱动单元 ----
    (["POWER TRAIN", "POWERTRAIN", "DRIVE UNIT", "TRANSMISSION",
      "ENGINE", "MOTOR", "DRIVELINE", "GEAR"],
     "powertrain_or_drive_unit_failure"),
    # ---- 熄火 / 动力丢失 ----
    (["STALL", "LOSS OF POWER", "PROPULSION LOSS", "SHUT DOWN",
      "SUDDEN POWER LOSS"],
     "vehicle_stall_or_loss_of_power"),
    # ---- 意外加速 ----
    (["UNINTENDED ACCELERATION", "SUDDEN ACCELERATION",
      "GHOST ACCELERATION", "UNEXPECTED ACCELERATION"],
     "unexpected_acceleration"),
    # ---- 摄像头 / 传感器 ----
    (["CAMERA", "SENSOR", "ULTRASONIC", "RADAR", "LIDAR"],
     "camera_or_sensor_failure"),
    # ---- 车身结构 ----
    (["STRUCTURE", "FRAME", "BODY", "CORROSION", "RUST", "PANEL",
      "ROOF", "TRUNK LID"],
     "body_structure_issue"),
    # ---- 充电 ----
    (["CHARGING", "CHARGE PORT", "CHARGER", "CHARGE CABLE",
      "ONBOARD CHARGER"],
     "charging_failure"),
]

# 摘要关键词规则（只在 component 未匹配时使用）
SUMMARY_KEYWORD_RULES = [
    (["BRAKE", "BRAKING"], "braking_failure_or_abnormal_braking"),
    (["STEERING"], "steering_failure_or_loss_of_control"),
    (["AIR BAG", "AIRBAG", "AIRBAGS"], "airbag_problem"),
    (["BATTERY", "ELECTRICAL", "HIGH VOLTAGE"], "electrical_or_battery_failure"),
    (["AEB", "ADAS", "FORWARD COLLISION", "LANE DEPARTURE", "LANE KEEP",
      "AUTOPILOT", "SELF DRIVING", "FULL SELF", "BLIND SPOT"],
     "adas_malfunction"),
    (["FIRE", "BURN", "SMOKE", "FLAME", "THERMAL RUNAWAY", "OVERHEAT"],
     "vehicle_fire_risk"),
    (["SEAT BELT", "SEATBELT", "RESTRAINT", "BUCKLE", "PRETENSIONER"],
     "seatbelt_or_restraint_issue"),
    (["VISIBILITY", "WIPER", "WINDSHIELD", "DEFROST", "HEADLIGHT",
      "TAILLIGHT", "LIGHTING"],
     "visibility_or_lighting_issue"),
    (["SUSPENSION", "WHEEL", "TIRE", "TYRE", "CONTROL ARM", "BUSHING"],
     "suspension_or_wheel_issue"),
    (["SOFTWARE", "DISPLAY", "INFOTAINMENT", "SCREEN", "FIRMWARE",
      "TOUCHSCREEN", "INSTRUMENT PANEL"],
     "software_or_display_failure"),
    (["LATCH", "LOCK", "DOOR", "TRUNK", "HOOD"],
     "door_lock_or_latch_failure"),
    (["POWER TRAIN", "POWERTRAIN", "DRIVE UNIT", "TRANSMISSION", "ENGINE",
      "MOTOR", "DRIVELINE", "PROPULSION"],
     "powertrain_or_drive_unit_failure"),
    (["STALL", "LOSS OF POWER", "SHUT DOWN", "PROPULSION LOSS",
      "LOST POWER", "CAR STOPPED"],
     "vehicle_stall_or_loss_of_power"),
    (["UNINTENDED ACCELERATION", "SUDDEN ACCELERATION",
      "UNEXPECTED ACCELERATION", "SURGED FORWARD", "SHOT FORWARD"],
     "unexpected_acceleration"),
    (["CAMERA", "SENSOR", "ULTRASONIC", "RADAR", "LIDAR"],
     "camera_or_sensor_failure"),
    (["STRUCTURE", "FRAME", "CORROSION", "RUST", "ROOF", "BODY PANEL"],
     "body_structure_issue"),
    (["CHARGING", "CHARGE PORT", "CHARGER", "ONBOARD CHARGER",
      "CHARGE CABLE", "PLUG"],
     "charging_failure"),
]

TEST_TEMPLATES = {
    "braking_failure_or_abnormal_braking": (
        "验证车辆是否存在制动失效、异常制动或制动性能下降问题。",
        "车辆制动系统应稳定响应，不应出现制动失效或异常制动。",
    ),
    "steering_failure_or_loss_of_control": (
        "验证车辆是否存在转向失效、转向助力异常或失控风险。",
        "车辆应保持稳定转向响应，不应出现转向卡滞、助力丢失或方向失控。",
    ),
    "adas_malfunction": (
        "验证车辆 ADAS 功能是否存在误触发、漏触发或异常接管。",
        "ADAS 应在真实风险场景下响应，在无风险场景下不应误触发。",
    ),
    "electrical_or_battery_failure": (
        "验证车辆电气系统或电池系统是否存在异常断电、故障告警或热失控风险。",
        "电气和电池系统应稳定工作，不应出现异常断电、热失控或关键功能失效。",
    ),
    "airbag_problem": (
        "验证安全气囊系统是否存在未按预期展开或误展开问题。",
        "安全气囊应在满足触发条件时正确展开，在非碰撞场景下不应误展开。",
    ),
    "vehicle_fire_risk": (
        "验证车辆在充电、行驶、碰撞后或静置状态下是否存在异常发热、冒烟或起火风险。",
        "车辆不应出现异常热失控、冒烟或明火。",
    ),
    "seatbelt_or_restraint_issue": (
        "验证车辆座椅安全带及约束系统是否存在失效、误锁止或预警异常问题。",
        "安全带应在碰撞或急刹时正确锁止，不应出现无法锁止、误锁止或预警失效。",
    ),
    "visibility_or_lighting_issue": (
        "验证车辆能见度、灯光或雨刮系统是否存在失效或性能下降问题。",
        "雨刮、除霜、照明系统应在需要时正常工作，不应出现视野受限。",
    ),
    "suspension_or_wheel_issue": (
        "验证车辆悬挂系统、车轮或轮胎是否存在异常磨损、断裂或异响问题。",
        "悬挂和车轮系统应保持结构完整，不应出现断裂、脱落或异常磨损。",
    ),
    "software_or_display_failure": (
        "验证车辆软件系统或显示屏是否存在崩溃、黑屏、触控失灵或系统卡滞问题。",
        "软件和显示屏应稳定运行，不应出现黑屏、系统崩溃或功能异常。",
    ),
    "door_lock_or_latch_failure": (
        "验证车门锁、闩锁或行李箱锁是否存在无法锁止、意外弹开或卡死问题。",
        "车门和锁系统应可靠锁止，不应出现行驶中弹开或无法关闭。",
    ),
    "powertrain_or_drive_unit_failure": (
        "验证车辆动力总成或驱动单元是否存在异响、抖动、过热或功率衰减问题。",
        "动力总成应稳定输出，不应出现异常噪音、抖动或功率输出下降。",
    ),
    "vehicle_stall_or_loss_of_power": (
        "验证车辆在行驶中是否存在突然熄火、动力中断或无法启动问题。",
        "车辆在行驶中应保持稳定动力输出，不应出现意外熄火或动力中断。",
    ),
    "unexpected_acceleration": (
        "验证车辆是否存在非预期加速或突然自动加速问题。",
        "车辆在低速、泊车场景下不应出现非预期的自行加速。",
    ),
    "camera_or_sensor_failure": (
        "验证车辆摄像头、雷达或超声波传感器是否存在误报、盲区或校准失效问题。",
        "感知传感器应准确、可靠地检测周围环境，不应出现误报或检测失效。",
    ),
    "body_structure_issue": (
        "验证车辆车身结构是否存在开裂、腐蚀或连接松动问题。",
        "车身结构应保持完整，不应出现异常腐蚀、开裂或连接失效。",
    ),
    "charging_failure": (
        "验证车辆充电系统是否存在无法充电、充电中断、过热或接口故障问题。",
        "充电系统应稳定连接并正常充电，不应出现充电中断或过热。",
    ),
    "unknown_vehicle_risk": (
        "基于公开投诉或召回描述识别潜在车辆安全风险，并设计进一步人工复核测试。",
        "车辆功能应符合安全预期，不应出现公开投诉或召回描述中的异常现象。",
    ),
}


def classify_risk(component: str, summary: str) -> str:
    """优先按 component 字段匹配，再按 summary 匹配。"""
    comp_upper = component.upper().strip()
    sum_upper = summary.upper().strip()

    # 第一轮：仅用 component 匹配
    for keywords, scenario in COMPONENT_PRIORITY_RULES:
        for kw in keywords:
            if kw in comp_upper:
                return scenario

    # 第二轮：用 component + summary 匹配
    for keywords, scenario in SUMMARY_KEYWORD_RULES:
        for kw in keywords:
            if kw in comp_upper or kw in sum_upper:
                return scenario

    return "unknown_vehicle_risk"


# ---------------------------------------------------------------------------
# 4. 数据容器
# ---------------------------------------------------------------------------
ratings_rows: list[dict] = []
recalls_rows: list[dict] = []
complaints_rows: list[dict] = []
test_cases: list[dict] = []
raw_results: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------
def main():
    ensure_dir(DATA_DIR)

    vehicles_out: list[dict] = []

    for i, v in enumerate(VEHICLES, 1):
        make = v["make"]
        model = v["model"]
        year = v["year"]
        key = vehicle_key(make, model, year)

        print(f"\n{'='*60}")
        print(f"[{i}/{len(VEHICLES)}] {make} {model} ({year})  key={key}")
        print("=" * 60)

        vehicles_out.append({"vehicle_key": key, "make": make, "model": model, "year": year})
        raw_results[key] = {}

        # ---- Safety Ratings ----
        rating_url = (
            f"{BASE_URL}/SafetyRatings/modelyear/{year}/make/{make}/model/{model}"
        )
        print(f"  Rating URL: {rating_url}")
        data = safe_get(rating_url)
        raw_results[key]["ratings"] = data

        vehicle_id = None
        if data and data.get("Results"):
            results_list = data["Results"]
            if isinstance(results_list, list) and results_list:
                vehicle_id = results_list[0].get("VehicleId")

        if vehicle_id:
            detail_url = f"{BASE_URL}/SafetyRatings/VehicleId/{vehicle_id}"
            print(f"  Detail URL: {detail_url}")
            detail = safe_get(detail_url)
            raw_results[key]["ratings_detail"] = detail
            if detail and detail.get("Results"):
                d = detail["Results"]
                if isinstance(d, list) and d:
                    d0 = d[0]
                    ratings_rows.append(
                        {
                            "vehicle_key": key,
                            "vehicle_id": vehicle_id,
                            "overall_rating": d0.get("OverallRating", d0.get("OverallFrontCrashRating", "")),
                            "frontal_crash_rating": d0.get("OverallFrontCrashRating", ""),
                            "side_crash_rating": d0.get("OverallSideCrashRating", ""),
                            "rollover_rating": d0.get("RolloverRating", ""),
                        }
                    )
                    print(f"  -> Rating 已获取")
            time.sleep(DELAY)
        else:
            print("  -> 未找到 VehicleId，跳过评级详情")

        # ---- Recalls ----
        recall_url = (
            f"{BASE_URL}/recalls/recallsByVehicle"
            f"?make={make}&model={model}&modelYear={year}"
        )
        print(f"  Recall URL: {recall_url}")
        rec = safe_get(recall_url)
        raw_results[key]["recalls"] = rec
        recall_count = 0
        if rec and rec.get("results"):
            for r in rec["results"]:
                component = r.get("Component", "")
                summary = r.get("Summary", "")
                recalls_rows.append(
                    {
                        "vehicle_key": key,
                        "campaign_number": r.get("NHTSACampaignNumber", ""),
                        "component": component,
                        "summary": summary,
                        "consequence": r.get("Consequence", ""),
                        "remedy": r.get("Remedy", ""),
                    }
                )
                scenario = classify_risk(component, summary)
                test_cases.append(
                    {
                        "vehicle_key": key,
                        "source_type": "recall",
                        "source_id": r.get("NHTSACampaignNumber", ""),
                        "component": component,
                        "risk_scenario": scenario,
                        "test_objective": TEST_TEMPLATES[scenario][0],
                        "expected_result": TEST_TEMPLATES[scenario][1],
                        "evidence": summary,
                    }
                )
                recall_count += 1
        print(f"  -> 获取到 {recall_count} 条召回")
        time.sleep(DELAY)

        # ---- Complaints ----
        comp_url = (
            f"{BASE_URL}/complaints/complaintsByVehicle"
            f"?make={make}&model={model}&modelYear={year}"
        )
        print(f"  Complaint URL: {comp_url}")
        comp = safe_get(comp_url)
        raw_results[key]["complaints"] = comp
        comp_count = 0
        if comp and comp.get("results"):
            for c in comp["results"]:
                component = c.get("components", "")
                summary = c.get("summary", "")
                complaints_rows.append(
                    {
                        "vehicle_key": key,
                        "odi_number": c.get("odiNumber", ""),
                        "component": component,
                        "summary": summary,
                        "crash": str(c.get("crash", "")),
                        "fire": str(c.get("fire", "")),
                        "injury": str(c.get("numberOfInjuries", "")),
                        "date_received": c.get("dateComplaintFiled", ""),
                    }
                )
                scenario = classify_risk(component, summary)
                test_cases.append(
                    {
                        "vehicle_key": key,
                        "source_type": "complaint",
                        "source_id": c.get("odiNumber", ""),
                        "component": component,
                        "risk_scenario": scenario,
                        "test_objective": TEST_TEMPLATES[scenario][0],
                        "expected_result": TEST_TEMPLATES[scenario][1],
                        "evidence": summary,
                    }
                )
                comp_count += 1
        print(f"  -> 获取到 {comp_count} 条投诉")
        time.sleep(DELAY)

    # -------------------------------------------------------------------
    # 6. 输出 CSV
    # -------------------------------------------------------------------
    print("\n\n写入 CSV 文件...")

    _write_csv(f"{DATA_DIR}/vehicles.csv",
               ["vehicle_key", "make", "model", "year"], vehicles_out)

    _write_csv(f"{DATA_DIR}/ratings.csv",
               ["vehicle_key", "vehicle_id", "overall_rating",
                "frontal_crash_rating", "side_crash_rating", "rollover_rating"],
               ratings_rows)

    _write_csv(f"{DATA_DIR}/recalls.csv",
               ["vehicle_key", "campaign_number", "component",
                "summary", "consequence", "remedy"],
               recalls_rows)

    _write_csv(f"{DATA_DIR}/complaints.csv",
               ["vehicle_key", "odi_number", "component",
                "summary", "crash", "fire", "injury", "date_received"],
               complaints_rows)

    _write_csv(f"{DATA_DIR}/test_case_candidates.csv",
               ["vehicle_key", "source_type", "source_id",
                "component", "risk_scenario", "test_objective",
                "expected_result", "evidence"],
               test_cases)

    # 保存原始 JSON
    with open(f"{DATA_DIR}/raw_results.json", "w", encoding="utf-8") as f:
        json.dump(raw_results, f, ensure_ascii=False, indent=2)

    # -------------------------------------------------------------------
    # 7. 统计
    # -------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("统计信息")
    print("=" * 60)
    print(f"  车型数量:            {len(vehicles_out)}")
    print(f"  rating 数量:         {len(ratings_rows)}")
    print(f"  recall 数量:         {len(recalls_rows)}")
    print(f"  complaint 数量:      {len(complaints_rows)}")
    print(f"  test case candidate 数量: {len(test_cases)}")
    print(f"\n所有输出文件在 {DATA_DIR}/ 目录下。")
    print("完成！")


def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    """写 CSV 文件，自动处理编码和空行。"""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {path}  ({len(rows)} 行)")


if __name__ == "__main__":
    main()
