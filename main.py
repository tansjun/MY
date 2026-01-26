import re
import requests
import logging
import random
import time
import string
import math
import os
import sys
import json
from bs4 import BeautifulSoup
from collections import OrderedDict
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
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

# 反检测配置
ANTI_DETECTION_CONFIG = {
    "chrome_args": [
        "--disable-blink-features=AutomationControlled,RenderStealToken,ComputePressure,WebDriverDetection",
        "--disable-features=WebRtcHideLocalIpsWithMdns,PreloadMediaEngagementData,AutoplayIgnoreWebAudio,CanvasFingerprintingProtection,NavigatorWeBDriverDetection",
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
        "--enable-dom-storage",
        "--enable-encrypted-media",
        "--enable-site-per-process",
        "--disable-features=VizDisplayCompositor",
        "--disable-breakpad",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-hang-monitor",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
        "--no-service-autorun",
        "--password-store=basic",
        "--use-mock-keychain",
        "--disable-features=AudioServiceOutOfProcess",
        "--disable-ipc-flooding-protection",
        "--allow-running-insecure-content",
        "--ignore-certificate-errors",
        "--ignore-ssl-errors",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        "--flag-switches-begin --disable-features=WebDriverDetection --flag-switches-end"
    ],
    "ignore_default_args": [
        "--enable-automation",
        "--disable-default-apps",
        "--disable-component-update",
        "--enable-blink-features=AutomationControlled"
    ]
}


# -------------------------- 初始化清理函数 --------------------------
def init_clean_invalid_files():
    """初始化清理无效的JSON文件"""
    invalid_files = ["iptv_storage_state.json", "storage_reuse_count.json"]
    for file in invalid_files:
        if os.path.exists(file):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content or not json.loads(content):
                        os.remove(file)
                        logging.info(f"清理无效文件：{file}")
            except:
                os.remove(file)
                logging.warning(f"清理异常文件：{file}")


# 执行初始化清理
init_clean_invalid_files()


# -------------------------- 反爬工具函数 --------------------------
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
    """随机执行人类无意义交互（增加交互类型和随机性）"""
    try:
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
            lambda: page.keyboard.press("Ctrl+A", delay=random.uniform(0.1, 0.3)) if random.choice(
                [True, False]) else None,
            lambda: page.keyboard.press("Space", delay=random.uniform(0.05, 0.2)),
            lambda: page.mouse.move(random.randint(0, viewport["width"]),
                                    random.randint(0, viewport["height"]))
        ]
        selected = random.sample(interactions, k=random.randint(1, 3))
        for action in selected:
            try:
                action()
                human_like_delay()
            except Exception as e:
                logging.warning(f"随机交互执行失败: {str(e)[:100]}")
    except Exception as e:
        logging.warning(f"随机交互初始化失败: {str(e)[:100]}")


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


def extract_verify_cookie_prefix(page):
    """从页面脚本中动态提取验证Cookie的前缀（避免硬编码）"""
    try:
        # 等待页面脚本加载
        page.wait_for_load_state("domcontentloaded", timeout=5000)
        # 执行JS提取前缀（和网页脚本的拼接逻辑对齐）
        prefix = page.evaluate("""() => {
            // 匹配网页中 'xxx'+'_'+Date.now() 的前缀部分
            const scripts = document.querySelectorAll('body script');
            for (const script of scripts) {
                const scriptContent = script.textContent;
                const prefixMatch = scriptContent.match(/var\\s+c\\s*=\\s*'([0-9a-f]+)'\\s*\\+\\s*'_'\\s*\\+\\s*Date\\.now\\(\\)/);
                if (prefixMatch) {
                    return prefixMatch[1];
                }
            }
            return null;
        }""")
        return prefix if prefix else "87eb4da0dd394d53"  # 兜底默认值
    except Exception as e:
        logging.warning(f"提取Cookie前缀失败，使用默认值：{e}")
        return "87eb4da0dd394d53"


