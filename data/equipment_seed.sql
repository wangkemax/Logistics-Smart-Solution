-- data/equipment_seed.sql — v1.1 Equipment Database 初始数据
-- 设备类型：AMR / GTP / ASRS / Shuttle / Conveyor / Sorter
-- 费用单位：万元（CAPEX）；功率：kW；MTBF：小时；维保：万元/年；占地面积：m²

-- ============================================================
-- AMR（潜伏式 AMR）
-- ============================================================
INSERT INTO equipment (equipment_type, model_name, manufacturer, capex_min, capex_max,
    throughput_unit, throughput_value, payload_kg, max_speed_mps, power_kw, mtbf_hours,
    maintenance_cost_pa, footprint_sqm, is_active, notes)
VALUES
    ('AMR', 'AMR-500L', '国产主流', 8.0, 15.0,
     'pos/hr', 80.0, 500.0, 1.5, 0.3, 8000.0,
     1.5, 0.8, 1, '潜伏式 AMR，额定载重500kg，适用箱式拣选'),

    ('AMR', 'AMR-1000L', '国产主流', 12.0, 22.0,
     'pos/hr', 60.0, 1000.0, 1.2, 0.5, 10000.0,
     2.0, 1.0, 1, '潜伏式 AMR，额定载重1000kg，适用托盘/大件搬运'),

    ('AMR', 'AMR-CW-200', '国产主流', 15.0, 28.0,
     'pos/hr', 40.0, 200.0, 2.0, 0.4, 12000.0,
     2.5, 0.6, 1, '顶升式 AMR，额定载重200kg，高速小型化');

-- ============================================================
-- GTP（叉式 AGV）
-- ============================================================
INSERT INTO equipment (equipment_type, model_name, manufacturer, capex_min, capex_max,
    throughput_unit, throughput_value, payload_kg, max_speed_mps, power_kw, mtbf_hours,
    maintenance_cost_pa, footprint_sqm, is_active, notes)
VALUES
    ('GTP', 'GTP-1500', '国产主流', 18.0, 35.0,
     'pos/hr', 50.0, 1500.0, 1.2, 0.8, 15000.0,
     3.0, 2.5, 1, '前移式叉车 AGV，额定载重1500kg，适用窄巷道'),

    ('GTP', 'GTP-3000', '国产主流', 25.0, 50.0,
     'pos/hr', 35.0, 3000.0, 1.0, 1.2, 18000.0,
     4.5, 3.5, 1, '平衡重叉式 AGV，额定载重3000kg，适用重载堆垛');

-- ============================================================
-- AS/RS（自动立体仓库）
-- ============================================================
INSERT INTO equipment (equipment_type, model_name, manufacturer, capex_min, capex_max,
    throughput_unit, throughput_value, payload_kg, max_speed_mps, power_kw, mtbf_hours,
    maintenance_cost_pa, footprint_sqm, is_active, notes)
VALUES
    ('AS/RS', 'ASRS-M8', '国产主流', 150.0, 300.0,
     'bin/hr', 80.0, 50.0, 0.8, 1.5, 20000.0,
     20.0, 25.0, 1, 'miniload 堆垛机，适用箱式存储，8m 轨高'),

    ('AS/RS', 'ASRS-M12', '国产主流', 200.0, 450.0,
     'bin/hr', 120.0, 50.0, 1.0, 2.0, 25000.0,
     28.0, 35.0, 1, 'miniload 堆垛机，适用箱式存储，12m 轨高');

-- ============================================================
-- Shuttle（多层穿梭车）
-- ============================================================
INSERT INTO equipment (equipment_type, model_name, manufacturer, capex_min, capex_max,
    throughput_unit, throughput_value, payload_kg, max_speed_mps, power_kw, mtbf_hours,
    maintenance_cost_pa, footprint_sqm, is_active, notes)
VALUES
    ('Shuttle', 'SH-200', '国产主流', 20.0, 40.0,
     'pos/hr', 200.0, 25.0, 3.0, 0.2, 12000.0,
     3.5, 0.5, 1, '四向穿梭车，适用箱式高密度存储，25kg载重'),

    ('Shuttle', 'SH-500', '国产主流', 30.0, 60.0,
     'pos/hr', 150.0, 50.0, 2.5, 0.3, 15000.0,
     5.0, 0.8, 1, '四向穿梭车，适用大箱/件杂货存储，50kg载重');

-- ============================================================
-- Conveyor（输送线）
-- ============================================================
INSERT INTO equipment (equipment_type, model_name, manufacturer, capex_min, capex_max,
    throughput_unit, throughput_value, payload_kg, max_speed_mps, power_kw, mtbf_hours,
    maintenance_cost_pa, footprint_sqm, is_active, notes)
VALUES
    ('Conveyor', 'CV-600', '国产主流', 3.0, 8.0,
     'pos/hr', 300.0, 50.0, 0.5, 0.15, 20000.0,
     1.0, 0.3, 1, '滚筒输送线，适用60cm宽纸箱，50kg载重'),

    ('Conveyor', 'CV-1200', '国产主流', 5.0, 12.0,
     'pos/hr', 200.0, 100.0, 0.4, 0.25, 25000.0,
     1.5, 0.5, 1, '滚筒输送线，适用120cm宽托盘/大件，100kg载重');

-- ============================================================
-- Sorter（分拣机）
-- ============================================================
INSERT INTO equipment (equipment_type, model_name, manufacturer, capex_min, capex_max,
    throughput_unit, throughput_value, payload_kg, max_speed_mps, power_kw, mtbf_hours,
    maintenance_cost_pa, footprint_sqm, is_active, notes)
VALUES
    ('Sorter', 'SRT-4000', '国产主流', 40.0, 80.0,
     'pos/hr', 4000.0, 30.0, 2.0, 5.0, 10000.0,
     8.0, 8.0, 1, '交叉带分拣机，适用电商/快递小件，4000件/小时'),

    ('Sorter', 'SRT-8000', '国产主流', 60.0, 120.0,
     'pos/hr', 8000.0, 30.0, 2.5, 8.0, 12000.0,
     12.0, 12.0, 1, '交叉带分拣机，适用高速分拣场景，8000件/小时');
