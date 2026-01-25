import re
import requests
import logging
import random
import time
import string
import math
import os
import sys
from bs4 import BeautifulSoup
from collections import OrderedDict
from datetime import datetime
from playwright.sync_api import sync_playwright
import config

# -------------------------- 基础配置 --------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("function.log", "w", encoding="utf-8"), logging.StreamHandler()])

# 省份名称 <-> value 映射字典
PROVINCE_MAPPING = {
    "越南": "vn", "湖北": "hb", "内蒙古": "nm", "重庆": "cq", "四川": "sc",
    "北京": "bj", "山东": "sd", "广东": "gd", "江苏": "js", "上海": "sh",
    "河北": "he", "天津": "tj", "安徽": "ah", "陕西": "sn", "河南": "ha",
    "吉林": "jl", "浙江": "zj", "海南": "hi", "黑龙江": "hl", "俄罗斯": "ru",
    "云南": "yn", "福建": "fj", "韩国": "kr", "山西": "sx", "湖南": "hn",
    "贵州": "gz", "台湾": "tw", "广西": "gx", "青海": "qh", "辽宁": "ln",
    "新疆": "xj", "江西": "jx", "甘肃": "gs", "宁夏": "nx"
}
VALUE_TO_PROVINCE = {v: k for k, v in PROVINCE_MAPPING.items()}

# 地区优先级排序（按要求：海口、澄迈、吉阳、儋州、临高、陵水）
AREA_PRIORITY = ["海口", "澄迈", "吉阳", "儋州", "临高", "陵水"]

USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 SLBrowser/9.0.7.12231"
]

MIN_THINK_DELAY = 0.5
MAX_THINK_DELAY = 3.0
MOUSE_STEP_COUNT = 10

WINDOW_SIZE_POOL = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900), (2560, 1440)
]


# -------------------------- 代码2的工具函数（保留反爬特性） --------------------------
def human_like_delay():
    """模拟人类思考延迟"""
    delay = random.expovariate(1 / 1.5)
    delay = max(MIN_THINK_DELAY, min(delay, MAX_THINK_DELAY))
    time.sleep(delay)
    return delay