def generate_human_like_verify_cookie(page):
    """生成带人类时序特征的验证Cookie（适配Cloudflare检测）"""
    try:
        # 1. 等待页面完全加载（确保和人类操作一致：先等页面加载再生成Cookie）
        page.wait_for_load_state("load", timeout=8000)
        # 模拟人类浏览行为：随机滚动+停留
        page.mouse.wheel(0, random.randint(100, 300))
        human_like_delay()
        page.mouse.wheel(0, random.randint(-200, 100))
        human_like_delay()

        # 2. 动态提取前缀（优先从Cookie中读取已有前缀，而非仅从脚本）
        existing_cookies = page.context.cookies()
        prefix = None
        for cookie in existing_cookies:
            if cookie["name"] == "list_js_verified" and "_" in cookie["value"]:
                prefix = cookie["value"].split("_")[0]
                break
        if not prefix:
            prefix = extract_verify_cookie_prefix(page)

        # 3. 生成Cookie（严格匹配网页原生格式：仅前缀+时间戳，移除随机后缀）
        ts = int(time.time() * 1000) + random.randint(-100, 100)
        verify_token = f"{prefix}_{ts}"  # 移除随机后缀，和网页原生一致
        # 4. 写入Cookie（属性严格匹配Cloudflare要求）
        page.context.add_cookies([{
            "name": "list_js_verified",
            "value": verify_token,
            "domain": "cqshushu.com",  # 移除前缀点，避免跨域Cookie异常
            "path": "/",
            "expires": int(time.time()) + 1800,  # 30分钟，匹配网页默认
            "httpOnly": False,
            "secure": page.url.startswith("https"),
            "sameSite": "None"  # 适配Cloudflare的SameSite策略
        }])
        # 强制刷新Cookie（确保生效）
        page.evaluate(f'document.cookie = "list_js_verified={verify_token}; path=/; domain=cqshushu.com; max-age=1800"')
        logging.info(f"生成适配Cloudflare的验证Cookie：{verify_token}")
        return verify_token
    except Exception as e:
        logging.warning(f"提取Cookie前缀失败，使用默认值：{e}")
        verify_token = f"87eb4da0dd394d53_{int(time.time() * 1000)}"
        page.context.add_cookies([{
            "name": "list_js_verified",
            "value": verify_token,
            "domain": "cqshushu.com",
            "path": "/",
            "expires": int(time.time()) + 1800,
            "httpOnly": False,
            "secure": page.url.startswith("https"),
            "sameSite": "None"
        }])
        return verify_token


def inject_anti_detection_scripts(page):
    """注入深度反检测脚本，精准绕过当前验证逻辑"""
    anti_detect_script = f"""
        // 1. 彻底屏蔽webdriver属性（覆盖验证脚本的检测逻辑）
        Object.defineProperty(navigator, 'webdriver', {{
            get: () => false,  // 验证脚本判断===true，此处返回false而非undefined
            set: () => {{}},
            configurable: false,
            enumerable: true
        }});

        // 2. 移除所有webdriver相关标识（覆盖验证脚本的遍历检测）
        const removeDriverKeys = () => {{
            const keys = Object.getOwnPropertyNames(window);
            for (let k of keys) {{
                if (/^\\$?cdc_/.test(k)||/__webdriver|__driver|__selenium|__fxdriver/i.test(k)) {{
                    delete window[k];
                }}
            }}
            delete window.domAutomation;
            delete window.domAutomationController;
            document.documentElement.removeAttribute('webdriver');
        }};
        removeDriverKeys();
        // 监听属性新增，实时删除
        const windowProxy = new Proxy(window, {{
            set: (target, prop, value) => {{
                if (/^\\$?cdc_/.test(prop)||/__webdriver|__driver|__selenium|__fxdriver/i.test(prop)) {{
                    return true;
                }}
                target[prop] = value;
                return true;
            }}
        }});
        Object.defineProperty(window, '__proto__', {{ value: windowProxy }});

        // 3. 伪装plugins为原生PluginArray类型
        const originalPlugins = navigator.plugins;
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                const plugins = originalPlugins || [{{
                    name: 'Chrome PDF Plugin',
                    filename: 'internal-pdf-viewer',
                    description: 'Portable Document Format'
                }}, {{
                    name: 'Chrome Widevine CDM',
                    filename: 'widevinecdm.dll',
                    description: 'Widevine Content Decryption Module'
                }}, {{
                    name: 'Native Client',
                    filename: 'internal-nacl-plugin',
                    description: 'Native Client'
                }}];
                Object.defineProperty(plugins, 'toString', {{
                    value: () => '[object PluginArray]',
                    configurable: false
                }});
                return plugins;
            }},
            configurable: false,
            enumerable: true
        }});

        // 4. 修复chrome.runtime.connect方法（验证脚本检测该方法是否为function）
        if (window.chrome && !window.chrome.runtime) {{
            window.chrome.runtime = {{
                connect: () => ({{
                    postMessage: () => {{}},
                    onMessage: {{ addListener: () => {{}} }}
                }}),
                sendMessage: () => {{}},
                onMessage: {{ addListener: () => {{}} }}
            }};
        }} else if (window.chrome && window.chrome.runtime && typeof window.chrome.runtime.connect !== 'function') {{
            window.chrome.runtime.connect = () => ({{
                postMessage: () => {{}},
                onMessage: {{ addListener: () => {{}} }}
            }});
        }}

        // 5. 篡改toString方法，避免检测到自定义getter
        const originalToString = Function.prototype.toString;
        Function.prototype.toString = function() {{
            if (this.name === 'get webdriver') {{
                return 'function get webdriver() {{ [native code] }}';
            }}
            return originalToString.call(this);
        }};

        // 6. 模拟验证脚本的Cookie生成逻辑（完全匹配格式）
        const verifyToken = 'a5229e9f0bcc0296_' + Date.now();
        document.cookie = `list_js_verified=${{verifyToken}}; path=/; max-age=3600`;

        // 7. 禁用console调试，避免特征暴露
        console.debug = console.log = console.warn = () => {{}};
    """
    page.add_init_script(anti_detect_script)
    logging.info("深度反检测脚本注入完成（适配当前验证逻辑）")


