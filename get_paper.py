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
高成功率学术文献下载器 v4.0
- 修复API调用问题
- 增强Sci-Hub/LibGen访问能力
- 添加代理支持和重试机制
- 新增更多备用下载源
"""

import pandas as pd
import aiohttp
import asyncio
import os
import time
import re
import json
import random
import ssl
from urllib.parse import urljoin, quote, urlparse, unquote
from pathlib import Path
import logging
from typing import Optional, Dict, List, Tuple, Set
from dataclasses import dataclass
import certifi

try:
    from tqdm.asyncio import tqdm as async_tqdm
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download_log.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    success: bool
    source: str
    content: Optional[bytes] = None
    error: Optional[str] = None


@dataclass  
class DownloadTask:
    doi: str
    clean_doi: str
    index: int
    metadata: Optional[Dict] = None
    filepath: Optional[Path] = None


class HighSuccessRateDownloader:
    """高成功率学术论文下载器"""
    
    def __init__(self,
                 output_dir: str = "downloaded_papers",
                 unpaywall_email: str = None,
                 max_concurrent: int = 8,
                 timeout: int = 60,
                 proxy: str = None):
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.unpaywall_email = unpaywall_email or "academic.research@gmail.com"
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.proxy = proxy
        
        self.failed_dir = self.output_dir / "failed_records"
        self.failed_dir.mkdir(exist_ok=True)
        
        # ========== 扩展的Sci-Hub镜像列表 ==========
        self.scihub_mirrors = [
            # 主要镜像
            "https://sci-hub.se",
            "https://sci-hub.st",
            "https://sci-hub.ru",
            "https://sci-hub.ren",
            "https://sci-hub.ee",
            "https://sci-hub.wf",
            # 备用镜像
            "https://sci-hub.hkvisa.net",
            "https://sci-hub.yncjkj.com", 
            "https://sci-hub.shop",
            "https://sci-hub.mksa.top",
            "https://sci-hub.webcn.top",
            "https://sci-hub.tf",
            "https://sci-hub.yt",
            # 中国镜像
            "https://www.sci-hub.ren",
            "https://sci-hub.org.cn",
            "https://sci-hub.net.cn",
        ]
        
        # ========== 扩展的LibGen镜像列表 ==========
        self.libgen_mirrors = [
            "https://libgen.rs",
            "https://libgen.is",
            "https://libgen.st",
            "https://libgen.li",
            "https://libgen.rocks",
            "https://libgen.lc",
            "https://libgen.gs",
            "http://gen.lib.rus.ec",
        ]
        
        # LibGen下载镜像
        self.libgen_download_mirrors = [
            "https://download.library.lol",
            "http://library.lol",
            "https://libgen.rocks/get.php",
            "http://libgen.lc/get.php",
        ]
        
        # User-Agent池
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0',
        ]
        
        # 可用镜像缓存
        self.working_scihub: List[str] = []
        self.working_libgen: List[str] = []
        
        # 统计
        self.stats = {'success': 0, 'failed': 0, 'skipped': 0}
        self.failed_dois: List[Dict] = []
        self.source_stats: Dict[str, int] = {}
        self.downloaded_dois: Set[str] = set()
        self.semaphore: Optional[asyncio.Semaphore] = None
        
        # DOI到MD5的缓存（用于LibGen）
        self.doi_md5_cache: Dict[str, str] = {}
    
    def _get_headers(self, referer: str = None) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }
        if referer:
            headers['Referer'] = referer
        return headers
    
    def _get_ssl_context(self):
        """获取SSL上下文（解决证书问题）"""
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
    
    def clean_doi(self, doi) -> Optional[str]:
        """清理DOI格式"""
        if pd.isna(doi) or not doi:
            return None
        
        doi = str(doi).strip()
        
        prefixes = [
            'https://doi.org/', 'http://doi.org/', 'doi.org/',
            'https://dx.doi.org/', 'http://dx.doi.org/',
            'doi:', 'DOI:', 'DOI ', 'doi '
        ]
        for prefix in prefixes:
            if doi.lower().startswith(prefix.lower()):
                doi = doi[len(prefix):]
        
        doi = doi.strip().rstrip('.')
        doi = unquote(doi)  # URL解码
        
        if re.match(r'^10\.\d{4,}/\S+$', doi):
            return doi
        
        match = re.search(r'(10\.\d{4,}/[^\s]+)', doi)
        if match:
            return match.group(1).rstrip('.')
        
        return None
    
    def clean_filename(self, filename: str, max_length: int = 80) -> str:
        """清理文件名"""
        illegal_chars = '<>:"/\\|?*\n\r\t'
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        filename = re.sub(r'[_\s]+', '_', filename)
        filename = filename.strip('_. ')
        
        if len(filename) > max_length:
            filename = filename[:max_length].rstrip('_. ')
        
        return filename or "unknown"
    
    def is_valid_pdf(self, content: bytes) -> bool:
        """验证是否为有效PDF"""
        if not content or len(content) < 1024:
            return False
        
        if content[:4] != b'%PDF':
            return False
        
        if len(content) < 5000:
            return False
        
        error_markers = [
            b'<!DOCTYPE html', b'<html', b'Access Denied',
            b'403 Forbidden', b'404 Not Found', b'captcha',
            b'robot', b'rate limit', b'too many requests',
            b'Please wait', b'checking your browser',
            b'cf-browser-verification', b'Just a moment'
        ]
        
        header = content[:3000].lower()
        for marker in error_markers:
            if marker.lower() in header:
                return False
        
        return True
    
    async def _create_session(self) -> aiohttp.ClientSession:
        """创建带SSL忽略的会话"""
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 3,
            limit_per_host=10,
            ttl_dns_cache=300,
            ssl=False,  # 忽略SSL验证
            enable_cleanup_closed=True
        )
        
        timeout = aiohttp.ClientTimeout(
            total=self.timeout,
            connect=15,
            sock_read=45
        )
        
        return aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            trust_env=True
        )
    
    async def _fetch_with_retry(self, session: aiohttp.ClientSession,
                                 url: str, 
                                 max_retries: int = 3,
                                 timeout: int = 30,
                                 is_json: bool = False,
                                 referer: str = None) -> Optional[bytes]:
        """带重试的获取"""
        for attempt in range(max_retries):
            try:
                headers = self._get_headers(referer)
                if is_json:
                    headers['Accept'] = 'application/json'
                
                async with session.get(
                    url, 
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                    proxy=self.proxy
                ) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    elif resp.status == 429:  # Rate limit
                        await asyncio.sleep(2 ** attempt)
                    elif resp.status in [403, 503]:
                        await asyncio.sleep(1)
                        
            except asyncio.TimeoutError:
                logger.debug(f"超时 (尝试 {attempt+1}/{max_retries}): {url}")
            except Exception as e:
                logger.debug(f"请求失败 (尝试 {attempt+1}/{max_retries}): {url} - {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
        
        return None
    
    async def _fetch_json(self, session: aiohttp.ClientSession,
                          url: str, timeout: int = 20) -> Optional[Dict]:
        """获取JSON"""
        content = await self._fetch_with_retry(session, url, timeout=timeout, is_json=True)
        if content:
            try:
                return json.loads(content)
            except:
                pass
        return None
    
    async def _fetch_pdf(self, session: aiohttp.ClientSession,
                         url: str, timeout: int = 45,
                         referer: str = None) -> Optional[bytes]:
        """获取PDF"""
        content = await self._fetch_with_retry(
            session, url, timeout=timeout, referer=referer
        )
        if content and self.is_valid_pdf(content):
            return content
        return None
    
    async def get_paper_metadata(self, session: aiohttp.ClientSession,
                                  doi: str) -> Optional[Dict]:
        """获取论文元数据"""
        url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
        data = await self._fetch_json(session, url)
        
        if data:
            message = data.get('message', {})
            title = message.get('title', ['Unknown'])[0] if message.get('title') else 'Unknown'
            
            authors = message.get('author', [])
            first_author = authors[0].get('family', 'Unknown') if authors else 'Unknown'
            
            year = 'Unknown'
            for date_field in ['published-print', 'published-online', 'created']:
                date_parts = message.get(date_field, {}).get('date-parts', [[None]])
                if date_parts and date_parts[0] and date_parts[0][0]:
                    year = date_parts[0][0]
                    break
            
            return {
                'title': title,
                'first_author': first_author,
                'year': year,
                'container': message.get('container-title', [''])[0] if message.get('container-title') else ''
            }
        
        return None
    
    # ==================== 下载源实现 ====================
    
    async def _download_from_unpaywall(self, session: aiohttp.ClientSession,
                                        doi: str) -> Optional[bytes]:
        """Unpaywall - 开放获取聚合"""
        try:
            url = f"https://api.unpaywall.org/v2/{quote(doi, safe='')}?email={self.unpaywall_email}"
            data = await self._fetch_json(session, url)
            
            if not data:
                return None
            
            pdf_urls = []
            
            # 最佳OA位置
            best_oa = data.get('best_oa_location')
            if best_oa:
                for key in ['url_for_pdf', 'url_for_landing_page', 'url']:
                    if best_oa.get(key):
                        pdf_urls.append(best_oa[key])
            
            # 所有OA位置
            for loc in data.get('oa_locations', []):
                for key in ['url_for_pdf', 'url']:
                    if loc.get(key):
                        pdf_urls.append(loc[key])
            
            # 去重并尝试下载
            seen = set()
            for url in pdf_urls:
                if url in seen:
                    continue
                seen.add(url)
                
                content = await self._fetch_pdf(session, url)
                if content:
                    return content
                
                # 如果不是PDF链接，尝试从页面提取
                if not url.endswith('.pdf'):
                    try:
                        page_content = await self._fetch_with_retry(session, url, timeout=20)
                        if page_content:
                            extracted = await self._extract_pdf_from_html(
                                session, page_content.decode('utf-8', errors='ignore'), url
                            )
                            if extracted:
                                return extracted
                    except:
                        pass
        
        except Exception as e:
            logger.debug(f"Unpaywall失败 {doi}: {e}")
        
        return None
    
    async def _download_from_pmc(self, session: aiohttp.ClientSession,
                                  doi: str) -> Optional[bytes]:
        """PubMed Central"""
        try:
            # 方法1: ID转换API
            url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={quote(doi)}&format=json"
            data = await self._fetch_json(session, url)
            
            if data:
                for record in data.get('records', []):
                    pmcid = record.get('pmcid')
                    if pmcid:
                        # 多种PDF URL格式
                        pdf_urls = [
                            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/",
                            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/main.pdf",
                            f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf",
                        ]
                        
                        for pdf_url in pdf_urls:
                            content = await self._fetch_pdf(session, pdf_url)
                            if content:
                                return content
            
            # 方法2: 直接搜索
            search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term={quote(doi)}[DOI]&retmode=json"
            search_data = await self._fetch_json(session, search_url)
            
            if search_data:
                id_list = search_data.get('esearchresult', {}).get('idlist', [])
                for pmid in id_list[:3]:
                    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmid}/pdf/"
                    content = await self._fetch_pdf(session, pdf_url)
                    if content:
                        return content
        
        except Exception as e:
            logger.debug(f"PMC失败 {doi}: {e}")
        
        return None
    
    async def _download_from_europe_pmc(self, session: aiohttp.ClientSession,
                                         doi: str) -> Optional[bytes]:
        """Europe PMC"""
        try:
            url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{quote(doi)}&format=json&resultType=core"
            data = await self._fetch_json(session, url)
            
            if data:
                results = data.get('resultList', {}).get('result', [])
                for result in results:
                    pmcid = result.get('pmcid')
                    if pmcid:
                        pdf_urls = [
                            f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf",
                            f"https://europepmc.org/articles/{pmcid}?pdf=render",
                        ]
                        
                        for pdf_url in pdf_urls:
                            content = await self._fetch_pdf(session, pdf_url)
                            if content:
                                return content
                    
                    # 检查全文URL
                    full_text_urls = result.get('fullTextUrlList', {}).get('fullTextUrl', [])
                    for ft in full_text_urls:
                        if ft.get('documentStyle') == 'pdf':
                            content = await self._fetch_pdf(session, ft.get('url'))
                            if content:
                                return content
        
        except Exception as e:
            logger.debug(f"EuropePMC失败 {doi}: {e}")
        
        return None
    
    async def _download_from_openalex(self, session: aiohttp.ClientSession,
                                       doi: str) -> Optional[bytes]:
        """OpenAlex"""
        try:
            url = f"https://api.openalex.org/works/doi:{quote(doi, safe='')}"
            data = await self._fetch_json(session, url)
            
            if data:
                pdf_urls = []
                
                # 开放获取URL
                oa_url = data.get('open_access', {}).get('oa_url')
                if oa_url:
                    pdf_urls.append(oa_url)
                
                # 主要位置
                primary_loc = data.get('primary_location', {})
                if primary_loc:
                    if primary_loc.get('pdf_url'):
                        pdf_urls.append(primary_loc['pdf_url'])
                    if primary_loc.get('landing_page_url'):
                        pdf_urls.append(primary_loc['landing_page_url'])
                
                # 所有位置
                for loc in data.get('locations', []):
                    if loc.get('pdf_url'):
                        pdf_urls.append(loc['pdf_url'])
                    if loc.get('landing_page_url') and loc.get('is_oa'):
                        pdf_urls.append(loc['landing_page_url'])
                
                for url in pdf_urls[:10]:
                    content = await self._fetch_pdf(session, url)
                    if content:
                        return content
        
        except Exception as e:
            logger.debug(f"OpenAlex失败 {doi}: {e}")
        
        return None
    
    async def _download_from_semantic_scholar(self, session: aiohttp.ClientSession,
                                               doi: str) -> Optional[bytes]:
        """Semantic Scholar"""
        try:
            url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi, safe='')}?fields=openAccessPdf,isOpenAccess,externalIds"
            data = await self._fetch_json(session, url)
            
            if data:
                oa_pdf = data.get('openAccessPdf')
                if oa_pdf and oa_pdf.get('url'):
                    content = await self._fetch_pdf(session, oa_pdf['url'])
                    if content:
                        return content
        
        except Exception as e:
            logger.debug(f"Semantic Scholar失败 {doi}: {e}")
        
        return None
    
    async def _download_from_core(self, session: aiohttp.ClientSession,
                                   doi: str) -> Optional[bytes]:
        """CORE"""
        try:
            # CORE搜索API
            url = f"https://core.ac.uk:443/api-v2/articles/search/doi%3A{quote(doi, safe='')}"
            data = await self._fetch_json(session, url, timeout=25)
            
            if data:
                for result in data.get('data', []):
                    download_url = result.get('downloadUrl')
                    if download_url:
                        content = await self._fetch_pdf(session, download_url)
                        if content:
                            return content
                    
                    # 尝试fullText链接
                    full_text = result.get('fullTextIdentifier')
                    if full_text:
                        content = await self._fetch_pdf(session, full_text)
                        if content:
                            return content
        
        except Exception as e:
            logger.debug(f"CORE失败 {doi}: {e}")
        
        return None
    
    async def _download_from_crossref(self, session: aiohttp.ClientSession,
                                       doi: str) -> Optional[bytes]:
        """CrossRef获取出版商PDF链接"""
        try:
            url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
            data = await self._fetch_json(session, url)
            
            if data:
                message = data.get('message', {})
                
                # 检查license是否开放
                licenses = message.get('license', [])
                is_open = any('creativecommons' in l.get('URL', '').lower() for l in licenses)
                
                links = message.get('link', [])
                for link in links:
                    content_type = link.get('content-type', '').lower()
                    if 'pdf' in content_type:
                        pdf_url = link.get('URL')
                        if pdf_url:
                            content = await self._fetch_pdf(session, pdf_url)
                            if content:
                                return content
                
                # 如果是开放获取，尝试资源URL
                if is_open:
                    resource = message.get('resource', {}).get('primary', {}).get('URL')
                    if resource:
                        content = await self._fetch_pdf(session, resource)
                        if content:
                            return content
        
        except Exception as e:
            logger.debug(f"CrossRef失败 {doi}: {e}")
        
        return None
    
    async def _download_from_doi_direct(self, session: aiohttp.ClientSession,
                                         doi: str) -> Optional[bytes]:
        """直接DOI解析"""
        try:
            doi_url = f"https://doi.org/{doi}"
            
            # 获取重定向后的页面
            page_content = await self._fetch_with_retry(session, doi_url, timeout=30)
            
            if page_content:
                # 尝试检测是否直接是PDF
                if self.is_valid_pdf(page_content):
                    return page_content
                
                html = page_content.decode('utf-8', errors='ignore')
                
                # 从页面提取PDF链接
                content = await self._extract_pdf_from_html(session, html, doi_url)
                if content:
                    return content
        
        except Exception as e:
            logger.debug(f"DOI直接下载失败 {doi}: {e}")
        
        return None
    
    async def _download_from_arxiv(self, session: aiohttp.ClientSession,
                                    doi: str) -> Optional[bytes]:
        """arXiv"""
        try:
            # 方法1: 通过Semantic Scholar获取arXiv ID
            url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi, safe='')}?fields=externalIds"
            data = await self._fetch_json(session, url)
            
            if data:
                arxiv_id = data.get('externalIds', {}).get('ArXiv')
                if arxiv_id:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    content = await self._fetch_pdf(session, pdf_url, timeout=30)
                    if content:
                        return content
            
            # 方法2: 如果DOI包含arXiv信息
            if 'arxiv' in doi.lower():
                arxiv_match = re.search(r'(\d{4}\.\d{4,5})', doi)
                if arxiv_match:
                    arxiv_id = arxiv_match.group(1)
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    content = await self._fetch_pdf(session, pdf_url)
                    if content:
                        return content
        
        except Exception as e:
            logger.debug(f"arXiv失败 {doi}: {e}")
        
        return None
    
    async def _download_from_biorxiv(self, session: aiohttp.ClientSession,
                                      doi: str) -> Optional[bytes]:
        """bioRxiv/medRxiv"""
        try:
            if '10.1101/' in doi:
                for server in ['biorxiv', 'medrxiv']:
                    # 尝试不同格式
                    pdf_urls = [
                        f"https://www.{server}.org/content/{doi}.full.pdf",
                        f"https://www.{server}.org/content/{doi}v1.full.pdf",
                        f"https://www.{server}.org/content/{doi}v2.full.pdf",
                    ]
                    
                    for pdf_url in pdf_urls:
                        content = await self._fetch_pdf(session, pdf_url)
                        if content:
                            return content
        
        except Exception as e:
            logger.debug(f"bioRxiv失败 {doi}: {e}")
        
        return None
    
    async def _download_from_doaj(self, session: aiohttp.ClientSession,
                                   doi: str) -> Optional[bytes]:
        """DOAJ"""
        try:
            url = f"https://doaj.org/api/search/articles/doi:{quote(doi, safe='')}"
            data = await self._fetch_json(session, url)
            
            if data:
                for result in data.get('results', []):
                    bibjson = result.get('bibjson', {})
                    links = bibjson.get('link', [])
                    
                    for link in links:
                        link_url = link.get('url')
                        if link_url:
                            content = await self._fetch_pdf(session, link_url)
                            if content:
                                return content
        
        except Exception as e:
            logger.debug(f"DOAJ失败 {doi}: {e}")
        
        return None
    
    async def _download_from_zenodo(self, session: aiohttp.ClientSession,
                                     doi: str) -> Optional[bytes]:
        """Zenodo"""
        try:
            # 直接查询
            url = f"https://zenodo.org/api/records?q=doi:{quote(doi)}"
            data = await self._fetch_json(session, url)
            
            if data:
                hits = data.get('hits', {}).get('hits', [])
                for hit in hits:
                    files = hit.get('files', [])
                    for file in files:
                        if file.get('key', '').lower().endswith('.pdf'):
                            pdf_url = file.get('links', {}).get('self')
                            if pdf_url:
                                content = await self._fetch_pdf(session, pdf_url)
                                if content:
                                    return content
        
        except Exception as e:
            logger.debug(f"Zenodo失败 {doi}: {e}")
        
        return None
    
    async def _download_from_libgen(self, session: aiohttp.ClientSession,
                                     doi: str) -> Optional[bytes]:
        """Library Genesis - 增强版"""
        mirrors = self.working_libgen if self.working_libgen else self.libgen_mirrors
        
        for mirror in mirrors[:5]:
            try:
                # 方法1: 科学文章数据库 (scimag)
                search_url = f"{mirror}/scimag/?q={quote(doi)}"
                page_content = await self._fetch_with_retry(session, search_url, timeout=25)
                
                if page_content:
                    html = page_content.decode('utf-8', errors='ignore')
                    
                    # 提取MD5
                    md5_match = re.search(r'md5[=:]([a-fA-F0-9]{32})', html, re.IGNORECASE)
                    if md5_match:
                        md5 = md5_match.group(1).lower()
                        
                        # 使用不同的下载镜像
                        download_urls = [
                            f"https://download.library.lol/scimag/{md5[:2]}/{md5}.pdf",
                            f"http://library.lol/scimag/{md5}",
                            f"{mirror}/get.php?md5={md5}",
                        ]
                        
                        for dl_url in download_urls:
                            content = await self._fetch_pdf(session, dl_url, timeout=60)
                            if content:
                                if mirror not in self.working_libgen:
                                    self.working_libgen.append(mirror)
                                return content
                    
                    # 方法2: 直接提取下载链接
                    dl_patterns = [
                        r'href=["\']([^"\']*library\.lol[^"\']+)["\']',
                        r'href=["\']([^"\']*get\.php[^"\']+)["\']',
                        r'href=["\']([^"\']*download[^"\']*\.pdf[^"\']*)["\']',
                    ]
                    
                    for pattern in dl_patterns:
                        matches = re.findall(pattern, html)
                        for match in matches[:3]:
                            dl_url = match if match.startswith('http') else urljoin(mirror, match)
                            content = await self._fetch_pdf(session, dl_url, timeout=60)
                            if content:
                                if mirror not in self.working_libgen:
                                    self.working_libgen.append(mirror)
                                return content
                
            except Exception as e:
                logger.debug(f"LibGen镜像 {mirror} 失败: {e}")
                continue
        
        return None
    
    async def _download_from_scihub(self, session: aiohttp.ClientSession,
                                     doi: str) -> Optional[bytes]:
        """Sci-Hub - 增强版"""
        mirrors = self.working_scihub if self.working_scihub else self.scihub_mirrors
        
        for mirror in mirrors[:8]:
            try:
                content = await self._try_scihub_mirror(session, mirror, doi)
                if content:
                    # 将成功的镜像移到前面
                    if mirror in self.working_scihub:
                        self.working_scihub.remove(mirror)
                    self.working_scihub.insert(0, mirror)
                    return content
                    
            except Exception as e:
                logger.debug(f"Sci-Hub镜像 {mirror} 失败: {e}")
                continue
            
            await asyncio.sleep(0.3)  # 镜像间短暂延迟
        
        return None
    
    async def _try_scihub_mirror(self, session: aiohttp.ClientSession,
                                  mirror: str, doi: str) -> Optional[bytes]:
        """尝试单个Sci-Hub镜像"""
        try:
            url = f"{mirror}/{doi}"
            headers = self._get_headers(referer=mirror)
            
            async with session.get(
                url, 
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=45),
                allow_redirects=True,
                proxy=self.proxy
            ) as resp:
                if resp.status != 200:
                    return None
                
                content = await resp.read()
                
                # 直接是PDF
                if self.is_valid_pdf(content):
                    return content
                
                # 解析HTML获取PDF链接
                html = content.decode('utf-8', errors='ignore')
                
                # 多种模式匹配
                patterns = [
                    # iframe嵌入
                    r'<iframe[^>]+src=["\']([^"\']+)["\']',
                    # embed嵌入
                    r'<embed[^>]+src=["\']([^"\']+)["\']',
                    # 按钮点击
                    r'onclick=["\'][^"\']*location[^"\']*=["\']([^"\']+)["\']',
                    # id=pdf
                    r'id=["\']?pdf["\']?[^>]+src=["\']([^"\']+)["\']',
                    # 直接PDF链接
                    r'(https?://[^\s<>"\']+\.pdf(?:\?[^\s<>"\']*)?)',
                    # 相对路径PDF
                    r'src=["\']([^"\']+\.pdf[^"\']*)["\']',
                    # //开头的链接
                    r'src=["\'](//[^\s<>"\']+)["\']',
                    # save按钮
                    r'save[^>]+href=["\']([^"\']+)["\']',
                ]
                
                pdf_urls = []
                for pattern in patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    pdf_urls.extend(matches)
                
                # 处理并尝试每个URL
                seen = set()
                for pdf_url in pdf_urls:
                    # 标准化URL
                    if pdf_url.startswith('//'):
                        pdf_url = 'https:' + pdf_url
                    elif not pdf_url.startswith('http'):
                        pdf_url = urljoin(mirror, pdf_url)
                    
                    if pdf_url in seen:
                        continue
                    seen.add(pdf_url)
                    
                    # 跳过明显不是PDF的链接
                    if any(x in pdf_url.lower() for x in ['captcha', 'challenge', 'cloudflare']):
                        continue
                    
                    pdf_content = await self._fetch_pdf(
                        session, pdf_url, timeout=60, referer=mirror
                    )
                    if pdf_content:
                        return pdf_content
                        
        except asyncio.TimeoutError:
            logger.debug(f"Sci-Hub {mirror} 超时")
        except Exception as e:
            logger.debug(f"Sci-Hub {mirror} 异常: {e}")
        
        return None
    
    async def _extract_pdf_from_html(self, session: aiohttp.ClientSession,
                                      html: str, base_url: str) -> Optional[bytes]:
        """从HTML页面提取PDF链接并下载"""
        patterns = [
            # 常见PDF链接模式
            r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
            r'href=["\']([^"\']*download[^"\']*)["\']',
            r'href=["\']([^"\']*fulltext[^"\']*pdf[^"\']*)["\']',
            r'data-pdf-url=["\']([^"\']+)["\']',
            r'content=["\']([^"\']+\.pdf)["\']',
            # 按钮和链接
            r'<a[^>]+class=["\'][^"\']*pdf[^"\']*["\'][^>]+href=["\']([^"\']+)["\']',
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]+class=["\'][^"\']*pdf[^"\']*["\']',
            # meta标签
            r'<meta[^>]+citation_pdf_url[^>]+content=["\']([^"\']+)["\']',
            r'citation_pdf_url["\s]+content=["\']([^"\']+)["\']',
        ]
        
        pdf_urls = []
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            pdf_urls.extend(matches)
        
        # 去重并尝试下载
        seen = set()
        for url in pdf_urls:
            pdf_url = url if url.startswith('http') else urljoin(base_url, url)
            
            if pdf_url in seen:
                continue
            seen.add(pdf_url)
            
            content = await self._fetch_pdf(session, pdf_url, referer=base_url)
            if content:
                return content
        
        # 尝试常见的PDF URL变体
        parsed = urlparse(base_url)
        variants = [
            base_url.rstrip('/') + '.pdf',
            base_url.rstrip('/') + '/pdf',
            re.sub(r'/abs/', '/pdf/', base_url),
            re.sub(r'/abstract/', '/pdf/', base_url),
            re.sub(r'/full/?$', '/pdf', base_url),
            re.sub(r'/html/?$', '/pdf', base_url),
        ]
        
        for variant in variants:
            if variant != base_url and variant not in seen:
                content = await self._fetch_pdf(session, variant)
                if content:
                    return content
        
        return None
    
    def generate_filename(self, doi: str, metadata: Optional[Dict] = None,
                          index: int = None) -> str:
        """生成文件名"""
        if metadata:
            author = self.clean_filename(metadata.get('first_author', 'Unknown'))
            year = str(metadata.get('year', 'Unknown'))
            title = self.clean_filename(metadata.get('title', 'Unknown')[:50])
            filename = f"{author}_{year}_{title}.pdf"
        else:
            clean_doi = self.clean_filename(doi.replace('/', '_'))
            filename = f"{clean_doi}.pdf"
        
        if index is not None:
            filename = f"{index:04d}_{filename}"
        
        return filename
    
    async def download_paper(self, session: aiohttp.ClientSession,
                              task: DownloadTask) -> DownloadResult:
        """下载单篇论文"""
        async with self.semaphore:
            # 检查是否已存在
            if task.filepath and task.filepath.exists() and task.filepath.stat().st_size > 5000:
                return DownloadResult(True, "skipped")
            
            # 定义下载源（按成功率排序）
            download_sources = [
                # 第一梯队：开放获取
                ('Unpaywall', self._download_from_unpaywall, 25),
                ('EuropePMC', self._download_from_europe_pmc, 20),
                ('PMC', self._download_from_pmc, 20),
                ('OpenAlex', self._download_from_openalex, 20),
                
                # 第二梯队：学术数据库
                ('SemanticScholar', self._download_from_semantic_scholar, 15),
                ('CORE', self._download_from_core, 20),
                ('CrossRef', self._download_from_crossref, 20),
                ('DOAJ', self._download_from_doaj, 15),
                
                # 第三梯队：预印本
                ('arXiv', self._download_from_arxiv, 20),
                ('bioRxiv', self._download_from_biorxiv, 15),
                ('Zenodo', self._download_from_zenodo, 20),
                
                # 第四梯队：直接访问
                ('DOI_Direct', self._download_from_doi_direct, 30),
                
                # 最后手段
                ('LibGen', self._download_from_libgen, 45),
                ('SciHub', self._download_from_scihub, 60),
            ]
            
            # 依次尝试每个下载源
            for source_name, download_func, timeout in download_sources:
                try:
                    result = await asyncio.wait_for(
                        download_func(session, task.clean_doi),
                        timeout=timeout
                    )
                    
                    if result and self.is_valid_pdf(result):
                        # 保存文件
                        if task.filepath:
                            with open(task.filepath, 'wb') as f:
                                f.write(result)
                        
                        logger.info(f"✓ [{source_name}] {task.clean_doi}")
                        return DownloadResult(True, source_name, result)
                
                except asyncio.TimeoutError:
                    logger.debug(f"{source_name} 超时: {task.clean_doi}")
                except Exception as e:
                    logger.debug(f"{source_name} 失败: {task.clean_doi} - {e}")
                
                # 短暂延迟
                await asyncio.sleep(0.2)
            
            logger.warning(f"✗ 全部失败: {task.clean_doi}")
            return DownloadResult(False, "all_failed", error="所有下载源均失败")
    
    async def test_mirrors(self, session: aiohttp.ClientSession):
        """测试镜像可用性"""
        logger.info("测试下载源可用性...")
        
        # 测试Sci-Hub
        async def test_scihub(mirror):
            try:
                async with session.get(
                    mirror,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers=self._get_headers()
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # 确保不是Cloudflare拦截页面
                        if 'sci-hub' in text.lower() or 'input' in text.lower():
                            return mirror
            except:
                pass
            return None
        
        tasks = [test_scihub(m) for m in self.scihub_mirrors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.working_scihub = [r for r in results if r and isinstance(r, str)]
        
        if self.working_scihub:
            logger.info(f"✓ 可用Sci-Hub镜像: {len(self.working_scihub)}个 - {self.working_scihub[:3]}")
        else:
            logger.warning("✗ 所有Sci-Hub镜像不可用")
        
        # 测试LibGen
        async def test_libgen(mirror):
            try:
                async with session.get(
                    mirror,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers=self._get_headers()
                ) as resp:
                    if resp.status == 200:
                        return mirror
            except:
                pass
            return None
        
        tasks = [test_libgen(m) for m in self.libgen_mirrors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.working_libgen = [r for r in results if r and isinstance(r, str)]
        
        if self.working_libgen:
            logger.info(f"✓ 可用LibGen镜像: {len(self.working_libgen)}个 - {self.working_libgen[:3]}")
        else:
            logger.warning("✗ 所有LibGen镜像不可用")
    
    async def download_batch_async(self, dois: List[str],
                                    delay: float = 0.3,
                                    use_metadata: bool = True,
                                    retry_failed: bool = True) -> Dict:
        """异步批量下载"""
        logger.info("="*60)
        logger.info(f"开始批量下载，共 {len(dois)} 篇论文")
        logger.info(f"并发数: {self.max_concurrent}")
        logger.info("="*60)
        
        # 重置统计
        self.stats = {'success': 0, 'failed': 0, 'skipped': 0}
        self.failed_dois = []
        self.source_stats = {}
        
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async with await self._create_session() as session:
            # 测试镜像
            await self.test_mirrors(session)
            
            # 准备任务
            tasks_data = []
            for i, doi in enumerate(dois):
                clean_doi = self.clean_doi(doi)
                if not clean_doi:
                    logger.warning(f"无效DOI跳过: {doi}")
                    self.stats['failed'] += 1
                    continue
                
                if clean_doi in self.downloaded_dois:
                    self.stats['skipped'] += 1
                    continue
                
                task = DownloadTask(
                    doi=doi,
                    clean_doi=clean_doi,
                    index=i + 1
                )
                tasks_data.append(task)
            
            # 获取元数据
            if use_metadata:
                logger.info("获取论文元数据...")
                for task in tasks_data[:100]:  # 限制元数据获取数量
                    task.metadata = await self.get_paper_metadata(session, task.clean_doi)
                    await asyncio.sleep(0.1)
            
            # 生成文件名
            for task in tasks_data:
                filename = self.generate_filename(task.clean_doi, task.metadata, task.index)
                task.filepath = self.output_dir / filename
            
            # 过滤已存在
            pending_tasks = []
            for task in tasks_data:
                if task.filepath.exists() and task.filepath.stat().st_size > 5000:
                    self.stats['skipped'] += 1
                    self.downloaded_dois.add(task.clean_doi)
                else:
                    pending_tasks.append(task)
            
            logger.info(f"跳过已存在: {self.stats['skipped']}篇, 待下载: {len(pending_tasks)}篇")
            
            # 批量下载
            batch_size = self.max_concurrent * 2
            all_results = []
            
            for batch_start in range(0, len(pending_tasks), batch_size):
                batch = pending_tasks[batch_start:batch_start + batch_size]
                
                download_tasks = [
                    self.download_paper(session, task) for task in batch
                ]
                
                if TQDM_AVAILABLE:
                    results = []
                    with tqdm(total=len(download_tasks), 
                             desc=f"批次 {batch_start//batch_size + 1}",
                             ncols=100) as pbar:
                        for coro in asyncio.as_completed(download_tasks):
                            result = await coro
                            results.append(result)
                            pbar.update(1)
                            pbar.set_postfix({
                                '成功': self.stats['success'],
                                '失败': self.stats['failed']
                            })
                            
                            if result.success and result.source != "skipped":
                                self.stats['success'] += 1
                            elif not result.success:
                                self.stats['failed'] += 1
                else:
                    results = await asyncio.gather(*download_tasks, return_exceptions=True)
                    for result in results:
                        if isinstance(result, DownloadResult):
                            if result.success and result.source != "skipped":
                                self.stats['success'] += 1
                            elif not result.success:
                                self.stats['failed'] += 1
                
                all_results.extend(results)
                
                # 批次间延迟
                if batch_start + batch_size < len(pending_tasks):
                    await asyncio.sleep(delay)
            
            # 统计下载源
            for i, result in enumerate(all_results):
                if isinstance(result, DownloadResult):
                    source = result.source
                    self.source_stats[source] = self.source_stats.get(source, 0) + 1
                    
                    if not result.success and i < len(pending_tasks):
                        task = pending_tasks[i]
                        self.failed_dois.append({
                            'doi': task.clean_doi,
                            'original': task.doi,
                            'metadata': task.metadata
                        })
                    elif result.success and i < len(pending_tasks):
                        self.downloaded_dois.add(pending_tasks[i].clean_doi)
            
            # 重试失败的DOI
            if retry_failed and self.failed_dois:
                await self._retry_failed(session)
        
        self._print_stats()
        self._save_failed_records()
        
        return self.stats
    
    async def _retry_failed(self, session: aiohttp.ClientSession):
        """重试失败的DOI"""
        if not self.failed_dois:
            return
        
        logger.info(f"\n重试 {len(self.failed_dois)} 个失败的DOI...")
        
        # 等待一段时间后重试
        await asyncio.sleep(5)
        
        retry_tasks = []
        for item in self.failed_dois[:50]:  # 限制重试数量
            task = DownloadTask(
                doi=item['original'],
                clean_doi=item['doi'],
                index=0,
                metadata=item.get('metadata')
            )
            filename = self.generate_filename(task.clean_doi, task.metadata)
            task.filepath = self.output_dir / filename
            retry_tasks.append(task)
        
        # 清空失败列表
        retry_dois = self.failed_dois[:50]
        self.failed_dois = self.failed_dois[50:]
        
        for task in retry_tasks:
            result = await self.download_paper(session, task)
            if result.success and result.source != "skipped":
                self.stats['success'] += 1
                self.stats['failed'] -= 1
                # 从failed_dois中移除
                retry_dois = [d for d in retry_dois if d['doi'] != task.clean_doi]
            
            await asyncio.sleep(1)
        
        # 将仍然失败的添加回列表
        self.failed_dois.extend(retry_dois)
    
    def download_batch(self, dois: List[str], **kwargs):
        """同步接口"""
        return asyncio.run(self.download_batch_async(dois, **kwargs))
    
    def _print_stats(self):
        """打印统计信息"""
        logger.info("\n" + "="*60)
        logger.info("下载完成统计")
        logger.info("="*60)
        logger.info(f"  ✓ 成功: {self.stats['success']}")
        logger.info(f"  ✗ 失败: {self.stats['failed']}")
        logger.info(f"  ○ 跳过: {self.stats['skipped']}")
        
        total = self.stats['success'] + self.stats['failed']
        if total > 0:
            success_rate = self.stats['success'] / total * 100
            logger.info(f"  成功率: {success_rate:.1f}%")
        
        if self.source_stats:
            logger.info("\n下载源统计:")
            sorted_stats = sorted(
                self.source_stats.items(), 
                key=lambda x: -x[1] if x[0] not in ['all_failed', 'skipped'] else 0
            )
            for source, count in sorted_stats:
                if source not in ['all_failed', 'skipped', 'invalid_doi']:
                    logger.info(f"  {source}: {count}")
    
    def _save_failed_records(self):
        """保存失败记录"""
        if self.failed_dois:
            timestamp = int(time.time())
            json_path = self.failed_dir / f"failed_dois_{timestamp}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(self.failed_dois, f, ensure_ascii=False, indent=2)
            
            txt_path = self.failed_dir / "failed_dois.txt"
            with open(txt_path, 'w', encoding='utf-8') as f:
                for item in self.failed_dois:
                    f.write(f"{item['doi']}\n")
            
            logger.info(f"\n失败记录已保存: {self.failed_dir}")
            logger.info(f"失败DOI数量: {len(self.failed_dois)}")


def read_dois_from_excel(excel_path: str, doi_column: str = None,
                          sheet_name=0) -> List[str]:
    """从Excel读取DOI列表"""
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    
    logger.info(f"Excel列名: {list(df.columns)}")
    
    if doi_column is None:
        possible_names = ['doi', 'DOI', 'Doi', 'doi号', 'DOI号']
        for name in possible_names:
            if name in df.columns:
                doi_column = name
                break
        
        if doi_column is None:
            for col in df.columns:
                if 'doi' in col.lower():
                    doi_column = col
                    break
        
        if doi_column is None:
            for col in df.columns:
                sample = df[col].dropna().astype(str).head(20)
                if any(sample.str.contains(r'10\.\d{4,}/', regex=True)):
                    doi_column = col
                    break
    
    if doi_column is None:
        raise ValueError(f"无法找到DOI列。可用列: {list(df.columns)}")
    
    logger.info(f"使用DOI列: {doi_column}")
    
    dois = df[doi_column].dropna().astype(str).tolist()
    # 去重
    dois = list(dict.fromkeys(dois))
    logger.info(f"共读取 {len(dois)} 个唯一DOI")
    
    return dois


def main():
    """主函数"""
    # ============ 配置区域 ============
    
    EXCEL_PATH = "multi_omics.xlsx"
    DOI_COLUMN = None
    OUTPUT_DIR = "multi_omics_papers"
    
    # Unpaywall邮箱（重要！使用真实邮箱可提高成功率）
    UNPAYWALL_EMAIL = "your.real.email@gmail.com"
    
    # 并发配置
    MAX_CONCURRENT = 8  # 并发数，建议5-10
    TIMEOUT = 90  # 总超时
    
    # 代理配置（如果需要）
    PROXY = None  # 例如: "http://127.0.0.1:7890"
    
    # ==================================
    
    if not os.path.exists(EXCEL_PATH):
        logger.error(f"文件不存在: {EXCEL_PATH}")
        logger.info("请确保Excel文件在当前目录")
        return
    
    try:
        dois = read_dois_from_excel(EXCEL_PATH, doi_column=DOI_COLUMN)
        
        if not dois:
            logger.warning("没有找到有效的DOI")
            return
        
        downloader = HighSuccessRateDownloader(
            output_dir=OUTPUT_DIR,
            unpaywall_email=UNPAYWALL_EMAIL,
            max_concurrent=MAX_CONCURRENT,
            timeout=TIMEOUT,
            proxy=PROXY
        )
        
        downloader.download_batch(
            dois,
            delay=0.3,
            use_metadata=True,
            retry_failed=True
        )
    
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()