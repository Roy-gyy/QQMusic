from typing import Any, List, Dict, Optional
import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright, TimeoutError
from fastmcp import FastMCP
import re

# 全局配置
MAX_RETRIES = 3           # 最大重试次数
ELEMENT_TIMEOUT = 30000   # 元素等待超时时间（毫秒）
PAGE_LOAD_TIMEOUT = 60000 # 页面加载超时时间（毫秒）

# 增加持久化用户数据目录
BROWSER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_data")
os.makedirs(BROWSER_DATA_DIR, exist_ok=True)

# 初始化 FastMCP 服务器
mcp = FastMCP("qqmusic")

# 全局变量
playwright: Optional[Playwright] = None
browser: Optional[Browser] = None
page: Optional[Page] = None

async def init_browser():
    """初始化浏览器，持久化用户数据目录，保证登录态"""
    global playwright, browser, page
    try:
        # 如果已经有实例在运行，先关闭它们
        if page:
            await page.close()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        # 重新初始化所有组件，使用持久化上下文
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA_DIR,
            headless=False,
            viewport={'width': 1280, 'height': 800},
            args=['--no-sandbox', '--disable-setuid-sandbox'],
            slow_mo=50
        )
        # 取第一个页面或新建
        if browser.pages:
            page = browser.pages[0]
        else:
            page = await browser.new_page()
        page.set_default_timeout(ELEMENT_TIMEOUT)
        return True
    except Exception as e:
        print(f"初始化浏览器失败: {str(e)}")
        await cleanup()
        return False

async def cleanup():
    """清理资源"""
    global playwright, browser, page
    try:
        if page:
            await page.close()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
    except Exception as e:
        print(f"清理资源时出错: {str(e)}")
    finally:
        playwright = None
        browser = None
        page = None

async def retry_action(action, max_retries=MAX_RETRIES, **kwargs):
    """通用重试机制"""
    retries = 0
    while retries < max_retries:
        try:
            return await action(**kwargs)
        except TimeoutError as e:
            retries += 1
            print(f"操作超时，尝试重试 ({retries}/{max_retries}): {str(e)}")
            if page:
                try:
                    await page.reload(timeout=PAGE_LOAD_TIMEOUT)
                    await asyncio.sleep(2)
                except Exception:
                    pass
        except Exception as e:
            print(f"执行操作时出错: {str(e)}")
            raise e
    
    return f"操作超时，已尝试 {max_retries} 次"

@mcp.tool()
async def login() -> str:
    """登录QQ音乐账号"""
    try:
        if not await init_browser():
            return "浏览器初始化失败"
        
        await page.goto("https://y.qq.com", timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)
        
        # 检查是否已经登录
        try:
            profile_element = await page.query_selector('.top_login__link_avatar')
            if profile_element:
                return "已登录QQ音乐账号"
        except Exception:
            pass
        
        # 点击登录按钮
        login_selectors = [
            'text="登录"',
            '.top_login__link_text',
            '.top_login__btn',
            'a:has-text("登录")',
            'button:has-text("登录")'
        ]
        
        login_clicked = False
        for selector in login_selectors:
            try:
                element = await page.wait_for_selector(selector, state='visible')
                if element:
                    await element.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    await element.click()
                    login_clicked = True
                    break
            except Exception:
                continue
        
        if not login_clicked:
            return "未能找到登录按钮，请刷新页面重试"
        
        await asyncio.sleep(2)
        
        # 等待用户登录成功
        max_wait_time = 180
        wait_interval = 5
        waited_time = 0
        
        while waited_time < max_wait_time:
            try:
                logged_in = False
                
                # 检查登录状态
                login_elements = await page.query_selector_all('text="登录"')
                if not login_elements:
                    logged_in = True
                
                if not logged_in:
                    avatar = await page.query_selector('.top_login__link_avatar')
                    if avatar:
                        logged_in = True
                
                if not logged_in:
                    username = await page.query_selector('.top_login__link_name')
                    if username:
                        logged_in = True
                
                if logged_in:
                    await asyncio.sleep(2)
                    return "登录成功！"
                
            except Exception:
                pass
            
            await asyncio.sleep(wait_interval)
            waited_time += wait_interval
            
            if waited_time % 20 == 0:
                try:
                    await page.reload(timeout=PAGE_LOAD_TIMEOUT)
                    await asyncio.sleep(3)
                except Exception:
                    pass
        
        return "登录等待超时。请重试或手动登录后再使用其他功能。"
        
    except Exception as e:
        return f"登录过程中出错: {str(e)}"