def handle_verification_page(page, home_url):
    """处理页面验证逻辑（适配Cloudflare，新增首页重入兜底）"""
    max_verify_retry = 3
    verify_retry_count = 0
    verify_success = False

    while verify_retry_count < max_verify_retry and not verify_success:
        try:
            # 检测是否出现「请从首页重新进入」提示
            retry_hint = page.locator("h1:has-text('请从首页重新进入。')")
            if retry_hint.is_visible():
                logging.warning("检测到首页重入提示，重新从首页加载")
                # 强制清空Cookie+缓存
                page.context.clear_cookies()
                page.evaluate("window.localStorage.clear(); window.sessionStorage.clear()")
                # 重新访问首页（模拟人类手动输入网址）
                page.goto(home_url, wait_until="networkidle", timeout=10000)
                human_like_delay()
                # 重新生成验证Cookie
                generate_human_like_verify_cookie(page)
                human_like_delay()

            # 等待验证脚本执行
            page.wait_for_load_state("load", timeout=10000)
            # 模拟人类交互：点击页面空白处+等待
            page.mouse.click(random.randint(200, 500), random.randint(200, 500), delay=random.uniform(0.2, 0.5))
            human_like_delay()

            # 检测验证是否通过
            error_ele = page.locator("h1[style*='color:red'], h1:has-text('请从首页重新进入。')")
            if not error_ele.is_visible():
                # 验证通过：执行一次随机交互，模拟人类操作
                # random_human_interactions(page)
                verify_success = True
                logging.info("页面验证通过，无Cloudflare拦截")
            else:
                raise Exception("检测到拦截提示（含首页重入）")

        except PlaywrightTimeoutError:
            verify_retry_count += 1
            logging.warning(f"验证页面加载超时，重试{verify_retry_count}/{max_verify_retry}")
            page.reload(wait_until="load", timeout=10000)
        except Exception as e:
            verify_retry_count += 1
            logging.error(f"验证处理异常，重试{verify_retry_count}/{max_verify_retry}：{str(e)[:200]}")
            page.context.clear_cookies()
            time.sleep(random.uniform(3, 5))  # 延长重试间隔，匹配人类重试行为
            page.reload(wait_until="load", timeout=10000)

    if verify_success:
        return True
    else:
        logging.error(f"验证页面处理失败，已重试{max_verify_retry}次")
        return False


# -------------------------- 经纬度随机生成函数 --------------------------
def generate_province_random_geo(province_value):
    """按省份生成对应区域的随机经纬度"""
    # 各省份核心经纬度范围（示例：可补充更多省份）
    province_geo_range = {
        "hi": {"lat": (18.1, 20.1), "lng": (108.3, 111.1)},  # 海南
        "cq": {"lat": (29.3, 30.8), "lng": (106.3, 107.8)},  # 重庆
        "gd": {"lat": (22.0, 23.5), "lng": (113.0, 114.5)},  # 广东
        "bj": {"lat": (39.7, 40.2), "lng": (116.2, 116.7)},  # 北京
        "sh": {"lat": (31.1, 31.4), "lng": (121.3, 121.6)},  # 上海
        "sc": {"lat": (30.4, 30.8), "lng": (104.0, 104.4)},  # 四川
        # 可继续补充其他省份...
    }
    # 默认使用海南范围（兜底）
    geo_range = province_geo_range.get(province_value, province_geo_range["hi"])
    random_lat = round(random.uniform(*geo_range["lat"]), 4)
    random_lng = round(random.uniform(*geo_range["lng"]), 4)
    logging.info(f"生成{VALUE_TO_PROVINCE.get(province_value, '海南')}随机经纬度：{random_lat}, {random_lng}")
    return {"latitude": random_lat, "longitude": random_lng}


# -------------------------- storage_state 容错函数 --------------------------
def randomize_storage_state(storage_path):
    """随机化改造storage_state文件，避免固定指纹（增加JSON解析容错）"""
    if not os.path.exists(storage_path):
        logging.warning(f"storage_state文件不存在：{storage_path}")
        return
    try:
        # 读取文件并校验是否为空/非JSON
        with open(storage_path, "r", encoding="utf-8") as f:
            file_content = f.read().strip()
            if not file_content:  # 文件为空
                logging.warning("storage_state文件为空，删除并跳过随机化")
                os.remove(storage_path)
                return
            state = json.loads(file_content)  # 解析JSON
    except json.JSONDecodeError as e:
        logging.error(f"storage_state文件JSON格式错误：{e}，删除异常文件")
        os.remove(storage_path)
        return
    except Exception as e:
        logging.warning(f"读取storage_state失败：{str(e)[:100]}")
        return

    # 原有随机化逻辑（保留）
    try:
        # 1. 随机新增localStorage/sessionStorage非核心键值对
        for frame in state.get("origins", []):
            # 处理localStorage
            if "localStorage" in frame:
                frame["localStorage"].append({
                    "name": f"random_key_{generate_random_string(6)}",
                    "value": generate_random_string(12)
                })
            # 处理sessionStorage
            if "sessionStorage" in frame:
                frame["sessionStorage"].append({
                    "name": f"session_rand_{generate_random_string(6)}",
                    "value": generate_random_string(12)
                })

        # 2. 随机调整cookies过期时间（±300秒，不影响核心验证）
        for cookie in state.get("cookies", []):
            if "expires" in cookie and cookie["expires"] > 0:
                cookie["expires"] += random.randint(-300, 300)

        # 写回修改后的状态（确保JSON格式正确）
        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logging.info("storage_state文件随机化改造完成")
    except Exception as e:
        logging.warning(f"随机化storage_state失败：{str(e)[:100]}")


