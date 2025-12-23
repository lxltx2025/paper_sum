# Medical AI Literature Batch Analysis System  

An intelligent literature analysis tool based on **Ollama + Qwen2.5:14B + WSL2**, designed specifically for researchers in the field of Medical AI.  

# I. Project Overview  

This system offers two core functions:  

1. **Intelligent Literature Analysis** - Batch analyze PDF literature and extract structured information  
2. **Efficient Paper Download** - Automatically download academic papers from multiple open-access sources  

----

## 1-1: Literature Analysis Function  

- 📚 Batch processing of PDF documents (supports any quantity)  
- 🤖 AI-powered analysis based on large language models (e.g., Qwen2.5:14B)  
- 🏷️ Automatic generation of structured abstracts and Chinese/English titles  
- 🔍 Extraction of keywords, diseases, technologies, and dataset information  
- 🔗 Automatic identification and extraction of GitHub code links  
- 📊 Multi-format report output (JSON, CSV, Markdown, HTML)  
- 🎯 Intelligent classification and importance scoring  
- 📈 Interactive HTML visualization reports  

----

## 1-2: Paper Download Function  

- 🌐 Support for 15+ academic data sources (Unpaywall, PMC, Sci-Hub, LibGen, etc.)  
- 🔄 Intelligent retry and multi-mirror switching  
- ⚡ High-concurrency asynchronous downloading  
- ✅ Automatic PDF validity verification  
- 📝 Detailed download logs [3](#0-2)  

---

# II. System Requirements  

> Hardware Requirements  

- **Memory**: 16GB or more recommended  
- **Storage**: At least 10GB of available space  
- **GPU**: Optional (model parameter scale determined by video memory)  

----

> Software Environment  

- **Operating System**: Windows/WSL2/Linux  
- **Python**: 3.8+  
- **Ollama**: Latest version  
- **Network**: Stable internet connection (for model and paper downloads)  

---

# III. Installation Steps  

> Install Ollama  

```bash
# Linux/WSL2
curl -fsSL https://ollama.com/install.sh | sh

# macOS
brew install ollama
```

> Download Qwen2.5:14B Model  

```bash
ollama pull qwen2.5:14b
```

> Clone the Project  

```bash
git clone https://github.com/lxltx2025/paper_sum.git
cd paper_sum
```

> Install Python Dependencies  

```bash
pip install -r requirements.txt
```

Key dependencies include:  

- `requests` - HTTP requests  
- `pandas` - Data processing  
- `tqdm` - Progress bar display  
- `rich` - Terminal beautification output  
- `PyMuPDF` (fitz) - PDF text extraction  
- `pdfplumber` - Alternative PDF processing  
- `aiohttp` - Asynchronous HTTP requests [5](#0-4)  

----

# IV. Configuration Instructions  

Edit the `config.py` file for configuration.  

> PDF Folder Path  

```python
PDF_FOLDER = Path("/mnt/d/repro/paper_sum/multi_omics_papers")
```

Modify to your actual PDF folder path.  

> Ollama Service Configuration  

```python
OLLAMA_BASE_URL = "http://localhost:11434" # Local runtime
OLLAMA_MODEL = "qwen2.5:14b"
```

> PDF Processing Parameters  

- `MAX_PAGES_TO_ANALYZE`: Maximum pages to analyze per PDF (50 pages by default)  
- `MAX_TEXT_LENGTH`: Maximum text length sent to LLM (12,000 characters by default)  
- `MIN_TEXT_LENGTH`: Minimum length for valid text (100 characters by default)  

> Output Folder  

```python
OUTPUT_FOLDER = Path("./multi_omics_output")
```

Analysis results will be saved in this folder.  

----

# V. Usage Methods  

> Method 1: Use Startup Script (Recommended)  

```bash
bash run.sh
```

The script automatically checks the environment, starts the Ollama service, and runs the analysis.  

> Method 2: Run Python Directly  

```bash
# 1. Start Ollama service (if not running)
ollama serve

# 2. Run literature analysis
python3 analyzer.py

# 3. Run paper download (optional)
python3 get_paper.py
```

---

# VI. Output File Description  

After analysis, the following files will be generated in the output folder:  

> analysis_results.json  

Complete analysis results in JSON format, including all extracted fields.  

> analysis_results.csv  

Tabular analysis results, openable with Excel.  

> summary_report.md  

Summary report in Markdown format, including:  

- Statistical overview  
- Main category distribution  
- Literature details sorted by importance  

> interactive_report.html  

Interactive visualization report, including:  

- Dynamic statistical cards  
- Chart visualizations (category distribution, year trends, keyword cloud)  
- Filterable literature list  
- Support for filtering by keywords, categories, years, etc.  

----

> Team Introduction  

The LXLTX-Lab is a research team composed mainly of masters and doctors from China and abroad, covering mainstream Medical AI research fields such as radiomics, pathomics, and genomics.  

Explore our query system for over 980 public medical image datasets and replay recordings of the latest medical-engineering cross-disciplinary frontier forums!  

Our mission is to bring together top talents worldwide, build a Medical AI ecosystem, and promote the translation of Medical AI from the laboratory to clinical practice. We look forward to your joining!  

For more information, visit our official website: https://www.lxltx.site/