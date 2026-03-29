"""
process_templates.py — v0.6.6 Labor & Process Modeling
=================================================

Static process templates keyed by labor module.
Each template describes the standard step sequence for that process.

These are industry-standard warehouse/DC process flows.
They activate based on which labor modules are enabled in the operation profile.
"""

from typing import Optional


# =============================================================================
# Process Template Definitions
# =============================================================================

PROCESS_TEMPLATES: dict[str, dict] = {

    "receiving_process": {
        "label": "入库作业流程",
        "description": "货物从供应商车辆到达至完成上架的完整步骤",
        "trigger_condition": "receiving_team == True",  # doc only
        "steps": [
            {"step_id": "rcv_01", "key": "truck_arrival",     "label": "车辆到达登记",     "role": "门卫/调度"},
            {"step_id": "rcv_02", "key": "dock_assignment",  "label": "月台分配",         "role": "调度"},
            {"step_id": "rcv_03", "key": "unloading",         "label": "卸货",             "role": "装卸组"},
            {"step_id": "rcv_04", "key": "quantity_check",   "label": "数量验收",         "role": "收货组"},
            {"step_id": "rcv_05", "key": "quality_check",    "label": "质量检验",         "role": "质检组"},
            {"step_id": "rcv_06", "key": "document_filing", "label": "单据归档",         "role": "收货组"},
            {"step_id": "rcv_07", "key": "putaway",         "label": "上架作业",         "role": "上架组"},
            {"step_id": "rcv_08", "key": "location_confirm", "label": "库位确认",         "role": "上架组"},
        ],
        "kpis": ["卸货效率 (托/小时)", "验收准确率 (%)", "上架及时率 (%)"],
    },

    "outbound_process": {
        "label": "出库作业流程",
        "description": "从订单释放到货物装车出库的完整步骤",
        "trigger_condition": "picking_team == True or packing_team == True",
        "steps": [
            {"step_id": "out_01", "key": "order_release",    "label": "订单释放",         "role": "WMS/计划组"},
            {"step_id": "out_02", "key": "wave_planning",   "label": "波次规划",         "role": "计划组"},
            {"step_id": "out_03", "key": "pick_list_gen",   "label": "拣货单生成",       "role": "WMS"},
            {"step_id": "out_04", "key": "picking",          "label": "拣选作业",         "role": "拣选组"},
            {"step_id": "out_05", "key": "pick_confirm",     "label": "拣货确认",         "role": "拣选组"},
            {"step_id": "out_06", "key": "sorting",          "label": "分拣归类",         "role": "分拣组"},
            {"step_id": "out_07", "key": "packing",          "label": "包装作业",         "role": "包装组"},
            {"step_id": "out_08", "key": "labeling",         "label": "贴标/复核",        "role": "包装组"},
            {"step_id": "out_09", "key": "staging",          "label": "暂存区集结",       "role": "集货组"},
            {"step_id": "out_10", "key": "loading",          "label": "装车作业",         "role": "装车组"},
            {"step_id": "out_11", "key": "departure_check",  "label": "发车确认",         "role": "调度"},
        ],
        "kpis": ["拣选效率 (行/小时)", "包装准确率 (%)", "装载率 (%)", "日出库单量"],
    },

    "storage_management": {
        "label": "存储管理流程",
        "description": "日常库内管理与库存维护的步骤",
        "trigger_condition": "inventory_control_team == True",
        "steps": [
            {"step_id": "stor_01", "key": "daily_count",     "label": "日常巡仓",         "role": "库管组"},
            {"step_id": "stor_02", "key": "cycle_count",    "label": "循环盘点",         "role": "库管组"},
            {"step_id": "stor_03", "key": "replenishment",  "label": "补货触发",         "role": "库管组/WMS"},
            {"step_id": "stor_04", "key": "location_optim",  "label": "库位优化",         "role": "库管组"},
            {"step_id": "stor_05", "key": "fifo_check",     "label": "FIFO检查",         "role": "库管组"},
            {"step_id": "stor_06", "key": "damage_report",  "label": "报损处理",         "role": "库管组"},
            {"step_id": "stor_07", "key": "inventory_report","label": "库存报表",         "role": "库管组"},
        ],
        "kpis": ["库存准确率 (%)", "盘点差异率 (%)", "库位利用率 (%)"],
    },

    "return_process": {
        "label": "退货处理流程",
        "description": "客户退货从接收到处理完毕的完整步骤",
        "trigger_condition": "return_processing_team == True",
        "steps": [
            {"step_id": "ret_01",  "key": "return_receiving", "label": "退货接收登记",    "role": "退货组"},
            {"step_id": "ret_02",  "key": "return_inspection", "label": "退货质检",        "role": "质检组"},
            {"step_id": "ret_03",  "key": "return分类",       "label": "分类判定",        "role": "退货组"},
            {"step_id": "ret_04",  "key": "restock",           "label": "合格品退库",      "role": "退货组"},
            {"step_id": "ret_05",  "key": "disposal",          "label": "不合格品处理",    "role": "退货组"},
            {"step_id": "ret_06",  "key": "return_report",     "label": "退货数据录入",    "role": "退货组"},
            {"step_id": "ret_07",  "key": "credit_process",    "label": "退款/扣款处理",   "role": "客服组"},
        ],
        "kpis": ["退货处理时效 (天)", "退货原因分类占比 (%)"],
    },

    "va_process": {
        "label": "增值服务流程",
        "description": "Kitting、换装、轻装配等增值服务的执行步骤",
        "trigger_condition": "value_added_required == True",
        "steps": [
            {"step_id": "va_01",  "key": "va_order_release","label": "VA订单释放",       "role": "计划组/WMS"},
            {"step_id": "va_02",  "key": "material_kitting","label": "物料调拨/配套",    "role": "VA组"},
            {"step_id": "va_03",  "key": "assembly_or_repack","label": "组装/换装作业",  "role": "VA组"},
            {"step_id": "va_04",  "key": "va_qc",            "label": "VA质检",           "role": "VA组"},
            {"step_id": "va_05",  "key": "va_relabel",       "label": "重新贴标",         "role": "VA组"},
            {"step_id": "va_06",  "key": "va_staging",       "label": "VA品集结",         "role": "VA组"},
            {"step_id": "va_07",  "key": "va_outbound",      "label": "并入出库流程",     "role": "出库组"},
        ],
        "kpis": ["VA作业效率 (套/小时)", "VA准确率 (%)"],
    },

    "temperature_control": {
        "label": "温控管理流程",
        "description": "冷藏/恒温区域的日常温控管理步骤",
        "trigger_condition": "temperature_control_required == True",
        "steps": [
            {"step_id": "tc_01",  "key": "tc_monitoring",   "label": "温湿度实时监控",    "role": "温控组"},
            {"step_id": "tc_02",  "key": "tc_alarm_response","label": "超温预警响应",      "role": "温控组"},
            {"step_id": "tc_03",  "key": "tc_door_discipline","label": "月台门禁管理",     "role": "温控组"},
            {"step_id": "tc_04",  "key": "tc_cleaning",    "label": "库内清洁消毒",      "role": "温控组"},
            {"step_id": "tc_05",  "key": "tc_record",      "label": "温控记录归档",      "role": "温控组"},
            {"step_id": "tc_06",  "key": "tc_equipment_check","label": "设备点检",        "role": "设备组"},
        ],
        "kpis": ["温控合规率 (%)", "设备正常运行时间 (%)"],
    },

    "support_process": {
        "label": "支持服务流程",
        "description": "系统对接、库存报表等支持服务的日常运营步骤",
        "trigger_condition": "support_required == True",
        "steps": [
            {"step_id": "sup_01", "key": "inventory_reporting","label": "库存报表生成",    "role": "计划组"},
            {"step_id": "sup_02", "key": "system_integration","label": "系统对接维护",    "role": "IT组"},
            {"step_id": "sup_03", "key": "data_backup",     "label": "数据备份",         "role": "IT组"},
            {"step_id": "sup_04", "key": "bi_reporting",    "label": "BI报表推送",       "role": "计划组"},
        ],
        "kpis": ["报表准时率 (%)", "系统可用率 (%)"],
    },
}


