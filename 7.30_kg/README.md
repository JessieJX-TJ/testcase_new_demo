# 智己多智能体知识图谱工作台 — 部署版

> 面向汽车测试与技术规范的多智能体知识图谱构建工作台。
> 自包含部署包：拷贝整个文件夹到目标服务器，安装依赖后即可运行。

---

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows / Linux / macOS |
| Python | **3.10 或 3.11** （PaddleOCR 不兼容 3.12+） |
| 磁盘空间 | >= 2 GB（含离线数据：PDF 缓 存、NHTSA 数据、MinerU 产物） |
| 内存 | >= 4 GB（PaddleOCR 模型加载需要 ~1.5 GB） |
| 网络 | 仅在线流水线和质量评估需要访问 `dashscope.aliyuncs.com`；离线验收无需联网 |

---

## 快速启动

```bash
# 1. 创建虚拟环境
conda create -n zjkg python=3.10 -y
conda activate zjkg

# 2. 安装依赖
pip install -r requirements.txt

# 3. 验证离线数据
python test_excel.py              # Excel 抽取 → 8906 条
python test_nhtsa.py              # NHTSA → 901 场景

# 4. 启动前端
streamlit run app.py --server.port 8501
```

浏览器打开 `http://<服务器IP>:8501`。

---

## 目录结构

```
7.27_kg/
├── app.py                          ← Streamlit 主入口（6 Tab）
├── extractor.py                    ← Excel 三元组抽取核心库
├── incremental.py                  ← 增量更新引擎
├── eval_online.py                  ← Qwen-VL-Plus 在线质量评估
├── requirements.txt                ← Python 依赖
├── README.md                       ← 本文件
│
├── test_excel.py                   ← 离线：Excel 三元组抽取
├── test_pdf_cache.py               ← 离线：PDF 缓存三元组统计
├── test_pdf_online.py              ← 离线：PDF 在线全链路（需 API）
├── test_incremental.py             ← 离线：增量更新
├── test_nhtsa.py                   ← 离线：NHTSA 数据统计
│
├── agentic_kg/                     ← 多智能体运行时
│   ├── agents/                     ← 5 个 Agent
│   ├── tools/                      ← 工具包装层
│   ├── skills/                     ← 5 个 Skill 定义
│   ├── memory/skill_registry.json  ← Skill 注册表
│   ├── models.py                   ← 统一数据模型
│   └── paths.py                    ← 路径 + API Key
│
├── pdf_pipeline/                   ← PDF 知识图谱流水线
│   ├── src/                        ← Python 模块（step2~step5 + utils）
│   ├── config/pipeline_config.json ← 流水线配置
│   └── data/
│       ├── manifests/              ← 图片清单（1148 张）
│       ├── intermediate/           ← OCR / 描述 / 三元组缓存
│       └── final/                  ← 最终知识图谱（~6812 条）
│
├── 智己PDF/                        ← MinerU 离线处理的 PDF 产物
│   ├── *.pdf                       ← 4 份技术规范 PDF 源文件
│   └── output/                     ← MinerU 拆图产物（图片 + JSON）
│
├── input/                          ← Excel 输入文件（5 个）
├── outputs/                        ← 离线批量抽取结果
├── domains/                        ← 增量更新业务域
├── nhtsa_data/                     ← NHTSA 数据（14 车型 / 901 场景）
└── workbench_outputs/              ← 运行时归档（自动创建）
```

---

## 数据说明

### 已内置的离线数据（开箱即用）

| 目录/文件 | 内容 | 生成方式 |
|----------|------|---------|
| `智己PDF/output/` | 4 份技术规范 PDF 的 MinerU 拆图产物（图片 + JSON） | MinerU 离线处理 |
| `pdf_pipeline/data/intermediate/` | PaddleOCR 术语 + Qwen-VL 描述 + Qwen-VL 三元组缓存 | PDF 在线流水线预计算 |
| `pdf_pipeline/data/final/` | 4 份文档的融合后知识图谱（6812 条三元组） | step5_fuse 预计算 |
| `nhtsa_data/` | 14 车型 NHTSA 召回/投诉数据、KG 三元组、测试用例 | `nhtsa_mvp.py` + `build_kg_and_tests.py` |
| `input/` | 5 个 Excel 测试用例表 | 手工准备 |