@mcp.tool()
async def search_songs(keywords: str, limit: int = 5) -> str:
    """
    根据关键词搜索歌曲
    Args:
        keywords: 搜索关键词
        limit: 返回结果数量限制
    """
    async def _search():
        # 构建搜索URL
        search_url = f"https://y.qq.com/n/ryqq/search?w={keywords}&t=song"
        await page.goto(search_url, timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)
        # 等待搜索结果加载
        await page.wait_for_selector('.songlist__list', timeout=10000)
        # 获取搜索结果
        songs = []
        song_elements = await page.query_selector_all('.songlist__item')
        for i, element in enumerate(song_elements):
            if i >= limit:
                break
            try:
                # 获取歌曲信息
                title_element = await element.query_selector('.songlist__songname_txt')
                artist_element = await element.query_selector('.songlist__artist')
                album_element = await element.query_selector('.songlist__album')
                duration_element = await element.query_selector('.songlist__time')
                # 提取文本
                title = await title_element.text_content() if title_element else "未知歌曲"
                artist = await artist_element.text_content() if artist_element else "未知歌手"
                album = await album_element.text_content() if album_element else "未知专辑"
                duration = await duration_element.text_content() if duration_element else ""
                # 修正 song_id 提取逻辑
                song_id = ""
                if title_element:
                    a_tag = await title_element.query_selector('a')
                    if a_tag:
                        song_link = await a_tag.get_attribute('href')
                        if song_link and '/songDetail/' in song_link:
                            song_id = song_link.split('/songDetail/')[-1].split('?')[0]
                # 调试：若song_id依然为空，打印HTML结构
                if not song_id and title_element:
                    html = await title_element.evaluate('(el) => el.outerHTML')
                    print(f"[调试] 未获取到song_id，title_element.outerHTML: {html}")
                songs.append({
                    'title': title.strip(),
                    'artist': artist.strip(),
                    'album': album.strip(),
                    'duration': duration.strip(),
                    'song_id': song_id
                })
            except Exception as e:
                print(f"提取歌曲信息时出错: {str(e)}")
                continue
        # 格式化输出
        result = "搜索结果：\n\n"
        for i, song in enumerate(songs, 1):
            result += f"{i}. {song['title']} - {song['artist']}\n"
            result += f"   专辑: {song['album']}\n"
            result += f"   时长: {song['duration']}\n"
            result += f"   歌曲ID: {song['song_id']}\n"
            if i < len(songs):
                result += "\n"
        return result
    return await retry_action(_search)

