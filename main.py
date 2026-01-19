import re
import requests
import logging
from collections import OrderedDict
from datetime import datetime
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler("function.log", "w", encoding="utf-8"), logging.StreamHandler()])

def parse_template(template_file):
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
            
            # 尝试从URL中提取可能的默认分类名
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
                        # 处理只有 #genre# 的情况
                        current_category = default_category
                        channels[current_category] = []
                    continue
                
                # 处理频道行 - 检测是否有逗号分隔
                if "," in line:
                    # 先检查是否是分类行（如：央视频道,#genre# 但被上面的条件漏掉了）
                    if line.lower().endswith("#genre#"):
                        current_category = line.split(",")[0].strip()
                        channels[current_category] = []
                        logging.debug(f"发现分类行: {current_category}")
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
                            
                            # 如果当前没有分类，创建默认分类
                            if current_category is None:
                                current_category = default_category
                                channels[current_category] = []
                                logging.debug(f"创建默认分类: {current_category}")
                            
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
                    
                    # 如果当前没有分类，创建默认分类
                    if current_category is None:
                        current_category = default_category
                        channels[current_category] = []
                        logging.debug(f"创建默认分类: {current_category}")
                    
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
    matched_channels = OrderedDict()

    for category, channel_list in template_channels.items():
        matched_channels[category] = OrderedDict()
        for channel_name in channel_list:
            for online_category, online_channel_list in all_channels.items():
                for online_channel_name, online_channel_url in online_channel_list:
                    if channel_name == online_channel_name:
                        matched_channels[category].setdefault(channel_name, []).append(online_channel_url)

    return matched_channels

def filter_source_urls(template_file):
    template_channels = parse_template(template_file)
    source_urls = config.source_urls

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
    return re.match(r'^http:\/\/\[[0-9a-fA-F:]+\]', url) is not None

def updateChannelUrlsM3U(channels, template_channels):
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
                    f_m3u.write(f"""#EXTINF:-1 tvg-id="1" tvg-name="{announcement['name']}" tvg-logo="{announcement['logo']}" group-title="{group['channel']}",{announcement['name']}\n""")
                    f_m3u.write(f"{announcement['url']}\n")
                    f_txt.write(f"{announcement['name']},{announcement['url']}\n")

            for category, channel_list in template_channels.items():
                f_txt.write(f"{category},#genre#\n")
                if category in channels:
                    for channel_name in channel_list:
                        if channel_name in channels[category]:
                            sorted_urls = sorted(channels[category][channel_name], key=lambda url: not is_ipv6(url) if config.ip_version_priority == "ipv6" else is_ipv6(url))
                            filtered_urls = []
                            for url in sorted_urls:
                                if url and url not in written_urls and not any(blacklist in url for blacklist in config.url_blacklist):
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

                                f_m3u.write(f"#EXTINF:-1 tvg-id=\"{index}\" tvg-name=\"{channel_name}\" tvg-logo=\"https://gcore.jsdelivr.net/gh/yuanzl77/TVlogo@master/png/{channel_name}.png\" group-title=\"{category}\",{channel_name}\n")
                                f_m3u.write(new_url + "\n")
                                f_txt.write(f"{channel_name},{new_url}\n")

            f_txt.write("\n")

if __name__ == "__main__":
    template_file = "demo.txt"
    channels, template_channels = filter_source_urls(template_file)
    updateChannelUrlsM3U(channels, template_channels)
