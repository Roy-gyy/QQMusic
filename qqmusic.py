from typing import Any, List, Dict, Optional
import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright, TimeoutError
from fastmcp import FastMCP

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
            # 专辑
            album = await try_text(['.data__album', '.songinfo__album', '.song_detail__album', '.album_name', '.song_detail__info .album'])
            # 发行时间
            release_time = await try_text(['.data__time', '.songinfo__time', '.song_detail__info .publish_time', '.song_detail__info .time', '.song_detail__info .pub_time'])
            # 简介
            desc = await try_text(['.song_detail__desc', '.data__desc', '.songinfo__desc', '.desc', '.song_detail__info .desc'])
            # 歌词
            lyrics = "暂无歌词"
            lyric_selectors = ['.lyric__text', '.song_lyric__content', '.lyric', '.song_detail__lyric', '.songinfo__lyric']
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
            # 3. 丰富简介选择器
            desc = "暂无简介"
            desc_selectors = ['.basic__desc', '.singer__desc', '.mod_singer_card .singer__desc']
            for sel in desc_selectors:
                try:
                    desc_candidate = await page.text_content(sel)
                    if desc_candidate:
                        desc = desc_candidate
                        break
                except Exception:
                    continue
            # 4. 统计信息采用能取到就取，取不到就跳过
            async def safe_text(selector):
                try:
                    txt = await page.text_content(selector)
                    return txt.strip() if txt else "0"
                except Exception:
                    return "0"
            song_count = await safe_text('.data__num_song')
            album_count = await safe_text('.data__num_album')
            mv_count = await safe_text('.data__num_mv')
            fans_count = await safe_text('.data__num_fans')
            result = f"歌手：{name.strip()}\n\n"
            result += f"简介：\n{desc.strip()}\n\n"
            result += f"统计信息：\n"
            result += f"单曲：{song_count} | 专辑：{album_count} | "
            result += f"MV：{mv_count} | 粉丝：{fans_count}"
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
            # 1. 点击评论按钮，弹出评论弹窗
            comment_btn_selectors = [
                'button:has-text("评论")',
                'a:has-text("评论")',
                '.mod_btn_comment',
                '.comment__btn',
                'span:has-text("评论")',
                'div[data-stat="y_new.song_comment"]',
            ]
            comment_btn = None
            for sel in comment_btn_selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        comment_btn = btn
                        break
                except Exception:
                    continue
            if comment_btn:
                await comment_btn.click()
                await asyncio.sleep(2)
            else:
                print("[调试] 未找到评论按钮，直接尝试抓取页面评论区")

            # 2. 评论弹窗内Tab选择器
            tab_selectors = {
                'hot': ['li:has-text("热门")', 'div.tab__item:has-text("热门")', 'button:has-text("热门")'],
                'new': ['li:has-text("最新")', 'div.tab__item:has-text("最新")', 'button:has-text("最新")'],
            }
            # 3. 评论内容区选择器（弹窗/主页面都兼容）
            comment_list_selectors = [
                '.comment__list', '.mod_comment_list', '.comment-list', '.mod_comment', '.popup__comment_list', '.popup_comment_list'
            ]
            comment_item_selectors = [
                '.comment__item', '.mod_comment_item', '.comment-item', '.comment-list-item', '.popup__comment_item', '.popup_comment_item'
            ]
            def format_comments(title, comments):
                if not comments:
                    return f"{title}：暂无评论。\n"
                result = f"{title}：\n\n"
                for i, c in enumerate(comments, 1):
                    result += f"{i}. {c['user']}：{c['content']}\n   时间：{c['time']}\n"
                    if i < len(comments):
                        result += "\n"
                return result
            all_results = []
            for tab, tab_names in [('热门评论', tab_selectors['hot']), ('最新评论', tab_selectors['new'])]:
                # 切换Tab
                tab_found = False
                for sel in tab_names:
                    try:
                        tab_btn = await page.query_selector(sel)
                        if tab_btn and await tab_btn.is_visible():
                            await tab_btn.click()
                            await asyncio.sleep(2)
                            tab_found = True
                            break
                    except Exception:
                        continue
                if not tab_found:
                    print(f"[调试] 未找到{tab}Tab，尝试直接抓取")
                # 滚动加载
                for _ in range(3):
                    await page.mouse.wheel(0, 1000)
                    await asyncio.sleep(1)
                # 抓取评论
                comment_elements = []
                for list_sel in comment_list_selectors:
                    try:
                        await page.wait_for_selector(list_sel, timeout=3000)
                        for item_sel in comment_item_selectors:
                            elements = await page.query_selector_all(f"{list_sel} {item_sel}")
                            if elements:
                                comment_elements = elements
                                break
                        if comment_elements:
                            break
                    except Exception:
                        continue
                # 兜底
                if not comment_elements:
                    for item_sel in comment_item_selectors:
                        try:
                            elements = await page.query_selector_all(item_sel)
                            if elements:
                                comment_elements = elements
                                break
                        except Exception:
                            continue
                comments = []
                for i, element in enumerate(comment_elements):
                    if i >= limit:
                        break
                    try:
                        user = await element.query_selector('.comment__user, .user__name, .comment-user, .user-name')
                        user_name = await user.text_content() if user else "匿名用户"
                        content = await element.query_selector('.comment__content, .comment-content, .content, .comment_text')
                        comment_text = await content.text_content() if content else ""
                        time_el = await element.query_selector('.comment__time, .comment-time, .time')
                        comment_time = await time_el.text_content() if time_el else ""
                        comments.append({
                            'user': user_name.strip(),
                            'content': comment_text.strip(),
                            'time': comment_time.strip()
                        })
                    except Exception as e:
                        # 写入调试日志
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(f"[调试] 提取{tab}信息时出错: {str(e)}\n")
                            print(f"已写入调试日志: {log_path}", flush=True)
                        except Exception as log_e:
                            print(f"写日志失败: {log_e}", flush=True)
                        continue
                if not comments:
                    # 输出页面结构片段到日志
                    try:
                        html = await page.evaluate('(el) => el.innerHTML', await page.query_selector('body'))
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(f"[调试] {tab}未找到评论，页面body片段：\n{html[:2000]}\n\n")
                        print(f"已写入调试日志: {log_path}", flush=True)
                    except Exception as e:
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(f"[调试] 获取页面HTML片段失败: {str(e)}\n")
                            print(f"已写入调试日志: {log_path}", flush=True)
                        except Exception as log_e:
                            print(f"写日志失败: {log_e}", flush=True)
                all_results.append(format_comments(tab, comments))
            # 主流程结尾：无论如何都写一次页面结构到日志
            try:
                html = await page.evaluate('(el) => el.innerHTML', await page.query_selector('body'))
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[调试] 主流程结尾页面body片段：\n{html[:2000]}\n\n")
                print(f"已写入调试日志: {log_path}", flush=True)
            except Exception as e:
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"[调试] 主流程结尾获取页面HTML片段失败: {str(e)}\n")
                    print(f"已写入调试日志: {log_path}", flush=True)
                except Exception as log_e:
                    print(f"写日志失败: {log_e}", flush=True)
            return '\n'.join(all_results)
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

