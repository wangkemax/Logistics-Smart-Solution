"""
process_design_builder.py — v0.8
=================================
Builds ProcessDesign section for BaseSolution.
One ProcessStage per enabled service in service_scope.
"""

from __future__ import annotations

from backend.schemas.base_solution_schema import ProcessDesign, ProcessStage


def build_process_design(
    *,
    service_scope: dict,
    region: str = "华东",
    industry: str = "GENERIC_3PL",
) -> ProcessDesign:
    """
    Build ProcessDesign from service_scope.

    Stages are ordered by actual warehouse flow:
      inbound → storage → outbound → value_added → support

    Parameters
    ----------
    service_scope : dict
        e.g. {
            "inbound": {"receiving": True, "quality_check": True, ...},
            "outbound": {"picking": True, ...},
            ...
        }
    region : str
        Used for SLA hour suggestions
    industry : str
        Used for industry-specific activity naming

    Returns
    -------
    ProcessDesign
    """
    stages: list[ProcessStage] = []
    flow_labels: list[str] = []

    # ── INBOUND ────────────────────────────────────────────────────────────
    inbound = service_scope.get("inbound", {})

    if inbound.get("receiving") or inbound.get("unloading"):
        stages.append(ProcessStage(
            stage_key="inbound_receiving",
            stage_name="入库收货",
            enabled=True,
            activities=[
                "车辆到达登记与排队叫号",
                "卸货与件数清点",
                "外观检查与异常记录",
                "WMS 入库单创建",
            ],
            handoff="交接给质检团队（如需质检）",
            sla="4小时内完成入库收货",
            sla_hours=4.0,
            kpis=["收货准时率", "货损率", "件数准确率"],
            roles_involved=["收货团队"],
        ))
        flow_labels.append("入库收货")

    if inbound.get("quality_check"):
        stages.append(ProcessStage(
            stage_key="inbound_quality_check",
            stage_name="质量检验",
            enabled=True,
            activities=[
                "抽样质检与合规检查",
                "质检异常登记与反馈",
                "合格品移交上架",
                "不合格品隔离处理",
            ],
            handoff="质检完成后移交上架团队",
            sla="2小时内完成质检",
            sla_hours=2.0,
            kpis=["质检合格率", "质检及时率"],
            roles_involved=["质检团队", "收货团队"],
        ))
        flow_labels.append("质量检验")

    if inbound.get("putaway"):
        stages.append(ProcessStage(
            stage_key="inbound_putaway",
            stage_name="上架存储",
            enabled=True,
            activities=[
                "系统推荐库位",
                "叉车/地牛搬运上架",
                "WMS 库位确认与库存更新",
                "库位标签打印与张贴",
            ],
            handoff="库存记录实时更新，等待出库指令",
            sla="8小时内完成上架",
            sla_hours=8.0,
            kpis=["上架准确率", "上架及时率", "库容利用率"],
            roles_involved=["上架团队", "叉车司机"],
        ))
        flow_labels.append("上架存储")

    # ── STORAGE ───────────────────────────────────────────────────────────
    storage = service_scope.get("storage", {})
    if storage and any(v for v in storage.values() if v):
        activities = []
        if storage.get("pallet_storage"):
            activities.append("托盘区日常巡仓")
        if storage.get("bin_storage"):
            activities.append("料箱区库存管理")
        if storage.get("temperature_control"):
            activities.append("温湿度日常监控与记录")
        if storage.get("bonded_storage"):
            activities.append("保税库存管理与海关对账")

        activities.extend(["FIFO 先进先出管理", "库存盘点（每日/每周）", "补货触发与库位优化"])
        stages.append(ProcessStage(
            stage_key="storage_management",
            stage_name="仓储管理",
            enabled=True,
            activities=list(dict.fromkeys(activities)),  # deduplicate preserving order
            handoff="等待出库订单指令",
            sla=None,
            sla_hours=None,
            kpis=["库存准确率", "库容利用率", "盘点差异率"],
            roles_involved=["仓储团队", "叉车司机"],
        ))
        flow_labels.append("仓储管理")

    # ── OUTBOUND ──────────────────────────────────────────────────────────
    outbound = service_scope.get("outbound", {})

    if outbound.get("picking"):
        stages.append(ProcessStage(
            stage_key="outbound_picking",
            stage_name="订单拣选",
            enabled=True,
            activities=[
                "波次生成与拣货单打印",
                "系统路径规划与RF扫描",
                "拣货数量确认",
                "异常件（找不到/数量差异）登记",
            ],
            handoff="移交给包装团队",
            sla=None,
            sla_hours=None,
            kpis=["拣选效率（件/人时）", "拣选准确率", "波次完成率"],
            roles_involved=["拣选团队"],
        ))
        flow_labels.append("订单拣选")

    if outbound.get("replenishment"):
        stages.append(ProcessStage(
            stage_key="outbound_replenishment",
            stage_name="补货调度",
            enabled=True,
            activities=["波次前预判库存不足货位", "从存储区向拣选区补货", "补货完成后系统确认"],
            handoff="补货完成后继续拣选流程",
            sla=None,
            sla_hours=None,
            kpis=["补货及时率", "拣选区缺货率"],
            roles_involved=["拣选团队", "补货团队"],
        ))
        flow_labels.append("补货调度")

    if outbound.get("packing"):
        stages.append(ProcessStage(
            stage_key="outbound_packing",
            stage_name="包装贴标",
            enabled=True,
            activities=[
                "包装材料选取与商品装箱",
                "面单/快递单打印与粘贴",
                "称重校验与运费核对",
                "异常重量件登记处理",
            ],
            handoff="移交给出库装车团队",
            sla=None,
            sla_hours=None,
            kpis=["包装合格率", "包装效率（件/人时）", "称重差异率"],
            roles_involved=["包装团队"],
        ))
        flow_labels.append("包装贴标")

    if outbound.get("labeling"):
        stages.append(ProcessStage(
            stage_key="outbound_labeling",
            stage_name="贴标与复查",
            enabled=True,
            activities=["条形码/RFID 标签打印", "标签粘贴与核对", "复查无误后移流出库"],
            handoff="移交给装车团队",
            sla=None,
            sla_hours=None,
            kpis=["贴标准确率", "贴标效率"],
            roles_involved=["包装团队"],
        ))
        flow_labels.append("贴标复查")

    if outbound.get("loading") or outbound.get("shipping"):
        stages.append(ProcessStage(
            stage_key="outbound_loading",
            stage_name="出库装车",
            enabled=True,
            activities=[
                "装车排队叫号",
                "装车扫描与件数核对",
                "交接单据确认",
                "发车时间记录与客户通知",
            ],
            handoff="承运商接单，货物在途",
            sla=None,
            sla_hours=None,
            kpis=["装载准时率", "出库件数准确率", "在途时效达标率"],
            roles_involved=["装车团队", "调度员"],
        ))
        flow_labels.append("出库装车")

    # ── VALUE ADDED ───────────────────────────────────────────────────────
    va = service_scope.get("value_added", {})
    va_activities: list[str] = []

    if va.get("kitting"):
        va_activities.append("组合包装（Kitting）：按套餐将多个 SKU 组成销售单元")
    if va.get("repack"):
        va_activities.append("换包加工（Repack）：拆除原包装、重新组装、贴新标签")
    if va.get("light_assembly"):
        va_activities.append("轻组装：简单组装作业（如带配件、说明书等）")
    if va.get("return_handling"):
        va_activities.append("退货处理：接收退货、质检分类、退货上架或报废处理")

    if va_activities:
        stages.append(ProcessStage(
            stage_key="value_added_service",
            stage_name="流通加工",
            enabled=True,
            activities=va_activities,
            handoff="返回主出库流程或进入退货处理分支",
            sla=None,
            sla_hours=None,
            kpis=["加工合格率", "流通加工准时率"],
            roles_involved=["增值加工团队"],
        ))
        flow_labels.append("流通加工")

    # ── SUPPORT ───────────────────────────────────────────────────────────
    support = service_scope.get("support", {})

    if support.get("inventory_reporting"):
        stages.append(ProcessStage(
            stage_key="inventory_reporting",
            stage_name="库存报表与客户对账",
            enabled=True,
            activities=[
                "每日库存报表生成",
                "客户库存数据推送",
                "库存预警与补货建议",
                "月度对账与差异说明",
            ],
            handoff="报表发送客户确认",
            sla=None,
            sla_hours=None,
            kpis=["报表准时率", "账实一致率", "数据推送准确率"],
            roles_involved=["运营支持团队", "客服"],
        ))
        flow_labels.append("库存报表")

    if support.get("system_integration"):
        stages.append(ProcessStage(
            stage_key="system_integration",
            stage_name="系统对接",
            enabled=True,
            activities=[
                "与客户 ERP/WMS 系统对接配置",
                "API 连通性测试",
                "订单/库存数据实时同步",
                "异常接口问题排查",
            ],
            handoff="系统对接稳定运行",
            sla=None,
            sla_hours=None,
            kpis=["接口可用率", "数据同步及时率"],
            roles_involved=["IT 支持团队"],
        ))
        flow_labels.append("系统对接")

    if support.get("data_reporting"):
        stages.append(ProcessStage(
            stage_key="data_reporting",
            stage_name="数据分析与运营报告",
            enabled=True,
            activities=[
                "KPI 周报/月报生成",
                "运营效率分析",
                "异常高峰分析",
                "优化建议报告",
            ],
            handoff="报告提交管理层评审",
            sla=None,
            sla_hours=None,
            kpis=["报告准时率", "分析覆盖率"],
            roles_involved=["运营支持团队"],
        ))
        flow_labels.append("数据分析")

    return ProcessDesign(
        stages=stages,
        flow_diagram_label=" → ".join(flow_labels) if flow_labels else "无完整流程",
        narrative="",
    )