def check_storage_reuse_count(storage_path, max_reuse=3):
    """检查storage_state复用次数，达到阈值则删除（增加JSON解析容错）"""
    count_file = "storage_reuse_count.json"
    count_data = {"count": 0}  # 默认值

    # 读取计数文件（增加容错）
    try:
        if os.path.exists(count_file):
            with open(count_file, "r", encoding="utf-8") as f:
                file_content = f.read().strip()
                if file_content:  # 非空才解析
                    count_data = json.loads(file_content)
                else:  # 文件为空，重置计数
                    count_data = {"count": 0}
    except json.JSONDecodeError as e:
        logging.error(f"复用计数文件格式错误：{e}，重置计数")
        count_data = {"count": 0}
    except Exception as e:
        logging.warning(f"读取复用计数失败：{str(e)[:100]}")

    # 计算新计数
    current_count = count_data.get("count", 0) + 1

    # 达到阈值则删除状态文件并重置计数
    if current_count >= max_reuse:
        if os.path.exists(storage_path):
            os.remove(storage_path)
            logging.info(f"storage_state已复用{max_reuse}次，已删除")
        current_count = 0

    # 写回新计数（确保JSON格式正确）
    try:
        with open(count_file, "w", encoding="utf-8") as f:
            json.dump({"count": current_count}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"写入复用计数失败：{str(e)[:100]}")

    return current_count


# -------------------------- IP处理核心函数 --------------------------
def extract_multicast_ips_from_page(page):
    """从页面动态提取组播源IP信息"""
    multicast_ips = []
    try:
        # 等待表格加载（增加超时时间，支持重试）
        multicast_table = page.locator('section[aria-label="组播源列表"] table.iptv-table')
        multicast_table.wait_for(state="visible", timeout=30000)

        # 获取表格所有行
        ip_rows = multicast_table.locator("tbody tr").all()
        logging.info(f"发现组播源IP总数：{len(ip_rows)}")

        for row_idx, row in enumerate(ip_rows):
            try:
                # 提取IP地址
                ip_link = row.locator('td[data-label="IP:"] a.ip-link')
                ip_address = ip_link.inner_text().strip() if ip_link.is_visible() else None

                # 提取状态
                status_badge = row.locator('td[data-label="状态:"] span.status-badge')
                status = status_badge.inner_text().strip() if status_badge.is_visible() else None

                # 提取类型
                type_cell = row.locator('td[data-label="类型:"]')
                ip_type = type_cell.inner_text().strip() if type_cell.is_visible() else None

                if ip_address:
                    multicast_ips.append({
                        "ip_address": ip_address,
                        "status": status,
                        "type": ip_type,
                        "row_locator": row,
                        "link_locator": ip_link
                    })
            except Exception as e:
                logging.error(f"提取第{row_idx + 1}行IP信息失败：{str(e)[:100]}")
                continue
    except PlaywrightTimeoutError:
        logging.error("组播源表格加载超时")
    except Exception as e:
        logging.error(f"提取组播IP失败：{str(e)[:100]}")
    return multicast_ips


def filter_and_sort_multicast_ips(ip_list):
    """筛选并排序组播IP"""
    # 过滤失效IP
    filtered_ips = [ip for ip in ip_list if ip.get('status') != "暂时失效"]
    logging.info(f"筛选后有效组播IP数量：{len(filtered_ips)}（过滤掉{len(ip_list) - len(filtered_ips)}个暂时失效IP）")

    if not filtered_ips:
        logging.warning("无有效组播IP（所有IP均为暂时失效）")
        return []

    # 按地区优先级排序
    def get_area_priority(ip_type):
        if not ip_type:
            return len(AREA_PRIORITY)
        for idx, area in enumerate(AREA_PRIORITY):
            if area in ip_type:
                return idx
        return len(AREA_PRIORITY)

    sorted_ips = sorted(filtered_ips, key=lambda x: get_area_priority(x.get('type')))

    # 日志输出排序结果
    logging.info("组播IP排序结果（按海口→澄迈→吉阳→儋州→临高→陵水）：")
    for i, ip in enumerate(sorted_ips[:5]):
        log_msg = f"   [{i + 1}] {ip['ip_address']} | 状态：{ip['status']} | 类型：{ip['type']}"
        logging.info(log_msg)

    return sorted_ips