@mcp.tool()
async def get_song_details(song_id: str) -> str:
    """
    获取歌曲详细信息
    Args:
        song_id: 歌曲ID
    """
    async def _get_song_details():
        song_url = f"https://y.qq.com/n/ryqq/songDetail/{song_id}"
        await page.goto(song_url, timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)
        log_path = r"D:/Redbook-Search-Comment-MCP2.0-main/qqmusic_debug.log"
        try:
            # 先等待主内容区域出现
            main_selectors = ['.song_detail__info', '.data__name', '.songinfo__name', '#app']
            found_main = False
            for sel in main_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=10000)
                    found_main = True
                    break
                except Exception:
                    continue
            if not found_main:
                raise Exception('未找到主内容区域')
            # 多组选择器兜底
            async def try_text(selectors, default=""):
                for sel in selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            txt = await el.text_content()
                            if txt and txt.strip():
                                return txt.strip()
                    except Exception:
                        continue
                return default
            # 歌名
            title = await try_text(['.data__name', '.songinfo__name', '.song_detail__info h1', '.song_detail__info .songname', 'h1'])
            # 歌手
            artist = await try_text(['.data__singer', '.songinfo__singer', '.song_detail__singer', '.singer_name', '.song_detail__info .singer', '.song_detail__info .author'])
            # --- 新增：遍历li.data_info__item_song提取专辑和发行时间，并调试输出 ---
            album = ""
            release_time = ""
            try:
                li_list = await page.query_selector_all('li.data_info__item_song')
                print(f"[调试] li.data_info__item_song数量: {len(li_list)}")
                for idx, li in enumerate(li_list):
                    txt = await li.inner_text()
                    print(f"[调试] li[{idx}] inner_text: {txt}")
                    a = await li.query_selector('a')
                    if a:
                        a_txt = await a.text_content()
                        print(f"[调试] li[{idx}] a标签内容: {a_txt}")
                    if txt.strip().startswith('专辑'):
                        if a:
                            album = a_txt or ""
                    if txt.strip().startswith('发行时间'):
                        lines = [line.strip() for line in txt.split('\n') if line.strip()]
                        if lines and len(lines) > 1:
                            release_time = lines[-1]
            except Exception as e:
                print(f"[调试] 遍历li.data_info__item_song出错: {str(e)}")
            # --- END ---
            if not album:
                album = await try_text(['li.data_info__item_song:has-text("专辑") a', '.data__album', '.songinfo__album', '.song_detail__album', '.album_name', '.song_detail__info .album', 'a[data-stat="album_name"]'])
            if not release_time:
                release_time = await try_text(['li.data_info__item_song:has-text("发行时间")', '.data__time', '.songinfo__time', '.song_detail__info .publish_time', '.song_detail__info .time', '.song_detail__info .pub_time', 'span[data-stat="publish_time"]'])
            # 3. 优先抓取data__desc_txt中的简介，循环等待内容不为空
            desc = "暂无简介"
            try:
                await page.wait_for_selector('div.data__desc_txt', timeout=10000)
                desc_el = await page.query_selector('div.data__desc_txt')
                if desc_el:
                    desc_text = ""
                    for _ in range(10):
                        desc_text = await desc_el.text_content()
                        if desc_text and desc_text.strip():
                            desc = desc_text.strip()
                            break
                        await asyncio.sleep(0.5)
                    print(f"[调试] desc_el: {desc_el}, desc_text: {desc_text}")
            except Exception as e:
                print(f"[调试] 简介抓取异常: {str(e)}")
            # 抓取歌词前截图
            try:
                await page.screenshot(path='D:/Redbook-Search-Comment-MCP2.0-main/qqmusic_debug_detail_before_lyric.png')
            except Exception as e:
                print(f"[调试] 抓取歌词前截图失败: {str(e)}")
            # 歌词抓取增强版
            lyrics = "该歌曲暂无歌词"
            try:
                # 常见歌词选择器列表，按优先级依次尝试
                lyric_selectors = [
                    'div.lyric_cont a.c_tx_highlight',
                    '.lyric__cont',
                    '.lyric__text',
                    '.song_lyric__content',
                    '.lyric',
                    '.song_detail__lyric',
                    '.songinfo__lyric',
                    'pre.lyric__cont',
                    'div.lyric__cont',
                    'div.song_lyric__content',
                    'div.lyric',
                    'div.song_detail__lyric',
                    'div.songinfo__lyric'
                ]
                for sel in lyric_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            txt = await el.text_content()
                            if txt and txt.strip():
                                lyrics = txt.strip()
                                break
                    except Exception:
                        continue
                # 兼容部分歌词在pre标签
                if (not lyrics or lyrics.strip() == '' or lyrics == '该歌曲暂无歌词'):
                    try:
                        pre_lyric = await page.query_selector('pre')
                        if pre_lyric:
                            txt = await pre_lyric.text_content()
                            if txt and txt.strip():
                                lyrics = txt.strip()
                    except Exception:
                        pass
            except Exception as e:
                print(f"[调试] 抓取歌词时异常: {str(e)}")
            # 抓取歌词后截图
            try:
                await page.screenshot(path='D:/Redbook-Search-Comment-MCP2.0-main/qqmusic_debug_detail_after_lyric.png')
            except Exception as e:
                print(f"[调试] 抓取歌词后截图失败: {str(e)}")
            # 格式化输出
            result = f"歌曲: {title or '未知歌曲'}\n"
            result += f"歌手: {artist or '未知歌手'}\n"
            result += f"专辑: {album or '未知专辑'}\n"
            result += f"发行时间: {release_time or '未知时间'}\n"
            result += f"歌曲ID: {song_id}\n\n"
            if desc:
                result += f"简介: {desc}\n\n"
            result += f"歌词:\n{lyrics}"
            # 如果主要信息都为空，写入日志
            if not title and not artist and not album:
                try:
                    html = await page.evaluate('(el) => el.innerHTML', await page.query_selector('body'))
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"[调试] get_song_details未抓到主要信息，页面body片段：\n{html[:2000]}\n\n")
                    print(f"已写入调试日志: {log_path}", flush=True)
                except Exception as e:
                    print(f"写日志失败: {str(e)}", flush=True)
            return result
        except Exception as e:
            try:
                html = await page.evaluate('(el) => el.innerHTML', await page.query_selector('body'))
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[调试] get_song_details异常，页面body片段：\n{html[:2000]}\n\n")
                print(f"已写入调试日志: {log_path}", flush=True)
            except Exception as e2:
                print(f"写日志失败: {str(e2)}", flush=True)
            return f"获取歌曲详情失败: {str(e)}"
    return await retry_action(_get_song_details)

