#!/usr/bin/env python3
"""
从 NHTSA 召回/投诉数据 → 知识图谱三元组 → 工程化测试用例 → 报告。
运行前提：先跑 nhtsa_mvp.py 生成 data/ 下的原始 CSV。
"""

import math
import os
import re
import sys
from datetime import datetime
from collections import Counter

try:
    import pandas as pd
    import numpy as np
except ImportError:
    sys.exit("pip install pandas numpy")

DATA_DIR = "data"

# ============================================================
# 1. 非技术投诉关键词（排除 FSD 权益、质保、服务类投诉）
# ============================================================
NON_TECH = [
    "TRANSFERABLE", "SUBSCRIPTION", "PURCHASE", "REFUND", "WARRANTY",
    "PRICE", "PACKAGE", "PROMISED", "SERVICE CENTER", "CUSTOMER SERVICE",
    "APPOINTMENT", "LEASE", "LOAN", "FINANC", "DELIVERY", "DEALER",
    "RESELL", "DEPOSIT", "ORDER FORM", "TRADE IN", "INSURANCE", "RENTAL",
    "LOANER", "SALES ", "MARKETING", "ADVERTIS", "REBATE", "INCENTIVE",
]

FAULT_KW = [
    "FAILURE", "MALFUNCTION", "WARNING", "CRASH", "COLLISION",
    "BRAKE", "STEERING", "FIRE", "INJURY", "DISABLED", "UNAVAILABLE",
    "STOPPED", "LOST POWER", "STUCK", "DANGEROUS", "UNSAFE",
    "SUDDEN", "UNEXPECTED", "DEFECTIVE", "FAULTY", "BROKEN",
    "FAILED", "SMOKE", "BURN", "OVERHEAT", "LOCKED", "DEPLOY",
    "NOISE", "VIBRATION", "LEAK", "CRACK", "BENT", "SHUT DOWN",
    "STALL", "ACCELERAT", "DECELERAT", "UNCONTROLL", "LOST CONTROL",
    "WON'T START", "DIED", "BLANK", "BLACK SCREEN",
    "AIRBAG", "SEAT BELT", "SUSPENSION", "WHEEL", "TIRE",
    "DOOR OPEN", "HOOD OPEN", "TRUNK OPEN", "LATCH", "WON'T MOVE",
]


def is_non_testable(summary: str) -> bool:
    s = str(summary).upper()
    return any(kw in s for kw in NON_TECH) and not any(kw in s for kw in FAULT_KW)


