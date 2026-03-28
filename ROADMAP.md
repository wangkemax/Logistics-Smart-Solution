# Roadmap

## v0.1 — MVP ✅
- 自动化场景推荐引擎（15 种场景）
- 成本测算 + ROI 计算
- PDF 方案报告生成（Jinja2 + WeasyPrint）
- FastAPI 后端 + Streamlit 前端
- SQLite 数据库

## v0.2 — 异步 Pipeline + UI 升级 ✅
- **异步 Pipeline**：后台线程执行，非阻塞，5 步实时状态
- **Redis 状态存储**：每步进度实时可查
- **三栏 Pipeline Run UI**：左输入 / 中状态 / 右结果
- **中途参数修正**：低置信度时支持 PATCH 修正
- **PDF 下载接口**：`/api/pipeline/{id}/download`
- **模板 None 防护**：所有 Jinja2 除法加 `or 0` 保护

## v0.3 — 任务持久化 ✅
- [x] Pipeline 任务写入 SQLite，支持刷新页面不丢失
- [x] 历史任务列表 API（`GET /api/pipeline/history`）
- [ ] 前端历史任务列表页面
- [ ] 单 Step 重试按钮
- [ ] 任务超时自动标记

## v0.4 — 高级 UI ✅
- [x] 权重滑块拖动实时刷新（`on_change=st.rerun`）
- [x] 雷达图多维对比可视化（🕸️ 雷达图 Tab）
- [x] Tender 文件预览关键字段检测（面积/SKU/日订单/行业）
- [ ] 置信度进度条
- [ ] PDF 报告在线预览

## v0.5 — LLM Extractor
- [ ] OpenClaw sessions_spawn 接入
- [ ] 结构化 JSON 提取（项目名称/行业/面积/SKU/订单量/预算/痛点）
- [ ] Prompt 优化：支持表格 + 非结构化文本
- [ ] 提取置信度评分 → 自动触发参数确认表单
- [ ] 异常字段提示 + 手动补充界面

## v0.6 — 知识库与案例学习
- [ ] 历史投标项目案例库
- [ ] 行业模板（电商/3PL/制造/医药/快递）
- [ ] 客户画像标签体系
- [ ] 中标结果反馈学习

---

## 技术债务

- [ ] 将 `project_service.py` 拆分为 `recommendation_service.py` + `cost_service.py`
- [ ] RESTful 统一错误码规范
- [ ] API 限流（/api/pipeline/* 防止滥用）
- [ ] Streamlit session_state 持久化到 localStorage