def extract_ip_port_from_detail_page(page):
    """从IP详情页提取IP+端口信息"""
    human_like_delay()
    try:
        page.wait_for_load_state("networkidle", timeout=20000)

        # 方式1：精准匹配IP端口标签
        ip_port_label = page.locator('span.ip-detail-label:text("IP端口:")')
        if ip_port_label.is_visible():
            ip_port_value = ip_port_label.locator("..").locator("span.ip-detail-value")
            ip_port_text = ip_port_value.inner_text().strip()
            if ip_port_text and ":" in ip_port_text:
                logging.info(f"详情页提取到IP+端口：{ip_port_text}")
                return ip_port_text

        # 方式2：兜底匹配所有value
        all_values = page.locator('span.ip-detail-value').all_inner_texts()
        for value in all_values:
            if ":" in value and "." in value:
                logging.info(f"兜底提取到IP+端口：{value.strip()}")
                return value.strip()

        # 方式3：正则提取
        page_text = page.inner_text("body")
        ip_port_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}:\d+\b', page_text)
        if ip_port_match:
            ip_port_text = ip_port_match.group()
            logging.info(f"正则提取到IP+端口：{ip_port_text}")
            return ip_port_text

        logging.warning("详情页未找到IP+端口信息")
    except Exception as e:
        logging.error(f"提取IP端口失败：{str(e)[:150]}")
    return None