# ============================================================
# 2. 部件细化（UNKNOWN OR OTHER → 基于摘要反推）
# ============================================================
REFINEMENT_RULES = [
    (["STEERING WHEEL", "STEERING STUCK", "STEERING LOCK", "POWER STEERING",
      "HARD TO STEER", "STEERING RACK", "STEERING COLUMN", "ELECTRIC POWER STEERING",
      "EPS ", "TURN THE WHEEL", "CANNOT STEER", "CAN'T STEER"], "STEERING_CONTROL"),
    (["BRAKE PEDAL", "BRAKING", "BRAKES FAIL", "BRAKE FAIL", "SERVICE BRAKE",
      "UNABLE TO STOP", "WON'T STOP", "HARD TO STOP", "BRAKE BOOST",
      "REGENERATIVE BRAK", "ABS ", "ANTI-LOCK", "BRAKE SYSTEM"], "SERVICE_BRAKES"),
    (["AUTOPILOT", "FSD ", "FULL SELF DRIVING", "SELF DRIVING",
      "FORWARD COLLISION", "PHANTOM BRAK", "AEB ", "LANE KEEP",
      "LANE DEPARTURE", "BLIND SPOT", "ADAPTIVE CRUISE", "TRAFFIC AWARE",
      "AUTO STEER", "NAVIGATE ON AUTO", "SUMMON", "AUTO PARK",
      "COLLISION AVOIDANCE", "AUTOMATIC EMERGENCY"], "ADAS"),
    (["SCREEN ", "DISPLAY ", "TOUCHSCREEN", "BLACK SCREEN", "BLANK SCREEN",
      "INFOTAINMENT", "INSTRUMENT CLUSTER", "CENTER SCREEN", "TOUCH SCREEN",
      "SCREEN WENT", "DISPLAY WENT", "REBOOT", "FIRMWARE", "SOFTWARE UPDATE",
      "MCU ", "OVER THE AIR"], "DISPLAY_OR_SOFTWARE"),
    (["BATTERY", "HIGH VOLTAGE", "HV BATTERY", "12V BATTERY", "12 VOLT",
      "THERMAL RUNAWAY", "BMS ", "RANGE SUDDEN",
      "CHARGE PORT", "CHARGING", "CHARGER", "ONBOARD CHARGER",
      "SUPERCHARG", "DC FAST", "WON'T CHARGE", "CANNOT CHARGE"], "BATTERY_OR_CHARGING"),
    (["AIR BAG", "AIRBAG", "SRS ", "RESTRAINT SYSTEM", "SIDE CURTAIN",
      "PASSENGER AIR", "DRIVER AIR", "FRONTAL AIR", "SEAT BELT PRETENSION"], "AIRBAG_OR_RESTRAINT"),
    (["SEAT BELT", "SEATBELT", "BUCKLE", "PRETENSIONER", "RETRACTOR",
      "OCCUPANT PROTECTION", "SEAT BELTS", "RESTRAINT"], "SEAT_BELTS"),
    (["WHEEL ", "WHEELS ", "TIRE ", "TYRE ", "SUSPENSION", "AXLE",
      "CONTROL ARM", "BUSHING", "LINK ", "LOWER ARM", "UPPER ARM",
      "BALL JOINT", "TIRE ROD", "SHOCK ", "STRUT ", "SPRING",
      "ALIGNMENT", "WOBBL", "SHAKE ", "VIBRAT"], "SUSPENSION_OR_WHEEL"),
    (["LOST POWER", "SHUT DOWN", "STALLED", "STALL ", "PROPULSION LOSS",
      "SUDDEN POWER LOSS", "VEHICLE DIED", "CAR DIED", "WON'T START",
      "DRIVE UNIT", "MOTOR ", "POWERTRAIN", "TRANSMISSION", "GEAR",
      "DRIVELINE", "HALF SHAFT", "CV JOINT", "INVERTER", "DC-DC"], "POWERTRAIN_OR_ELECTRICAL"),
    (["CAMERA ", "SENSOR ", "ULTRASONIC", "RADAR ", "LIDAR",
      "VISIBILITY", "BLIND ", "DETECTION", "PARKING SENSOR",
      "REARVIEW", "SIDE CAMERA", "FRONT CAMERA", "BACKUP CAMERA"], "CAMERA_OR_SENSOR"),
    (["DOOR ", "LATCH", "LOCK ", "TRUNK ", "HOOD ", "HANDLE",
      "WINDOW ", "POWER WINDOW", "WON'T OPEN", "WON'T CLOSE",
      "STUCK OPEN", "STUCK CLOSE", "AUTO WINDOW"], "DOOR_LOCK_OR_LATCH"),
    (["WINDSHIELD", "WIPER", "DEFROST", "HEADLIGHT", "TAILLIGHT",
      "FOG LIGHT", "TURN SIGNAL", "HAZARD LIGHT", "LIGHTING",
      "GLASS ", "CRACK ", "CHIP ", "VISIBILITY"], "VISIBILITY_OR_LIGHTING"),
    (["ACCELERAT", "SURGED FORWARD", "SHOT FORWARD", "LURCH",
      "GHOST ACCELERAT", "UNINTENDED ACCEL", "SUDDEN ACCEL",
      "SPEED UP ON ITS OWN", "TOOK OFF"], "UNEXPECTED_ACCELERATION"),
    (["STRUCTURE", "FRAME", "CORROSION", "RUST", "BODY PANEL",
      "ROOF ", "PILLAR ", "CHASSIS", "SUBFRAME", "WELD",
      "PAINT ", "PEELING", "BUBBLING"], "BODY_STRUCTURE"),
    (["FIRE", "FLAME", "BURN", "SMOKE", "OVERHEAT", "THERMAL",
      "MELT", "SCORCH", "IGNIT", "COMBUST"], "FIRE_OR_THERMAL"),
    (["SEAT ", "SEATS ", "HEADREST", "ARMREST", "UPHOLSTERY",
      "CUSHION", "RECLINE", "HEATED SEAT", "VENTILATED SEAT"], "SEATS"),
]

VAGUE = {"UNKNOWN OR OTHER", "UNKNOWN", "OTHER", "NOT SURE", "N/A", "", "NONE"}


def refine_component(original: str, summary: str) -> str:
    c = str(original).upper().strip()
    if c not in VAGUE and len(c) >= 2:
        return c
    s = str(summary).upper()
    for patterns, name in REFINEMENT_RULES:
        if any(p in s for p in patterns):
            return name
    return "UNCATEGORIZED"


# ============================================================
# 3. 风险类型权重
# ============================================================
RISK_WEIGHTS = {
    "vehicle_fire_risk": 5, "braking_failure_or_abnormal_braking": 4,
    "steering_failure_or_loss_of_control": 4, "airbag_problem": 3,
    "adas_malfunction": 3, "seatbelt_or_restraint_issue": 3,
    "unexpected_acceleration": 3, "electrical_or_battery_failure": 2,
    "software_or_display_failure": 2, "camera_or_sensor_failure": 2,
    "powertrain_or_drive_unit_failure": 2, "vehicle_stall_or_loss_of_power": 2,
    "suspension_or_wheel_issue": 2, "charging_failure": 2,
    "visibility_or_lighting_issue": 1, "door_lock_or_latch_failure": 1,
    "body_structure_issue": 1, "unknown_vehicle_risk": 0,
}