@mcp.tool()
async def search_artist_id_by_name(name: str) -> str:
    """
    根据歌手名搜索artist_id，适配新版QQ音乐歌手搜索页面。
    Args:
        name: 歌手名
    Returns:
        artist_id: 歌手ID（若未找到返回空字符串）
    """
    async def _search_artist():
        search_url = f"https://y.qq.com/n/ryqq/search?w={name}&t=singer"
        await page.goto(search_url, timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)
        try:
            # 遍历所有a[href*='/singer/']，调试输出
            all_artist_links = await page.query_selector_all('a[href*="/singer/"]')
            debug_candidates = []
            for link in all_artist_links:
                href = await link.get_attribute('href')
                text = await link.text_content()
                debug_candidates.append({'href': href, 'text': text})
                # 精确匹配歌手名
                if text and text.strip() == name.strip() and href and '/singer/' in href:
                    artist_id = href.split('/singer/')[-1].split('?')[0]
                    print(f"[调试] 精确匹配到歌手: {text}, artist_id: {artist_id}")
                    return artist_id
            print(f"[调试] 未精确匹配到歌手名，候选链接: {json.dumps(debug_candidates, ensure_ascii=False)}")
            # 兜底：返回第一个候选artist_id
            if debug_candidates and debug_candidates[0]['href'] and '/singer/' in debug_candidates[0]['href']:
                artist_id = debug_candidates[0]['href'].split('/singer/')[-1].split('?')[0]
                print(f"[调试] 兜底返回第一个artist_id: {artist_id}")
                return artist_id
            else:
                print("[调试] 没有任何候选歌手链接，返回空字符串")
                return ""
        except Exception as e:
            print(f"搜索歌手ID时出错: {str(e)}")
            return ""
    return await retry_action(_search_artist)