def generate_random_string(length=8):
    """生成随机字符串"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def human_mouse_move(page, start_x, start_y, end_x, end_y):
    """模拟人类非直线鼠标移动"""
    step_x = (end_x - start_x) / MOUSE_STEP_COUNT
    step_y = (end_y - start_y) / MOUSE_STEP_COUNT

    for i in range(MOUSE_STEP_COUNT):
        jitter_x = random.uniform(-5, 5)
        jitter_y = random.uniform(-5, 5)
        speed_factor = math.sin(i / MOUSE_STEP_COUNT * math.pi)
        current_x = start_x + step_x * i * speed_factor + jitter_x
        current_y = start_y + step_y * i * speed_factor + jitter_y

        page.mouse.move(current_x, current_y)
        time.sleep(random.uniform(0.01, 0.05))


def random_human_interactions(page):
    """随机执行人类无意义交互"""
    viewport = page.viewport_size
    interactions = [
        lambda: page.mouse.click(random.randint(50, viewport["width"] - 50),
                                 random.randint(50, viewport["height"] - 50),
                                 delay=random.uniform(0.05, 0.2)),
        lambda: page.mouse.wheel(0, random.randint(-200, 300),
                                 delta_mode=random.choice([0, 1])),
        lambda: page.keyboard.press("Tab", delay=random.uniform(0.1, 0.3)),
        lambda: page.mouse.click(random.randint(100, viewport["width"] - 100),
                                 random.randint(100, viewport["height"] - 100),
                                 button="right", delay=random.uniform(0.1, 0.2)),
        lambda: page.keyboard.press("Ctrl+A", delay=random.uniform(0.1, 0.3)) if random.choice([True, False]) else None
    ]
    selected = random.sample(interactions, k=random.randint(1, 2))
    for action in selected:
        try:
            action()
            human_like_delay()
        except:
            pass


def validate_province(province_input):
    """校验并标准化省份参数"""
    if province_input in VALUE_TO_PROVINCE:
        province_value = province_input
        province_name = VALUE_TO_PROVINCE[province_input]
    elif province_input in PROVINCE_MAPPING:
        province_value = PROVINCE_MAPPING[province_input]
        province_name = province_input
    else:
        raise ValueError(
            f"无效的省份参数：{province_input}\n"
            f"支持的省份名称：{list(PROVINCE_MAPPING.keys())}\n"
            f"支持的value值：{list(PROVINCE_MAPPING.values())}"
        )
    return province_value, province_name


# -------------------------- 代码2的IP处理核心函数 --------------------------
def extract_multicast_ips_from_page(page):
    """
    从页面动态提取组播源IP信息（仅处理组播表格，忽略酒店表格）
    直接通过Playwright定位渲染后的DOM，而非静态HTML解析
    """
    multicast_ips = []

    # 定位组播源表格（精准定位：aria-label="组播源列表" 的section下的表格）
    multicast_table = page.locator('section[aria-label="组播源列表"] table.iptv-table')
    # 等待表格加载完成
    multicast_table.wait_for(state="visible", timeout=15000)

    # 获取表格所有行
    ip_rows = multicast_table.locator("tbody tr").all()
    logging.info(f"发现组播源IP总数：{len(ip_rows)}")
    print(f"📥 发现组播源IP总数：{len(ip_rows)}")

    for row_idx, row in enumerate(ip_rows):
        try:
            # 提取IP地址（a.ip-link的文本）
            ip_link = row.locator('td[data-label="IP:"] a.ip-link')
            ip_address = ip_link.inner_text().strip() if ip_link.is_visible() else None

            # 提取状态（status-badge的文本）
            status_badge = row.locator('td[data-label="状态:"] span.status-badge')
            status = status_badge.inner_text().strip() if status_badge.is_visible() else None

            # 提取类型（类型列的文本）
            type_cell = row.locator('td[data-label="类型:"]')
            ip_type = type_cell.inner_text().strip() if type_cell.is_visible() else None

            if ip_address:  # 仅保留有IP的条目
                multicast_ips.append({
                    "ip_address": ip_address,
                    "status": status,
                    "type": ip_type,
                    "row_locator": row,  # 保留行定位器，用于后续点击
                    "link_locator": ip_link  # 保留IP链接定位器
                })
        except Exception as e:
            logging.error(f"提取第{row_idx + 1}行IP信息失败：{str(e)[:100]}")
            print(f"⚠️ 提取第{row_idx + 1}行IP信息失败：{str(e)[:100]}")
            continue

    return multicast_ips


def filter_and_sort_multicast_ips(ip_list):
    """
    筛选并排序组播IP：
    1. 过滤状态为"暂时失效"的IP
    2. 按AREA_PRIORITY中的地区顺序排序
    """
    # 步骤1：过滤非"暂时失效"的IP
    filtered_ips = [ip for ip in ip_list if ip.get('status') != "暂时失效"]
    logging.info(f"筛选后有效组播IP数量：{len(filtered_ips)}（过滤掉{len(ip_list) - len(filtered_ips)}个暂时失效IP）")
    print(f"🔍 筛选后有效组播IP数量：{len(filtered_ips)}（过滤掉{len(ip_list) - len(filtered_ips)}个暂时失效IP）")

    if not filtered_ips:
        logging.warning("无有效组播IP（所有IP均为暂时失效）")
        print("❌ 无有效组播IP（所有IP均为暂时失效）")
        return []

    # 步骤2：按地区优先级排序
    def get_area_priority(ip_type):
        """获取IP类型对应的地区优先级（未匹配的放最后）"""
        if not ip_type:
            return len(AREA_PRIORITY)
        for idx, area in enumerate(AREA_PRIORITY):
            if area in ip_type:
                return idx
        return len(AREA_PRIORITY)  # 未匹配的地区优先级最低

    # 按地区优先级排序
    sorted_ips = sorted(filtered_ips, key=lambda x: get_area_priority(x.get('type')))

    # 输出排序日志
    logging.info("组播IP排序结果（按海口→澄迈→吉阳→儋州→临高→陵水）：")
    print("📊 组播IP排序结果（按海口→澄迈→吉阳→儋州→临高→陵水）：")
    for i, ip in enumerate(sorted_ips[:5]):  # 仅展示前5条
        log_msg = f"   [{i + 1}] {ip['ip_address']} | 状态：{ip['status']} | 类型：{ip['type']}"
        logging.info(log_msg)
        print(log_msg)

    return sorted_ips


def extract_ip_port_from_detail_page(page):
    """
    从IP详情页提取IP+端口信息（抓取渲染后的DOM中的span.ip-detail-value）
    返回格式：IP:端口（如 119.41.166.139:8188）
    """
    human_like_delay()
    # 等待详情页加载完成
    page.wait_for_load_state("domcontentloaded", timeout=20000)

    # 定位IP端口行的value（精准匹配：IP端口标签后的value）
    # 方式1：先找"IP端口:"标签，再找同级的value
    ip_port_label = page.locator('span.ip-detail-label:text("IP端口:")')
    if ip_port_label.is_visible():
        ip_port_value = ip_port_label.locator("..").locator("span.ip-detail-value")
        ip_port_text = ip_port_value.inner_text().strip()
        if ip_port_text and ":" in ip_port_text:
            logging.info(f"详情页提取到IP+端口：{ip_port_text}")
            print(f"✅ 详情页提取到IP+端口：{ip_port_text}")
            return ip_port_text

    # 方式2：直接定位所有ip-detail-value，筛选含":"的（兜底）
    all_values = page.locator('span.ip-detail-value').all_inner_texts()
    for value in all_values:
        if ":" in value and "." in value:  # 包含IP和端口的特征
            logging.info(f"兜底提取到IP+端口：{value.strip()}")
            print(f"✅ 兜底提取到IP+端口：{value.strip()}")
            return value.strip()

    # 方式3：从页面URL/文本中提取（最终兜底）
    page_text = page.inner_text("body")
    ip_port_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d+\b', page_text)
    if ip_port_match:
        ip_port_text = ip_port_match.group()
        logging.info(f"正则提取到IP+端口：{ip_port_text}")
        print(f"✅ 正则提取到IP+端口：{ip_port_text}")
        return ip_port_text

    logging.warning("详情页未找到IP+端口信息")
    print("❌ 详情页未找到IP+端口信息")
    return None


def get_province_multicast_ip_ports(province_input):
    """
    获取指定省份的组播源IP及端口信息
    :param province_input: 省份名称（如"海南"）或value值（如"hi"）
    :return: 前两条有效组播IP的详情（含IP+端口）
    """
    # 1. 校验并标准化省份参数
    try:
        province_value, province_name = validate_province(province_input)
    except ValueError as e:
        logging.error(f"参数校验失败：{e}")
        print(f"❌ 参数校验失败：{e}")
        return None

    storage_path = "iptv_storage_state.json"
    final_ip_details = []  # 存储最终的IP+端口信息

    with sync_playwright() as p:
        # 随机选择基础配置
        random_ua = random.choice(USER_AGENT_POOL)
        random_width, random_height = random.choice(WINDOW_SIZE_POOL)
        random_color_scheme = random.choice(["light", "dark"])
        random_device_scale = random.choice([1.0, 1.25, 1.5])

        # 启动浏览器（关闭headless便于调试，上线时改为True）
        browser = p.chromium.launch(
            headless=True,  # 调试时设为False，可看到浏览器操作；上线改为True
            args=[
                "--disable-blink-features=AutomationControlled,RenderStealToken,ComputePressure",
                "--disable-features=WebRtcHideLocalIpsWithMdns,PreloadMediaEngagementData,AutoplayIgnoreWebAudio,CanvasFingerprintingProtection",
                "--disable-webgl",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-popup-blocking",
                "--disable-background-networking",
                "--disable-preconnect",
                "--disable-ipv6",
                "--disable-notifications",
                "--disable-extensions",
                "--disable-plugins",
                "--start-maximized",
                f"--window-size={random_width},{random_height}",
                "--enable-dom-storage",
                "--enable-encrypted-media",
                "--enable-site-per-process",
            ],
            ignore_default_args=[
                "--enable-automation",
                "--disable-default-apps",
                "--disable-component-update"
            ]
        )

        # 创建上下文
        context = browser.new_context(
            user_agent=random_ua,
            viewport={"width": random_width, "height": random_height},
            locale=random.choice(["zh-CN", "zh-Hans-CN", "zh"]),
            timezone_id="Asia/Shanghai",
            color_scheme=random_color_scheme,
            device_scale_factor=random_device_scale,
            storage_state=storage_path if os.path.exists(storage_path) else None,
            extra_http_headers={
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "max-age=0",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "DNT": "1" if random.choice([True, False]) else "0",
                f"X-Random-{generate_random_string()}": generate_random_string(16)
            },
        )

        # 拦截无用请求（加快加载）
        def handle_route(route, request):
            blocked_types = ["image", "video", "audio", "font", "stylesheet", "ping"]
            blocked_domains = ["ad.", "analytics.", "track.", "cdn.ads.", "google-analytics.com", "gtag.js"]
            if request.resource_type in blocked_types or any(d in request.url for d in blocked_domains):
                route.abort()
            else:
                headers = request.headers.copy()
                headers["Referer"] = random.choice(["", "https://iptv.cqshushu.com/"]) if random.choice(
                    [True, False]) else headers.get("Referer")
                route.continue_(headers=headers)

        context.route("**/*", handle_route)
        page = context.new_page()

        # 注入反检测JS
        page.add_init_script(f"""
            Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
            navigator.hardwareConcurrency = {random.choice([4, 8, 12, 16])};
            navigator.deviceMemory = {random.choice([4, 8, 16])};
            navigator.maxTouchPoints = {random.choice([0, 1, 5])};
            delete navigator.locks;
            delete window._playwrightDevtoolsDetector;
            delete window.__playwright_evaluation_script__;
            const originalNow = Date.now;
            Date.now = () => originalNow() + {random.randint(-100, 100)};
            console.debug = () => {{}};
            console.log = (...args) => {{}};
        """)

        try:
            start_time = time.time()
            logging.info(f"开始抓取 {province_name} 的组播源IP信息")
            print(f"🚀 开始抓取 {province_name} 的组播源IP信息")
            print(f"📌 随机User-Agent：{random_ua[:50]}...")

            # 访问首页
            home_url = "https://iptv.cqshushu.com/"
            max_retry_goto = 3
            retry_goto_count = 0
            page_loaded = False
            while retry_goto_count < max_retry_goto and not page_loaded:
                try:
                    human_like_delay()
                    page.goto(home_url, wait_until="domcontentloaded", timeout=60000)
                    if page.content().strip() != "<html><head></head><body></body></html>":
                        page_loaded = True
                    else:
                        raise Exception("页面加载后内容为空")
                    break
                except Exception as e:
                    retry_goto_count += 1
                    logging.warning(f"首页访问重试{retry_goto_count}/{max_retry_goto}：{str(e)[:100]}")
                    print(f"⚠️ 首页访问重试{retry_goto_count}/{max_retry_goto}：{str(e)[:100]}")
                    human_like_delay()
                    if retry_goto_count == max_retry_goto:
                        raise Exception("首页多次加载为空，终止操作")

            # 随机交互（模拟人类浏览）
            random_human_interactions(page)

            # 定位并选择省份
            province_select = page.locator("#provinceSelect")
            province_select.wait_for(state="visible", timeout=15000)

            # 模拟鼠标移动到下拉框
            box = province_select.bounding_box()
            if box:
                viewport = page.viewport_size
                target_x = box["x"] + box["width"] / 2 + random.randint(-3, 3)
                target_y = box["y"] + box["height"] / 2 + random.randint(-3, 3)
                start_x = random.randint(10, viewport["width"] // 2)
                start_y = random.randint(10, viewport["height"] // 2)
                human_mouse_move(page, start_x, start_y, target_x, target_y)
                human_like_delay()

            # 选择省份
            hover_delay = random.uniform(0.1, 0.3)
            time.sleep(hover_delay)
            province_select.hover()
            human_like_delay()
            select_delay = random.uniform(0.1, 0.3)
            time.sleep(select_delay)
            province_select.select_option(value=province_value)
            logging.info(f"已选择省份：{province_name}")
            print(f"✅ 已选择省份：{province_name}")

            # 等待省份页面跳转
            random_human_interactions(page)
            max_retry_jump = 3
            retry_jump_count = 0
            while retry_jump_count < max_retry_jump:
                try:
                    page.wait_for_url(f"**{province_value}**", wait_until="domcontentloaded", timeout=20000)
                    break
                except Exception as e:
                    retry_jump_count += 1
                    logging.warning(f"页面跳转重试{retry_jump_count}/{max_retry_jump}：{str(e)[:100]}")
                    print(f"⚠️ 页面跳转重试{retry_jump_count}/{max_retry_jump}：{str(e)[:100]}")
                    human_like_delay()
                    if retry_jump_count == max_retry_jump:
                        raise Exception("页面跳转多次超时")

            # ========== 核心步骤1：提取组播IP列表 ==========
            multicast_ips = extract_multicast_ips_from_page(page)
            if not multicast_ips:
                logging.error("未提取到任何组播源IP")
                print("❌ 未提取到任何组播源IP")
                return None

            # ========== 核心步骤2：筛选并排序组播IP ==========
            sorted_ips = filter_and_sort_multicast_ips(multicast_ips)
            if not sorted_ips:
                return None

            # ========== 核心步骤3：选择前两条IP，抓取详情页端口 ==========
            target_ips = sorted_ips[:2]
            logging.info(f"选择前{len(target_ips)}条有效组播IP进入详情页")
            print(f"\n🎯 选择前{len(target_ips)}条有效组播IP进入详情页：")
            for i, ip in enumerate(target_ips):
                log_msg = f"   [{i + 1}] {ip['ip_address']} | 类型：{ip['type']} | 状态：{ip['status']}"
                logging.info(log_msg)
                print(log_msg)

            for idx, target_ip in enumerate(target_ips):
                try:
                    logging.info(f"正在访问第{idx + 1}条IP详情页：{target_ip['ip_address']}")
                    print(f"\n🔗 正在访问第{idx + 1}条IP详情页：{target_ip['ip_address']}")

                    # 模拟人类点击IP链接（使用保留的link_locator，避免重新定位）
                    ip_link = target_ip["link_locator"]
                    # 鼠标移动到链接上
                    link_box = ip_link.bounding_box()
                    if link_box:
                        human_mouse_move(page,
                                         random.randint(50, 100), random.randint(50, 100),
                                         link_box["x"] + link_box["width"] / 2,
                                         link_box["y"] + link_box["height"] / 2)
                        human_like_delay()

                    # 点击IP链接（触发gotoIP函数，跳转到详情页）
                    ip_link.click()
                    human_like_delay()

                    # ========== 提取详情页的IP+端口 ==========
                    ip_port = extract_ip_port_from_detail_page(page)

                    # 保存结果
                    final_ip_details.append({
                        "rank": idx + 1,
                        "ip_address": target_ip["ip_address"],
                        "status": target_ip["status"],
                        "type": target_ip["type"],
                        "ip_port": ip_port,  # 核心结果：IP:端口
                        "detail_url": page.url
                    })

                    # 返回省份列表页（继续处理下一个IP，最后一个IP无需返回）
                    if idx < len(target_ips) - 1:
                        page.go_back()
                        human_like_delay()
                        page.wait_for_load_state("domcontentloaded")
                        # 重新等待组播表格加载（返回后可能需要重新定位）
                        page.locator('section[aria-label="组播源列表"] table.iptv-table').wait_for(state="visible")

                except Exception as e:
                    logging.error(f"第{idx + 1}条IP详情页抓取失败：{str(e)[:150]}")
                    print(f"❌ 第{idx + 1}条IP详情页抓取失败：{str(e)[:150]}")
                    continue

            logging.info(f"总耗时：{time.time() - start_time:.2f}秒")
            print(f"\n⏱️  总耗时：{time.time() - start_time:.2f}秒")
            return final_ip_details

        except Exception as e:
            logging.error(f"核心逻辑出错：{str(e)[:200]}")
            print(f"\n❌ 核心逻辑出错：{str(e)[:200]}")
            try:
                logging.info(f"当前页面URL：{page.url}")
                print(f"📝 当前页面URL：{page.url}")
            except:
                pass
            return None
        finally:
            # 持久化缓存
            if 'context' in locals():
                context.storage_state(path=storage_path)
            # 关闭浏览器
            if 'browser' in locals():
                context.close()
                browser.close()
                logging.info("浏览器已关闭")
                print("\n✅ 浏览器已关闭")


# -------------------------- 代码1的保留功能（修改动态链接生成逻辑） --------------------------
def display_basic_info(ip_details):
    """展示提取的IP基础信息（适配新的IP详情结构）"""
    if not ip_details:
        print("未获取到任何IP信息")
        logging.warning("未获取到任何IP信息")
        return

    print("\n===== IP基础信息 =====")
    for idx, item in enumerate(ip_details, 1):
        print(f"{idx}. IP地址: {item['ip_address']}")
        print(f"   状态: {item['status'] or '未知'}")
        print(f"   类型: {item['type'] or '未知'}")
        print(f"   IP+端口: {item['ip_port'] or '未获取到'}")
        print("-" * 50)


def get_all_source_urls(province_input="海南"):
    """
    获取所有待爬取的链接：包括config中的和动态生成的（基于真实端口）
    :param province_input: 省份名称/value，默认海南
    """
    # 1. 通过Playwright获取IP+端口信息
    ip_details = get_province_multicast_ip_ports(province_input)

    # 展示原始IP信息
    display_basic_info(ip_details)

    # 生成动态链接（使用真实获取的端口，不再预设）
    dynamic_links = []
    base_url = "http://iptv.cqshushu.com/?s={ip_port}&t=multicast&channels=1&format=txt"

    if ip_details:
        for ip_item in ip_details:
            ip_port = ip_item.get('ip_port')
            if ip_port:
                # URL编码冒号
                encoded_ip_port = ip_port.replace(":", "%3A")
                link = base_url.format(ip_port=encoded_ip_port)
                dynamic_links.append(link)
                logging.info(f"生成链接 (IP: {ip_item['ip_address']}, 端口: {ip_port.split(':')[1]}): {link}")
                print(
                    f"\n生成链接 (IP: {ip_item['ip_address']}, 类型: {ip_item['type']}, 端口: {ip_port.split(':')[1]}):")
                print(link)

    # 2. 合并config中的链接和动态生成的链接（去重）
    all_source_urls = list(config.source_urls)  # 先复制config中的链接
    for link in dynamic_links:
        if link not in all_source_urls:  # 去重
            all_source_urls.append(link)

    print(f"\n===== 合并后的爬取链接总数 =====")
    print(f"Config中的链接数: {len(config.source_urls)}")
    print(f"动态生成的链接数: {len(dynamic_links)}")
    print(f"合并后总链接数: {len(all_source_urls)}")
    logging.info(f"合并后总链接数: {len(all_source_urls)}")

    return all_source_urls


def parse_template(template_file):
    """保留代码1的模板解析功能"""
    template_channels = OrderedDict()
    current_category = None

    with open(template_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    template_channels[current_category] = []
                elif current_category:
                    channel_name = line.split(",")[0].strip()
                    template_channels[current_category].append(channel_name)

    return template_channels


def fetch_channels(url):
    """保留代码1的频道爬取功能"""
    channels = OrderedDict()

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/plain,text/html,*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }

        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        text = response.text.strip()

        # 调试日志
        logging.info(f"url: {url} 响应状态: {response.status_code}")
        logging.info(f"响应内容长度: {len(text)} 字符")
        logging.info(f"响应前200字符: {text[:200] if text else '空响应'}")

        lines = text.splitlines() if text else []

        # 检查是否为 M3U 格式
        is_m3u = any("#EXTINF" in line for line in lines[:10]) if lines else False
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"url: {url} 获取成功，判断为{source_type}格式，共 {len(lines)} 行")

        if is_m3u:
            # M3U 格式解析逻辑保持不变
            current_category = None
            channel_name = None

            for line in lines:
                line = line.strip()
                if line.startswith("#EXTINF"):
                    match = re.search(r'group-title="(.*?)",(.*)', line)
                    if match:
                        current_category = match.group(1).strip()
                        channel_name = match.group(2).strip()
                        if current_category not in channels:
                            channels[current_category] = []
                    else:
                        # 尝试其他可能的格式
                        match = re.search(r'tvg-name="(.*?)"', line)
                        if match:
                            channel_name = match.group(1).strip()
                elif line and not line.startswith("#"):
                    channel_url = line.strip()
                    if current_category and channel_name:
                        channels[current_category].append((channel_name, channel_url))
                        channel_name = None
        else:
            # TXT 格式解析 - 增强版
            current_category = None
            line_num = 0

            # 核心修改：定义关键词到分类的映射（按优先级排序）
            keyword_categories = [
                ('4K', '4K频道'),
                ('CCTV', '央视频道'),
                ('卫视', '卫视频道'),
                ('SD', 'SD频道'),
                ('海南', '海南地方'),
            ]

            # 尝试从URL中提取可能的默认分类名（仅未匹配关键词时使用）
            default_category = "默认分类"
            url_match = re.search(r'/([^/]+?)\.(txt|m3u|m3u8)$', url)
            if url_match:
                default_category = url_match.group(1)
            else:
                # 尝试从URL参数中提取
                param_match = re.search(r'[?&]name=([^&]+)', url)
                if param_match:
                    default_category = param_match.group(1)

            for line in lines:
                line_num += 1
                line = line.strip()

                # 跳过空行
                if not line:
                    continue

                # 如果是简短的注释行，跳过
                if line.startswith("#") and len(line) < 50 and "," not in line:
                    continue

                # 检查是否为分类行（包含 #genre#）
                if "#genre#" in line.lower():
                    parts = line.split(",", 1)
                    if len(parts) >= 2:
                        current_category = parts[0].strip()
                        channels[current_category] = []
                        logging.debug(f"发现分类: {current_category}")
                    else:
                        # 处理只有 #genre# 的情况（仍用关键词匹配逻辑）
                        current_category = None
                    continue

                # 处理频道行 - 检测是否有逗号分隔
                if "," in line:
                    # 先检查是否是分类行（如：央视频道,#genre# 但被上面的条件漏掉了）
                    if line.lower().endswith("#genre#"):
                        current_category = line.split(",")[0].strip()
                        channels[current_category] = []
                        logging.debug(f"发现无标记分类: {current_category}")
                        continue

                    parts = line.split(",", 1)
                    if len(parts) == 2:
                        channel_name = parts[0].strip()
                        channel_url = parts[1].strip()

                        # 检查第二部分是否是有效的URL
                        url_pattern = re.compile(
                            r'^(https?|rtp|rtsp|udp)://|'
                            r'^\d{1,3}(\.\d{1,3}){3}:\d+|'
                            r'^[a-zA-Z0-9]+://'
                        )

                        if url_pattern.search(channel_url):
                            # 清理频道名称中的特殊标记
                            channel_name = re.sub(r'[#].*$', '', channel_name).strip()

                            # 核心修改：无分类时，优先按频道名称关键词匹配分类
                            if current_category is None:
                                matched_category = None
                                # 按优先级遍历关键词
                                for keyword, cat in keyword_categories:
                                    if keyword in channel_name:
                                        matched_category = cat
                                        break
                                # 未匹配到关键词才用默认分类
                                current_category = matched_category if matched_category else default_category
                                # 初始化分类（如果不存在）
                                if current_category not in channels:
                                    channels[current_category] = []
                                logging.debug(f"根据频道名称匹配分类: {channel_name} → {current_category}")

                            # 如果频道名称为空，从URL提取或使用默认名称
                            if not channel_name:
                                if channel_url:
                                    # 尝试从URL提取频道名称
                                    url_name_match = re.search(r'/([^/]+?)(?:\.m3u8|\.ts|\.mp4)?$', channel_url)
                                    if url_name_match:
                                        channel_name = url_name_match.group(1)
                                    else:
                                        # 从URL中提取IP或域名部分
                                        host_match = re.search(r'://([^/]+)', channel_url)
                                        if host_match:
                                            channel_name = host_match.group(1)
                                        else:
                                            channel_name = f"频道_{line_num}"
                                else:
                                    channel_name = f"频道_{line_num}"

                            # 添加频道
                            if channel_url:
                                channels[current_category].append((channel_name, channel_url))
                                logging.debug(f"添加频道: {channel_name} -> {channel_url[:50]}...")
                        else:
                            # 可能是一个分类行但没有#genre#
                            potential_category = line.split(",")[0].strip()
                            if potential_category and len(potential_category) < 50:  # 分类名通常不会太长
                                current_category = potential_category
                                channels[current_category] = []
                                logging.debug(f"发现无标记分类: {current_category}")
                elif line and re.search(r'^(https?|rtp|rtsp|udp)://|^\d{1,3}(\.\d{1,3}){3}:\d+', line):
                    # 只有URL，没有逗号分隔
                    channel_url = line.strip()

                    # 尝试从URL提取频道名称
                    url_name_match = re.search(r'/([^/]+?)(?:\.m3u8|\.ts|\.mp4)?$', channel_url)
                    if url_name_match:
                        channel_name = url_name_match.group(1)
                    else:
                        # 从URL中提取IP或域名部分
                        host_match = re.search(r'://([^/]+)', channel_url)
                        if host_match:
                            channel_name = host_match.group(1)
                        else:
                            channel_name = f"频道_{line_num}"

                    # 核心修改：无分类时，优先按频道名称关键词匹配分类
                    if current_category is None:
                        matched_category = None
                        # 按优先级遍历关键词
                        for keyword, cat in keyword_categories:
                            if keyword in channel_name:
                                matched_category = cat
                                break
                        # 未匹配到关键词才用默认分类
                        current_category = matched_category if matched_category else default_category
                        # 初始化分类（如果不存在）
                        if current_category not in channels:
                            channels[current_category] = []
                        logging.debug(f"根据频道名称匹配分类: {channel_name} → {current_category}")

                    if channel_url:
                        channels[current_category].append((channel_name, channel_url))
                        logging.debug(f"添加未命名频道: {channel_name} -> {channel_url[:50]}...")

        # 统计和日志
        total_channels = sum(len(ch_list) for ch_list in channels.values())
        categories = list(channels.keys())

        if total_channels > 0:
            logging.info(f"url: {url} 爬取成功✅，共 {len(categories)} 个分类，{total_channels} 个频道")

            # 记录每个分类的频道数量
            for category, ch_list in channels.items():
                logging.info(f"分类 '{category}': {len(ch_list)} 个频道")
        else:
            logging.warning(f"url: {url} 获取到0个频道，可能是格式不支持或内容为空")

            # 如果lines不为空但解析不到频道，记录原始内容的前几行用于调试
            if lines and len(lines) > 0:
                logging.warning(f"原始内容前10行:")
                for i, line in enumerate(lines[:10], 1):
                    logging.warning(f"行{i}: {line}")

    except requests.RequestException as e:
        logging.error(f"url: {url} 爬取失败❌, Error: {e}")
        # 尝试记录响应状态码和内容（如果有）
        if 'response' in locals():
            logging.error(f"状态码: {response.status_code}")
            logging.error(f"响应头: {response.headers}")
            if hasattr(response, 'text') and response.text:
                logging.error(f"响应内容前500字符: {response.text[:500]}")
            else:
                logging.error("响应内容为空")
    except Exception as e:
        logging.error(f"url: {url} 解析时发生意外错误: {e}")
        import traceback
        logging.error(traceback.format_exc())

    return channels


def match_channels(template_channels, all_channels):
    """保留代码1的频道匹配功能"""
    matched_channels = OrderedDict()

    for category, channel_list in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in channel_list:
            for online_category, online_channel_list in all_channels.items():
                for online_channel_name, online_channel_url in online_channel_list:
                    if channel_name == online_channel_name:
                        matched_channels[category].setdefault(channel_name, []).append(online_channel_url)

    return matched_channels


def filter_source_urls(template_file, province_input="海南"):
    """修改：支持传入省份参数"""
    template_channels = parse_template(template_file)
    # 获取合并后的所有源链接（传入省份参数）
    source_urls = get_all_source_urls(province_input)

    all_channels = OrderedDict()
    for url in source_urls:
        fetched_channels = fetch_channels(url)
        for category, channel_list in fetched_channels.items():
            if category in all_channels:
                all_channels[category].extend(channel_list)
            else:
                all_channels[category] = channel_list

    matched_channels = match_channels(template_channels, all_channels)

    return matched_channels, template_channels


def is_ipv6(url):
    """保留代码1的IPv6判断功能"""
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None


def updateChannelUrlsM3U(channels, template_channels):
    """保留代码1的M3U/TXT生成功能"""
    written_urls = set()

    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    for group in config.announcements:
        for announcement in group['entries']:
            if announcement['name'] is None:
                announcement['name'] = current_date

    with open("live.m3u", "w", encoding="utf-8") as f_m3u:
        f_m3u.write(f"""#EXTM3U x-tvg-url={",".join(f'"{epg_url}"' for epg_url in config.epg_urls)}\n""")

        with open("live.txt", "w", encoding="utf-8") as f_txt:
            for group in config.announcements:
                f_txt.write(f"{group['channel']},#genre#\n")
                for announcement in group['entries']:
                    f_m3u.write(
                        f"""#EXTINF:-1 tvg-id="1" tvg-name="{announcement['name']}" tvg-logo="{announcement['logo']}" group-title="{group['channel']}",{announcement['name']}\n""")
                    f_m3u.write(f"{announcement['url']}\n")
                    f_txt.write(f"{announcement['name']},{announcement['url']}\n")

            for category, channel_list in template_channels.items():
                f_txt.write(f"{category},#genre#\n")
                if category in channels:
                    for channel_name in channel_list:
                        if channel_name in channels[category]:
                            sorted_urls = sorted(channels[category][channel_name], key=lambda url: not is_ipv6(
                                url) if config.ip_version_priority == "ipv6" else is_ipv6(url))
                            filtered_urls = []
                            for url in sorted_urls:
                                if url and url not in written_urls and not any(
                                        blacklist in url for blacklist in config.url_blacklist):
                                    filtered_urls.append(url)
                                    written_urls.add(url)

                            total_urls = len(filtered_urls)
                            for index, url in enumerate(filtered_urls, start=1):
                                if is_ipv6(url):
                                    url_suffix = f"$LR•IPV6" if total_urls == 1 else f"$LR•IPV6『线路{index}』"
                                else:
                                    url_suffix = f"$LR•IPV4" if total_urls == 1 else f"$LR•IPV4『线路{index}』"
                                if '$' in url:
                                    base_url = url.split('$', 1)[0]
                                else:
                                    base_url = url

                                new_url = f"{base_url}{url_suffix}"

                                f_m3u.write(
                                    f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" tvg-logo=\"https://gcore.jsdelivr.net/gh/yuanzl77/TVlogo@master/png/{channel_name}.png\" group-title=\"{category}\",{channel_name}\n")
                                f_m3u.write(new_url + "\n")
                                f_txt.write(f"{channel_name},{new_url}\n")

            f_txt.write("\n")


# -------------------------- 主函数（支持省份输入） --------------------------
if __name__ == "__main__":
    # 处理省份参数（命令行传入或默认海南）
    target_province = "海南"
    if len(sys.argv) >= 2:
        target_province = sys.argv[1]
        print(f"📌 接收到省份参数：{target_province}")

    template_file = "demo.txt"
    try:
        channels, template_channels = filter_source_urls(template_file, target_province)
        updateChannelUrlsM3U(channels, template_channels)
        print("\n🎉 全部流程执行完成，已生成 live.m3u 和 live.txt 文件")
    except Exception as e:
        logging.error(f"主流程执行失败：{e}")
        print(f"\n❌ 主流程执行失败：{e}")
