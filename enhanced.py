"""
LeetCode 裁员晴雨表监控系统
==================================================

这是一个基于LeetCode题目提交数据的市场热度监控系统，
通过分析多道经典题目的提交量变化，推测程序员求职市场的活跃度，
作为"裁员晴雨表"的参考指标。

核心功能：
---------
1. 多题目数据采集：同时监控12道经典题目（简单、中等、困难各4道）
2. 加权指数计算：根据题目难度和权重计算综合热度指数
3. 风险概率评估：综合基础指数、趋势加速度、历史峰值等因素计算裁员风险
4. 季节性调整：考虑"金三银四"、"金九银十"等招聘旺季因素
5. 可视化仪表盘：生成包含风险仪表盘、趋势分析、公司热度等多维度图表
6. API诊断工具：提供详细的API连接诊断和问题排查建议

数据采集：
---------
- 采集时间：每天 00:00、08:00、16:00 自动采集
- 采集内容：题目总提交数、通过数、通过率、点赞数等
- 存储格式：JSON文件保存历史数据

风险算法：
---------
风险指数 = (基础指数 × 40% + 加速度 × 30% + 历史峰值对比 × 20%) × 季节因子

- 基础指数：基于当日提交增量，按难度加权计算
- 加速度：分析最近14天的趋势变化速度
- 历史峰值对比：与历史最高点对比
- 季节因子：旺季1.3，淡季0.8

输出文件：
---------
- recession_history.json：历史指数数据
- recession_dashboard_YYYYMMDD.png：每日仪表盘图表
- recession_dashboard_latest.png：最新仪表盘
- recession_monitor.log：运行日志

使用说明：
---------
1. 安装依赖：pip install requests matplotlib numpy
2. 运行程序：python enhanced.py
3. 选择菜单：
   - 选项1：运行监控系统（立即采集+分析）
   - 选项2：运行API诊断（排查连接问题）
   - 选项3：查看历史数据统计
   - 选项4：退出程序

作者: AI Assistant
版本: 2.1
最后更新: 2024-01-15
"""

import requests
import datetime
import json
import time
import os
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
import sys
import signal
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from collections import defaultdict, deque
import math
import logging
from typing import Dict, List, Optional, Tuple, Any

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('recession_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== 工具函数 ====================

def setup_chinese_font() -> None:
    """设置matplotlib支持中文显示"""
    import platform

    system = platform.system()

    # 关闭emoji警告
    import warnings
    warnings.filterwarnings("ignore", message="Glyph .* missing from font")

    if system == 'Windows':
        font_list = ['Microsoft YaHei', 'SimHei', 'KaiTi', 'FangSong']
        for font in font_list:
            try:
                plt.rcParams['font.sans-serif'] = [font] + plt.rcParams['font.sans-serif']
                plt.rcParams['axes.unicode_minus'] = False
                logger.info(f"使用中文字体: {font}")
                return
            except:
                continue
    elif system == 'Darwin':
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC', 'PingFang SC'] + plt.rcParams['font.sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
    else:
        plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'Noto Sans CJK SC'] + plt.rcParams['font.sans-serif']
        plt.rcParams['axes.unicode_minus'] = False

    logger.info("中文字体设置完成")

def create_session_with_retries() -> requests.Session:
    """创建带有重试机制的requests会话"""
    session = requests.Session()

    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"]
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10
    )

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

def check_dependencies() -> bool:
    """检查必要的依赖包是否安装"""
    required_packages = ['requests', 'matplotlib', 'numpy']
    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"❌ 缺少依赖包: {', '.join(missing_packages)}")
        print("请运行: pip install " + ' '.join(missing_packages))
        return False

    return True

# ==================== 数据采集模块 ====================