@mcp.tool()
async def get_artist_info(artist_id: str) -> str:
    """
    获取歌手详细信息
    Args:
        artist_id: 歌手ID或歌手名
    """
    async def _get_artist_info():
        _artist_id = artist_id
        # 如果传入的是中文名，先查ID
        if not all(c.isalnum() for c in artist_id):
            _artist_id = await search_artist_id_by_name(artist_id)
            if not _artist_id:
                return f"未找到歌手：{artist_id}"
        artist_url = f"https://y.qq.com/n/ryqq/singer/{_artist_id}"
        await page.goto(artist_url, timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)
        # 1. 跳转后判断实际页面URL，若被重定向则友好提示
        if not page.url.startswith(artist_url):
            if 'login' in page.url or 'y.qq.com' in page.url:
                return "未登录或被重定向到首页，请在自动化浏览器中登录QQ音乐账号后重试。"
            else:
                return f"页面被重定向，当前URL: {page.url}"
        try:
            # 2. 丰富选择器，兜底提取歌手名
            name = None
            name_selectors = ['.data__name', '.singer__name', '.mod_singer_card .singer__name']
            for sel in name_selectors:
                try:
                    name = await page.text_content(sel)
                    if name:
                        break
                except Exception:
                    continue
            if not name:
                name = "未知歌手"
            # 3. 优先抓取data_desc_txt中的简介，直接获取纯文本内容
            desc = "暂无简介"
            try:
                await page.wait_for_selector('div.data__desc_txt', timeout=10000)
                desc_el = await page.query_selector('div.data__desc_txt')
                if desc_el:
                    desc_text = await desc_el.text_content()
                    if desc_text and desc_text.strip():
                        desc = desc_text.strip()
            except Exception as e:
                print(f"[调试] 简介抓取异常: {str(e)}")
            # 4. 统计信息：适配mod_data_statistic结构
            song_count = "0"
            album_count = "0"
            mv_count = "0"
            try:
                stat_root = await page.query_selector('ul.mod_data_statistic')
                if stat_root:
                    items = await stat_root.query_selector_all('li.data_statistic__item')
                    for item in items:
                        tit = await item.text_content()
                        if '单曲' in tit:
                            num_el = await item.query_selector('strong.data_statistic__number')
                            if num_el:
                                song_count = (await num_el.text_content()).strip()
                        elif '专辑' in tit:
                            num_el = await item.query_selector('strong.data_statistic__number')
                            if num_el:
                                album_count = (await num_el.text_content()).strip()
                        elif 'MV' in tit:
                            num_el = await item.query_selector('strong.data_statistic__number')
                            if num_el:
                                mv_count = (await num_el.text_content()).strip()
            except Exception:
                pass
            # 格式化输出
            result = f"歌手：{name.strip()}\n\n"
            result += f"简介：\n{desc.strip()}\n\n"
            result += f"统计信息：\n"
            result += f"单曲：{song_count} | 专辑：{album_count} | MV：{mv_count}"
            return result
        except Exception as e:
            return f"获取歌手信息失败: {str(e)}\n请确认已登录QQ音乐且网络畅通，或页面结构未发生重大变化。"
    return await retry_action(_get_artist_info)

@mcp.tool()
async def get_artist_songs(artist_id: str, limit: int = 10) -> str:
    """
    获取歌手的热门歌曲
    
    Args:
        artist_id: 歌手ID
        limit: 返回歌曲数量限制
    """
    async def _get_artist_songs():
        # 访问歌手页面
        artist_url = f"https://y.qq.com/n/ryqq/singer/{artist_id}"
        await page.goto(artist_url, timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)

        try:
            # 等待歌曲列表加载
            await page.wait_for_selector('.songlist__list', timeout=10000)
            
            # 获取歌曲列表
            songs = []
            song_elements = await page.query_selector_all('.songlist__item')
            
            for i, element in enumerate(song_elements):
                if i >= limit:
                    break
                try:
                    # 获取歌曲信息
                    title_element = await element.query_selector('.songlist__songname_txt')
                    album_element = await element.query_selector('.songlist__album')
                    duration_element = await element.query_selector('.songlist__time')

                    # 提取文本
                    title = await title_element.text_content() if title_element else "未知歌曲"
                    album = await album_element.text_content() if album_element else "未知专辑"
                    duration = await duration_element.text_content() if duration_element else ""

                    # 修正 song_id 提取逻辑
                    song_id = ""
                    if title_element:
                        a_tag = await title_element.query_selector('a')
                        if a_tag:
                            song_link = await a_tag.get_attribute('href')
                            if song_link and '/songDetail/' in song_link:
                                song_id = song_link.split('/songDetail/')[-1].split('?')[0]
                    # 调试：若song_id依然为空，打印HTML结构
                    if not song_id and title_element:
                        html = await title_element.evaluate('(el) => el.outerHTML')
                        print(f"[调试] 未获取到song_id，title_element.outerHTML: {html}")

                    songs.append({
                        'title': title.strip(),
                        'album': album.strip(),
                        'duration': duration.strip(),
                        'song_id': song_id
                    })
                except Exception as e:
                    print(f"提取歌曲信息时出错: {str(e)}")
                    continue
            
            # 格式化输出
            result = "热门歌曲：\n\n"
            for i, song in enumerate(songs, 1):
                result += f"{i}. {song['title']}\n"
                result += f"   专辑: {song['album']}\n"
                result += f"   时长: {song['duration']}\n"
                result += f"   歌曲ID: {song['song_id']}\n"
                if i < len(songs):
                    result += "\n"
            
            return result
            
        except Exception as e:
            return f"获取歌手热门歌曲失败: {str(e)}"

    return await retry_action(_get_artist_songs)

