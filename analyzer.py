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
医学AI文献批量分析系统
基于 Ollama + Qwen2.5:14B + WSL2

功能：
- 批量分析PDF文献
- 生成结构化摘要、标签、关键词
- 提取GitHub代码链接
- 输出JSON/CSV/Markdown/HTML报告
"""

import os
import sys
import json
import re
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

# 第三方库
import requests
import pandas as pd
from tqdm import tqdm
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

# PDF处理
import fitz  # PyMuPDF
import pdfplumber

# 配置
try:
    from config import *
except ImportError:
    print("请确保config.py在同一目录下")
    sys.exit(1)

console = Console()

# ============ 数据模型 ============

@dataclass
class PaperAnalysis:
    """论文分析结果数据模型"""
    # 基本信息
    file_name: str
    file_path: str
    file_hash: str
    analysis_time: str
    
    # 结构化摘要
    title: str = ""
    title_cn: str = ""  # 中文标题
    authors: List[str] = field(default_factory=list)
    publication_year: str = ""
    journal_conference: str = ""
    doi: str = ""
    
    # 摘要与核心内容
    abstract: str = ""
    abstract_cn: str = ""  # 中文摘要
    research_objective: str = ""  # 研究目标
    methodology: str = ""  # 方法论
    key_findings: List[str] = field(default_factory=list)  # 关键发现
    innovations: List[str] = field(default_factory=list)  # 创新点
    limitations: List[str] = field(default_factory=list)  # 局限性
    future_work: str = ""  # 未来工作
    
    # 标准化标签
    primary_category: str = ""  # 主分类
    secondary_categories: List[str] = field(default_factory=list)  # 副分类
    content_type: str = ""  # 内容类型
    research_stage: str = ""  # 研究阶段
    
    # 核心关键词
    keywords: List[str] = field(default_factory=list)  # 英文关键词
    keywords_cn: List[str] = field(default_factory=list)  # 中文关键词
    
    # 实体信息
    diseases: List[str] = field(default_factory=list)  # 涉及疾病
    technologies: List[str] = field(default_factory=list)  # 使用技术
    datasets: List[str] = field(default_factory=list)  # 使用数据集
    metrics: Dict[str, str] = field(default_factory=dict)  # 性能指标
    
    # 代码与资源链接
    github_links: List[str] = field(default_factory=list)
    other_links: List[str] = field(default_factory=list)
    
    # 评估信息
    importance_score: int = 5  # 1-10重要性评分
    importance_reason: str = ""  # 评分理由
    
    # 影响与应用
    clinical_impact: str = ""  # 临床影响
    potential_applications: List[str] = field(default_factory=list)  # 潜在应用
    
    # 处理状态
    status: str = "success"  # success, error, partial
    error_message: str = ""
    raw_text_length: int = 0


# ============ PDF文本提取 ============

class PDFExtractor:
    """PDF文本提取器"""
    
    @staticmethod
    def extract_text_pymupdf(pdf_path: Path, max_pages: int = 15) -> str:
        """使用PyMuPDF提取文本"""
        try:
            doc = fitz.open(str(pdf_path))
            texts = []
            for page_num in range(min(len(doc), max_pages)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    texts.append(text)
            doc.close()
            return "\n\n".join(texts)
        except Exception as e:
            console.print(f"[yellow]PyMuPDF提取失败: {e}[/yellow]")
            return ""
    
    @staticmethod
    def extract_text_pdfplumber(pdf_path: Path, max_pages: int = 15) -> str:
        """使用pdfplumber提取文本（备用）"""
        try:
            texts = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_num, page in enumerate(pdf.pages[:max_pages]):
                    text = page.extract_text()
                    if text:
                        texts.append(text)
            return "\n\n".join(texts)
        except Exception as e:
            console.print(f"[yellow]pdfplumber提取失败: {e}[/yellow]")
            return ""
    
    @staticmethod
    def extract_links(pdf_path: Path) -> Tuple[List[str], List[str]]:
        """提取PDF中的链接"""
        github_links = []
        other_links = []
        
        try:
            doc = fitz.open(str(pdf_path))
            for page in doc:
                # 提取注释链接
                for link in page.get_links():
                    uri = link.get("uri", "")
                    if uri:
                        if "github.com" in uri.lower() or "gitlab.com" in uri.lower():
                            if uri not in github_links:
                                github_links.append(uri)
                        elif uri.startswith("http"):
                            if uri not in other_links:
                                other_links.append(uri)
                
                # 从文本中提取链接
                text = page.get_text()
                # GitHub链接模式
                github_pattern = r'https?://(?:www\.)?github\.com/[^\s\)\]\}"\'>]+'
                for match in re.finditer(github_pattern, text, re.IGNORECASE):
                    url = match.group().rstrip('.,;:')
                    if url not in github_links:
                        github_links.append(url)
                
                # GitLab链接
                gitlab_pattern = r'https?://(?:www\.)?gitlab\.com/[^\s\)\]\}"\'>]+'
                for match in re.finditer(gitlab_pattern, text, re.IGNORECASE):
                    url = match.group().rstrip('.,;:')
                    if url not in github_links:
                        github_links.append(url)
            
            doc.close()
        except Exception as e:
            console.print(f"[yellow]链接提取失败: {e}[/yellow]")
        
        return github_links, other_links
    
    @classmethod
    def extract(cls, pdf_path: Path) -> Tuple[str, List[str], List[str]]:
        """提取PDF内容和链接"""
        # 尝试PyMuPDF
        text = cls.extract_text_pymupdf(pdf_path, MAX_PAGES_TO_ANALYZE)
        
        # 如果PyMuPDF失败或文本太短，尝试pdfplumber
        if len(text) < MIN_TEXT_LENGTH:
            text_alt = cls.extract_text_pdfplumber(pdf_path, MAX_PAGES_TO_ANALYZE)
            if len(text_alt) > len(text):
                text = text_alt
        
        # 提取链接
        github_links, other_links = cls.extract_links(pdf_path)
        
        return text, github_links, other_links


# ============ Ollama API调用 ============

class OllamaAnalyzer:
    """Ollama分析器"""
    
    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.api_url = f"{self.base_url}/api/generate"
    
    def check_connection(self) -> bool:
        """检查Ollama服务连接"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if any(self.model in name for name in model_names):
                    return True
                console.print(f"[yellow]模型 {self.model} 未找到，可用模型: {model_names}[/yellow]")
            return False
        except Exception as e:
            console.print(f"[red]连接Ollama失败: {e}[/red]")
            return False
    
    def _create_analysis_prompt(self, text: str, github_links: List[str]) -> str:
        """创建分析提示词"""
        
        # 截断文本
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH] + "\n...[文本已截断]..."
        
        github_info = "\n".join(github_links) if github_links else "未找到"
        
        prompt = f"""你是一位专业的医学AI领域文献分析专家。请仔细分析以下医学AI论文，并以JSON格式输出结构化分析结果。

## 已提取的GitHub链接：
{github_info}

## 论文内容：
{text}

## 分析要求：
请提取并分析以下信息，以严格的JSON格式返回：

```json
{{
    "title": "论文英文标题",
    "title_cn": "论文中文标题（翻译）",
    "authors": ["作者1", "作者2"],
    "publication_year": "发表年份",
    "journal_conference": "期刊或会议名称",
    "doi": "DOI号（如有）",
    
    "abstract": "英文摘要（200字以内）",
    "abstract_cn": "中文摘要（200字以内翻译）",
    
    "research_objective": "研究目标（一句话概括）",
    "methodology": "方法论概述（100字以内）",
    
    "key_findings": [
        "关键发现1",
        "关键发现2",
        "关键发现3"
    ],
    
    "innovations": [
        "创新点1",
        "创新点2"
    ],
    
    "limitations": [
        "局限性1",
        "局限性2"
    ],
    
    "future_work": "未来工作方向",
    
    "primary_category": "主分类（从以下选择一个：医学影像AI、临床决策支持、药物研发AI、基因组学与精准医疗、自然语言处理(医疗)、病理学AI、放射学AI、手术机器人与辅助、健康监测与可穿戴、流行病学与公共卫生、心理健康AI、其他）",
    
    "secondary_categories": ["副分类1", "副分类2"],
    
    "content_type": "内容类型（从以下选择：原创研究、综述文章、方法论文、临床研究、技术报告、案例研究）",
    
    "research_stage": "研究阶段（从以下选择：基础研究、概念验证、临床前研究、临床试验、临床应用、商业化）",
    
    "keywords": ["英文关键词1", "英文关键词2", "英文关键词3", "英文关键词4", "英文关键词5"],
    "keywords_cn": ["中文关键词1", "中文关键词2", "中文关键词3"],
    
    "diseases": ["涉及疾病1", "涉及疾病2"],
    "technologies": ["使用技术1", "使用技术2", "使用技术3"],
    "datasets": ["使用数据集1", "使用数据集2"],
    
    "metrics": {{
        "指标名称1": "数值或描述",
        "指标名称2": "数值或描述"
    }},
    
    "importance_score": 7,
    "importance_reason": "重要性评分理由（考虑创新性、临床价值、方法学贡献等）",
    
    "clinical_impact": "临床影响分析（50字以内）",
    "potential_applications": ["潜在应用1", "潜在应用2"]
}}
```

## 注意事项：
1. 严格使用JSON格式，确保可以被解析
2. 所有字段都必须填写，如无信息请填"未提及"或空数组[]
3. 重要性评分1-10，其中8-10为高重要性
4. 关键词提取要精准、专业
5. 标签分类要准确匹配预定义选项
6. 只输出JSON，不要有其他解释文字
   """
        return prompt
   
    def analyze(self, text: str, github_links: List[str]) -> Dict[str, Any]:
        """调用Ollama分析论文"""
        prompt = self._create_analysis_prompt(text, github_links)
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": 4096,
            }
        }
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    self.api_url,
                    json=payload,
                    timeout=REQUEST_TIMEOUT
                )
                
                if response.status_code == 200:
                    result = response.json()
                    response_text = result.get("response", "")
                    
                    # 解析JSON
                    return self._parse_response(response_text)
                else:
                    console.print(f"[yellow]API返回错误 {response.status_code}[/yellow]")
                    
            except requests.exceptions.Timeout:
                console.print(f"[yellow]请求超时，重试 {attempt + 1}/{MAX_RETRIES}[/yellow]")
            except Exception as e:
                console.print(f"[yellow]请求错误: {e}，重试 {attempt + 1}/{MAX_RETRIES}[/yellow]")
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        
        return {}
   
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """解析LLM响应中的JSON"""
        # 尝试直接解析
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass
        
        # 尝试提取JSON块
        json_patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*\}'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, response_text)
            for match in matches:
                try:
                    text = match if isinstance(match, str) else match[0]
                    # 找到最外层的花括号
                    start = text.find('{')
                    end = text.rfind('}') + 1
                    if start != -1 and end > start:
                        json_str = text[start:end]
                        return json.loads(json_str)
                except json.JSONDecodeError:
                    continue
        
        console.print("[yellow]无法解析JSON响应[/yellow]")
        return {}


