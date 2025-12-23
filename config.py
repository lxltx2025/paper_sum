# ╭──────────────────────────────────────────────────────╮
# │                                                      │
# │   ██╗     ██╗  ██╗██╗  ████████╗██╗  ██╗             │
# │   ██║     ╚██╗██╔╝██║  ╚══██╔══╝╚██╗██╔╝             │
# │   ██║      ╚███╔╝ ██║     ██║    ╚███╔╝              │
# │   ██║      ██╔██╗ ██║     ██║    ██╔██╗              │
# │   ███████╗██╔╝ ██╗███████╗██║   ██╔╝ ██╗             │
# │   ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝   ╚═╝  ╚═╝             │
# │                                                      │
# │   Author: LXLTX-Lab                                  │
# │   GitHub: https://github.com/lxltx2025               │
# │   Date: 2025-12-23                                   │
# │   License: MIT                                       │
# │                                                      │
# ╰──────────────────────────────────────────────────────╯

"""
配置文件 - 医学AI文献分析系统
"""

import os
from pathlib import Path

# ============ 路径配置 ============
# PDF文件夹路径（请修改为你的实际路径）
PDF_FOLDER = Path("/mnt/d/repro/paper_sum/multi_omics_papers")  # WSL2路径示例
# Windows路径转换示例: /mnt/c/Users/xxx/Documents/Papers

# 输出文件夹
OUTPUT_FOLDER = Path("./multi_omics_output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# ============ Ollama配置 ============
OLLAMA_BASE_URL = "http://172.16.25.135:11434"
OLLAMA_MODEL = "qwen2.5:14b"

# API调用配置
REQUEST_TIMEOUT = 300  # 秒
MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒

# ============ PDF处理配置 ============
MAX_PAGES_TO_ANALYZE = 50  # 每个PDF最多分析的页数
MAX_TEXT_LENGTH = 12000   # 发送给LLM的最大文本长度（字符）
MIN_TEXT_LENGTH = 100     # 有效文本的最小长度

# ============ 并发配置 ============
MAX_WORKERS = 2  # 并发处理的PDF数量（根据内存调整）
BATCH_SIZE = 5   # 批处理大小

# ============ 分类标签配置 ============
PRIMARY_CATEGORIES = [
    "医学影像AI",
    "临床决策支持",
    "药物研发AI",
    "基因组学与精准医疗",
    "自然语言处理(医疗)",
    "病理学AI",
    "放射学AI",
    "手术机器人与辅助",
    "健康监测与可穿戴",
    "流行病学与公共卫生",
    "心理健康AI",
    "其他"
]

SECONDARY_CATEGORIES = [
    "深度学习", "机器学习", "联邦学习", "迁移学习",
    "图像分割", "目标检测", "图像分类", "图像生成",
    "大语言模型", "知识图谱", "多模态学习",
    "时序分析", "生存分析", "因果推断",
    "可解释AI", "隐私保护", "模型压缩",
    "临床验证", "真实世界研究", "回顾性研究", "前瞻性研究",
    "综述", "方法论", "基准测试", "数据集"
]

CONTENT_TYPES = [
    "原创研究", "综述文章", "方法论文", 
    "临床研究", "技术报告", "案例研究"
]

RESEARCH_STAGES = [
    "基础研究", "概念验证", "临床前研究",
    "临床试验", "临床应用", "商业化"
]

# ============ 输出文件名 ============
JSON_OUTPUT = OUTPUT_FOLDER / "analysis_results.json"
CSV_OUTPUT = OUTPUT_FOLDER / "analysis_results.csv"
MARKDOWN_OUTPUT = OUTPUT_FOLDER / "summary_report.md"
HTML_OUTPUT = OUTPUT_FOLDER / "interactive_report.html"