@mcp.tool()
async def post_song_comment(song_id: str, comment: str) -> str:
    """
    在指定歌曲下发表评论
    Args:
        song_id: 歌曲ID
        comment: 要发布的评论内容
    """
    async def _post_song_comment():
        song_url = f"https://y.qq.com/n/ryqq/songDetail/{song_id}"
        await page.goto(song_url, timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(2)
        try:
            # 优先查找QQ音乐新版评论输入框
            input_selectors = [
                'div.comment__textarea_default.c_tx_normal[contenteditable="true"]',
                'div[contenteditable="true"]',
                'textarea.comment__textarea',
                'textarea[placeholder*="说点什么"]',
                '.comment__textarea',
                'textarea'
            ]
            comment_input = None
            for selector in input_selectors:
                try:
                    # 先用query_selector获取ElementHandle
                    element = await page.query_selector(selector)
                    if element:
                        comment_input = element
                        break
                except Exception:
                    continue
            if not comment_input:
                return "未能找到评论输入框，无法发表评论。"
            await comment_input.click()
            await asyncio.sleep(1)
            # 确保comment_input为ElementHandle，evaluate调用无参数数量错误
            try:
                await comment_input.evaluate(
                    '''(el, text) => {
                        el.innerText = text;
                        el.textContent = text;
                        el.value = text;
                        el.dispatchEvent(new Event("input", {bubbles:true}));
                        el.dispatchEvent(new Event("compositionend", {bubbles:true}));
                        el.dispatchEvent(new Event("change", {bubbles:true}));
                    }''',
                    comment
                )
                print("[调试] 已用ElementHandle.evaluate设置评论内容并触发事件")
            except Exception as e:
                print(f"[调试] evaluate设置评论内容失败: {str(e)}")
                return f"evaluate设置评论内容失败: {str(e)}"
            await asyncio.sleep(1)
            # 尝试点击发送按钮
            send_selectors = [
                'button.comment__btn_send',
                'button:has-text("发送")',
                'button[aria-label*="发送"]',
                'button',
                '.comment__btn_send',
                '.mod_comment_send',
                'a.comment__btn_send'
            ]
            send_success = False
            for selector in send_selectors:
                try:
                    send_btn = await page.query_selector(selector)
                    if send_btn and await send_btn.is_enabled():
                        await send_btn.click()
                        await asyncio.sleep(2)
                        send_success = True
                        break
                except Exception:
                    continue
            if send_success:
                return f"已成功发表评论：{comment}"
            else:
                return "未能成功点击发送按钮，评论可能未发布。"
        except Exception as e:
            return f"发表评论时出错: {str(e)}"
    return await retry_action(_post_song_comment)

if __name__ == "__main__":
    # 初始化并运行服务器
    print("启动QQ音乐MCP服务器...")
    print("请在MCP客户端（如Claude for Desktop）中配置此服务器")
    mcp.run(transport='stdio')