@mcp.tool()
async def get_song_comments(song_id: str, limit: int = 10) -> str:
    """
    获取歌曲的热门评论和最新评论（弹窗Tab切换）
    Args:
        song_id: 歌曲ID
        limit: 每类评论返回数量限制
    """
    async def _get_song_comments():
        song_url = f"https://y.qq.com/n/ryqq/songDetail/{song_id}"
        await page.goto(song_url, timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)
        log_path = r"D:/Redbook-Search-Comment-MCP2.0-main/qqmusic_debug.log"
        try:
            # 自动点击评论按钮，确保评论区加载
            comment_btn_selectors = [
                'button:has-text("评论")',
                'a:has-text("评论")',
                '.mod_btn_comment',
                '.comment__btn',
                'span:has-text("评论")',
                'div[data-stat="y_new.song_comment"]',
            ]
            for sel in comment_btn_selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(2)
                        break
                except Exception:
                    continue
            # 多次滚动页面，确保评论区异步加载
            for _ in range(5):
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(1)

            # 参考歌手详情的方式，直接遍历评论区结构
            comments = []
            try:
                # 遍历所有评论区（精彩评论和近期热评）
                comment_blocks = await page.query_selector_all('div.mod_hot_comment ul.comment__list')
                for block in comment_blocks:
                    items = await block.query_selector_all('li.comment__list_item.c_b_normal')
                    for element in items:
                        try:
                            user_el = await element.query_selector('h4.comment__title')
                            user_name = await user_el.text_content() if user_el else "匿名用户"
                            time_el = await element.query_selector('div.comment__date')
                            comment_time = await time_el.text_content() if time_el else ""
                            content_el = await element.query_selector('p.comment__text > span')
                            content_html = await content_el.inner_html() if content_el else ""
                            def img_to_title(match):
                                title = re.search(r'title="([^"]+)"', match.group(0))
                                return title.group(1) if title else ""
                            content = re.sub(r'<img[^>]*>', img_to_title, content_html)
                            content = re.sub(r'<br\s*/?>', '\n', content)
                            content = re.sub(r'<[^>]+>', '', content)
                            content = content.strip()
                            like_el = await element.query_selector('a.comment__zan')
                            like_count = await like_el.text_content() if like_el else ""
                            comments.append({
                                'user': user_name.strip(),
                                'content': content,
                                'time': comment_time.strip(),
                                'like': like_count.strip()
                            })
                        except Exception as e:
                            print(f"[调试] 评论提取异常: {str(e)}")
                            continue
            except Exception as e:
                print(f"[调试] 评论区结构提取异常: {str(e)}")
            # 格式化输出
            if not comments:
                return "未找到任何评论，可能是页面结构变化或评论区为空。"
            result = "评论：\n\n"
            for i, c in enumerate(comments, 1):
                result += f"{i}. {c['user']}（{c['time']}，赞{c['like']}）\n{c['content']}\n\n"
            return result
        except Exception as e:
            try:
                html = await page.evaluate('(el) => el.innerHTML', await page.query_selector('body'))
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[调试] 评论区异常，页面body片段：\n{html[:2000]}\n\n")
                print(f"已写入调试日志: {log_path}", flush=True)
            except Exception as e2:
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"[调试] 获取页面HTML片段失败: {str(e2)}\n")
                    print(f"已写入调试日志: {log_path}", flush=True)
                except Exception as log_e:
                    print(f"写日志失败: {log_e}", flush=True)
            return f"获取歌曲评论失败: {str(e)}"
    return await retry_action(_get_song_comments)



if __name__ == "__main__":
    # 初始化并运行服务器
    print("启动QQ音乐MCP服务器...")
    print("请在MCP客户端（如Claude for Desktop）中配置此服务器")
    mcp.run(transport='stdio')