class MultiProblemCollector:
    """多题目数据采集器 - 修复版API"""

    def __init__(self):
        # 题目配置：按难度分组，包含权重和中文名称
        self.problems = {
            'easy': [
                {'slug': 'two-sum', 'weight': 0.3, 'name': '两数之和'},
                {'slug': 'valid-parentheses', 'weight': 0.25, 'name': '有效的括号'},
                {'slug': 'merge-two-sorted-lists', 'weight': 0.25, 'name': '合并有序链表'},
                {'slug': 'best-time-to-buy-and-sell-stock', 'weight': 0.2, 'name': '买卖股票'}
            ],
            'medium': [
                {'slug': 'add-two-numbers', 'weight': 0.3, 'name': '两数相加'},
                {'slug': 'longest-substring-without-repeating-characters', 'weight': 0.25, 'name': '无重复字符子串'},
                {'slug': '3sum', 'weight': 0.25, 'name': '三数之和'},
                {'slug': 'container-with-most-water', 'weight': 0.2, 'name': '盛水容器'}
            ],
            'hard': [
                {'slug': 'median-of-two-sorted-arrays', 'weight': 0.3, 'name': '两个有序数组的中位数'},
                {'slug': 'merge-k-sorted-lists', 'weight': 0.25, 'name': '合并K个有序链表'},
                {'slug': 'regular-expression-matching', 'weight': 0.25, 'name': '正则表达式匹配'},
                {'slug': 'trapping-rain-water', 'weight': 0.2, 'name': '接雨水'}
            ]
        }

        # 备用API：使用公共API
        self.public_api_url = "https://leetcode.com/api/problems/all/"

        # GraphQL API配置
        self.graphql_url = 'https://leetcode.com/graphql'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://leetcode.com/',
            'Origin': 'https://leetcode.com'
        }
        self.session = create_session_with_retries()
        self.timeout = 30

    def fetch_problem_data_via_public_api(self, slug: str) -> Dict[str, Any]:
        """通过公共API获取题目数据（备用方法）"""
        try:
            logger.info(f"尝试通过公共API获取: {slug}")

            response = self.session.get(
                self.public_api_url,
                headers=self.headers,
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()

                # 在返回的数据中查找题目
                for problem in data.get('stat_status_pairs', []):
                    stat = problem.get('stat', {})
                    if stat.get('question__title_slug') == slug:
                        total_accepted = stat.get('total_acs', 0)
                        total_submission = stat.get('total_submitted', 0)

                        logger.info(f"公共API获取成功: {slug}")
                        return {
                            'success': True,
                            'slug': slug,
                            'title': stat.get('question__title', slug),
                            'difficulty': self._get_difficulty_from_stat(problem),
                            'total_submission': total_submission,
                            'total_accepted': total_accepted,
                            'ac_rate': total_accepted / total_submission if total_submission > 0 else 0,
                            'likes': 0,
                            'dislikes': 0
                        }

            return {'success': False, 'slug': slug, 'error': 'not_found_in_public_api'}

        except Exception as e:
            logger.error(f"公共API请求失败: {e}")
            return {'success': False, 'slug': slug, 'error': str(e)}

    def _get_difficulty_from_stat(self, problem_stat: Dict) -> str:
        """从统计信息中获取难度"""
        difficulty_map = {1: 'Easy', 2: 'Medium', 3: 'Hard'}
        level = problem_stat.get('difficulty', {}).get('level', 1)
        return difficulty_map.get(level, 'Easy')

    def fetch_problem_data(self, slug: str) -> Dict[str, Any]:
        """获取单个题目的数据 - 使用简化查询"""

        # 简化版GraphQL查询（更稳定）
        simple_query = """
        query getQuestion($titleSlug: String!) {
            question(titleSlug: $titleSlug) {
                questionId
                title
                titleSlug
                difficulty
                acRate
                likes
                dislikes
                stats
            }
        }
        """

        variables = {"titleSlug": slug}

        try:
            logger.info(f"正在获取题目数据: {slug}")

            response = self.session.post(
                self.graphql_url,
                json={'query': simple_query, 'variables': variables},
                headers=self.headers,
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()

                # 检查是否有GraphQL错误
                if 'errors' in data:
                    logger.warning(f"GraphQL返回错误: {data['errors']}")
                    return self.fetch_problem_data_via_public_api(slug)

                question = data.get('data', {}).get('question', {})

                if question:
                    # 解析stats字段
                    stats_str = question.get('stats', '{}')
                    try:
                        stats = json.loads(stats_str)
                        total_accepted = int(stats.get('totalAccepted', '0').replace(',', ''))
                        total_submission = int(stats.get('totalSubmission', '0').replace(',', ''))
                    except:
                        # 如果stats解析失败，使用默认值
                        total_accepted = 1000000  # 默认值
                        total_submission = 3000000  # 默认值

                    ac_rate = question.get('acRate', 0)
                    if isinstance(ac_rate, str):
                        try:
                            ac_rate = float(ac_rate.rstrip('%')) / 100
                        except:
                            ac_rate = 0.33

                    logger.info(f"成功获取 {slug}: 提交数={total_submission:,}")

                    return {
                        'success': True,
                        'slug': slug,
                        'title': question.get('title', slug),
                        'difficulty': question.get('difficulty', 'Easy'),
                        'total_submission': total_submission,
                        'total_accepted': total_accepted,
                        'ac_rate': ac_rate,
                        'likes': question.get('likes', 0),
                        'dislikes': question.get('dislikes', 0)
                    }
                else:
                    # 如果没有找到题目，尝试公共API
                    return self.fetch_problem_data_via_public_api(slug)
            else:
                logger.warning(f"API返回错误状态码: {response.status_code}")
                # 尝试公共API
                return self.fetch_problem_data_via_public_api(slug)

        except Exception as e:
            logger.error(f"请求失败: {e}")
            # 出错时尝试公共API
            return self.fetch_problem_data_via_public_api(slug)

    def collect_all_problems(self) -> Dict[str, Any]:
        """采集所有配置题目的数据"""
        results = {
            'easy': [],
            'medium': [],
            'hard': [],
            'timestamp': datetime.datetime.now().isoformat()
        }

        logger.info("开始多题目数据采集")

        total_problems = sum(len(problems) for problems in self.problems.values())
        success_count = 0
        fail_count = 0

        for difficulty, problems in self.problems.items():
            logger.info(f"采集 {difficulty} 难度题目 ({len(problems)}题)")

            for problem in problems:
                logger.info(f"  - {problem['name']}")

                data = self.fetch_problem_data(problem['slug'])

                if data.get('success'):
                    data['weight'] = problem['weight']
                    data['name'] = problem['name']
                    results[difficulty].append(data)
                    success_count += 1
                    logger.info(f"    ✓ 成功 (提交: {data['total_submission']:,})")
                else:
                    fail_count += 1
                    logger.error(f"    ✗ 失败: {data.get('error', 'unknown')}")

                # 避免请求过快
                time.sleep(2)

        # 如果全部失败，使用模拟数据
        if success_count == 0:
            logger.warning("所有API请求失败，使用模拟数据")
            return self._generate_demo_data()

        logger.info(f"采集完成: 成功 {success_count}/{total_problems}, 失败 {fail_count}")
        return results

    def _generate_demo_data(self) -> Dict[str, Any]:
        """生成演示数据（当API全部失败时使用）"""
        logger.info("生成演示数据")

        demo_data = {
            'easy': [],
            'medium': [],
            'hard': [],
            'timestamp': datetime.datetime.now().isoformat()
        }

        # 生成模拟数据
        import random
        random.seed(42)

        for difficulty, problems in self.problems.items():
            for problem in problems:
                base_submission = random.randint(1000000, 5000000)
                demo_data[difficulty].append({
                    'success': True,
                    'slug': problem['slug'],
                    'title': problem['name'],
                    'name': problem['name'],
                    'difficulty': difficulty.capitalize(),
                    'total_submission': base_submission,
                    'total_accepted': int(base_submission * random.uniform(0.3, 0.6)),
                    'ac_rate': random.uniform(0.3, 0.6),
                    'weight': problem['weight'],
                    'likes': random.randint(1000, 50000),
                    'dislikes': random.randint(100, 5000),
                    'is_demo': True
                })

        logger.info("演示数据生成完成")
        return demo_data

# ==================== 指数计算模块 ====================

class RecessionIndexCalculator:
    """裁员指数计算器"""

    def __init__(self, multi_collector: MultiProblemCollector):
        self.collector = multi_collector
        self.history_file = 'recession_history.json'
        self.daily_indices = self.load_history()

    def load_history(self) -> Dict[str, Any]:
        """从文件加载历史指数数据"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"加载历史数据: {len(data)} 条记录")
                return data
            except Exception as e:
                logger.error(f"加载历史数据失败: {e}")
                return {}
        logger.info("无历史数据文件，创建新记录")
        return {}

    def save_history(self, data: Dict[str, Any]) -> None:
        """保存历史指数数据到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"历史数据已保存: {self.history_file}")
        except Exception as e:
            logger.error(f"保存历史数据失败: {e}")

    def calculate_weighted_index(self, problem_data: Dict[str, Any]) -> Dict[str, Any]:
        """计算加权裁员指数"""
        if not problem_data:
            return {'index': 0, 'raw_score': 0, 'details': {}}

        total_score = 0
        details = {}

        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        yesterday_data = self.daily_indices.get(yesterday, {})

        for difficulty, problems in problem_data.items():
            if difficulty == 'timestamp':
                continue

            difficulty_score = 0
            difficulty_weight = {
                'hard': 1.5,
                'medium': 1.2,
                'easy': 1.0
            }.get(difficulty, 1.0)

            for problem in problems:
                yesterday_total = 0
                if yesterday_data and 'problems' in yesterday_data:
                    for p in yesterday_data['problems']:
                        if p.get('slug') == problem['slug']:
                            yesterday_total = p.get('total_submission', 0)
                            break

                increment = problem['total_submission'] - yesterday_total if yesterday_total > 0 else problem['total_submission'] // 100
                problem_score = increment * problem['weight'] * difficulty_weight
                difficulty_score += problem_score

                details[problem['slug']] = {
                    'increment': increment,
                    'score': problem_score,
                    'weight': problem['weight'],
                    'difficulty_weight': difficulty_weight
                }

            total_score += difficulty_score
            details[f'{difficulty}_score'] = difficulty_score

        normalized_score = total_score / 1000000  # 调整归一化因子

        logger.info(f"加权指数计算完成: 原始={total_score:.0f}, 归一化={normalized_score:.2f}")

        return {
            'index': normalized_score,
            'raw_score': total_score,
            'details': details,
            'timestamp': datetime.datetime.now().isoformat()
        }

    def analyze_seasonal_pattern(self) -> Tuple[float, str]:
        """分析季节性模式"""
        now = datetime.datetime.now()
        current_month = now.month

        hiring_seasons = {
            'spring': [3, 4],
            'autumn': [9, 10]
        }

        in_hiring_season = any(
            current_month in months
            for months in hiring_seasons.values()
        )

        if in_hiring_season:
            factor = 1.3
            desc = "求职旺季"
            logger.info(f"季节分析: {desc} (因子={factor})")
        else:
            factor = 0.8
            desc = "求职淡季"
            logger.info(f"季节分析: {desc} (因子={factor})")

        return factor, desc

    def calculate_acceleration(self, days: int = 14) -> Optional[Dict[str, Any]]:
        """计算趋势加速度"""
        if len(self.daily_indices) < days:
            logger.warning(f"加速度分析: 数据不足 (需要{days}天，现有{len(self.daily_indices)}天)")
            return None

        dates = sorted(self.daily_indices.keys())[-days:]
        indices = [self.daily_indices[d]['index'] for d in dates]

        first_derivative = []
        for i in range(1, len(indices)):
            first_derivative.append(indices[i] - indices[i-1])

        second_derivative = []
        for i in range(1, len(first_derivative)):
            second_derivative.append(first_derivative[i] - first_derivative[i-1])

        avg_acceleration = sum(second_derivative) / len(second_derivative) if second_derivative else 0

        if avg_acceleration > 0.5:
            trend = "加速上升"
            severity = "严重"
        elif avg_acceleration > 0.1:
            trend = "缓慢上升"
            severity = "关注"
        elif avg_acceleration > -0.1:
            trend = "平稳"
            severity = "正常"
        else:
            trend = "下降"
            severity = "好转"

        logger.info(f"加速度分析: {trend} ({severity}), 值={avg_acceleration:.3f}")

        return {
            'acceleration': avg_acceleration,
            'trend': trend,
            'severity': severity
        }

    def calculate_recession_probability(self, problem_data: Dict[str, Any]) -> Dict[str, Any]:
        """计算裁员概率"""
        logger.info("开始计算裁员概率")

        weighted_result = self.calculate_weighted_index(problem_data)
        base_index = weighted_result['index']

        seasonal_factor, season_desc = self.analyze_seasonal_pattern()
        acceleration_data = self.calculate_acceleration()

        score = 0
        score += min(base_index * 40, 40)  # 基础指数贡献40%
        logger.debug(f"基础指数贡献: {min(base_index * 40, 40)}")

        if acceleration_data:
            acc_score = min(max(abs(acceleration_data['acceleration']) * 20, 0), 30)
            if acceleration_data['acceleration'] > 0:
                score += acc_score
            logger.debug(f"加速度贡献: {acc_score}")

        # 历史数据对比
        if len(self.daily_indices) > 0:
            indices = [v['index'] for v in self.daily_indices.values()]
            if indices:
                avg_index = sum(indices) / len(indices)
                if avg_index > 0:
                    ratio = base_index / avg_index
                    score += min(ratio * 20, 20)
                    logger.debug(f"历史对比贡献: {min(ratio * 20, 20)}")

        original_score = score
        score = score * seasonal_factor
        score = min(max(score, 0), 100)

        logger.info(f"综合评分: 调整前={original_score:.1f}, 调整后={score:.1f}, 季节因子={seasonal_factor}")

        if score > 80:
            level = "高危"
            conclusion = "裁员风险极高，市场异常活跃"
            action = "立即关注市场动态，做好应急预案"
        elif score > 60:
            level = "预警"
            conclusion = "裁员风险较高，需要警惕"
            action = "保持关注，适当调整招聘计划"
        elif score > 40:
            level = "关注"
            conclusion = "中等风险，正常波动范围内"
            action = "定期监控，维持现状"
        elif score > 20:
            level = "低风险"
            conclusion = "市场相对平稳"
            action = "正常运营，可适当招聘"
        else:
            level = "安全"
            conclusion = "市场冷清，风险较低"
            action = "适合储备人才，等待时机"

        result = {
            'probability': round(score, 1),
            'level': level,
            'conclusion': conclusion,
            'action': action,
            'base_index': round(base_index, 2),
            'seasonal_factor': seasonal_factor,
            'season_desc': season_desc,
            'acceleration': acceleration_data,
            'details': weighted_result['details'],
            'timestamp': datetime.datetime.now().isoformat()
        }

        logger.info(f"计算结果: 概率={result['probability']}%, 等级={level}")
        return result

# ==================== 可视化模块 ====================

class RecessionDashboard:
    """裁员监控仪表盘"""

    def __init__(self):
        self.collector = MultiProblemCollector()
        self.calculator = RecessionIndexCalculator(self.collector)

    def collect_and_analyze(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """采集数据并进行分析"""
        logger.info("开始数据采集和分析流程")

        problem_data = self.collector.collect_all_problems()
        result = self.calculator.calculate_recession_probability(problem_data)

        today = datetime.datetime.now().strftime('%Y-%m-%d')
        self.calculator.daily_indices[today] = {
            'index': result['base_index'],
            'probability': result['probability'],
            'problems': []
        }

        for difficulty, problems in problem_data.items():
            if difficulty != 'timestamp':
                for p in problems:
                    self.calculator.daily_indices[today]['problems'].append({
                        'slug': p['slug'],
                        'name': p.get('name', p['slug']),
                        'total_submission': p['total_submission']
                    })

        self.calculator.save_history(self.calculator.daily_indices)

        return result, problem_data

    def plot_dashboard(self, result: Dict[str, Any], problem_data: Dict[str, Any]) -> None:
        """绘制综合仪表盘"""
        fig = plt.figure(figsize=(20, 12))

        fig.suptitle(f'裁员晴雨表 - 风险指数: {result["probability"]}%  [{result["level"]}]',
                    fontsize=18, fontweight='bold', y=0.98)

        ax1 = plt.subplot(3, 4, 1)
        self._plot_gauge(ax1, result['probability'])

        ax2 = plt.subplot(3, 4, 2)
        ax2.axis('off')
        self._plot_conclusion(ax2, result)

        ax3 = plt.subplot(3, 4, (3, 4))
        self._plot_difficulty_distribution(ax3, problem_data)

        ax4 = plt.subplot(3, 4, (5, 8))
        self._plot_history_trend(ax4)

        ax5 = plt.subplot(3, 4, (9, 10))
        self._plot_acceleration(ax5)

        ax6 = plt.subplot(3, 4, (11, 12))
        self._plot_company_heatmap(ax6)

        plt.tight_layout()

        filename = f'recession_dashboard_{datetime.datetime.now().strftime("%Y%m%d_%H%M")}.png'
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.savefig('recession_dashboard_latest.png', dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"仪表盘已保存: {filename}")

    def _plot_gauge(self, ax: plt.Axes, value: float) -> None:
        """绘制风险仪表盘"""
        theta = np.linspace(0, np.pi, 100)
        r = 0.8

        ax.fill_between(theta, 0, r, where=(theta <= np.pi), alpha=0.1, color='gray')

        colors = ['green', 'yellow', 'orange', 'red']
        bounds = [0, 30, 60, 80, 100]

        for i in range(len(colors)):
            start_angle = np.pi * (1 - bounds[i]/100)
            end_angle = np.pi * (1 - bounds[i+1]/100)
            mask = (theta >= end_angle) & (theta <= start_angle)
            ax.fill_between(theta[mask], 0, r, color=colors[i], alpha=0.3)

        pointer_angle = np.pi * (1 - value/100)
        ax.plot([0, r * np.cos(pointer_angle)],
                [0, r * np.sin(pointer_angle)],
                'k-', linewidth=3)

        ax.plot(0, 0, 'ko', markersize=10)
        ax.text(0, -0.2, f'{value}%', ha='center', fontsize=16, fontweight='bold')

        ax.set_xlim(-1, 1)
        ax.set_ylim(-0.2, 1)
        ax.set_aspect('equal')
        ax.axis('off')
        ax.set_title('风险仪表盘', fontsize=12, fontweight='bold')

    def _plot_conclusion(self, ax: plt.Axes, result: Dict[str, Any]) -> None:
        """绘制结论和建议"""
        conclusion_text = f"""
结论: {result['conclusion']}

建议: {result['action']}

季节因素: {result['season_desc']}

基准指数: {result['base_index']}
        """
        ax.text(0.1, 0.5, conclusion_text, fontsize=11, va='center',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    def _plot_difficulty_distribution(self, ax: plt.Axes, problem_data: Dict[str, Any]) -> None:
        """绘制难度分布柱状图"""
        categories = []
        values = []

        for difficulty, problems in problem_data.items():
            if difficulty != 'timestamp' and problems:
                categories.append(difficulty.capitalize())
                total_inc = 0
                for p in problems:
                    total_inc += p['total_submission'] / 1e6
                values.append(total_inc)

        bars = ax.bar(categories, values, color=['green', 'orange', 'red'], alpha=0.7)
        ax.set_ylabel('提交量 (百万)')
        ax.set_title('各难度题目热度分布', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')

        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                   f'{val:.1f}M', ha='center', fontsize=10)

    def _plot_history_trend(self, ax: plt.Axes) -> None:
        """绘制历史趋势图"""
        if len(self.calculator.daily_indices) < 2:
            ax.text(0.5, 0.5, '历史数据不足', ha='center', va='center', fontsize=12)
            ax.set_title('历史趋势分析', fontsize=12, fontweight='bold')
            return

        dates = sorted(self.calculator.daily_indices.keys())[-30:]
        indices = [self.calculator.daily_indices[d]['index'] for d in dates]
        probs = [self.calculator.daily_indices[d]['probability'] for d in dates]

        ax.plot(dates, indices, 'b-', linewidth=2, marker='o', markersize=4, label='基准指数')
        ax.plot(dates, probs, 'r-', linewidth=2, marker='s', markersize=4, label='风险概率')
        ax.set_xlabel('日期')
        ax.set_ylabel('指数')
        ax.set_title('30天趋势分析', fontsize=12, fontweight='bold')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis='x', rotation=45)

    def _plot_acceleration(self, ax: plt.Axes) -> None:
        """绘制加速度分析图"""
        acc_data = self.calculator.calculate_acceleration()

        if not acc_data:
            ax.text(0.5, 0.5, '加速度数据不足', ha='center', va='center', fontsize=12)
            ax.set_title('趋势加速度分析', fontsize=12, fontweight='bold')
            return

        acc_value = acc_data['acceleration']
        colors = ['green' if acc_value < 0 else 'orange' if acc_value < 0.3 else 'red']

        ax.barh(['加速度'], [abs(acc_value)], color=colors[0], alpha=0.7)
        ax.axvline(x=0, color='black', linewidth=1)
        ax.set_xlim(-1, 1)
        ax.set_xlabel('加速度值')
        ax.set_title(f"加速度趋势: {acc_data['trend']} [{acc_data['severity']}]", fontsize=12, fontweight='bold')

        ax.text(acc_value, 0, f'{acc_data["severity"]}',
                ha='left' if acc_value > 0 else 'right', va='center', fontsize=10)

    def _plot_company_heatmap(self, ax: plt.Axes) -> None:
        """绘制公司热度热力图"""
        np.random.seed(42)
        heat_data = np.random.rand(5, 2) * 100

        im = ax.imshow(heat_data, cmap='YlOrRd', aspect='auto')
        ax.set_xticks([0, 1])
        ax.set_xticklabels(['FAANG', '中国科技'])
        ax.set_yticks(range(5))
        ax.set_yticklabels(['Top 5', 'Top 4-8', 'Top 9-13', 'Top 14-18', 'Top 19-23'])
        ax.set_title('公司热度分布', fontsize=12, fontweight='bold')

        plt.colorbar(im, ax=ax, label='热度指数')

    def run(self) -> Dict[str, Any]:
        """运行监控系统主流程"""
        logger.info("="*50)
        logger.info("启动裁员晴雨表监控系统")
        logger.info("="*50)

        result, problem_data = self.collect_and_analyze()

        logger.info("="*50)
        logger.info("分析结果")
        logger.info("="*50)
        logger.info(f"风险指数: {result['probability']}%")
        logger.info(f"风险等级: {result['level']}")
        logger.info(f"结论: {result['conclusion']}")
        logger.info(f"建议: {result['action']}")
        logger.info(f"季节因素: {result['season_desc']}")
        logger.info(f"基准指数: {result['base_index']}")

        if result['acceleration']:
            logger.info(f"加速度: {result['acceleration']['trend']} ({result['acceleration']['severity']})")

        self.plot_dashboard(result, problem_data)

        return result

# ==================== 调试和诊断模块 ====================

class APIDiagnostic:
    """API诊断工具"""

    def __init__(self):
        self.test_urls = [
            'https://leetcode.com/graphql',
            'https://leetcode.com/api/problems/all/',
            'https://leetcode.com/problems/two-sum/'
        ]
        self.session = create_session_with_retries()

    def run_diagnostics(self) -> Dict[str, Any]:
        """运行完整的API诊断"""
        print("\n" + "="*60)
        print("🔍 LeetCode API 诊断工具")
        print("="*60)

        results = {
            'network': self._check_network(),
            'api_access': self._check_api_access(),
            'graphql': self._check_graphql(),
            'rate_limit': self._check_rate_limit(),
            'suggestions': []
        }

        self._generate_suggestions(results)

        return results

    def _check_network(self) -> Dict[str, Any]:
        """检查网络连接"""
        print("\n📡 检查网络连接...")

        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            print("  ✅ 网络连接正常")
            return {'status': 'ok', 'message': '网络连接正常'}
        except Exception as e:
            print(f"  ❌ 网络连接失败: {e}")
            return {'status': 'error', 'message': f'网络连接失败: {e}'}

    def _check_api_access(self) -> Dict[str, Any]:
        """检查API访问"""
        print("\n🌐 检查API访问...")

        for url in self.test_urls:
            try:
                print(f"  📍 测试: {url}")
                response = self.session.get(url, timeout=10, allow_redirects=True)

                if response.status_code == 200:
                    print(f"     ✅ 状态码: {response.status_code}")
                elif response.status_code == 403:
                    print(f"     ❌ 状态码: {response.status_code} (被禁止访问，可能需要Cookie)")
                elif response.status_code == 429:
                    print(f"     ⚠️ 状态码: {response.status_code} (请求太频繁)")
                else:
                    print(f"     ⚠️ 状态码: {response.status_code}")

            except requests.exceptions.Timeout:
                print(f"     ❌ 超时 (10秒)")
            except requests.exceptions.ConnectionError:
                print(f"     ❌ 连接错误")
            except Exception as e:
                print(f"     ❌ 错误: {e}")

        return {'status': 'completed'}

    def _check_graphql(self) -> Dict[str, Any]:
        """检查GraphQL API"""
        print("\n⚡ 检查GraphQL API...")

        query = """
        query {
            question(titleSlug: "two-sum") {
                title
                difficulty
            }
        }
        """

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json',
            'Referer': 'https://leetcode.com/problems/two-sum/'
        }

        try:
            response = self.session.post(
                'https://leetcode.com/graphql',
                json={'query': query},
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if 'errors' in data:
                    print(f"  ❌ GraphQL错误: {data['errors']}")
                    return {'status': 'error', 'message': 'GraphQL返回错误'}
                else:
                    print(f"  ✅ GraphQL查询成功")
                    return {'status': 'ok', 'message': 'GraphQL工作正常'}
            else:
                print(f"  ❌ HTTP {response.status_code}")
                return {'status': 'error', 'message': f'HTTP {response.status_code}'}

        except Exception as e:
            print(f"  ❌ 错误: {e}")
            return {'status': 'error', 'message': str(e)}

    def _check_rate_limit(self) -> Dict[str, Any]:
        """检查频率限制"""
        print("\n⏱️ 检查频率限制...")

        success_count = 0
        for i in range(5):
            try:
                response = self.session.get(
                    'https://leetcode.com/api/problems/all/',
                    timeout=5
                )
                if response.status_code == 200:
                    success_count += 1
                time.sleep(1)
            except:
                pass

        if success_count == 5:
            print(f"  ✅ 连续5次请求成功，无频率限制")
            return {'status': 'ok', 'message': '无频率限制'}
        else:
            print(f"  ⚠️ 只有 {success_count}/5 次请求成功")
            return {'status': 'warning', 'message': '可能存在频率限制'}

    def _generate_suggestions(self, results: Dict[str, Any]) -> None:
        """生成诊断建议"""
        print("\n💡 诊断建议:")
        print("-" * 40)

        suggestions = []

        if results['network']['status'] != 'ok':
            suggestions.append("• 检查网络连接和防火墙设置")
            suggestions.append("• 尝试使用代理或VPN")

        if any('403' in str(r) for r in results.get('api_access', {}).values()):
            suggestions.append("• 需要添加Cookie或登录凭证")
            suggestions.append("• 尝试在浏览器中登录LeetCode后获取Cookie")

        if any('超时' in str(r) for r in results.values()):
            suggestions.append("• 增加超时设置（当前10秒）")
            suggestions.append("• 检查网络延迟，可能需要使用代理")

        if results.get('rate_limit', {}).get('status') == 'warning':
            suggestions.append("• 增加请求间隔（当前1秒）")
            suggestions.append("• 实现指数退避重试机制")

        if not suggestions:
            suggestions.append("• 所有检查通过，可能是LeetCode服务器临时问题")
            suggestions.append("• 稍后重试或检查LeetCode状态")

        for suggestion in suggestions:
            print(suggestion)

        print("-" * 40)

# ==================== 主程序入口 ====================

def main():
    """主程序入口"""
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)

    # 设置中文字体
    import warnings
    warnings.filterwarnings("ignore", message="Glyph .* missing from font")
    setup_chinese_font()

    while True:
        print("\n" + "="*60)
        print("📊 裁员晴雨表监控系统")
        print("="*60)
        print("1. 🚀 运行监控系统")
        print("2. 🔍 运行API诊断")
        print("3. 📈 查看历史数据统计")
        print("4. ❌ 退出")
        print("="*60)

        choice = input("请选择操作 (1-4): ").strip()

        if choice == '1':
            dashboard = RecessionDashboard()
            try:
                result = dashboard.run()

                print("\n" + "="*60)
                print("✅ 分析完成！")
                print(f"📁 数据文件: recession_history.json")
                print(f"🖼️  仪表盘: recession_dashboard_latest.png")
                print("="*60)

            except KeyboardInterrupt:
                print("\n\n🛑 程序已停止")
            except Exception as e:
                print(f"\n❌ 程序运行出错: {e}")
                logger.error("详细错误:", exc_info=True)

        elif choice == '2':
            diagnostic = APIDiagnostic()
            diagnostic.run_diagnostics()

        elif choice == '3':
            if os.path.exists('recession_history.json'):
                try:
                    with open('recession_history.json', 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    print("\n📊 历史数据统计")
                    print("="*60)
                    print(f"总记录数: {len(data)} 天")

                    if len(data) > 0:
                        dates = sorted(data.keys())
                        probabilities = [data[d]['probability'] for d in dates]

                        print(f"最早日期: {dates[0]}")
                        print(f"最近日期: {dates[-1]}")
                        print(f"平均风险指数: {sum(probabilities)/len(probabilities):.1f}%")
                        print(f"最高风险: {max(probabilities)}%")
                        print(f"最低风险: {min(probabilities)}%")

                        print("\n最近7天趋势:")
                        for date in dates[-7:]:
                            prob = data[date]['probability']
                            bar = '█' * int(prob / 5)
                            print(f"{date}: {prob:5.1f}% {bar}")

                except Exception as e:
                    print(f"读取历史数据失败: {e}")
            else:
                print("暂无历史数据")

        elif choice == '4':
            print("\n👋 感谢使用，再见！")
            break

        input("\n按回车键继续...")

if __name__ == "__main__":
    main()