### 如何刷新 NHTSA 数据

```bash
# 在项目父目录下（智己项目/）执行：
cd ..
python nhtsa_mvp.py          # ① 从 NHTSA API 重新采集（需要网络）
python build_kg_and_tests.py  # ② 重新构建 KG + 测试用例 + 报告
# 然后把新生成的 data/*.csv 拷贝到 7.27_kg/nhtsa_data/
```

### 如何更新 PDF 离线缓存

```bash
# 在项目父目录下执行 PDF 在线流水线重新生成所有缓存：
cd ../pdf_kg_pipeline
python src/pipeline.py
# 然后把新生成的 data/ 拷贝到 7.27_kg/pdf_pipeline/data/
```

---

## 离线验收（无需 API，零联网）

以下命令均可在终端直接运行，不消耗 API 额度：

```bash
# 1. Excel 三元组抽取
python test_excel.py                       # 批量抽取全部 5 个 Excel
python test_excel.py --file input/3_3_3离车上锁功能对比.xlsx  # 抽取单个文件

# 2. PDF 缓存三元组统计
python test_pdf_cache.py                   # 列出所有可用图片
python test_pdf_cache.py --all             # 批量统计全部 1148 张图片
python test_pdf_cache.py --image lighting_spec_0001  # 查看单张详情

# 3. 增量更新
python test_incremental.py                 # 完整 demo
python test_incremental.py --init          # 仅初始化基线
python test_incremental.py --show          # 查看 pending 状态

# 4. NHTSA 数据统计
python test_nhtsa.py                       # 汇总统计
python test_nhtsa.py --top 10              # Top 10 高优先级风险
python test_nhtsa.py --vehicle "toyota|rav4|2022"  # 查询指定车型
```

---

## 在线验收（需要 API + PaddleOCR）

```bash
# PDF 在线全链路（单张图片）
python test_pdf_online.py --image lighting_spec_0001

# PDF 在线质量评估
python eval_online.py --image lighting_spec_0001
```

---

## 大模型依赖

本项目仅在以下场景需要调用云端大模型（阿里云百炼 DashScope）：

| 阶段 | 模型 | 用途 |
|------|------|------|
| 表格结构描述 (step3_desc) | **Qwen-VL-Plus** | 输入表格图片，识别类型/主题/行列语义/实体/条件/输出 |
| 三元组抽取 (step4_extract) | **Qwen-VL-Plus** | 输入图片 + OCR白名单 + 描述，输出候选三元组 |
| 语义融合 (step5_fuse) | **Qwen-Plus** | 精确去重 + 语义归并 + 术语统一 + 冲突标记 |
| 在线质量评估 (eval_online) | **Qwen-VL-Plus** | 对比图片+OCR+三元组，输出结构化评分和修复建议 |
| Excel LLM 重抽 (llm_reextract_row_v2) | **Qwen-Plus** | 基于原始行数据 + 改进方向重新抽取 |
| Skill 草稿生成 (curator) | **Qwen-Plus** | 分析新模板，生成抽取规则建议 |

### API 提供商

| 项目 | 值 |
|------|-----|
| 提供商 | 阿里云百炼 DashScope |
| API 端点 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| SDK | OpenAI 兼容模式（`openai` 包） |

### 配置 API Key

**推荐方式**（无需改代码）：设置系统环境变量

```bash
# Linux/Mac
export DASHSCOPE_API_KEY="sk-your-key-here"

# Windows
set DASHSCOPE_API_KEY=sk-your-key-here
```

**备用方式**（修改代码）：以下 3 个文件末尾均有 `os.environ.setdefault("DASHSCOPE_API_KEY", "sk-...")`，替换其中的 key 值：

| 文件 | 行号 |
|------|------|
| `agentic_kg/paths.py` | L99 |
| `app.py` | L667 |
| `test_pdf_online.py` | L14 |

---

## 5 个正式 Skill