def get_active_processes(labor_modules: dict) -> dict[str, dict]:
    """
    Return the subset of PROCESS_TEMPLATES that are active for a given labor_modules dict.

    Activation rules:
      receiving_team    → receiving_process
      picking/packing/loading team → outbound_process
      inventory_control_team → storage_management
      return_processing_team → return_process
      value_added_required=True → va_process
      temperature_control_required=True → temperature_control
      support_required=True → support_process
    """
    active = {}

    if labor_modules.get("receiving_team"):
        active["receiving_process"] = PROCESS_TEMPLATES["receiving_process"]

    # outbound_process triggers if any outbound labor module is active
    outbound_active = any([
        labor_modules.get("picking_team"),
        labor_modules.get("packing_team"),
        labor_modules.get("loading_team"),
    ])
    if outbound_active:
        active["outbound_process"] = PROCESS_TEMPLATES["outbound_process"]

    if labor_modules.get("inventory_control_team"):
        active["storage_management"] = PROCESS_TEMPLATES["storage_management"]

    if labor_modules.get("return_processing_team"):
        active["return_process"] = PROCESS_TEMPLATES["return_process"]

    # va_process and temperature_control / support_process are triggered from
    # operation_profile fields, passed via labor_modules dict with underscore prefix
    if labor_modules.get("_value_added_required"):
        active["va_process"] = PROCESS_TEMPLATES["va_process"]

    if labor_modules.get("_temperature_control_required"):
        active["temperature_control"] = PROCESS_TEMPLATES["temperature_control"]

    if labor_modules.get("_support_required"):
        active["support_process"] = PROCESS_TEMPLATES["support_process"]

    return active


def build_process_modules(
    labor_modules: dict,
    value_added_required: bool = False,
    temperature_control_required: bool = False,
    support_required: bool = False,
) -> dict[str, dict]:
    """
    Build process_modules dict for downstream consumption.

    Each entry: {
        "label": str,
        "description": str,
        "steps": [...],
        "kpis": [...],
    }
    """
    # Enrich labor_modules with profile flags (underscore-prefixed to avoid collision)
    enriched = dict(labor_modules)
    enriched["_value_added_required"] = value_added_required
    enriched["_temperature_control_required"] = temperature_control_required
    enriched["_support_required"] = support_required

    active = get_active_processes(enriched)

    # Build the output dict with step count summary
    result = {}
    for proc_key, proc_template in active.items():
        result[proc_key] = {
            "label": proc_template["label"],
            "description": proc_template["description"],
            "steps": [
                {"step_id": s["step_id"], "key": s["key"], "label": s["label"], "role": s["role"]}
                for s in proc_template["steps"]
            ],
            "step_count": len(proc_template["steps"]),
            "kpis": proc_template["kpis"],
        }

    return result