# ============================================================
# 4. 工程化测试用例模板（16 套）
# ============================================================
TEST_TEMPLATES = {
    "braking_failure_or_abnormal_braking": {
        "title": "多工况制动性能稳定性复现测试",
        "environment": "封闭试验场 | 干燥平直路面 | -10°C ~ 40°C",
        "preconditions": "1.胎压标准值\n2.制动液位正常，无制动系统故障码\n3.制动盘/片在许用范围内\n4.制动系统自检通过",
        "steps": "1.以30/60/100 km/h稳定行驶\n2.轻度制动(0.2g)→中度(0.5g)→紧急(>0.8g)\n3.记录制动距离、减速度、踏板力/行程\n4.各工况重复5次，检查热衰退\n5.湿滑路面(μ≈0.3)重复测试\n6.观察异常噪音/振动/跑偏/告警",
        "signals": "制动踏板位移 | 主缸压力 | 轮缸压力 | 车速 | 减速度 | ABS/ESC状态 | 制动告警灯 | 踏板力 | 制动距离 | 横摆角速度",
        "criteria": "通过:制动距离<法规限值;无制动失效;无异常跑偏;ABS/ESC正常介入\n失败:任何一次制动失效;制动距离超限值;跑偏>1.5m;热衰退>30%",
    },
    "steering_failure_or_loss_of_control": {
        "title": "多车速级转向助力稳定性与失效模式测试",
        "environment": "封闭试验场 | 干燥平直路面+定圆广场 | 0°C ~ 35°C",
        "preconditions": "1.EPS无故障码\n2.胎压标准，前束/外倾在公差内\n3.方向盘转角传感器校准完成\n4.静止时方向盘力矩<3.5Nm",
        "steps": "1.以10/30/60/100 km/h直线行驶\n2.小角度连续正弦转向(±15°,0.2Hz)\n3.中角度变道(双移线ISO 3888-2)\n4.定圆广场30km/h稳态圆周转向\n5.记录力矩、转角、EPS电流、车速、横摆角速度\n6.重复10次\n7.断电模拟下评估机械备份转向力",
        "signals": "方向盘转角 | 方向盘力矩 | EPS电机电流 | 车速 | 横摆角速度 | 侧向加速度 | EPS故障码 | 转向助力状态 | 车道偏离量",
        "criteria": "通过:无卡滞;助力矩在标定内;无异常力突变;机械备份<150N\n失败:卡滞;助力完全丢失;跑偏>0.5m/s²;无告警但助力异常",
    },
    "adas_malfunction": {
        "title": "ADAS功能误触发/漏触发/异常接管综合测试",
        "environment": "封闭试验场+公共道路 | 日间+夜间 | 晴天+雨天",
        "preconditions": "1.ADAS校准完成\n2.摄像头/雷达/超声波传感器无遮挡\n3.软件为最新量产版本\n4.目标车(GVT)和假人(VRU)就位",
        "steps": "AEB:\n1a.CCRs(前车静止):30/50/70km/h接近\n1b.CCRm(前车慢行):自车50/70km/h\n1c.CPFA(行人横穿):自车20/30/40km/h\nACC:\n2a.跟车0→60→0循环\n2b.Cut-in/Cut-out场景\nLKA:\n3a.车道偏离预警(0.3/0.5/0.7m/s)\n3b.弯道保持(R=250/500m, 80/100km/h)\n误触发:\n4a.空旷道路巡航30min\n4b.金属护栏/隧道/龙门架干扰",
        "signals": "AEB激活状态 | TTC | 碰撞速度降低量 | ACC跟车距离 | 加减速度 | 接管次数 | LKA纠偏力矩 | 车道偏离量 | 告警 | 误触发次数",
        "criteria": "通过:AEB在真实风险下触发(TTC<2.5s),无风险不误触发;ACC平稳(jerk<5m/s3);LKA纠偏<0.3m\n失败:漏触发;空旷路误触发>1次/30min;异常接管;ACC跟车波动>30%",
    },
    "electrical_or_battery_failure": {
        "title": "电气系统与电池系统异常工况综合测试",
        "environment": "环境仓+封闭试验场 | -20°C/+25°C/+50°C",
        "preconditions": "1.SOC分别为95%/50%/10%\n2.BMS无故障码\n3.12V蓄电池>12.5V\n4.热管理系统正常",
        "steps": "1.不同温度下快充/慢充\n2.满载0-100km/h全油门加速\n3.连续爬坡(8%坡度,10km)\n4.120km/h巡航30min→立即快充\n5.模拟12V亏电(10.5V)尝试启动\n6.记录电池温度、单体压差、绝缘电阻、SOC跳变",
        "signals": "电池总电压 | 单体电压 | 温度场 | 绝缘电阻 | SOC/SOH | 12V电压 | DCDC输出 | 热管理功率 | 故障码 | 功率限制",
        "criteria": "通过:无异常断电;单体压差<50mV;绝缘>500Ω/V;热管理在±2°C内\n失败:行驶中断电;单体压差>200mV;绝缘报警;BMS故障码;充电中断",
    },
    "airbag_problem": {
        "title": "安全气囊系统展开/误展开/未展开场景验证",
        "environment": "碰撞实验室 | 台车试验台",
        "preconditions": "1.SRS无故障码\n2.座椅位置/乘员分类传感器校准\n3.气囊模块/碰撞传感器/ACU版本正确\n4.高速摄像/加速度计就位",
        "steps": "1.静态:读取SRS状态,检查气囊电阻\n2.台车:\n  2a.正面刚性壁障50km/h(应展开)\n  2b.侧面移动壁障32km/h(侧气囊应展开)\n  2c.低速15km/h(不应展开)\n3.非碰撞:\n  3a.过坑/减速带30km/h(不应误展开)\n  3b.急刹1.0g(不应误展开)\n4.检查展开时间/充气压力/覆盖范围",
        "signals": "碰撞传感器信号 | ACU点火指令 | 气囊展开时间 | 充气压力 | 覆盖范围 | 加速度曲线 | SRS告警灯 | 故障码 | HIC/胸部压缩量",
        "criteria": "通过:碰撞阈值内展开(<30ms);非碰撞无误展开;SRS灯正常;乘员伤害值合规\n失败:碰撞未展开;误展开;展开超时;乘员伤害值超标",
    },
    "vehicle_fire_risk": {
        "title": "多工况热失控与火灾风险验证测试",
        "environment": "环境仓+防火试验区 | 25°C/45°C | 热成像仪",
        "preconditions": "1.电池包无损伤,绝缘正常\n2.充电系统/高压线束外观完好\n3.灭火设备与应急团队就位\n4.热成像和温度传感器布点完成",
        "steps": "充电:\n1a.高温45°C快充0-100%\n1b.监测充电接口/电池包/充电机温度\n行驶:\n2a.120km/h+8%坡度组合\n2b.热成像扫描高压部件\n碰撞后:\n3a.模拟底部托底(150mm障碍物)\n3b.监测电池变形/电压/温度\n静置:\n4a.满电高温静置48h\n4b.监测电压/绝缘/温度变化",
        "signals": "电池温度 | 充电接口温度 | 红外热成像 | 绝缘电阻 | 单体电压 | 烟雾传感器 | 冷却液温度 | 电池包形变",
        "criteria": "通过:所有温度在许用内;无烟雾/明火;绝缘>100Ω/V;无热失控\n失败:出现明火/持续烟雾;电池>60°C(非快充);绝缘骤降>50%;鼓包/漏液",
    },
    "seatbelt_or_restraint_issue": {
        "title": "安全带/约束系统锁止与预紧功能验证",
        "environment": "台车实验室 | 整车试验区",
        "preconditions": "1.卷收器/带扣/预紧器外观正常\n2.SRS无故障码\n3.座椅参考位置\n4.假人(HIII 50%)正确安放",
        "steps": "静态:\n1a.缓慢拉出(不应锁止)\n1b.快速拉出(<0.3m应锁止)\n1c.倾斜15°(应锁止)\n动态:\n2a.急刹0.8g(应锁止,不误释放)\n2b.台车正面50km/h碰撞\n3.检查预紧器作动时间/力值/行程\n4.测试带扣锁止力/释放力",
        "signals": "安全带拉出位移 | 锁止时间 | 预紧器点火时间 | 织带力 | 假人位移 | 带扣力 | SRS信号 | 告警灯",
        "criteria": "通过:快速拉出0.3m内锁止;急刹不释放;预紧器正常点火;带扣力>10N\n失败:快速拉出未锁止;误锁止/误释放;预紧器未点火;带扣意外脱开",
    },
    "visibility_or_lighting_issue": {
        "title": "能见度与灯光系统功能完整性测试",
        "environment": "灯光暗室+封闭试验场 | 日间+夜间+模拟雨天",
        "preconditions": "1.所有灯具模块正常\n2.灯光校准完成\n3.雨刮片/清洗液正常\n4.光照度计就位",
        "steps": "灯光:\n1a.近/远光照度和分布(法规测试)\n1b.转向灯/制动灯/倒车灯/雾灯功能\n1c.自动大灯切换(日间/隧道/夜间)\n雨刮:\n2a.各档位刮刷频率\n2b.自动雨刮灵敏度(不同雨量)\n除霜:\n3a.前风挡除霜(-18°C)\n3b.后风挡加热\n视野:A柱盲区/后视镜视野",
        "signals": "照度(lux) | 光束截止线 | 灯光颜色/亮度 | 雨刮频率 | 除霜时间 | 视野角度 | 自动大灯切换时间",
        "criteria": "通过:照度符合FMVSS108;雨刮>80%面积;除霜20min内>80%视野\n失败:任何灯具失效;雨刮无效;除霜失败;隧道内大灯未开启",
    },
    "suspension_or_wheel_issue": {
        "title": "悬挂/车轮系统结构强度与耐久性测试",
        "environment": "底盘测功机+耐久试验场 | 比利时路/搓板路/坑洼路",
        "preconditions": "1.悬挂紧固件扭矩校验\n2.胎压/磨损在规格内\n3.四轮定位在校准范围\n4.底盘连接点无裂纹",
        "steps": "1.各悬挂点刚度测量\n2.动态:比利时路50km/h×5km / 搓板路30km/h×3km / 坑洼路20km/h\n3.高速过减速带×10次\n4.检查异常噪音/振动\n5.复测四轮定位\n6.目视+探伤检查悬挂部件",
        "signals": "悬挂位移 | 簧上/簧下加速度 | 应力应变 | 轮胎磨损量 | 四轮定位参数 | 紧固件扭矩 | 噪音dB(A) | 振动频谱",
        "criteria": "通过:无裂纹/断裂;定位偏差<公差;扭矩衰减<20%;无异响\n失败:控制臂/连杆/弹簧断裂;轮胎异常磨损;定位超差;紧固件松脱",
    },
    "software_or_display_failure": {
        "title": "车载软件与显示屏功能稳定性测试",
        "environment": "整车电子实验室+实车路试 | -20°C~70°C",
        "preconditions": "1.ECU软件为最新量产配置\n2.显示屏无物理损伤\n3.CAN/LIN/Ethernet通信正常\n4.CAN logger就位",
        "steps": "显示:\n1a.反复切换中控功能页×100次\n1b.多点触控响应(2/3/5点)\n1c.极端温度屏幕响应(-20°C/70°C)\n软件:\n2a.连续运行24h(导航+媒体+空调+ADAS)\n2b.记录黑屏/重启/卡顿次数\nOTA:\n3a.模拟升级中断/回滚\n3b.验证升级后配置保持",
        "signals": "屏幕响应时间 | CPU/GPU温度 | 内存占用 | CAN总线负载 | 故障码 | 黑屏/重启计数 | 触控延迟 | 系统日志",
        "criteria": "通过:24h无黑屏/死机;触控<100ms;OTA成功率>99%\n失败:黑屏/冻结;触控失效;系统重启>1次/24h;OTA导致车辆无法启动",
    },
    "door_lock_or_latch_failure": {
        "title": "车门锁/闩锁系统安全性与可靠性测试",
        "environment": "车身实验室+实车静态测试",
        "preconditions": "1.车门/行李箱盖/前舱盖完整\n2.锁体/锁扣无磨损\n3.电动门锁供电正常",
        "steps": "静态:\n1a.反复开关各车门×100次\n1b.测量锁扣啮合力\n1c.遥控/APP/钥匙/NFC各×50次\n动态:\n2a.行驶中试开门(应防止误开)\n2b.碰撞模拟后车门解锁\n过载:\n3a.纵/横向30g载荷(FMVSS206)\n3b.验证门不弹开",
        "signals": "锁体位置信号 | 执行器电流 | 门状态信号 | 锁扣啮合力 | 载荷-位移 | 故障码",
        "criteria": "通过:任何工况不意外弹开;门缝<4mm;碰撞后可内外打开;FMVSS206载荷下保持啮合\n失败:行驶中弹开;闭锁失效;碰撞后无法解锁",
    },
    "powertrain_or_drive_unit_failure": {
        "title": "动力总成/驱动单元性能与耐久性测试",
        "environment": "底盘测功机+耐久试验场",
        "preconditions": "1.驱动电机/发动机无故障码\n2.变速箱/减速器油液正常\n3.半轴/传动轴无异常间隙\n4.冷却系统正常",
        "steps": "功率:\n1a.全油门0-100km/h(记录功率曲线)\n1b.不同SOC下功率一致性\n耐久:\n2a.120km/h×2h高速巡航\n2b.WLTC×10循环\nNVH:\n3a.各车速电机/变速箱噪声\n3b.异常振动FFT分析",
        "signals": "电机转速/转矩 | 功率 | 效率 | 温度 | NVH频谱 | 故障码 | 能量消耗 | 传动效率",
        "criteria": "通过:功率在标称±5%内;无异响;温度在许用内;无传动故障码\n失败:功率衰减>10%;异常噪音/振动;传动故障码;半轴断裂",
    },
    "vehicle_stall_or_loss_of_power": {
        "title": "行驶中动力中断/意外熄火场景复现测试",
        "environment": "封闭试验场 | 高温/低温/常温",
        "preconditions": "1.SOC分别为80%/50%/20%/5%\n2.无已知DTC\n3.12V电池正常",
        "steps": "1.各SOC下全油门加速至限速\n2.高速巡航中收油门→再加速\n3.爬坡(8%坡度,5km)\n4.低速蠕行(5km/h,10min)\n5.频繁启停:20次红绿灯起步\n6.记录READY灯/DTC/动力中断",
        "signals": "电机转矩 | 高压电压 | 接触器状态 | READY信号 | DTC | SOC | 电池温度 | 车速",
        "criteria": "通过:任何工况无动力中断;READY持续亮;无高压互锁断\n失败:行驶中动力中断;READY熄灭;接触器异常断开;需重启恢复",
    },
    "unexpected_acceleration": {
        "title": "非预期加速/突然加速场景验证测试",
        "environment": "封闭试验场 | 低速测试区",
        "preconditions": "1.加速踏板传感器校准\n2.制动优先(BOS)功能验证\n3.自动驻车/坡道辅助正常\n4.ADAS可手动关闭",
        "steps": "泊车:\n1a.D/R档低速蠕行(不踩加速踏板)\n1b.反复D↔R切换×20次\n1c.停车入位轻踩加速踏板\n低速:\n2a.减速带前松踏板(不应加速)\n2b.转弯后直行(不踩踏板)\n信号异常:\n3a.APP传感器信号短时丢失→应进入安全模式\n3b.APP1/APP2不一致→应限功率",
        "signals": "APP1/APP2信号 | 电机转矩指令 | 车速 | 制动踏板信号 | BOS介入状态 | 档位 | DTC",
        "criteria": "通过:无自发加速;制动优先正常;APP异常进入安全模式\n失败:不踩踏板自加速;踩制动不降扭;APP异常全功率输出",
    },
    "camera_or_sensor_failure": {
        "title": "感知传感器校准与可靠性测试",
        "environment": "传感器标定实验室+试验场",
        "preconditions": "1.所有传感器在线,无通信故障\n2.镜头/罩面无污损\n3.校准目标板/角反就位",
        "steps": "静态:各传感器校准精度验证\n动态:\n2a.目标检测距离/角度精度\n2b.多目标跟踪能力\n2c.恶劣天气衰减(雨/雾)\n2d.遮挡报警验证\n故障注入:\n3a.单传感器断电→系统降级策略\n3b.传感器脏污→告警提示",
        "signals": "目标距离 | 目标角度 | 检测率 | 误报率 | 盲区覆盖 | 传感器温度 | 通信延迟 | 故障码",
        "criteria": "通过:检测率>95%;误报率<5%;故障时系统告警\n失败:无输出;检测率<80%;误报率>20%;故障时静默",
    },
    "charging_failure": {
        "title": "充电系统兼容性与异常工况测试",
        "environment": "充电测试站 | 环境仓-20°C/+25°C/+50°C",
        "preconditions": "1.充电口无损伤/异物\n2.BMS充电策略最新\n3.不同品牌充电桩各3台",
        "steps": "兼容性:\n1a.不同品牌/功率充电桩(3.3/7/11/22/150kW)\n1b.充电中反复插拔×5次\n异常工况:\n2a.充电中模拟电网断电→恢复\n2b.充电中通信中断\n2c.接口过热保护验证\n极端温度:-20°C/+50°C各完整充电一次",
        "signals": "充电功率 | 电压/电流 | 接口温度 | CP/PP信号 | 充电时间 | SOC变化 | 故障码",
        "criteria": "通过:各品牌兼容;功率在标称±10%;无中断(除安全保护);接口温升<50K\n失败:某品牌无法充电;频繁中断;接口>90°C",
    },
    "body_structure_issue": {
        "title": "车身结构完整性与耐腐蚀性测试",
        "environment": "车身测量实验室+盐雾试验箱",
        "preconditions": "1.焊接/胶接检查完成\n2.车身尺寸测量基准建立\n3.防腐涂层无可见损伤",
        "steps": "1.车身扭转刚度测量\n2.480h盐雾暴露\n3.底盘安装点/悬架塔顶/门框关键尺寸\n4.焊接点/胶接缝/涂层目视检查",
        "signals": "车身尺寸 | 扭转刚度 | 腐蚀面积 | 涂层附着力 | 焊点完整性",
        "criteria": "通过:尺寸在公差内;无结构裂纹;腐蚀面积<5%;涂层合格\n失败:焊点开裂;腐蚀穿孔;尺寸超差",
    },
}

