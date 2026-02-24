import requests
import datetime
import json
import time
import os
import matplotlib.pyplot as plt
from matplotlib import font_manager
import sys
import signal
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# 设置中文字体
def setup_chinese_font():
    """设置matplotlib支持中文显示"""
    import platform

    system = platform.system()

    # 根据操作系统设置中文字体
    if system == 'Windows':
        # Windows系统
        font_list = ['Microsoft YaHei', 'SimHei', 'KaiTi', 'FangSong']
        for font in font_list:
            try:
                plt.rcParams['font.sans-serif'] = [font] + plt.rcParams['font.sans-serif']
                plt.rcParams['axes.unicode_minus'] = False
                print(f"✅ 使用中文字体: {font}")
                return
            except:
                continue
    elif system == 'Darwin':  # macOS
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC', 'PingFang SC'] + plt.rcParams[
            'font.sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
    else:  # Linux
        plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'Noto Sans CJK SC'] + plt.rcParams['font.sans-serif']
        plt.rcParams['axes.unicode_minus'] = False

    print("✅ 中文字体设置完成")


def create_session_with_retries():
    """创建带有重试机制的requests会话"""
    session = requests.Session()

    # 设置重试策略
    retry_strategy = Retry(
        total=3,  # 总共重试3次
        backoff_factor=1,  # 重试间隔：1, 2, 4秒
        status_forcelist=[429, 500, 502, 503, 504],  # 遇到这些状态码时重试
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


class TwoSumDataCollector:
    """Two Sum 数据采集器 - 自动采集模式（无schedule依赖）"""

    def __init__(self, data_file='two_sum_history.json'):
        self.data_file = data_file
        self.url = 'https://leetcode.com/graphql'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://leetcode.com/problems/two-sum/',
            'Origin': 'https://leetcode.com'
        }
        self.session = create_session_with_retries()
        self.history = self.load_history()
        self.running = True
        self.max_retries = 3
        self.timeout = 30  # 增加超时时间到30秒

        # 设置信号处理
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        """处理Ctrl+C信号"""
        print("\n\n🛑 收到停止信号，正在保存数据...")
        self.running = False
        self.save_history()
        print("👋 程序已停止")
        sys.exit(0)

    def load_history(self):
        """加载历史数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 确保数据格式正确
                    if isinstance(data, list):
                        # 如果是旧格式（列表），转换为字典
                        history_dict = {}
                        for record in data:
                            if isinstance(record, dict) and 'date' in record:
                                history_dict[record['date']] = {
                                    'total_submission': record.get('total_submission', 0),
                                    'total_accepted': record.get('total_accepted', 0),
                                    'ac_rate': record.get('ac_rate', 0),
                                    'likes': record.get('likes', 0),
                                    'dislikes': record.get('dislikes', 0)
                                }
                        return history_dict
                    return data
            except Exception as e:
                print(f"加载历史数据失败: {e}")
                return {}
        return {}

    def save_history(self):
        """保存历史数据"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            print(f"\n✅ 数据已保存到 {self.data_file}")
        except Exception as e:
            print(f"❌ 保存数据失败: {e}")

    def fetch_current_data(self):
        """获取当前数据 - 使用GraphQL（带重试机制）"""
        query = """
        query getQuestionDetail($titleSlug: String!) {
            question(titleSlug: $titleSlug) {
                title
                difficulty
                stats
                acRate
                likes
                dislikes
                totalAccepted
                totalSubmission
            }
        }
        """

        variables = {
            "titleSlug": "two-sum"
        }

        for attempt in range(self.max_retries):
            try:
                print(f"📡 尝试获取数据 (第{attempt + 1}次尝试)...")

                response = self.session.post(
                    self.url,
                    json={
                        'query': query,
                        'variables': variables
                    },
                    headers=self.headers,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    question = data.get('data', {}).get('question', {})

                    if question:
                        # 解析stats
                        stats_str = question.get('stats', '{}')
                        try:
                            stats = json.loads(stats_str)
                            total_accepted = int(stats.get('totalAccepted', '0').replace(',', ''))
                            total_submission = int(stats.get('totalSubmission', '0').replace(',', ''))
                        except:
                            # 如果stats解析失败，尝试直接获取
                            total_accepted = int(question.get('totalAccepted', '0').replace(',', '')) if question.get(
                                'totalAccepted') else 0
                            total_submission = int(
                                question.get('totalSubmission', '0').replace(',', '')) if question.get(
                                'totalSubmission') else 0

                        ac_rate = question.get('acRate', 0)
                        if isinstance(ac_rate, str):
                            try:
                                ac_rate = float(ac_rate.rstrip('%')) / 100
                            except:
                                ac_rate = 0.38

                        print(f"✅ 第{attempt + 1}次尝试成功！")
                        return {
                            'success': True,
                            'title': question.get('title', 'Two Sum'),
                            'difficulty': question.get('difficulty', 'Easy'),
                            'total_accepted': total_accepted,
                            'total_submission': total_submission,
                            'ac_rate': ac_rate,
                            'likes': question.get('likes', 0),
                            'dislikes': question.get('dislikes', 0)
                        }
                else:
                    print(f"⚠️ 请求失败，状态码: {response.status_code}")

            except requests.exceptions.Timeout:
                print(f"⏰ 第{attempt + 1}次尝试超时")
            except requests.exceptions.ConnectionError:
                print(f"🔌 第{attempt + 1}次尝试连接错误")
            except Exception as e:
                print(f"❌ 第{attempt + 1}次尝试失败: {e}")

            if attempt < self.max_retries - 1:
                wait_time = (attempt + 1) * 5  # 递增等待时间：5, 10, 15秒
                print(f"⏳ 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)

        # 如果GraphQL失败，尝试备用方法
        print("⚠️ GraphQL所有尝试失败，尝试备用API...")
        return self.fetch_from_official_api()

    def fetch_from_official_api(self):
        """备用方法：使用官方API（带重试机制）"""
        try:
            url = "https://leetcode.com/api/problems/all/"

            for attempt in range(self.max_retries):
                try:
                    print(f"📡 尝试备用API (第{attempt + 1}次尝试)...")

                    response = self.session.get(url, headers=self.headers, timeout=self.timeout)

                    if response.status_code == 200:
                        data = response.json()

                        for problem in data.get('stat_status_pairs', []):
                            stat = problem.get('stat', {})
                            if stat.get('question__title_slug') == 'two-sum':
                                total_accepted = stat.get('total_acs', 0)
                                total_submission = stat.get('total_submitted', 0)

                                print(f"✅ 备用API第{attempt + 1}次尝试成功！")
                                return {
                                    'success': True,
                                    'title': stat.get('question__title', 'Two Sum'),
                                    'difficulty': 'Easy',
                                    'total_accepted': total_accepted,
                                    'total_submission': total_submission,
                                    'ac_rate': total_accepted / total_submission if total_submission > 0 else 0,
                                    'likes': 0,
                                    'dislikes': 0
                                }

                except Exception as e:
                    print(f"❌ 备用API第{attempt + 1}次尝试失败: {e}")

                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    print(f"⏳ 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)

            return {'success': False}

        except Exception as e:
            print(f"备用API请求失败: {e}")
            return {'success': False}

    def collect_data(self):
        """采集数据"""
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n{'=' * 60}")
        print(f"📊 开始采集数据 - {current_time}")
        print('=' * 60)

        result = self.fetch_current_data()

        if result.get('success'):
            today = datetime.datetime.now().strftime('%Y-%m-%d')

            # 检查今天是否已经采集过
            if today in self.history:
                print(f"⚠️ 今天({today})已经采集过数据，将更新为最新数据")

            # 保存今天的数据
            self.history[today] = {
                'total_submission': result['total_submission'],
                'total_accepted': result['total_accepted'],
                'ac_rate': result['ac_rate'],
                'likes': result.get('likes', 0),
                'dislikes': result.get('dislikes', 0),
                'collection_time': datetime.datetime.now().strftime('%H:%M:%S')
            }

            # 显示今天的数据
            self.display_result(result, today)

            # 计算今日新增
            self.calculate_increment(today)

            # 保存到文件
            self.save_history()

            # 生成图表 - 即使只有一个数据也生成图表
            self.plot_history()

            return True
        else:
            print("❌ 所有数据采集方式都失败了")
            print("是否使用演示数据？(y/n): ", end='')
            choice = input().strip().lower()
            if choice == 'y':
                return self.use_demo_data()
            return False

    def use_demo_data(self):
        """使用模拟数据"""
        today = datetime.datetime.now().strftime('%Y-%m-%d')

        # 模拟数据
        demo_data = {
            'success': True,
            'title': 'Two Sum (演示数据)',
            'difficulty': 'Easy',
            'total_accepted': 3456789,
            'total_submission': 9123456,
            'ac_rate': 3456789 / 9123456,
            'likes': 45678,
            'dislikes': 1345
        }

        print("⚠️ 使用演示数据")

        self.history[today] = {
            'total_submission': demo_data['total_submission'],
            'total_accepted': demo_data['total_accepted'],
            'ac_rate': demo_data['ac_rate'],
            'likes': demo_data['likes'],
            'dislikes': demo_data['dislikes'],
            'collection_time': datetime.datetime.now().strftime('%H:%M:%S'),
            'is_demo': True
        }

        self.display_result(demo_data, today, is_demo=True)
        self.calculate_increment(today)
        self.save_history()
        self.plot_history()

        return True

    def display_result(self, result, today, is_demo=False):
        """显示采集结果"""
        print(f"\n📅 日期: {today}")
        if is_demo:
            print("⚠️  注意：当前显示的是演示数据")
        print(f"📝 题目: {result['title']}")
        print(f"🎯 难度: {result['difficulty']}")
        print(f"📈 总提交数: {result['total_submission']:,}")
        print(f"✅ 通过数: {result['total_accepted']:,}")
        print(f"📊 通过率: {result['ac_rate']:.2%}")
        print(f"👍 点赞数: {result.get('likes', 0):,}")
        print(f"👎 点踩数: {result.get('dislikes', 0):,}")

    def calculate_increment(self, today):
        """计算每日新增提交数"""
        dates = sorted(self.history.keys())
        if len(dates) >= 2:
            # 找到今天之前的最近一个有效日期
            today_index = dates.index(today)
            if today_index > 0:
                yesterday = dates[today_index - 1]
                today_total = self.history[today]['total_submission']
                yesterday_total = self.history[yesterday]['total_submission']
                increment = today_total - yesterday_total

                self.history[today]['daily_increment'] = increment
                print(f"🆕 今日新增提交: {increment:,}")

                # 计算近7天平均
                if len(dates) >= 8:
                    last_7_dates = dates[-8:-1]
                    increments = []
                    for d in last_7_dates:
                        if 'daily_increment' in self.history[d]:
                            increments.append(self.history[d]['daily_increment'])

                    if increments:
                        avg_increment = sum(increments) // len(increments)
                        print(f"📊 近7天平均每日新增: {avg_increment:,}")

                        # 裁员信号判断
                        print("\n🔍 裁员晴雨表信号:")
                        if increment > avg_increment * 1.5:
                            print("   🔥🔥🔥 高危信号：今日新增远超平均值！")
                            print("   💡 解读：市场极度活跃，裁员风险高")
                        elif increment > avg_increment * 1.2:
                            print("   🔥🔥 预警信号：今日新增高于平均值")
                            print("   💡 解读：市场活跃度上升，需要关注")
                        elif increment < avg_increment * 0.8:
                            print("   ✅ 平稳信号：今日新增低于平均值")
                            print("   💡 解读：市场相对冷清，风险较低")
                        else:
                            print("   👀 正常波动")
                            print("   💡 解读：市场平稳运行")

    def plot_history(self):
        """生成历史趋势图表 - 修改为支持单个数据点"""
        if len(self.history) == 0:
            print("没有数据，无法生成图表")
            return

        dates = sorted(self.history.keys())
        totals = [self.history[d]['total_submission'] for d in dates]
        accepted = [self.history[d]['total_accepted'] for d in dates]

        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))
        fig.suptitle('LeetCode Two Sum 历史数据趋势（裁员晴雨表）', fontsize=16, fontweight='bold')

        # 1. 累计提交趋势
        if len(dates) == 1:
            # 只有一个数据点，显示为点
            ax1.plot(dates, totals, 'bo', markersize=8, label='总提交数')
            ax1.plot(dates, accepted, 'go', markersize=8, label='通过数')
            ax1.set_title('累计提交/通过趋势（只有一个数据点）', fontsize=12)
        else:
            # 多个数据点，显示为线
            ax1.plot(dates, totals, 'b-', linewidth=2, marker='o', markersize=4, label='总提交数')
            ax1.plot(dates, accepted, 'g-', linewidth=2, marker='s', markersize=4, label='通过数')
            ax1.set_title('累计提交/通过趋势', fontsize=12)

        ax1.set_ylabel('数量')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(axis='x', rotation=45)

        # 2. 每日新增提交柱状图
        if len(dates) >= 2:
            # 有多个数据点，计算增量
            increments = []
            inc_dates = []
            for i in range(1, len(dates)):
                increment = totals[i] - totals[i - 1]
                if increment >= 0:
                    increments.append(increment)
                    inc_dates.append(dates[i])

            if increments:
                # 计算平均值用于颜色判断
                avg_increment = sum(increments) // len(increments) if increments else 0
                colors = []
                for inc in increments:
                    if inc > avg_increment * 1.5:
                        colors.append('red')
                    elif inc > avg_increment * 1.2:
                        colors.append('orange')
                    else:
                        colors.append('green')

                bars = ax2.bar(inc_dates, increments, color=colors, alpha=0.7)
                ax2.set_title('每日新增提交趋势（裁员晴雨表）', fontsize=12)

                # 添加参考线
                if avg_increment > 0:
                    ax2.axhline(y=avg_increment, color='blue', linestyle='--', alpha=0.5,
                                label=f'平均值 ({avg_increment:,})')
                    ax2.axhline(y=avg_increment * 1.5, color='red', linestyle='--', alpha=0.5,
                                label='高危线')
                    ax2.axhline(y=avg_increment * 1.2, color='orange', linestyle='--', alpha=0.5,
                                label='关注线')
        else:
            # 只有一个数据点，显示提示信息
            ax2.text(0.5, 0.5, '需要至少两个数据点才能显示每日新增趋势',
                     ha='center', va='center', transform=ax2.transAxes, fontsize=12,
                     color='gray')
            ax2.set_title('每日新增提交趋势（数据不足）', fontsize=12)

        ax2.set_ylabel('新增提交数')
        ax2.grid(True, alpha=0.3, axis='y')
        if len(dates) >= 2:
            ax2.legend()
        ax2.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        # 保存图表
        filename = f'two_sum_history_{datetime.datetime.now().strftime("%Y%m%d")}.png'
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"\n📊 趋势图已保存: {filename}")

        # 同时保存一个固定名称的图表，方便查看
        plt.savefig('two_sum_history_latest.png', dpi=150, bbox_inches='tight')
        print(f"📊 最新趋势图: two_sum_history_latest.png")

    def should_collect_now(self, last_collection):
        """判断现在是否需要采集"""
        now = datetime.datetime.now()

        # 定义采集时间点
        collect_times = ["00:00", "08:00", "16:00"]

        current_time = now.strftime("%H:%M")

        # 检查当前时间是否在采集时间点附近（前后5分钟内）
        for collect_time in collect_times:
            collect_hour, collect_minute = map(int, collect_time.split(':'))
            current_hour, current_minute = map(int, current_time.split(':'))

            # 计算时间差（分钟）
            time_diff = abs((current_hour * 60 + current_minute) - (collect_hour * 60 + collect_minute))

            if time_diff <= 5:  # 5分钟内
                # 检查今天这个时间点是否已经采集过
                today = now.strftime('%Y-%m-%d')
                collection_key = f"{today}_{collect_time}"

                if collection_key != last_collection:
                    return True, collection_key

        return False, None

    def run(self):
        """运行采集服务"""
        print("\n" + "=" * 60)
        print("🚀 LEETCODE TWO SUM 自动采集服务")
        print("=" * 60)
        print("📅 首次采集: 立即执行")
        print("⏰ 定时采集: 每天 00:00, 08:00, 16:00")
        print("💾 数据保存:", self.data_file)
        print("📊 图表保存: two_sum_history_*.png")
        print("🛑 停止服务: 按 Ctrl+C")
        print("=" * 60)

        # 立即执行一次采集
        print("\n📡 执行首次采集...")
        self.collect_data()

        # 记录上次采集的时间点
        last_collection = None

        print("\n⏳ 定时服务已启动，等待下次采集...")
        print("   下次采集时间: 今天的 00:00, 08:00, 16:00")

        # 持续运行
        while self.running:
            should_collect, collection_key = self.should_collect_now(last_collection)

            if should_collect:
                print(f"\n⏰ 到达采集时间点 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self.collect_data()
                last_collection = collection_key
                print("\n⏳ 等待下次采集...")

            # 每分钟检查一次
            time.sleep(60)


def main():
    """主函数"""
    # 检查依赖
    try:
        import matplotlib
    except ImportError:
        print("❌ 请先安装matplotlib: pip install matplotlib")
        sys.exit(1)

    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except ImportError:
        print("❌ 请先安装requests: pip install requests")
        sys.exit(1)

    # 设置中文字体
    setup_chinese_font()

    collector = TwoSumDataCollector()

    try:
        collector.run()
    except KeyboardInterrupt:
        # 信号处理器会处理这个
        pass
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        collector.save_history()


if __name__ == "__main__":
    main()