| Skill ID | 名称 | 工具 | 零 API |
|----------|------|------|--------|
| `excel.lock_test_case.v1` | 离车上锁 Excel 抽取 | extractor.build_lock_output_lines | ✅ |
| `excel.grouped_test_case.v1` | 分组车身控制 Excel 抽取 | extractor.build_grouped_output_lines | ✅ |
| `pdf.online_table_pipeline.v1` | PDF 在线多阶段抽取 | OCR + Qwen-VL-Plus ×2 | ❌ |
| `fusion.semantic_dedup_conflict.v1` | 三元组语义融合 | Qwen-Plus | ❌ |
| `incremental.case_scoped_diff.v1` | 案例作用域增量更新 | SHA1 哈希追踪 | ✅ |

---

## Streamlit 前端 Tab 说明

| Tab | 功能 | 零 API |
|-----|------|--------|
| 📗 Excel 图谱工作台 | 上传 Excel → 抽取三元组 → 图谱可视化 → 工程师校验 | ✅ |
| 📘 PDF KG 工作台 | 图片导航 → 离线缓存/在线运行 → 三元组校验 → 质量评估 | 部分 |
| 🚗 NHTSA 工作台 | 14 车型风险仪表盘 → Top 10 → 场景分布 → 测试用例 | ✅ |
| 📙 增量更新 | 基线 vs 候选 Excel → case 级 diff | ✅ |
| 🧠 Skills 进化 | Skill 注册表展示 + 手动创建 Skill + pending 审阅 | ✅ |
| ⚙️ Agent OS | 多智能体运行时总览 | ✅ |

---

## MinerU 离线 PDF 处理说明

当前 PDF 离线缓存由 **MinerU** 预先处理生成，步骤：

1. 用 MinerU 将 PDF 转为 Markdown + 提取表格图片
2. 将 MinerU 产物放到 `智己PDF/output/` 下
3. 运行 `pdf_pipeline/src/scan_inputs.py` 生成 `image_manifest.json`
4. 运行 PDF 在线流水线批量生成 OCR / 描述 / 三元组缓存

如果需要在**新服务器上重建离线缓存**，需要安装 MinerU：

```bash
pip install magic-pdf
# 然后对每个 PDF 执行：
magic-pdf pdf-parse 智己PDF/xxx.pdf
```

MinerU 不是本项目直接依赖，仅用于 PDF 前处理阶段。部署时 `智己PDF/output/` 和 `pdf_pipeline/data/` 已包含全部预处理产物，无需重新运行 MinerU。

---

## 部署清单

```bash
# 1. 将整个 7.27_kg/ 文件夹拷贝到目标服务器
scp -r 7.27_kg user@host:~/7.27_kg

# 2. SSH 到目标服务器
ssh user@host

# 3. 创建虚拟环境并安装依赖
cd ~/7.27_kg
conda create -n zjkg python=3.10 -y
conda activate zjkg
pip install -r requirements.txt

# 4. 设置 API Key（可选，离线验收可跳过）
export DASHSCOPE_API_KEY="sk-your-key-here"

# 5. 离线验收
python test_excel.py
python test_nhtsa.py --top 10

# 6. 启动服务（后台运行）
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 &
```

---

## 常见问题

**Q: Streamlit 报 `use_container_width` 已弃用？**
A: 本项目已全面适配。如仍报错，升级 streamlit：`pip install streamlit --upgrade`

**Q: PaddleOCR 安装失败？**
A: 确保 Python 版本是 3.10 或 3.11。3.12+ 不兼容。

**Q: 在线评估报 API Key 错误？**
A: 检查 3 个文件中的 API Key，或设置环境变量 `DASHSCOPE_API_KEY`。

**Q: PDF 图片显示路径不存在？**
A: manifest 中的 Linux 路径会自动映射到当前项目目录。如映射失败，检查 `智己PDF/output/` 子目录结构是否完整。

**Q: 中文文件名在 Linux 上乱码？**
A: 确保文件系统编码为 UTF-8，传输时使用 `rsync -a` 或 `scp -r` 保持编码。

---

*交付版本 · 2026-07-31*