_DEFAULT_TPL = {
    "title": "基于投诉/召回描述的定向功能复核",
    "environment": "封闭试验场+台架实验室",
    "preconditions": "1.车辆正常可用\n2.无已知相关故障码\n3.测试设备校准完成",
    "steps": "1.根据投诉/召回描述复现场景\n2.记录系统状态和参数\n3.重复确认问题可复现性\n4.与正常车辆对比分析",
    "signals": "相关传感器信号 | 系统状态 | 故障码 | 主观评价",
    "criteria": "通过:无法复现异常;功能符合设计\n失败:复现异常;功能偏离设计",
}


def get_template(scenario: str) -> dict:
    return TEST_TEMPLATES.get(scenario, _DEFAULT_TPL)


# ============================================================
# 5. 主流程
# ============================================================
def load():
    complaints = pd.read_csv(os.path.join(DATA_DIR, "complaints.csv"))
    recalls = pd.read_csv(os.path.join(DATA_DIR, "recalls.csv"))
    tcc = pd.read_csv(os.path.join(DATA_DIR, "test_case_candidates.csv"))
    return tcc, complaints, recalls


def _safe_div(a, b, d=0.0):
    return a / b if b else d


def main():
    print("加载数据...")
    tcc, complaints, recalls = load()
    print(f"  test_case_candidates: {len(tcc)}")

    # ----- 5a. 过滤非技术投诉 -----
    tcc["is_non_testable"] = tcc["evidence"].apply(lambda x: is_non_testable(str(x)))
    nt_count = tcc["is_non_testable"].sum()
    testable = tcc[~tcc["is_non_testable"]].copy()
    print(f"  排除非技术投诉: {nt_count} 条, 保留: {len(testable)} 条")

    # ----- 5b. 部件细化 -----
    testable["refined_component"] = testable.apply(
        lambda r: refine_component(r["component"], r["evidence"]), axis=1
    )

    # ----- 5c. 关联 crash/fire/injury/recall -----
    complaints["crash_bool"] = complaints["crash"].astype(str).str.lower().isin(["true", "1", "yes"])
    complaints["fire_bool"] = complaints["fire"].astype(str).str.lower().isin(["true", "1", "yes"])
    complaints["inj_num"] = pd.to_numeric(complaints["injury"], errors="coerce").fillna(0).astype(int)

    comp_agg = complaints.groupby(["vehicle_key", "component"]).agg(
        crash_count=("crash_bool", "sum"),
        fire_count=("fire_bool", "sum"),
        injury_count=("inj_num", "sum"),
    ).reset_index()

    recall_agg = recalls.groupby(["vehicle_key", "component"]).size().reset_index(name="recall_count")

    # ----- 5d. 聚合风险场景 -----
    agg = testable.groupby(
        ["vehicle_key", "risk_scenario", "refined_component"], dropna=False
    ).agg(
        evidence_count=("source_id", "count"),
        source_types=("source_type", lambda x: ",".join(sorted(set(x)))),
        sample_evidence=("evidence", lambda x: str(x.iloc[0])[:500]),
        test_objective=("test_objective", "first"),
        expected_result=("expected_result", "first"),
    ).reset_index()

    orig_comp = testable.groupby(
        ["vehicle_key", "risk_scenario", "refined_component"]
    )["component"].agg(lambda x: x.value_counts().index[0]).reset_index()
    agg = agg.merge(orig_comp, on=["vehicle_key", "risk_scenario", "refined_component"])

    agg = agg.merge(comp_agg, on=["vehicle_key", "component"], how="left")
    agg = agg.merge(recall_agg, on=["vehicle_key", "component"], how="left")
    for c in ["crash_count", "fire_count", "injury_count", "recall_count"]:
        agg[c] = agg[c].fillna(0).astype(int)

    # ----- 5e. 评分 -----
    agg["rw"] = agg["risk_scenario"].map(RISK_WEIGHTS).fillna(0)
    agg["frequency_score"] = agg["evidence_count"].apply(lambda x: round(math.log(1 + x), 2))
    agg["severity_score"] = (
        agg["rw"] + agg["crash_count"] * 2 + agg["fire_count"] * 3
        + agg["injury_count"] * 4 + agg["recall_count"] * 3
    )
    f_max, f_min = agg["frequency_score"].max(), agg["frequency_score"].min()
    s_max, s_min = agg["severity_score"].max(), agg["severity_score"].min()
    agg["freq_norm"] = agg["frequency_score"].apply(
        lambda x: round((x - f_min) / (f_max - f_min + 1e-9) * 10, 2)
    )
    agg["sev_norm"] = agg["severity_score"].apply(
        lambda x: round((x - s_min) / (s_max - s_min + 1e-9) * 10, 2)
    )
    agg["priority_score"] = round(agg["freq_norm"] * 0.5 + agg["sev_norm"] * 0.5, 2)

    agg = agg.sort_values("priority_score", ascending=False).reset_index(drop=True)
    agg.insert(0, "scenario_id", [f"R{i+1:04d}" for i in range(len(agg))])

    out_cols = [
        "scenario_id", "vehicle_key", "risk_scenario", "component",
        "refined_component", "evidence_count", "source_types",
        "crash_count", "fire_count", "injury_count", "recall_count",
        "rw", "frequency_score", "severity_score",
        "freq_norm", "sev_norm", "priority_score",
        "sample_evidence", "test_objective", "expected_result",
    ]
    rs = agg[out_cols]
    rs.to_csv(os.path.join(DATA_DIR, "risk_scenarios.csv"), index=False, encoding="utf-8-sig")
    print(f"  -> data/risk_scenarios.csv ({len(rs)} 条)")

    # ----- 5f. 构建知识图谱三元组 -----
    triples = []
    for _, r in rs.iterrows():
        vk, sc, cp = r["vehicle_key"], r["risk_scenario"], r["refined_component"]
        ev = str(r.get("sample_evidence", ""))[:300]
        triples.append((vk, "HAS_RISK_SCENARIO", sc, ev, vk))
        triples.append((sc, "AFFECTS_COMPONENT", cp, ev, vk))
        triples.append((sc, "GENERATES_TEST_CASE", r["scenario_id"], ev, vk))

    for _, r in recalls.iterrows():
        vk = r["vehicle_key"]
        triples.append((vk, "HAS_RECALL", str(r.get("campaign_number", "")),
                        str(r.get("summary", ""))[:300], vk))

    for _, c in complaints.iterrows():
        vk = c["vehicle_key"]
        triples.append((vk, "HAS_COMPLAINT", str(c.get("odi_number", "")),
                        str(c.get("summary", ""))[:300], vk))

    for _, t in testable.iterrows():
        triples.append((str(t.get("source_id", "")), "INDICATES_RISK",
                        t["risk_scenario"], str(t.get("evidence", ""))[:300],
                        t["vehicle_key"]))

    kg = pd.DataFrame(triples, columns=["head", "relation", "tail", "evidence", "vehicle_key"])
    kg = kg.drop_duplicates(subset=["head", "relation", "tail"]).reset_index(drop=True)
    kg.to_csv(os.path.join(DATA_DIR, "kg_triples.csv"), index=False, encoding="utf-8-sig")
    print(f"  -> data/kg_triples.csv ({len(kg)} 条, {kg['relation'].nunique()} 种关系)")

    # ----- 5g. 生成工程化测试用例 -----
    tc_rows = []
    for i, (_, r) in enumerate(rs.iterrows()):
        tpl = get_template(r["risk_scenario"])
        tc_rows.append({
            "test_case_id": f"TC{i+1:05d}",
            "vehicle_key": r["vehicle_key"],
            "risk_scenario": r["risk_scenario"],
            "refined_component": r["refined_component"],
            "test_case_title": tpl["title"],
            "test_objective": r["test_objective"],
            "test_environment": tpl["environment"],
            "preconditions": tpl["preconditions"],
            "test_steps": tpl["steps"],
            "observed_signals": tpl["signals"],
            "expected_result": r["expected_result"],
            "pass_fail_criteria": tpl["criteria"],
            "priority_score": r["priority_score"],
            "evidence_count": r["evidence_count"],
            "sample_evidence": str(r["sample_evidence"])[:300],
        })

    tc = pd.DataFrame(tc_rows)
    tc.to_csv(os.path.join(DATA_DIR, "test_cases.csv"), index=False, encoding="utf-8-sig")
    print(f"  -> data/test_cases.csv ({len(tc)} 条)")

    # ----- 5h. 生成报告 -----
    _generate_report(rs, tc, kg, nt_count, len(tcc))

    # ----- 5i. 摘要 -----
    print("\n" + "=" * 60)
    print("生成摘要")
    print("=" * 60)
    print(f"  排除非技术投诉:  {nt_count} 条")
    print(f"  风险场景:        {len(rs)} 条 ({rs['risk_scenario'].nunique()} 种)")
    print(f"  知识图谱三元组:  {len(kg)} 条 ({kg['relation'].nunique()} 种关系)")
    print(f"  工程化测试用例:  {len(tc)} 条 ({16} 套模板)")
    print(f"  输出文件:        data/risk_scenarios.csv, kg_triples.csv, test_cases.csv, demo_report.md")

    print("\nTop 10 优先级风险:")
    for _, r in rs.head(10).iterrows():
        print(f"  {r['scenario_id']} | {r['vehicle_key']} | {r['risk_scenario']}"
              f" | {r['refined_component'][:30]} | p={r['priority_score']}"
              f" | {r['crash_count']}C/{r['fire_count']}F/{r['injury_count']}I")

    print("\n知识图谱关系分布:")
    for rel, cnt in kg["relation"].value_counts().items():
        print(f"  {rel:30s} {cnt:5d}")

    print("\n完成!")


