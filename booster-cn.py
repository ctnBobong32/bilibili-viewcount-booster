import sys
import threading
import random
from time import sleep
from typing import Optional
from datetime import date, datetime, timedelta

import requests
from fake_useragent import UserAgent

# 参数配置
timeout = 3         # 代理连接超时时间（秒）
thread_num = 75     # 过滤有效代理的线程数
round_time = 305    # 每轮刷播放量的间隔时间（秒）
update_pbar_count = 10  # 每通过xx个代理更新进度条
bv = sys.argv[1]    # 视频BV号
target = int(sys.argv[2])  # 目标播放量

# 统计参数
successful_hits = 0     # 成功请求计数
initial_view_count = 0  # 初始播放量

def time(seconds: int) -> str:
    if seconds < 60:
        return f'{seconds}秒'
    else:
        return f'{int(seconds / 60)}分钟{seconds % 60}秒'

def pbar(n: int, total: int, hits: Optional[int], view_increase: Optional[int]) -> str:
    progress = '━' * int(n / total * 50)
    blank = ' ' * (50 - len(progress))
    if hits is None or view_increase is None:
        return f'\r{n}/{total} {progress}{blank}'
    else:
        return f'\r{n}/{total} {progress}{blank} [成功数: {hits}, 播放增长: {view_increase}]'

# 1. 获取代理
print()
day = date.today()
while True:  # 查找最近有代理的日期
    day = day - timedelta(days=1)
    proxy_url = f'https://api.checkerproxy.net/v1/landing/archive/{day.strftime("%Y-%m-%d")}'
    print(f'正在从 {proxy_url} 获取代理...')
    response = requests.get(proxy_url)
    if response.status_code == requests.codes.ok:
        data = response.json()
        total_proxies = data['data']['proxyList']
        print(f'成功获取 {len(total_proxies)} 个代理')
        break
    else:
        print('未找到可用代理')

# 2. 多线程过滤有效代理
if len(total_proxies) > 10000:
    print('代理数量超过10000，随机选取10000个代理')
    random.shuffle(total_proxies)
    total_proxies = total_proxies[:10000]

active_proxies = []
count = 0
def filter_proxys(proxies: 'list[str]') -> None:
    global count
    for proxy in proxies:
        count = count + 1
        try:
            requests.post('http://httpbin.org/post',
                          proxies={'http': 'http://'+proxy},
                          timeout=timeout)
            active_proxies.append(proxy)
        except:  # 代理连接超时
            pass
        print(f'{pbar(count, len(total_proxies), hits=None, view_increase=None)} {100*count/len(total_proxies):.1f}%   ', end='')


start_filter_time = datetime.now()
print('\n正在使用 http://httpbin.org/post 筛选有效代理...')
thread_proxy_num = len(total_proxies) // thread_num
threads = []
for i in range(thread_num):
    start = i * thread_proxy_num
    end = start + thread_proxy_num if i < (thread_num - 1) else None
    thread = threading.Thread(target=filter_proxys, args=(total_proxies[start:end],))
    thread.start()
    threads.append(thread)
for thread in threads:
    thread.join()
filter_cost_seconds = int((datetime.now()-start_filter_time).total_seconds())
print(f'\n成功筛选出 {len(active_proxies)} 个有效代理，耗时 {time(filter_cost_seconds)}')

# 3. 刷播放量
print(f'\n开始于 {datetime.now().strftime("%H:%M:%S")} 为视频 {bv} 刷播放量')
current = 0
info = {}  # 初始化视频信息

# 获取初始播放量
try:
    info = requests.get(f'https://api.bilibili.com/x/web-interface/view?bvid={bv}',
                       headers={'User-Agent': UserAgent().random}).json()['data']
    initial_view_count = info['stat']['view']
    current = initial_view_count
    print(f'初始播放量: {initial_view_count}')
except Exception as e:
    print(f'获取初始播放量失败: {e}')

while True:
    reach_target = False
    start_time = datetime.now()
    
    # 使用每个代理发送播放请求
    for i, proxy in enumerate(active_proxies):
        try:
            if i % update_pbar_count == 0:  # 更新进度条
                print(f'{pbar(current, target, successful_hits, current - initial_view_count)} 正在更新播放量...', end='')
                info = (requests.get(f'https://api.bilibili.com/x/web-interface/view?bvid={bv}',
                                     headers={'User-Agent': UserAgent().random})
                        .json()['data'])
                current = info['stat']['view']
                if current >= target:
                    reach_target = True
                    print(f'{pbar(current, target, successful_hits, current - initial_view_count)} 已完成                 ', end='')
                    break

            requests.post('http://api.bilibili.com/x/click-interface/click/web/h5',
                          proxies={'http': 'http://'+proxy},
                          headers={'User-Agent': UserAgent().random},
                          timeout=timeout,
                          data={
                              'aid': info['aid'],
                              'cid': info['cid'],
                              'bvid': bv,
                              'part': '1',
                              'mid': info['owner']['mid'],
                              'jsonp': 'jsonp',
                              'type': info['desc_v2'][0]['type'] if info['desc_v2'] else '1',
                              'sub_type': '0'
                          })
            successful_hits += 1
            print(f'{pbar(current, target, successful_hits, current - initial_view_count)} 代理({i+1}/{len(active_proxies)}) 成功   ', end='')
        except:  # 代理连接超时
            print(f'{pbar(current, target, successful_hits, current - initial_view_count)} 代理({i+1}/{len(active_proxies)}) 失败      ', end='')

    if reach_target:  # 达到目标播放量
        break
    remain_seconds = int(round_time-(datetime.now()-start_time).total_seconds())
    if remain_seconds > 0:
        for second in reversed(range(remain_seconds)):
            print(f'{pbar(current, target, successful_hits, current - initial_view_count)} 下一轮: {time(second)}          ', end='')
            sleep(1)

success_rate = (successful_hits / len(active_proxies)) * 100 if active_proxies else 0
print(f'\n完成时间 {datetime.now().strftime("%H:%M:%S")}')
print(f'统计信息:')
print(f'- 初始播放量: {initial_view_count}')
print(f'- 最终播放量: {current}')
print(f'- 总增长量: {current - initial_view_count}')
print(f'- 成功请求数: {successful_hits}')
print(f'- 成功率: {success_rate:.2f}%\n')