# ============ 文献分析器 ============

class PaperBatchAnalyzer:
    """批量文献分析器"""
    
    def __init__(self, pdf_folder: Path):
        self.pdf_folder = Path(pdf_folder)
        self.ollama = OllamaAnalyzer()
        self.results: List[PaperAnalysis] = []
        
    def get_pdf_files(self) -> List[Path]:
        """获取所有PDF文件"""
        pdf_files = list(self.pdf_folder.glob("**/*.pdf"))
        console.print(f"[green]找到 {len(pdf_files)} 个PDF文件[/green]")
        return pdf_files
    
    def compute_file_hash(self, file_path: Path) -> str:
        """计算文件哈希"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()[:12]
    
    def analyze_single_pdf(self, pdf_path: Path) -> PaperAnalysis:
        """分析单个PDF"""
        file_name = pdf_path.name
        file_hash = self.compute_file_hash(pdf_path)
        
        # 创建基础结果
        result = PaperAnalysis(
            file_name=file_name,
            file_path=str(pdf_path),
            file_hash=file_hash,
            analysis_time=datetime.now().isoformat()
        )
        
        try:
            # 提取文本和链接
            text, github_links, other_links = PDFExtractor.extract(pdf_path)
            result.raw_text_length = len(text)
            result.github_links = github_links
            result.other_links = other_links
            
            if len(text) < MIN_TEXT_LENGTH:
                result.status = "error"
                result.error_message = "提取的文本太短"
                return result
            
            # 调用Ollama分析
            analysis = self.ollama.analyze(text, github_links)
            
            if not analysis:
                result.status = "error"
                result.error_message = "LLM分析返回空结果"
                return result
            
            # 填充分析结果
            self._populate_result(result, analysis)
            result.status = "success"
            
        except Exception as e:
            result.status = "error"
            result.error_message = str(e)
            console.print(f"[red]分析 {file_name} 失败: {e}[/red]")
        
        return result
    
    def _populate_result(self, result: PaperAnalysis, analysis: Dict) -> None:
        """填充分析结果"""
        # 基本信息
        result.title = analysis.get("title", "")
        result.title_cn = analysis.get("title_cn", "")
        result.authors = analysis.get("authors", [])
        result.publication_year = analysis.get("publication_year", "")
        result.journal_conference = analysis.get("journal_conference", "")
        result.doi = analysis.get("doi", "")
        
        # 摘要
        result.abstract = analysis.get("abstract", "")
        result.abstract_cn = analysis.get("abstract_cn", "")
        result.research_objective = analysis.get("research_objective", "")
        result.methodology = analysis.get("methodology", "")
        result.key_findings = analysis.get("key_findings", [])
        result.innovations = analysis.get("innovations", [])
        result.limitations = analysis.get("limitations", [])
        result.future_work = analysis.get("future_work", "")
        
        # 标签
        result.primary_category = analysis.get("primary_category", "其他")
        result.secondary_categories = analysis.get("secondary_categories", [])
        result.content_type = analysis.get("content_type", "")
        result.research_stage = analysis.get("research_stage", "")
        
        # 关键词
        result.keywords = analysis.get("keywords", [])
        result.keywords_cn = analysis.get("keywords_cn", [])
        
        # 实体
        result.diseases = analysis.get("diseases", [])
        result.technologies = analysis.get("technologies", [])
        result.datasets = analysis.get("datasets", [])
        result.metrics = analysis.get("metrics", {})
        
        # 评估
        score = analysis.get("importance_score", 5)
        result.importance_score = max(1, min(10, int(score) if isinstance(score, (int, float)) else 5))
        result.importance_reason = analysis.get("importance_reason", "")
        
        # 影响
        result.clinical_impact = analysis.get("clinical_impact", "")
        result.potential_applications = analysis.get("potential_applications", [])
    
    def run(self) -> List[PaperAnalysis]:
        """运行批量分析"""
        # 检查Ollama连接
        console.print(Panel("[bold]医学AI文献批量分析系统[/bold]", style="blue"))
        
        console.print("[cyan]检查Ollama服务...[/cyan]")
        if not self.ollama.check_connection():
            console.print("[red]无法连接到Ollama服务，请确保服务已启动[/red]")
            console.print("[yellow]提示: 在终端运行 'ollama serve' 启动服务[/yellow]")
            return []
        console.print("[green]✓ Ollama服务连接成功[/green]")
        
        # 获取PDF文件
        pdf_files = self.get_pdf_files()
        if not pdf_files:
            console.print("[red]未找到PDF文件[/red]")
            return []
        
        # 批量分析
        console.print(f"\n[cyan]开始分析 {len(pdf_files)} 个文件...[/cyan]\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[green]分析进度", total=len(pdf_files))
            
            for pdf_path in pdf_files:
                progress.update(task, description=f"[green]分析: {pdf_path.name[:40]}...")
                result = self.analyze_single_pdf(pdf_path)
                self.results.append(result)
                progress.advance(task)
        
        # 统计
        success_count = sum(1 for r in self.results if r.status == "success")
        console.print(f"\n[green]分析完成: {success_count}/{len(self.results)} 成功[/green]")
        
        return self.results


# ============ 报告生成器 ============

class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, results: List[PaperAnalysis]):
        self.results = results
    
    def generate_all(self):
        """生成所有报告"""
        console.print("\n[cyan]生成报告...[/cyan]")
        
        self.generate_json()
        self.generate_csv()
        self.generate_markdown()
        self.generate_html()
        
        console.print(f"[green]✓ 所有报告已生成到 {OUTPUT_FOLDER}[/green]")
    
    def generate_json(self):
        """生成JSON报告"""
        data = [asdict(r) for r in self.results]
        with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        console.print(f"  [green]✓ JSON: {JSON_OUTPUT}[/green]")
    
    def _calculate_stats(self) -> Dict:
        """计算统计数据"""
        stats = {
            "total": len(self.results),
            "success": sum(1 for r in self.results if r.status == "success"),
            "high_importance": sum(1 for r in self.results if r.importance_score >= 8),
            "medium_importance": sum(1 for r in self.results if 5 <= r.importance_score < 8),
            "low_importance": sum(1 for r in self.results if r.importance_score < 5),
            "with_github": sum(1 for r in self.results if r.github_links and len(r.github_links) > 0),
            "without_github": sum(1 for r in self.results if not r.github_links or len(r.github_links) == 0),
            "primary_categories": {},
            "secondary_categories": {},
            "content_types": {},
            "research_stages": {},
            "keywords": {},
            "years": {},
            "diseases": {}  # 新增：疾病统计
        }
        
        for r in self.results:
            # 主分类
            cat = r.primary_category or "未分类"
            stats["primary_categories"][cat] = stats["primary_categories"].get(cat, 0) + 1
            
            # 副分类
            for sc in r.secondary_categories:
                stats["secondary_categories"][sc] = stats["secondary_categories"].get(sc, 0) + 1
            
            # 内容类型
            ct = r.content_type or "未知"
            stats["content_types"][ct] = stats["content_types"].get(ct, 0) + 1
            
            # 研究阶段
            rs = r.research_stage or "未知"
            stats["research_stages"][rs] = stats["research_stages"].get(rs, 0) + 1
            
            # 关键词
            for kw in r.keywords[:5]:
                stats["keywords"][kw] = stats["keywords"].get(kw, 0) + 1
            
            # 年份
            year = r.publication_year or "未知"
            stats["years"][year] = stats["years"].get(year, 0) + 1
            
            # 疾病/病种统计（新增）
            for disease in r.diseases:
                if disease and disease != "未提及":
                    stats["diseases"][disease] = stats["diseases"].get(disease, 0) + 1
        
        return stats
    
    def generate_csv(self):
        """生成CSV报告"""
        rows = []
        for r in self.results:
            row = {
                '文件名': r.file_name,
                '标题': r.title,
                '中文标题': r.title_cn,
                '作者': '; '.join(r.authors),
                '年份': r.publication_year,
                '期刊/会议': r.journal_conference,
                'DOI': r.doi,
                '主分类': r.primary_category,
                '副分类': '; '.join(r.secondary_categories),
                '内容类型': r.content_type,
                '研究阶段': r.research_stage,
                '关键词': '; '.join(r.keywords),
                '中文关键词': '; '.join(r.keywords_cn),
                '疾病': '; '.join(r.diseases),
                '技术': '; '.join(r.technologies),
                '数据集': '; '.join(r.datasets),
                'GitHub链接': '; '.join(r.github_links),
                '重要性评分': r.importance_score,
                '重要性理由': r.importance_reason,
                '中文摘要': r.abstract_cn,
                '研究目标': r.research_objective,
                '关键发现': '; '.join(r.key_findings),
                '创新点': '; '.join(r.innovations),
                '临床影响': r.clinical_impact,
                '状态': r.status
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        df.to_csv(CSV_OUTPUT, index=False, encoding='utf-8-sig')
        console.print(f"  [green]✓ CSV: {CSV_OUTPUT}[/green]")
    
    def generate_markdown(self):
        """生成Markdown报告"""
        lines = [
            "# 医学AI文献分析报告",
            f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"\n总计分析: {len(self.results)} 篇文献",
            "",
            "---",
            ""
        ]
        
        # 统计信息
        success_count = sum(1 for r in self.results if r.status == "success")
        high_importance = sum(1 for r in self.results if r.importance_score >= 8)
        
        lines.extend([
            "## 📊 统计概览",
            "",
            f"- **成功分析**: {success_count} 篇",
            f"- **高重要性(8-10分)**: {high_importance} 篇",
            ""
        ])
        
        # 分类统计
        categories = {}
        for r in self.results:
            cat = r.primary_category or "未分类"
            categories[cat] = categories.get(cat, 0) + 1
        
        lines.extend([
            "### 主分类分布",
            ""
        ])
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            lines.append(f"- {cat}: {count} 篇")
        
        lines.extend(["", "---", ""])
        
        # 文献详情
        lines.append("## 📚 文献详情")
        lines.append("")
        
        # 按重要性排序
        sorted_results = sorted(self.results, key=lambda x: -x.importance_score)
        
        for i, r in enumerate(sorted_results, 1):
            importance_emoji = "🔴" if r.importance_score >= 8 else ("🟡" if r.importance_score >= 5 else "🟢")
            
            lines.extend([
                f"### {i}. {r.title or r.file_name}",
                "",
                f"**中文标题**: {r.title_cn or '无'}",
                "",
                f"**重要性**: {importance_emoji} {r.importance_score}/10",
                "",
                f"**分类**: {r.primary_category} | {', '.join(r.secondary_categories)}",
                "",
                f"**关键词**: {', '.join(r.keywords)}",
                ""
            ])
            
            if r.abstract_cn:
                lines.extend([
                    "**摘要**:",
                    f"> {r.abstract_cn}",
                    ""
                ])
            
            if r.key_findings:
                lines.append("**关键发现**:")
                for finding in r.key_findings:
                    lines.append(f"- {finding}")
                lines.append("")
            
            if r.innovations:
                lines.append("**创新点**:")
                for inn in r.innovations:
                    lines.append(f"- {inn}")
                lines.append("")
            
            if r.github_links:
                lines.append("**代码链接**:")
                for link in r.github_links:
                    lines.append(f"- [{link}]({link})")
                lines.append("")
            
            lines.extend(["---", ""])
        
        with open(MARKDOWN_OUTPUT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        console.print(f"  [green]✓ Markdown: {MARKDOWN_OUTPUT}[/green]")
    
    def generate_html(self):
        """生成HTML交互式报告"""
        # 准备数据
        data = [asdict(r) for r in self.results]
        data_json = json.dumps(data, ensure_ascii=False)
        
        # 统计数据
        stats = self._calculate_stats()
        stats_json = json.dumps(stats, ensure_ascii=False)
        
        html_content = self._get_html_template(data_json, stats_json)
        
        with open(HTML_OUTPUT, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        console.print(f"  [green]✓ HTML: {HTML_OUTPUT}[/green]")
    
    def _calculate_stats(self) -> Dict:
        """计算统计数据"""
        stats = {
            "total": len(self.results),
            "success": sum(1 for r in self.results if r.status == "success"),
            "high_importance": sum(1 for r in self.results if r.importance_score >= 8),
            "medium_importance": sum(1 for r in self.results if 5 <= r.importance_score < 8),
            "low_importance": sum(1 for r in self.results if r.importance_score < 5),
            "primary_categories": {},
            "secondary_categories": {},
            "content_types": {},
            "research_stages": {},
            "keywords": {},
            "years": {}
        }
        
        for r in self.results:
            # 主分类
            cat = r.primary_category or "未分类"
            stats["primary_categories"][cat] = stats["primary_categories"].get(cat, 0) + 1
            
            # 副分类
            for sc in r.secondary_categories:
                stats["secondary_categories"][sc] = stats["secondary_categories"].get(sc, 0) + 1
            
            # 内容类型
            ct = r.content_type or "未知"
            stats["content_types"][ct] = stats["content_types"].get(ct, 0) + 1
            
            # 研究阶段
            rs = r.research_stage or "未知"
            stats["research_stages"][rs] = stats["research_stages"].get(rs, 0) + 1
            
            # 关键词
            for kw in r.keywords[:5]:
                stats["keywords"][kw] = stats["keywords"].get(kw, 0) + 1
            
            # 年份
            year = r.publication_year or "未知"
            stats["years"][year] = stats["years"].get(year, 0) + 1
        
        return stats
    
    def _get_html_template(self, data_json: str, stats_json: str) -> str:
        """返回HTML模板"""
        
        html = r'''<!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>医学AI文献分析报告</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
        <style>
            :root {
                --bg-primary: #0f0f1a;
                --bg-secondary: #1a1a2e;
                --bg-card: #232342;
                --text-primary: #f0f0f0;
                --text-secondary: #9ca3af;
                --accent: #06b6d4;
                --accent-hover: #0891b2;
                --high: #ef4444;
                --medium: #f59e0b;
                --low: #22c55e;
                --border: #374151;
                --github: #8b5cf6;
            }
            [data-theme="light"] {
                --bg-primary: #f8fafc;
                --bg-secondary: #ffffff;
                --bg-card: #ffffff;
                --text-primary: #1e293b;
                --text-secondary: #64748b;
                --border: #cbd5e1;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: var(--bg-primary);
                color: var(--text-primary);
                line-height: 1.6;
                min-height: 100vh;
            }
            .container { max-width: 1400px; margin: 0 auto; padding: 24px; }
            
            /* Header */
            .header {
                display: flex; justify-content: space-between; align-items: center;
                padding: 24px 32px; background: var(--bg-secondary); border-radius: 16px;
                margin-bottom: 24px; border: 1px solid var(--border);
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            }
            .header h1 { 
                color: var(--accent); font-size: 1.75rem; font-weight: 700;
                letter-spacing: -0.5px;
            }
            .header-buttons { display: flex; gap: 12px; }
            
            /* Buttons */
            .btn {
                padding: 10px 20px; border: none; border-radius: 10px;
                cursor: pointer; font-weight: 600; font-size: 0.875rem;
                transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 6px;
            }
            .btn-primary { background: var(--accent); color: #fff; }
            .btn-primary:hover { background: var(--accent-hover); transform: translateY(-1px); }
            .btn-secondary { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); }
            .btn-secondary:hover { background: var(--border); }
            .btn-github { background: var(--github); color: #fff; }
            .btn-github:hover { opacity: 0.9; }
            .btn.active { box-shadow: 0 0 0 3px rgba(6, 182, 212, 0.3); }
            
            /* Stats Grid */
            .stats-grid {
                display: grid; grid-template-columns: repeat(7, 1fr);
                gap: 16px; margin-bottom: 24px;
            }
            .stat-card {
                background: var(--bg-secondary); padding: 20px; border-radius: 14px;
                text-align: center; border: 1px solid var(--border); cursor: pointer;
                transition: all 0.2s ease;
            }
            .stat-card:hover { transform: translateY(-2px); border-color: var(--accent); }
            .stat-card .number { 
                font-size: 2rem; font-weight: 700; color: var(--accent);
                line-height: 1.2;
            }
            .stat-card .label { 
                color: var(--text-secondary); margin-top: 6px; font-size: 0.8rem;
                font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px;
            }
            .stat-card.high .number { color: var(--high); }
            .stat-card.medium .number { color: var(--medium); }
            .stat-card.low .number { color: var(--low); }
            .stat-card.github .number { color: var(--github); }
            
            /* Charts Section */
            .charts-section {
                display: grid; grid-template-columns: repeat(3, 1fr);
                gap: 20px; margin-bottom: 24px;
            }
            .chart-container {
                background: var(--bg-secondary); padding: 24px; border-radius: 16px;
                border: 1px solid var(--border);
            }
            .chart-container h3 { 
                margin-bottom: 20px; color: var(--text-primary); font-size: 1rem;
                font-weight: 600; display: flex; align-items: center; gap: 8px;
            }
            .chart-wrapper { position: relative; height: 260px; width: 100%; }
            
            /* Word Cloud */
            .word-cloud {
                display: flex; flex-wrap: wrap; gap: 10px; justify-content: center;
                align-items: center; padding: 20px; min-height: 220px;
            }
            .word-cloud span { 
                cursor: pointer; padding: 4px 8px; transition: all 0.2s;
                border-radius: 4px;
            }
            .word-cloud span:hover { 
                transform: scale(1.1); 
                background: rgba(6, 182, 212, 0.1);
            }
            
            /* Filters Section */
            .filters-section {
                background: var(--bg-secondary); padding: 24px; border-radius: 16px;
                margin-bottom: 24px; border: 1px solid var(--border);
            }
            .filters-header {
                display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 20px;
            }
            .filters-header h3 { 
                color: var(--text-primary); font-size: 1.1rem; font-weight: 600;
            }
            .results-count {
                padding: 8px 16px; background: var(--bg-card); border-radius: 10px;
                color: var(--accent); font-weight: 600; font-size: 0.875rem;
                border: 1px solid var(--border);
            }
            .filter-row { 
                display: grid; grid-template-columns: repeat(4, 1fr);
                gap: 16px; margin-bottom: 16px;
            }
            .filter-group label { 
                display: block; margin-bottom: 8px; color: var(--text-secondary); 
                font-size: 0.8rem; font-weight: 600; text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .filter-group input, .filter-group select {
                width: 100%; padding: 12px 14px; border: 1px solid var(--border); 
                border-radius: 10px; background: var(--bg-card); color: var(--text-primary); 
                font-size: 0.9rem; transition: border-color 0.2s;
            }
            .filter-group input:focus, .filter-group select:focus { 
                outline: none; border-color: var(--accent); 
            }
            .filter-group input::placeholder { color: var(--text-secondary); }
            .filter-buttons { display: flex; gap: 12px; margin-top: 8px; }
            
            /* Papers Grid */
            .papers-grid {
                display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px;
            }
            .paper-card {
                background: var(--bg-secondary); border-radius: 16px; padding: 24px;
                border: 1px solid var(--border); transition: all 0.25s ease;
                position: relative;
            }
            .paper-card:hover { 
                transform: translateY(-3px); 
                box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                border-color: var(--accent);
            }
            .paper-card.has-github { border-left: 4px solid var(--github); }
            
            .paper-header {
                display: flex; justify-content: space-between; align-items: flex-start;
                margin-bottom: 16px; gap: 16px;
            }
            .paper-title { 
                font-size: 1.05rem; font-weight: 600; margin-bottom: 6px; 
                color: var(--text-primary); line-height: 1.4;
            }
            .paper-title-cn { 
                font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 12px;
                line-height: 1.5;
            }
            .paper-journal { 
                font-size: 0.85rem; color: var(--accent); margin-bottom: 10px; 
                padding: 8px 12px; background: rgba(6, 182, 212, 0.1);
                border-radius: 8px; display: inline-block; font-weight: 500;
            }
            .paper-meta { 
                font-size: 0.8rem; color: var(--text-secondary); 
                display: flex; align-items: center; gap: 6px;
            }
            
            /* === 优化后的收藏按钮 === */
            .action-area {
                display: flex; flex-direction: column; align-items: center; gap: 12px;
            }
            .importance-badge {
                font-size: 1.5rem; font-weight: 700; padding: 8px; 
                border-radius: 12px; min-width: 50px; text-align: center;
            }
            .importance-high { color: var(--high); }
            .importance-medium { color: var(--medium); }
            .importance-low { color: var(--low); }
            
            .favorite-btn {
                width: 44px; height: 44px;
                border-radius: 12px;
                border: 2px solid var(--border);
                background: transparent;
                color: var(--text-secondary);
                font-size: 1.5rem;
                cursor: pointer;
                display: flex; align-items: center; justify-content: center;
                transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            }
            
            .favorite-btn:hover {
                border-color: var(--medium);
                color: var(--medium);
                transform: scale(1.1);
                background: rgba(245, 158, 11, 0.1);
            }
            
            .favorite-btn.active {
                background: var(--medium);
                border-color: var(--medium);
                color: #ffffff;
                box-shadow: 0 4px 15px rgba(245, 158, 11, 0.4);
                transform: scale(1.05);
            }
            /* ======================== */
            
            .github-badge {
                display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px;
                background: var(--github); color: #fff; border-radius: 20px; 
                font-size: 0.7rem; font-weight: 600; margin-left: 10px;
            }
            
            .tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
            .tag { 
                padding: 5px 12px; border-radius: 20px; font-size: 0.75rem; 
                font-weight: 600; cursor: pointer; transition: all 0.2s;
            }
            .tag:hover { transform: scale(1.05); }
            .tag-primary { background: rgba(6, 182, 212, 0.15); color: var(--accent); }
            .tag-secondary { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
            .tag-type { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }
            .tag-disease { background: rgba(239, 68, 68, 0.15); color: #f87171; }
            
            .keywords { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
            .keyword {
                padding: 4px 10px; background: var(--bg-card); border-radius: 6px;
                font-size: 0.75rem; color: var(--text-secondary); cursor: pointer;
                border: 1px solid var(--border); transition: all 0.2s;
            }
            .keyword:hover { border-color: var(--accent); color: var(--accent); }
            
            .github-links { margin-bottom: 14px; }
            .github-link {
                display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px;
                background: linear-gradient(135deg, #24292e 0%, #1a1a2e 100%); 
                color: #fff; text-decoration: none; border-radius: 8px;
                font-size: 0.8rem; font-weight: 500; margin-right: 8px; margin-bottom: 8px;
                transition: all 0.2s;
            }
            .github-link:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
            
            .expand-btn {
                width: 100%; padding: 12px; background: var(--bg-card);
                border: 1px solid var(--border); border-radius: 10px; 
                color: var(--text-secondary); cursor: pointer; font-weight: 500;
                transition: all 0.2s;
            }
            .expand-btn:hover { background: var(--border); color: var(--text-primary); }
            
            .details { 
                display: none; margin-top: 20px; padding-top: 20px; 
                border-top: 1px solid var(--border); 
            }
            .details.show { display: block; }
            .detail-section { margin-bottom: 18px; }
            .detail-section h4 { 
                color: var(--accent); margin-bottom: 10px; font-size: 0.85rem;
                font-weight: 600; display: flex; align-items: center; gap: 6px;
            }
            .detail-section p { color: var(--text-secondary); font-size: 0.875rem; line-height: 1.7; }
            .detail-section ul { list-style: none; padding-left: 0; }
            .detail-section li { 
                color: var(--text-secondary); font-size: 0.875rem; 
                padding: 6px 0 6px 20px; position: relative; line-height: 1.6;
            }
            .detail-section li::before { 
                content: "→"; color: var(--accent); position: absolute; left: 0;
            }
            
            /* Modal */
            .modal {
                display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.8); z-index: 2000; align-items: center; 
                justify-content: center; backdrop-filter: blur(4px);
            }
            .modal.show { display: flex; }
            .modal-content {
                background: var(--bg-secondary); padding: 32px; border-radius: 20px; 
                max-width: 480px; width: 90%; border: 1px solid var(--border);
            }
            .modal-content h3 { 
                margin-bottom: 8px; color: var(--text-primary); font-size: 1.25rem;
            }
            .modal-content > p { margin-bottom: 24px; }
            .export-options { display: flex; flex-direction: column; gap: 12px; }
            .export-btn {
                padding: 16px 20px; border: 1px solid var(--border); border-radius: 12px;
                background: var(--bg-card); color: var(--text-primary); cursor: pointer; 
                text-align: left; font-size: 0.95rem; font-weight: 500; transition: all 0.2s;
                display: flex; align-items: center; gap: 12px;
            }
            .export-btn:hover { background: var(--border); transform: translateX(4px); }
            
            .no-results { 
                text-align: center; padding: 80px 20px; color: var(--text-secondary); 
                grid-column: 1 / -1; 
            }
            .no-results h3 { font-size: 1.5rem; margin-bottom: 12px; color: var(--text-primary); }
            
            /* Responsive */
            @media (max-width: 1200px) {
                .charts-section { grid-template-columns: 1fr 1fr; }
                .stats-grid { grid-template-columns: repeat(4, 1fr); }
            }
            @media (max-width: 900px) {
                .papers-grid { grid-template-columns: 1fr; }
                .charts-section { grid-template-columns: 1fr; }
                .filter-row { grid-template-columns: repeat(2, 1fr); }
                .stats-grid { grid-template-columns: repeat(2, 1fr); }
            }
            @media (max-width: 600px) {
                .filter-row { grid-template-columns: 1fr; }
                .header { flex-direction: column; text-align: center; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔬 医学AI文献分析报告</h1>
                <div class="header-buttons">
                    <button class="btn btn-secondary" id="exportBtn">📥 导出收藏</button>
                    <button class="btn btn-primary" id="themeBtn">☀️ 浅色</button>
                </div>
            </div>
            
            <div class="stats-grid" id="statsGrid"></div>
            
            <div class="charts-section">
                <div class="chart-container">
                    <h3>📊 主分类分布</h3>
                    <div class="chart-wrapper"><canvas id="primaryChart"></canvas></div>
                </div>
                <div class="chart-container">
                    <h3>📈 副分类分布</h3>
                    <div class="chart-wrapper"><canvas id="secondaryChart"></canvas></div>
                </div>
                <div class="chart-container">
                    <h3>☁️ 关键词云</h3>
                    <div class="word-cloud" id="wordCloud"></div>
                </div>
            </div>
            
            <div class="filters-section">
                <div class="filters-header">
                    <h3>🔍 筛选与搜索</h3>
                    <span class="results-count" id="resultsCount">0 篇文献</span>
                </div>
                
                <div class="filter-row">
                    <div class="filter-group">
                        <label>关键词搜索</label>
                        <input type="text" id="searchInput" placeholder="搜索标题、关键词、期刊...">
                    </div>
                    <div class="filter-group">
                        <label>主分类</label>
                        <select id="primaryFilter"><option value="">全部分类</option></select>
                    </div>
                    <div class="filter-group">
                        <label>副分类</label>
                        <select id="secondaryFilter"><option value="">全部</option></select>
                    </div>
                    <div class="filter-group">
                        <label>内容类型</label>
                        <select id="contentTypeFilter"><option value="">全部类型</option></select>
                    </div>
                </div>
                
                <div class="filter-row">
                    <div class="filter-group">
                        <label>研究阶段</label>
                        <select id="stageFilter"><option value="">全部阶段</option></select>
                    </div>
                    <div class="filter-group">
                        <label>重要性</label>
                        <select id="importanceFilter">
                            <option value="">全部</option>
                            <option value="high">⭐ 高 (8-10)</option>
                            <option value="medium">中 (5-7)</option>
                            <option value="low">低 (1-4)</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label>代码开源</label>
                        <select id="githubFilter">
                            <option value="">全部</option>
                            <option value="yes">✓ 有代码</option>
                            <option value="no">✗ 无代码</option>
                        </select>
                    </div>
                    <div class="filter-group">
                        <label>排序</label>
                        <select id="sortBy">
                            <option value="importance">按重要性</option>
                            <option value="year">按年份</option>
                            <option value="name">按文件名</option>
                            <option value="github">有代码优先</option>
                        </select>
                    </div>
                </div>
                
                <div class="filter-buttons">
                    <button class="btn btn-secondary" id="clearBtn">🔄 清除筛选</button>
                    <button class="btn btn-primary" id="favoritesBtn">⭐ 只看收藏</button>
                    <button class="btn btn-github" id="githubOnlyBtn">💻 只看有代码</button>
                </div>
            </div>
            
            <div class="papers-grid" id="papersGrid"></div>
        </div>
        
        <div class="modal" id="exportModal">
            <div class="modal-content">
                <h3>📥 导出收藏的文献</h3>
                <p style="color:var(--text-secondary);">已收藏 <strong id="favCount">0</strong> 篇文献</p>
                <div class="export-options" id="exportOptions"></div>
                <button class="btn btn-secondary" style="width:100%;margin-top:20px;" id="closeModalBtn">关闭</button>
            </div>
        </div>

    <script>
    (function() {
        var papers = __PAPERS_DATA__;
        var stats = __STATS_DATA__;

        var favorites = [];
        try { 
            var saved = localStorage.getItem('medai_fav');
            if (saved) favorites = JSON.parse(saved);
        } catch(e) { favorites = []; }
        
        var showOnlyFavorites = false;
        var currentTheme = localStorage.getItem('medai_theme') || 'dark';
        var charts = {};
        
        var withGithubCount = 0;
        var withoutGithubCount = 0;
        for (var i = 0; i < papers.length; i++) {
            if (papers[i].github_links && papers[i].github_links.length > 0) withGithubCount++;
            else withoutGithubCount++;
        }

        function escapeHtml(s) {
            if (!s) return '';
            var div = document.createElement('div');
            div.textContent = s;
            return div.innerHTML;
        }
        
        function escapeAttr(s) {
            if (!s) return '';
            return String(s).replace(/'/g, "&#39;").replace(/"/g, "&quot;");
        }

        function init() {
            applyTheme(currentTheme);
            initStats();
            initFilters();
            initCharts();
            initWordCloud();
            bindEvents();
            applyFilters();
        }
        
        function bindEvents() {
            document.getElementById('searchInput').addEventListener('input', applyFilters);
            document.getElementById('primaryFilter').addEventListener('change', applyFilters);
            document.getElementById('secondaryFilter').addEventListener('change', applyFilters);
            document.getElementById('contentTypeFilter').addEventListener('change', applyFilters);
            document.getElementById('stageFilter').addEventListener('change', applyFilters);
            document.getElementById('importanceFilter').addEventListener('change', applyFilters);
            document.getElementById('githubFilter').addEventListener('change', applyFilters);
            document.getElementById('sortBy').addEventListener('change', applyFilters);
            
            document.getElementById('themeBtn').addEventListener('click', toggleTheme);
            document.getElementById('clearBtn').addEventListener('click', clearFilters);
            document.getElementById('favoritesBtn').addEventListener('click', toggleFavorites);
            document.getElementById('githubOnlyBtn').addEventListener('click', function() {
                document.getElementById('githubFilter').value = 'yes';
                applyFilters();
            });
            
            document.getElementById('exportBtn').addEventListener('click', showExportModal);
            document.getElementById('closeModalBtn').addEventListener('click', closeExportModal);
            document.getElementById('exportModal').addEventListener('click', function(e) {
                if (e.target === this) closeExportModal();
            });
            
            var exportOptions = document.getElementById('exportOptions');
            exportOptions.innerHTML = 
                '<button class="export-btn" data-format="json">📄 JSON 格式</button>' +
                '<button class="export-btn" data-format="csv">📊 CSV 表格</button>' +
                '<button class="export-btn" data-format="md">📝 Markdown</button>' +
                '<button class="export-btn" data-format="html">🌐 HTML 网页</button>';
            exportOptions.addEventListener('click', function(e) {
                var btn = e.target.closest('.export-btn');
                if (btn) exportFavorites(btn.getAttribute('data-format'));
            });
        }

        function toggleTheme() {
            currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(currentTheme);
            localStorage.setItem('medai_theme', currentTheme);
            setTimeout(initCharts, 100);
        }

        function applyTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            document.getElementById('themeBtn').textContent = theme === 'dark' ? '☀️ 浅色' : '🌙 深色';
        }

        function initStats() {
            var html = '';
            html += '<div class="stat-card" data-action="clear"><div class="number">' + papers.length + '</div><div class="label">总计</div></div>';
            html += '<div class="stat-card high" data-filter="importance" data-value="high"><div class="number">' + (stats.high_importance || 0) + '</div><div class="label">高重要性</div></div>';
            html += '<div class="stat-card medium" data-filter="importance" data-value="medium"><div class="number">' + (stats.medium_importance || 0) + '</div><div class="label">中重要性</div></div>';
            html += '<div class="stat-card low" data-filter="importance" data-value="low"><div class="number">' + (stats.low_importance || 0) + '</div><div class="label">低重要性</div></div>';
            html += '<div class="stat-card github" data-filter="github" data-value="yes"><div class="number">' + withGithubCount + '</div><div class="label">有代码</div></div>';
            html += '<div class="stat-card" data-filter="github" data-value="no"><div class="number">' + withoutGithubCount + '</div><div class="label">无代码</div></div>';
            html += '<div class="stat-card" style="cursor:default"><div class="number" style="color:var(--text-primary)">' + favorites.length + '</div><div class="label">已收藏</div></div>';
            
            var grid = document.getElementById('statsGrid');
            grid.innerHTML = html;
            
            grid.addEventListener('click', function(e) {
                var card = e.target.closest('.stat-card');
                if (!card) return;
                if (card.getAttribute('data-action') === 'clear') clearFilters();
                else if (card.getAttribute('data-filter') === 'importance') {
                    document.getElementById('importanceFilter').value = card.getAttribute('data-value');
                    applyFilters();
                } else if (card.getAttribute('data-filter') === 'github') {
                    document.getElementById('githubFilter').value = card.getAttribute('data-value');
                    applyFilters();
                }
            });
        }

        function initFilters() {
            var cats = stats.primary_categories || {};
            var sel = document.getElementById('primaryFilter');
            Object.keys(cats).sort().forEach(function(k) {
                var opt = document.createElement('option');
                opt.value = k; opt.textContent = k + ' (' + cats[k] + ')';
                sel.appendChild(opt);
            });
            
            var cats2 = stats.secondary_categories || {};
            var sel2 = document.getElementById('secondaryFilter');
            Object.keys(cats2).forEach(function(k) {
                var opt = document.createElement('option');
                opt.value = k; opt.textContent = k + ' (' + cats2[k] + ')';
                sel2.appendChild(opt);
            });
            
            var types = stats.content_types || {};
            var sel3 = document.getElementById('contentTypeFilter');
            Object.keys(types).forEach(function(k) {
                if (k && k !== '未知') {
                    var opt = document.createElement('option');
                    opt.value = k; opt.textContent = k;
                    sel3.appendChild(opt);
                }
            });
            
            var stages = stats.research_stages || {};
            var sel4 = document.getElementById('stageFilter');
            Object.keys(stages).forEach(function(k) {
                if (k && k !== '未知') {
                    var opt = document.createElement('option');
                    opt.value = k; opt.textContent = k;
                    sel4.appendChild(opt);
                }
            });
        }

        function initCharts() {
            if (typeof Chart === 'undefined') return;
            
            var textColor = currentTheme === 'dark' ? '#f0f0f0' : '#1e293b';
            var gridColor = currentTheme === 'dark' ? '#374151' : '#e2e8f0';
            var colors = ['#06b6d4', '#8b5cf6', '#f59e0b', '#ef4444', '#22c55e', '#ec4899', '#6366f1', '#14b8a6'];
            
            for (var k in charts) { if (charts[k]) charts[k].destroy(); }
            charts = {};
            
            var ctx1 = document.getElementById('primaryChart');
            if (ctx1) {
                var data1 = stats.primary_categories || {};
                var labels1 = Object.keys(data1);
                var values1 = Object.values(data1);
                charts.primary = new Chart(ctx1, {
                    type: 'doughnut',
                    data: { labels: labels1, datasets: [{ data: values1, backgroundColor: colors, borderWidth: 0 }] },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        cutout: '65%',
                        plugins: { 
                            legend: { position: 'right', labels: { color: textColor, font: { size: 11 }, padding: 12, usePointStyle: true } }
                        },
                        onClick: function(e, el) {
                            if (el && el.length > 0) {
                                document.getElementById('primaryFilter').value = labels1[el[0].index];
                                applyFilters();
                            }
                        }
                    }
                });
            }
            
            var ctx2 = document.getElementById('secondaryChart');
            if (ctx2) {
                var data2 = stats.secondary_categories || {};
                var arr2 = [];
                for (var k in data2) { if (data2.hasOwnProperty(k)) arr2.push({ name: k, count: data2[k] }); }
                arr2.sort(function(a, b) { return b.count - a.count; });
                arr2 = arr2.slice(0, 8);
                charts.secondary = new Chart(ctx2, {
                    type: 'bar',
                    data: { 
                        labels: arr2.map(function(x) { return x.name.length > 10 ? x.name.substr(0, 10) + '..' : x.name; }), 
                        datasets: [{ data: arr2.map(function(x) { return x.count; }), backgroundColor: '#8b5cf6', borderRadius: 6 }] 
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false, indexAxis: 'y',
                        plugins: { legend: { display: false } },
                        scales: { 
                            x: { ticks: { color: textColor }, grid: { color: gridColor, drawBorder: false } }, 
                            y: { ticks: { color: textColor, font: { size: 11 } }, grid: { display: false } } 
                        }
                    }
                });
            }
        }

        function initWordCloud() {
            var kw = stats.keywords || {};
            var arr = [];
            for (var k in kw) { if (kw.hasOwnProperty(k) && k && k.length > 1) arr.push({ word: k, count: kw[k] }); }
            arr.sort(function(a, b) { return b.count - a.count; });
            arr = arr.slice(0, 25);
            
            var container = document.getElementById('wordCloud');
            if (arr.length === 0) {
                container.innerHTML = '<span style="color:var(--text-secondary)">暂无数据</span>';
                return;
            }
            
            var max = arr[0].count, min = arr[arr.length - 1].count;
            var colors = ['#06b6d4', '#8b5cf6', '#f59e0b', '#22c55e', '#ec4899', '#6366f1'];
            var html = '';
            for (var i = 0; i < arr.length; i++) {
                var item = arr[i];
                var ratio = max > min ? (item.count - min) / (max - min) : 0.5;
                var size = 13 + ratio * 16;
                html += '<span style="font-size:' + size + 'px;color:' + colors[i % colors.length] + ';font-weight:' + (500 + Math.round(ratio * 200)) + '" data-word="' + escapeAttr(item.word) + '">' + escapeHtml(item.word) + '</span> ';
            }
            container.innerHTML = html;
            container.onclick = function(e) {
                if (e.target.tagName === 'SPAN' && e.target.getAttribute('data-word')) {
                    document.getElementById('searchInput').value = e.target.getAttribute('data-word');
                    applyFilters();
                }
            };
        }

        function applyFilters() {
            var filtered = papers.slice();
            
            var search = (document.getElementById('searchInput').value || '').toLowerCase().trim();
            if (search) {
                filtered = filtered.filter(function(p) {
                    return (p.title || '').toLowerCase().indexOf(search) >= 0 || 
                        (p.title_cn || '').toLowerCase().indexOf(search) >= 0 || 
                        (p.keywords || []).join(' ').toLowerCase().indexOf(search) >= 0 || 
                        (p.journal_conference || '').toLowerCase().indexOf(search) >= 0;
                });
            }
            
            var primary = document.getElementById('primaryFilter').value;
            if (primary) filtered = filtered.filter(function(p) { return p.primary_category === primary; });
            
            var secondary = document.getElementById('secondaryFilter').value;
            if (secondary) filtered = filtered.filter(function(p) { return (p.secondary_categories || []).indexOf(secondary) >= 0; });
            
            var contentType = document.getElementById('contentTypeFilter').value;
            if (contentType) filtered = filtered.filter(function(p) { return p.content_type === contentType; });
            
            var stage = document.getElementById('stageFilter').value;
            if (stage) filtered = filtered.filter(function(p) { return p.research_stage === stage; });
            
            var imp = document.getElementById('importanceFilter').value;
            if (imp === 'high') filtered = filtered.filter(function(p) { return (p.importance_score || 0) >= 8; });
            else if (imp === 'medium') filtered = filtered.filter(function(p) { var s = p.importance_score || 0; return s >= 5 && s < 8; });
            else if (imp === 'low') filtered = filtered.filter(function(p) { return (p.importance_score || 0) < 5; });
            
            var gh = document.getElementById('githubFilter').value;
            if (gh === 'yes') filtered = filtered.filter(function(p) { return p.github_links && p.github_links.length > 0; });
            else if (gh === 'no') filtered = filtered.filter(function(p) { return !p.github_links || p.github_links.length === 0; });
            
            if (showOnlyFavorites) filtered = filtered.filter(function(p) { return favorites.indexOf(p.file_hash) >= 0; });
            
            var sortBy = document.getElementById('sortBy').value;
            if (sortBy === 'importance') filtered.sort(function(a, b) { return (b.importance_score || 0) - (a.importance_score || 0); });
            else if (sortBy === 'name') filtered.sort(function(a, b) { return (a.file_name || '').localeCompare(b.file_name || ''); });
            else if (sortBy === 'year') filtered.sort(function(a, b) { return (b.publication_year || '').localeCompare(a.publication_year || ''); });
            else if (sortBy === 'github') {
                filtered.sort(function(a, b) {
                    var aH = (a.github_links && a.github_links.length > 0) ? 1 : 0;
                    var bH = (b.github_links && b.github_links.length > 0) ? 1 : 0;
                    return bH !== aH ? bH - aH : (b.importance_score || 0) - (a.importance_score || 0);
                });
            }
            
            renderPapers(filtered);
            document.getElementById('resultsCount').textContent = filtered.length + ' / ' + papers.length + ' 篇文献';
        }

        function renderPapers(list) {
            var grid = document.getElementById('papersGrid');
            if (!list || list.length === 0) {
                grid.innerHTML = '<div class="no-results"><h3>未找到匹配的文献</h3><p>尝试调整筛选条件</p></div>';
                return;
            }
            
            var html = '';
            for (var i = 0; i < list.length; i++) {
                var p = list[i];
                var score = p.importance_score || 5;
                var impClass = score >= 8 ? 'high' : (score >= 5 ? 'medium' : 'low');
                var isFav = favorites.indexOf(p.file_hash) >= 0;
                var hasGithub = p.github_links && p.github_links.length > 0;
                var diseases = (p.diseases || []).filter(function(d) { return d && d !== '未提及' && d !== '未知'; });
                
                html += '<div class="paper-card' + (hasGithub ? ' has-github' : '') + '" data-hash="' + escapeAttr(p.file_hash) + '">';
                html += '<div class="paper-header"><div style="flex:1;min-width:0">';
                html += '<div class="paper-title">' + escapeHtml(p.title || p.file_name);
                if (hasGithub) html += '<span class="github-badge">💻 开源</span>';
                html += '</div>';
                if (p.title_cn) html += '<div class="paper-title-cn">' + escapeHtml(p.title_cn) + '</div>';
                
                var journalParts = [];
                if (p.journal_conference) journalParts.push(p.journal_conference);
                if (p.publication_year) journalParts.push(p.publication_year);
                if (journalParts.length > 0) html += '<div class="paper-journal">📰 ' + escapeHtml(journalParts.join(' · ')) + '</div>';
                
                if (p.authors && p.authors.length) {
                    html += '<div class="paper-meta">👤 ' + escapeHtml(p.authors.slice(0, 3).join(', ')) + (p.authors.length > 3 ? ' 等' : '') + '</div>';
                }
                html += '</div>';
                html += '<div class="action-area">';
                html += '<div class="importance-badge importance-' + impClass + '">' + score + '</div>';
                html += '<button class="favorite-btn' + (isFav ? ' active' : '') + '" data-hash="' + escapeAttr(p.file_hash) + '">' + (isFav ? '⭐' : '☆') + '</button>';
                html += '</div></div>';
                
                html += '<div class="tags">';
                if (p.primary_category) html += '<span class="tag tag-primary" data-filter="primary" data-value="' + escapeAttr(p.primary_category) + '">' + escapeHtml(p.primary_category) + '</span>';
                (p.secondary_categories || []).slice(0, 2).forEach(function(c) { html += '<span class="tag tag-secondary">' + escapeHtml(c) + '</span>'; });
                if (p.content_type && p.content_type !== '未知') html += '<span class="tag tag-type">' + escapeHtml(p.content_type) + '</span>';
                html += '</div>';
                
                if (diseases.length > 0) {
                    html += '<div class="tags">';
                    diseases.slice(0, 3).forEach(function(d) { html += '<span class="tag tag-disease">' + escapeHtml(d) + '</span>'; });
                    html += '</div>';
                }
                
                var kws = (p.keywords || []).slice(0, 5);
                if (kws.length > 0) {
                    html += '<div class="keywords">';
                    kws.forEach(function(k) { html += '<span class="keyword" data-word="' + escapeAttr(k) + '">' + escapeHtml(k) + '</span>'; });
                    html += '</div>';
                }
                
                if (hasGithub) {
                    html += '<div class="github-links">';
                    p.github_links.slice(0, 2).forEach(function(link) {
                        var name = 'GitHub';
                        var m = link.match(/github\.com\/([^\/]+\/[^\/]+)/i);
                        if (m) name = m[1];
                        html += '<a href="' + escapeAttr(link) + '" target="_blank" rel="noopener" class="github-link">🔗 ' + escapeHtml(name) + '</a>';
                    });
                    html += '</div>';
                }
                
                html += '<button class="expand-btn">展开详情 ▼</button>';
                html += '<div class="details">';
                if (p.abstract_cn) html += '<div class="detail-section"><h4>📄 摘要</h4><p>' + escapeHtml(p.abstract_cn) + '</p></div>';
                if (p.research_objective) html += '<div class="detail-section"><h4>🎯 研究目标</h4><p>' + escapeHtml(p.research_objective) + '</p></div>';
                if (p.key_findings && p.key_findings.length) {
                    html += '<div class="detail-section"><h4>🔍 关键发现</h4><ul>';
                    p.key_findings.forEach(function(f) { html += '<li>' + escapeHtml(f) + '</li>'; });
                    html += '</ul></div>';
                }
                if (p.innovations && p.innovations.length) {
                    html += '<div class="detail-section"><h4>💡 创新点</h4><ul>';
                    p.innovations.forEach(function(f) { html += '<li>' + escapeHtml(f) + '</li>'; });
                    html += '</ul></div>';
                }
                if (p.methodology) html += '<div class="detail-section"><h4>🔬 方法论</h4><p>' + escapeHtml(p.methodology) + '</p></div>';
                if (diseases.length > 0) html += '<div class="detail-section"><h4>🩺 研究病种</h4><p>' + escapeHtml(diseases.join('、')) + '</p></div>';
                if (p.technologies && p.technologies.length) html += '<div class="detail-section"><h4>🛠️ 技术栈</h4><p>' + escapeHtml(p.technologies.join('、')) + '</p></div>';
                if (p.importance_reason) html += '<div class="detail-section"><h4>⭐ 重要性分析</h4><p>' + escapeHtml(p.importance_reason) + '</p></div>';
                html += '<div class="detail-section"><h4>📁 文件信息</h4><p>' + escapeHtml(p.file_name) + '</p></div>';
                html += '</div></div>';
            }
            
            grid.innerHTML = html;
            
            grid.onclick = function(e) {
                var target = e.target;
                if (target.classList.contains('favorite-btn')) {
                    toggleFavorite(target.getAttribute('data-hash'));
                } else if (target.classList.contains('expand-btn')) {
                    var details = target.nextElementSibling;
                    var isShown = details.classList.toggle('show');
                    target.textContent = isShown ? '收起详情 ▲' : '展开详情 ▼';
                } else if (target.getAttribute('data-filter') === 'primary') {
                    document.getElementById('primaryFilter').value = target.getAttribute('data-value');
                    applyFilters();
                } else if (target.classList.contains('keyword')) {
                    document.getElementById('searchInput').value = target.getAttribute('data-word');
                    applyFilters();
                }
            };
        }

        function toggleFavorite(hash) {
            var idx = favorites.indexOf(hash);
            if (idx >= 0) favorites.splice(idx, 1);
            else favorites.push(hash);
            try { localStorage.setItem('medai_fav', JSON.stringify(favorites)); } catch(e) {}
            initStats();
            updateFavCount();
            applyFilters();
        }

        function toggleFavorites() {
            showOnlyFavorites = !showOnlyFavorites;
            document.getElementById('favoritesBtn').classList.toggle('active', showOnlyFavorites);
            applyFilters();
        }

        function updateFavCount() {
            document.getElementById('favCount').textContent = favorites.length;
        }

        function clearFilters() {
            document.getElementById('searchInput').value = '';
            document.getElementById('primaryFilter').value = '';
            document.getElementById('secondaryFilter').value = '';
            document.getElementById('contentTypeFilter').value = '';
            document.getElementById('stageFilter').value = '';
            document.getElementById('importanceFilter').value = '';
            document.getElementById('githubFilter').value = '';
            document.getElementById('sortBy').value = 'importance';
            showOnlyFavorites = false;
            document.getElementById('favoritesBtn').classList.remove('active');
            applyFilters();
        }

        function showExportModal() {
            updateFavCount();
            document.getElementById('exportModal').classList.add('show');
        }

        function closeExportModal() {
            document.getElementById('exportModal').classList.remove('show');
        }

        function exportFavorites(fmt) {
            var favPapers = papers.filter(function(p) { return favorites.indexOf(p.file_hash) >= 0; });
            if (favPapers.length === 0) { alert('请先收藏一些文献'); return; }
            
            var content, filename, mime;
            var ts = new Date().toISOString().slice(0, 10);
            
            if (fmt === 'json') {
                content = JSON.stringify(favPapers, null, 2);
                filename = 'favorites_' + ts + '.json';
                mime = 'application/json';
            } else if (fmt === 'csv') {
                var rows = [['标题', '中文标题', '期刊', '年份', '分类', '重要性', 'GitHub']];
                favPapers.forEach(function(p) {
                    rows.push([p.title || '', p.title_cn || '', p.journal_conference || '', p.publication_year || '', p.primary_category || '', p.importance_score || '', (p.github_links || []).join(';')]);
                });
                content = '\uFEFF' + rows.map(function(r) { return r.map(function(c) { return '"' + String(c).replace(/"/g, '""') + '"'; }).join(','); }).join('\n');
                filename = 'favorites_' + ts + '.csv';
                mime = 'text/csv';
            } else if (fmt === 'md') {
                content = '# 收藏的医学AI文献\n\n';
                favPapers.forEach(function(p, i) {
                    content += '## ' + (i + 1) + '. ' + (p.title || p.file_name) + '\n\n';
                    if (p.title_cn) content += '> ' + p.title_cn + '\n\n';
                    if (p.journal_conference) content += '**期刊**: ' + p.journal_conference + (p.publication_year ? ' (' + p.publication_year + ')' : '') + '\n\n';
                    content += '**重要性**: ' + (p.importance_score || 5) + '/10\n\n';
                    if (p.github_links && p.github_links.length) p.github_links.forEach(function(l) { content += '- ' + l + '\n'; });
                    content += '\n---\n\n';
                });
                filename = 'favorites_' + ts + '.md';
                mime = 'text/markdown';
            } else if (fmt === 'html') {
                content = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>收藏</title><style>body{font-family:system-ui,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;background:#0f0f1a;color:#f0f0f0}.paper{background:#232342;padding:20px;margin:20px 0;border-radius:12px;border-left:4px solid #06b6d4}h1{color:#06b6d4}a{color:#8b5cf6}</style></head><body><h1>收藏的文献</h1>';
                favPapers.forEach(function(p, i) {
                    content += '<div class="paper"><h3>' + (i + 1) + '. ' + escapeHtml(p.title || p.file_name) + '</h3>';
                    if (p.title_cn) content += '<p style="opacity:0.7">' + escapeHtml(p.title_cn) + '</p>';
                    if (p.journal_conference) content += '<p style="color:#06b6d4">' + escapeHtml(p.journal_conference) + (p.publication_year ? ' · ' + p.publication_year : '') + '</p>';
                    if (p.github_links && p.github_links.length) p.github_links.forEach(function(l) { content += '<a href="' + l + '" target="_blank">GitHub</a> '; });
                    content += '</div>';
                });
                content += '</body></html>';
                filename = 'favorites_' + ts + '.html';
                mime = 'text/html';
            } else return;
            
            try {
                var blob = new Blob([content], { type: mime + ';charset=utf-8' });
                var a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = filename;
                a.click();
            } catch(e) { alert('导出失败'); }
            closeExportModal();
        }

        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
        else init();
    })();
    </script>
    </body>
    </html>'''
        
        html = html.replace('__PAPERS_DATA__', data_json)
        html = html.replace('__STATS_DATA__', stats_json)
        
        return html


# ============ 主程序入口 ============

def main():
    """主函数"""
    console.print(Panel.fit(
        "[bold cyan]医学AI文献批量分析系统[/bold cyan]\n"
        "[dim]基于 Ollama + Qwen2.5:14B + WSL2[/dim]",
        border_style="cyan"
    ))
    
    # 检查PDF文件夹
    if not PDF_FOLDER.exists():
        console.print(f"[red]错误: PDF文件夹不存在: {PDF_FOLDER}[/red]")
        console.print("[yellow]请在 config.py 中设置正确的 PDF_FOLDER 路径[/yellow]")
        return
    
    # 创建分析器并运行
    analyzer = PaperBatchAnalyzer(PDF_FOLDER)
    results = analyzer.run()
    
    if results:
        # 生成报告
        generator = ReportGenerator(results)
        generator.generate_all()
        
        # 显示结果摘要
        console.print("\n")
        table = Table(title="分析结果摘要")
        table.add_column("指标", style="cyan")
        table.add_column("数值", style="green")
        
        success = sum(1 for r in results if r.status == "success")
        high_imp = sum(1 for r in results if r.importance_score >= 8)
        with_github = sum(1 for r in results if r.github_links)
        
        table.add_row("总文档数", str(len(results)))
        table.add_row("成功分析", str(success))
        table.add_row("高重要性(8-10)", str(high_imp))
        table.add_row("包含GitHub链接", str(with_github))
        
        console.print(table)
        
        console.print(f"\n[bold green]✅ 分析完成！[/bold green]")
        console.print(f"[cyan]请查看输出文件夹: {OUTPUT_FOLDER}[/cyan]")
        console.print(f"[cyan]在浏览器中打开 {HTML_OUTPUT} 查看交互式报告[/cyan]")
    else:
        console.print("[yellow]没有成功分析任何文献[/yellow]")


if __name__ == "__main__":
    main()