def _generate_report(rs, tc, kg, nt_count, total_orig):
    lines = []
    def w(s=""):
        lines.append(s)

    w("# NHTSA 车辆安全风险知识图谱 — 演示报告")
    w()
    w(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    w()

    w("## 1. 数据源与处理")
    w()
    w("- **数据源**: NHTSA 公开 API (SafetyRatings / recallsByVehicle / complaintsByVehicle)")
    n_veh = rs["vehicle_key"].nunique()
    w(f"- **覆盖车型**: {n_veh} 款 (9 款纯电 + 5 款燃油/混动, 均为 2022 年)")
    w(f"- **原始投诉**: {total_orig} 条 → 排除非技术投诉 {nt_count} 条 → 可用 {total_orig - nt_count} 条")
    w()

    w("## 2. 知识图谱规模")
    w()
    w(f"- **三元组总数**: {len(kg)}")
    w(f"- **关系类型**: {kg['relation'].nunique()} 种")
    w()
    w("| 关系 | 数量 | 含义 |")
    w("|------|------|------|")
    for rel, cnt in kg["relation"].value_counts().items():
        desc = {
            "HAS_RISK_SCENARIO": "车辆 → 存在风险场景",
            "HAS_RECALL": "车辆 → 有召回记录",
            "HAS_COMPLAINT": "车辆 → 有投诉记录",
            "INDICATES_RISK": "召回/投诉 → 指向风险",
            "AFFECTS_COMPONENT": "风险 → 影响部件",
            "GENERATES_TEST_CASE": "风险 → 生成测试用例",
        }.get(rel, "")
        w(f"| {rel} | {cnt} | {desc} |")
    w()

    w("## 3. 风险场景分布")
    w()
    w("| 风险场景 | 数量 | 最高优先级 |")
    w("|----------|------|------------|")
    for s, grp in rs.groupby("risk_scenario"):
        w(f"| {s} | {len(grp)} | {grp['priority_score'].max():.1f} |")
    w()

    w("## 4. 车型风险对比")
    w()
    w("| 车型 | 场景数 | 总证据 | 最高优先级 | 首要风险 |")
    w("|------|--------|--------|------------|----------|")
    for vk, grp in rs.groupby("vehicle_key"):
        w(f"| {vk} | {len(grp)} | {grp['evidence_count'].sum()} | {grp['priority_score'].max():.1f} | {grp.iloc[0]['risk_scenario']} |")
    w()

    w("## 5. Top 10 高优先级风险场景")
    w()
    w("| 排名 | 场景ID | 车型 | 风险场景 | 细化部件 | 证据 | 碰撞 | 火灾 | 受伤 | 优先级 |")
    w("|------|--------|------|----------|----------|------|------|------|------|--------|")
    for i, (_, r) in enumerate(rs.head(10).iterrows(), 1):
        w(f"| {i} | {r['scenario_id']} | {r['vehicle_key']} | {r['risk_scenario']} "
          f"| {r['refined_component'][:30]} | {r['evidence_count']} "
          f"| {r['crash_count']} | {r['fire_count']} | {r['injury_count']} | {r['priority_score']} |")
    w()

    w("## 6. 示例工程化测试用例 (Top 3)")
    w()
    for i, (_, row) in enumerate(tc.head(3).iterrows(), 1):
        w(f"### 6.{i} {row['test_case_id']} — {row['test_case_title']}")
        w()
        w(f"- **车型**: {row['vehicle_key']}")
        w(f"- **风险场景**: {row['risk_scenario']}")
        w(f"- **细化部件**: {row['refined_component']}")
        w(f"- **优先级**: {row['priority_score']}")
        w()
        w(f"**测试环境**: {row['test_environment']}")
        w()
        w(f"**前置条件**:")
        for line in str(row['preconditions']).split('\n'):
            if line.strip():
                w(f"  {line.strip()}")
        w()
        w(f"**测试步骤**:")
        for line in str(row['test_steps']).split('\n'):
            if line.strip():
                w(f"  {line.strip()}")
        w()
        w(f"**观测信号**: {row['observed_signals']}")
        w()
        w("**通过/失败标准**:")
        for line in str(row['pass_fail_criteria']).split('\n')[:3]:
            if line.strip():
                w(f"  {line.strip()}")
        w()

    w("## 7. 局限性与下一步")
    w()
    w("- 仅 3 款车型，样本量有限")
    w("- 风险分类为规则匹配，非 NLP 模型")
    w("- 测试用例为通用模板，未针对具体车型标定参数")
    w("- 非技术投诉过滤依赖关键词列表，可能有漏网")
    w()
    w("**下一步**:")
    w("- 扩展车型至 50+ 覆盖主流品牌")
    w("- 接入 C-NCAP / Euro NCAP 测试标准交叉验证")
    w("- 引入 LLM 做投诉文本深度理解和部件自动提取")
    w("- 将三元组导入 Neo4j 支持图查询")
    w("- 参数化测试用例（根据车型标定值自动填入阈值）")
    w()

    path = os.path.join(DATA_DIR, "demo_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  -> {path}")


if __name__ == "__main__":
    main()