def get_province_multicast_ip_ports(province_input):
    """获取指定省份的组播源IP及端口信息"""
    # 1. 校验省份参数
    try:
        province_value, province_name = validate_province(province_input)
    except ValueError as e:
        logging.error(f"参数校验失败：{e}")
        return None

    storage_path = "iptv_storage_state.json"
    final_ip_details = []
    start_time = time.time()

    with sync_playwright() as p:
        # 随机选择基础配置
        random_ua = random.choice(USER_AGENT_POOL)
        random_width, random_height = random.choice(WINDOW_SIZE_POOL)
        random_color_scheme = random.choice(["light", "dark"])
        random_device_scale = random.choice([1.0, 1.25, 1.5])

        # 启动浏览器（增强反检测参数）
        chrome_args = ANTI_DETECTION_CONFIG["chrome_args"].copy()
        chrome_args.append(f"--window-size={random_width},{random_height}")

        # 新增Cloudflare反检测参数
        chrome_args.extend([
            "--disable-features=UserAgentClientHint",  # 禁用UA客户端提示（Cloudflare重点检测）
            "--enable-features=NetworkService,NetworkServiceInProcess",
            "--force-color-profile=srgb",  # 统一颜色配置，避免指纹差异
            "--lang=zh-CN,zh",  # 强制语言，匹配国内访问特征
            "--disable-background-timer-throttling",  # 禁用后台定时器节流
            "--disable-renderer-throttling",  # 禁用渲染节流
            "--no-zygote",  # 禁用zygote进程，减少特征
        ])

        browser = p.chromium.launch(
            headless=False,  # 生产环境先保持False，排查通过后再改为True
            args=chrome_args,
            ignore_default_args=ANTI_DETECTION_CONFIG["ignore_default_args"],
            slow_mo=random.uniform(100, 200),  # 放慢操作速度（从50-150提升到100-200）
            channel="chrome"  # 指定原生Chrome通道，避免Chromium默认特征
        )

        # 检查并处理storage_state复用次数
        check_storage_reuse_count(storage_path, max_reuse=3)  # 最多复用3次

        # 随机化改造storage_state（若存在且有效）
        if os.path.exists(storage_path):
            # 预校验文件是否有效
            try:
                with open(storage_path, "r", encoding="utf-8") as f:
                    if not f.read().strip():
                        os.remove(storage_path)  # 空文件直接删除
                    else:
                        randomize_storage_state(storage_path)
            except:
                if os.path.exists(storage_path):
                    os.remove(storage_path)

        # 校验storage_state有效性
        storage_state = None
        if os.path.exists(storage_path):
            try:
                with open(storage_path, "r", encoding="utf-8") as f:
                    json.loads(f.read())  # 预解析验证
                    storage_state = storage_path
            except:
                os.remove(storage_path)
                storage_state = None

        # 创建上下文（增强指纹伪装+经纬度随机化）
        context = browser.new_context(
            user_agent=random_ua,
            viewport={"width": random_width, "height": random_height},
            locale=random.choice(["zh-CN", "zh-Hans-CN", "zh"]),
            timezone_id="Asia/Shanghai",
            color_scheme=random_color_scheme,
            device_scale_factor=random_device_scale,
            storage_state=storage_state,  # 仅传入有效文件路径
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
                f"X-Random-{generate_random_string()}": generate_random_string(16),
                "Referer": random.choice(["", "https://iptv.cqshushu.com"])
            },
            geolocation=generate_province_random_geo(province_value),  # 按省份生成随机经纬度
            permissions=["geolocation"]
        )

        # 拦截无用请求
        def handle_route(route, request):
            blocked_types = ["image", "video", "audio", "font", "stylesheet", "ping"]
            blocked_domains = ["ad.", "analytics.", "track.", "cdn.ads.", "google-analytics.com", "gtag.js"]
            if request.resource_type in blocked_types or any(d in request.url for d in blocked_domains):
                route.abort()
            else:
                headers = request.headers.copy()
                headers["Referer"] = random.choice(["", "https://iptv.cqshushu.com"])
                route.continue_(headers=headers)

        context.route("**/*", handle_route)
        page = context.new_page()

        # 注入深度反检测脚本
        inject_anti_detection_scripts(page)

        try:
            logging.info(f"开始抓取 {province_name} 的组播源IP信息，User-Agent: {random_ua[:50]}...")

            # 访问首页并处理验证
            home_url = "https://iptv.cqshushu.com"
            max_retry_goto = 2
            retry_goto_count = 0
            page_loaded = False

            while retry_goto_count < max_retry_goto and not page_loaded:
                try:
                    human_like_delay()
                    # 模拟人类手动输入网址（先访问about:blank，再输入首页地址）
                    page.goto("about:blank", wait_until="load", timeout=5000)
                    human_like_delay()
                    page.evaluate(f'window.location.href = "{home_url}"')  # 用JS模拟手动输入
                    page.wait_for_load_state("networkidle", timeout=60000)

                    # 处理页面验证
                    if not handle_verification_page(page, home_url):
                        raise Exception("页面验证失败")

                    # 新增：首页加载后模拟人类浏览
                    page.mouse.wheel(0, random.randint(300, 500))  # 向下滚动
                    human_like_delay()
                    page.mouse.move(random.randint(100, 800), random.randint(100, 600))  # 随机移动鼠标
                    human_like_delay()
                    page.mouse.wheel(0, random.randint(-200, 100))  # 向上滚动
                    human_like_delay()

                    if page.content().strip() != "<html><head></head><body></body></html>":
                        page_loaded = True
                    else:
                        raise Exception("页面加载后内容为空")
                except Exception as e:
                    retry_goto_count += 1
                    logging.warning(f"首页访问重试{retry_goto_count}/{max_retry_goto}：{str(e)[:100]}")
                    human_like_delay()
                    if retry_goto_count == max_retry_goto:
                        raise Exception("首页多次加载失败，终止操作")

            # 随机人类交互
            # random_human_interactions(page)

            # 定位并选择省份（增加重试和等待）
            max_retry_select = 2
            retry_select_count = 0
            province_selected = False

            while retry_select_count < max_retry_select and not province_selected:
                try:
                    province_select = page.locator("#provinceSelect")
                    province_select.wait_for(state="visible", timeout=20000)

                    # 模拟人类鼠标移动
                    box = province_select.bounding_box()
                    if box:
                        viewport = page.viewport_size
                        target_x = box["x"] + box["width"] / 2 + random.randint(-3, 3)
                        target_y = box["y"] + box["height"] / 2 + random.randint(-3, 3)
                        start_x = random.randint(10, viewport["width"] // 2)
                        start_y = random.randint(10, viewport["height"] // 2)
                        human_mouse_move(page, start_x, start_y, target_x, target_y)

                    # 选择省份
                    human_like_delay()
                    hover_delay = random.uniform(0.1, 0.3)
                    time.sleep(hover_delay)
                    province_select.hover()
                    human_like_delay()
                    select_delay = random.uniform(0.1, 0.3)
                    time.sleep(select_delay)
                    province_select.select_option(value=province_value)
                    logging.info(f"已选择省份：{province_name}")
                    province_selected = True
                except PlaywrightTimeoutError:
                    retry_select_count += 1
                    logging.warning(f"省份选择重试{retry_select_count}/{max_retry_select}：定位超时")
                    human_like_delay()
                    page.reload(wait_until="networkidle")
                except Exception as e:
                    retry_select_count += 1
                    logging.warning(f"省份选择重试{retry_select_count}/{max_retry_select}：{str(e)[:100]}")
                    human_like_delay()

            if not province_selected:
                raise Exception("省份选择多次失败")

            # 等待页面跳转
            max_retry_jump = 2
            retry_jump_count = 0
            while retry_jump_count < max_retry_jump:
                try:
                    page.wait_for_url(f"**{province_value}**", wait_until="domcontentloaded", timeout=20000)
                    break
                except Exception as e:
                    retry_jump_count += 1
                    logging.warning(f"页面跳转重试{retry_jump_count}/{max_retry_jump}：{str(e)[:100]}")
                    human_like_delay()
                    if retry_jump_count == max_retry_jump:
                        raise Exception("页面跳转多次超时")

            # 提取组播IP列表
            multicast_ips = extract_multicast_ips_from_page(page)
            if not multicast_ips:
                logging.error("未提取到任何组播源IP")
                return None

            # 筛选并排序IP
            sorted_ips = filter_and_sort_multicast_ips(multicast_ips)
            if not sorted_ips:
                return None

            # 处理前两条IP
            target_ips = sorted_ips[:2]
            logging.info(f"选择前{len(target_ips)}条有效组播IP进入详情页")
            for i, ip in enumerate(target_ips):
                log_msg = f"   [{i + 1}] {ip['ip_address']} | 类型：{ip['type']} | 状态：{ip['status']}"
                logging.info(log_msg)

            for idx, target_ip in enumerate(target_ips):
                try:
                    logging.info(f"正在访问第{idx + 1}条IP详情页：{target_ip['ip_address']}")

                    # 模拟人类点击IP链接
                    ip_link = target_ip["link_locator"]
                    link_box = ip_link.bounding_box()
                    if link_box:
                        human_mouse_move(page,
                                         random.randint(50, 100), random.randint(50, 100),
                                         link_box["x"] + link_box["width"] / 2,
                                         link_box["y"] + link_box["height"] / 2)
                        human_like_delay()

                    # 点击链接
                    ip_link.click(delay=random.uniform(0.1, 0.3))
                    human_like_delay()

                    # 提取IP+端口
                    ip_port = extract_ip_port_from_detail_page(page)

                    # 保存结果
                    final_ip_details.append({
                        "rank": idx + 1,
                        "ip_address": target_ip["ip_address"],
                        "status": target_ip["status"],
                        "type": target_ip["type"],
                        "ip_port": ip_port,
                        "detail_url": page.url
                    })

                    # 返回列表页（最后一条无需返回）
                    if idx < len(target_ips) - 1:
                        page.go_back()
                        human_like_delay()
                        page.wait_for_load_state("domcontentloaded")
                        page.locator('section[aria-label="组播源列表"] table.iptv-table').wait_for(state="visible")

                except Exception as e:
                    logging.error(f"第{idx + 1}条IP详情页抓取失败：{str(e)[:150]}")
                    continue

        except json.JSONDecodeError as e:
            logging.error(f"JSON解析失败：{e}，重置storage_state后重试")
            # 重置相关文件后重试（可选）
            if os.path.exists("iptv_storage_state.json"):
                os.remove("iptv_storage_state.json")
            if os.path.exists("storage_reuse_count.json"):
                os.remove("storage_reuse_count.json")
            return get_province_multicast_ip_ports(province_input)  # 重试一次
        except Exception as e:
            logging.error(f"核心逻辑出错：{str(e)[:200]}")
            try:
                logging.info(f"当前页面URL：{page.url}")
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

        logging.info(f"抓取完成，总耗时：{time.time() - start_time:.2f}秒")
        return final_ip_details


# -------------------------- 保留功能函数 --------------------------
def display_basic_info(ip_details):
    """展示提取的IP基础信息"""
    if not ip_details:
        logging.warning("未获取到任何IP信息")
        return

    logging.info("\n===== IP基础信息 =====")
    for idx, item in enumerate(ip_details, 1):
        log_msg = (
            f"{idx}. IP地址: {item['ip_address']}\n"
            f"   状态: {item['status'] or '未知'}\n"
            f"   类型: {item['type'] or '未知'}\n"
            f"   IP+端口: {item['ip_port'] or '未获取到'}"
        )
        logging.info(log_msg)
        logging.info("-" * 50)


def get_all_source_urls(province_input="海南"):
    """获取所有待爬取的链接"""
    # 获取IP+端口信息
    ip_details = get_province_multicast_ip_ports(province_input)

    # 展示原始IP信息
    display_basic_info(ip_details)

    # 生成动态链接
    dynamic_links = []
    base_url = "http://iptv.cqshushu.com/?s={ip_port}&t=multicast&channels=1&format=txt"

    if ip_details:
        for ip_item in ip_details:
            ip_port = ip_item.get('ip_port')
            if ip_port:
                encoded_ip_port = ip_port.replace(":", "%3A")
                link = base_url.format(ip_port=encoded_ip_port)
                dynamic_links.append(link)
                logging.info(f"生成链接 (IP: {ip_item['ip_address']}, 端口: {ip_port.split(':')[1]}): {link}")

    # 合并链接并去重
    all_source_urls = list(config.source_urls)
    for link in dynamic_links:
        if link not in all_source_urls:
            all_source_urls.append(link)

    logging.info(f"\n===== 合并后的爬取链接总数 =====")
    logging.info(f"Config中的链接数: {len(config.source_urls)}")
    logging.info(f"动态生成的链接数: {len(dynamic_links)}")
    logging.info(f"合并后总链接数: {len(all_source_urls)}")

    return all_source_urls


def parse_template(template_file):
    """解析模板文件"""
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
    """爬取频道信息"""
    channels = OrderedDict()

    try:
        headers = {
            'User-Agent': random.choice(USER_AGENT_POOL),
            'Accept': 'text/plain,text/html,*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }

        response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
        response.raise_for_status()
        response.encoding = 'utf-8'
        text = response.text.strip()

        logging.info(f"url: {url} 响应状态: {response.status_code}")
        logging.info(f"响应内容长度: {len(text)} 字符")
        logging.info(f"响应前200字符: {text[:200] if text else '空响应'}")

        lines = text.splitlines() if text else []
        is_m3u = any("#EXTINF" in line for line in lines[:10]) if lines else False
        source_type = "m3u" if is_m3u else "txt"
        logging.info(f"url: {url} 获取成功，判断为{source_type}格式，共 {len(lines)} 行")

        if is_m3u:
            # M3U格式解析
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
                        match = re.search(r'tvg-name="(.*?)"', line)
                        if match:
                            channel_name = match.group(1).strip()
                elif line and not line.startswith("#"):
                    channel_url = line.strip()
                    if current_category and channel_name:
                        channels[current_category].append((channel_name, channel_url))
                        channel_name = None
        else:
            # TXT格式解析
            current_category = None
            line_num = 0

            # 关键词到分类的映射
            keyword_categories = [
                ('4K', '4K频道'),
                ('CCTV', '央视频道'),
                ('卫视', '卫视频道'),
                ('SD', 'SD频道'),
                ('海南', '海南地方'),
            ]

            # 提取默认分类
            default_category = "默认分类"
            url_match = re.search(r'/([^/]+?)\.(txt|m3u|m3u8)$', url)
            if url_match:
                default_category = url_match.group(1)
            else:
                param_match = re.search(r'[?&]name=([^&]+)', url)
                if param_match:
                    default_category = param_match.group(1)

            for line in lines:
                line_num += 1
                line = line.strip()

                if not line:
                    continue

                if line.startswith("#") and len(line) < 50 and "," not in line:
                    continue

                # 分类行处理
                if "#genre#" in line.lower():
                    parts = line.split(",", 1)
                    if len(parts) >= 2:
                        current_category = parts[0].strip()
                        channels[current_category] = []
                        logging.debug(f"发现分类: {current_category}")
                    else:
                        current_category = None
                    continue

                # 频道行处理
                if "," in line:
                    if line.lower().endswith("#genre#"):
                        current_category = line.split(",")[0].strip()
                        channels[current_category] = []
                        logging.debug(f"发现无标记分类: {current_category}")
                        continue

                    parts = line.split(",", 1)
                    if len(parts) == 2:
                        channel_name = parts[0].strip()
                        channel_url = parts[1].strip()

                        # 验证URL格式
                        url_pattern = re.compile(
                            r'^(https?|rtp|rtsp|udp)://|'
                            r'^\d{1,3}(\.\d{1,3}){3}:\d+|'
                            r'^[a-zA-Z0-9]+://'
                        )

                        if url_pattern.search(channel_url):
                            # 清理频道名称
                            channel_name = re.sub(r'[#].*$', '', channel_name).strip()

                            # 关键词匹配分类
                            if current_category is None:
                                matched_category = None
                                for keyword, cat in keyword_categories:
                                    if keyword in channel_name:
                                        matched_category = cat
                                        break
                                current_category = matched_category if matched_category else default_category
                                if current_category not in channels:
                                    channels[current_category] = []
                                logging.debug(f"根据频道名称匹配分类: {channel_name} → {current_category}")

                            # 补全默认频道名称
                            if not channel_name:
                                url_name_match = re.search(r'/([^/]+?)(?:\.m3u8|\.ts|\.mp4)?$', channel_url)
                                if url_name_match:
                                    channel_name = url_name_match.group(1)
                                else:
                                    host_match = re.search(r'://([^/]+)', channel_url)
                                    if host_match:
                                        channel_name = host_match.group(1)
                                    else:
                                        channel_name = f"频道_{line_num}"

                            # 添加频道
                            channels[current_category].append((channel_name, channel_url))
                            logging.debug(f"添加频道: {channel_name} -> {channel_url[:50]}...")
                        else:
                            potential_category = line.split(",")[0].strip()
                            if potential_category and len(potential_category) < 50:
                                current_category = potential_category
                                channels[current_category] = []
                                logging.debug(f"发现无标记分类: {current_category}")
                elif line and re.search(r'^(https?|rtp|rtsp|udp)://|^\d{1,3}(\.\d{1,3}){3}:\d+', line):
                    # 纯URL行处理
                    channel_url = line.strip()
                    url_name_match = re.search(r'/([^/]+?)(?:\.m3u8|\.ts|\.mp4)?$', channel_url)
                    if url_name_match:
                        channel_name = url_name_match.group(1)
                    else:
                        host_match = re.search(r'://([^/]+)', channel_url)
                        if host_match:
                            channel_name = host_match.group(1)
                        else:
                            channel_name = f"频道_{line_num}"

                    if current_category is None:
                        current_category = default_category
                        if current_category not in channels:
                            channels[current_category] = []
                    channels[current_category].append((channel_name, channel_url))
                    logging.debug(f"添加纯URL频道: {channel_name} -> {channel_url[:50]}...")
    except Exception as e:
        logging.error(f"爬取频道失败: {str(e)[:200]}")

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

    current_date = datetime.now().strftime("%Y-%m-%d")
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
