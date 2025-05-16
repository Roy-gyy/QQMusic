from typing import Any, List, Dict, Optional
import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from fastmcp import FastMCP

# 初始化 FastMCP 服务器
mcp = FastMCP("qqmusic")

# 全局变量
playwright: Optional[Playwright] = None
browser: Optional[Browser] = None
page: Optional[Page] = None

async def init_browser():
    """初始化浏览器"""
    global playwright, browser, page
    try:
        # 如果已经有实例在运行，先关闭它们
        if page:
            await page.close()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
        
        # 重新初始化所有组件
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=False,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = await browser.new_page(
            viewport={'width': 1280, 'height': 800}
        )
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

@mcp.tool()
async def login() -> str:
    """登录QQ音乐账号"""
    try:
        # 初始化浏览器
        if not await init_browser():
            return "浏览器初始化失败"
        
        # 访问QQ音乐登录页面
        await page.goto("https://y.qq.com", timeout=60000)
        await asyncio.sleep(3)
        
        # 查找登录按钮并点击
        login_elements = await page.query_selector_all('text="登录"')
        if login_elements:
            await login_elements[0].click()
            await asyncio.sleep(2)  # 等待登录框出现
            
            print("请在打开的浏览器窗口中完成登录操作。登录成功后，系统将自动继续。")
            
            # 等待用户登录成功
            max_wait_time = 180  # 等待3分钟
            wait_interval = 5
            waited_time = 0
            
            while waited_time < max_wait_time:
                try:
                    # 检查是否已登录成功
                    still_login = await page.query_selector_all('text="登录"')
                    if not still_login:
                        await asyncio.sleep(2)  # 等待页面加载
                        return "登录成功！"
                except Exception:
                    pass
                
                # 继续等待
                await asyncio.sleep(wait_interval)
                waited_time += wait_interval
            
            return "登录等待超时。请重试或手动登录后再使用其他功能。"
        else:
            return "已登录QQ音乐账号"
            
    except Exception as e:
        print(f"登录过程中出错: {str(e)}")
        await cleanup()
        return f"登录出错: {str(e)}"

@mcp.tool()
async def search_songs(keywords: str, limit: int = 5) -> str:
    """根据关键词搜索歌曲
    
    Args:
        keywords: 搜索关键词
        limit: 返回结果数量限制
    """
    if not page:
        return "请先登录QQ音乐账号"
    
    try:
        # 构建搜索URL并访问
        search_url = f"https://y.qq.com/n/ryqq/search?w={keywords}"
        print(f"访问搜索页面: {search_url}")
        await page.goto(search_url, timeout=60000)
        await asyncio.sleep(5)  # 等待页面加载
        
        # 等待搜索结果加载
        await page.wait_for_selector('.songlist__list', timeout=10000)
        print("搜索结果页面已加载")
        
        # 获取歌曲列表
        songs = []
        song_elements = await page.query_selector_all('.songlist__item')
        print(f"找到 {len(song_elements)} 个搜索结果")
        
        for song_element in song_elements[:limit]:
            try:
                # 获取歌曲标题
                title_element = await song_element.query_selector('.songlist__songname_txt')
                title = await title_element.text_content() if title_element else "未知歌曲"
                
                # 获取歌手名称
                artist_element = await song_element.query_selector('.songlist__artist')
                artist = await artist_element.text_content() if artist_element else "未知歌手"
                
                # 获取专辑名称
                album_element = await song_element.query_selector('.songlist__album')
                album = await album_element.text_content() if album_element else "未知专辑"
                
                # 获取歌曲时长
                duration_element = await song_element.query_selector('.songlist__time')
                duration = await duration_element.text_content() if duration_element else "未知时长"
                
                # 获取歌曲ID
                song_id = None
                link_element = await song_element.query_selector('a.songlist__songname')
                if link_element:
                    href = await link_element.get_attribute('href')
                    if href:
                        song_id = href.split('/')[-1]
                
                songs.append({
                    "title": title.strip(),
                    "artist": artist.strip(),
                    "album": album.strip(),
                    "duration": duration.strip(),
                    "song_id": song_id
                })
                
            except Exception as e:
                print(f"处理歌曲元素时出错: {str(e)}")
                continue
        
        # 格式化返回结果
        if songs:
            result = "搜索结果：\n\n"
            for i, song in enumerate(songs, 1):
                result += f"{i}. {song['title']} - {song['artist']}\n"
                result += f"   专辑: {song['album']}\n"
                result += f"   时长: {song['duration']}\n"
                result += f"   歌曲ID: {song['song_id']}\n\n"
            
            return result
        else:
            return f"未找到与\"{keywords}\"相关的歌曲"
    
    except Exception as e:
        print(f"搜索歌曲时出错: {str(e)}")
        return f"搜索歌曲时出错: {str(e)}"

@mcp.tool()
async def get_song_details(song_id: str) -> str:
    """获取歌曲详细信息
    
    Args:
        song_id: 歌曲ID
    """
    if not page:
        return "请先登录QQ音乐账号"
    
    try:
        # 访问歌曲页面
        url = f"https://y.qq.com/n/ryqq/songDetail/{song_id}"
        print(f"访问歌曲页面: {url}")
        await page.goto(url, timeout=60000)
        await asyncio.sleep(5)  # 等待页面加载
        
        # 等待页面主要内容加载
        try:
            await page.wait_for_selector('.data__name', timeout=10000)
            print("页面主要内容已加载")
        except Exception as e:
            print(f"等待页面元素超时: {str(e)}")
        
        # 获取歌曲信息
        song_info = {}
        
        # 获取歌曲标题
        title_element = await page.query_selector('.data__name')
        song_info["歌曲名"] = await title_element.text_content() if title_element else "未知歌曲"
        
        # 获取歌手信息
        artist_element = await page.query_selector('.data__singer')
        song_info["歌手"] = await artist_element.text_content() if artist_element else "未知歌手"
        
        # 获取专辑信息
        album_element = await page.query_selector('.data__album')
        song_info["专辑"] = await album_element.text_content() if album_element else "未知专辑"
        
        # 获取发行时间
        time_element = await page.query_selector('.data__info time')
        song_info["发行时间"] = await time_element.text_content() if time_element else "未知时间"
        
        # 获取歌词
        lyrics_element = await page.query_selector('.lyric')
        if lyrics_element:
            lyrics = await lyrics_element.text_content()
            song_info["歌词"] = lyrics.strip()
        else:
            song_info["歌词"] = "暂无歌词"
        
        # 格式化返回结果
        result = f"歌曲: {song_info['歌曲名']}\n"
        result += f"歌手: {song_info['歌手']}\n"
        result += f"专辑: {song_info['专辑']}\n"
        result += f"发行时间: {song_info['发行时间']}\n"
        result += f"歌曲ID: {song_id}\n\n"
        result += "歌词:\n"
        result += song_info['歌词']
        
        return result
    
    except Exception as e:
        print(f"获取歌曲详情时出错: {str(e)}")
        return f"获取歌曲详情时出错: {str(e)}"

@mcp.tool()
async def get_top_lists() -> str:
    """获取QQ音乐所有排行榜"""
    if not page:
        return "请先登录QQ音乐账号"
    
    try:
        # 访问排行榜页面
        await page.goto("https://y.qq.com/n/ryqq/toplist", timeout=60000)
        await asyncio.sleep(5)  # 等待页面加载
        
        # 等待排行榜列表加载
        await page.wait_for_selector('.toplist_nav__item', timeout=10000)
        
        # 获取所有排行榜
        top_lists = []
        list_elements = await page.query_selector_all('.toplist_nav__item')
        
        for list_element in list_elements:
            try:
                # 获取排行榜名称
                name_element = await list_element.query_selector('.toplist_nav__title')
                name = await name_element.text_content() if name_element else "未知排行榜"
                
                # 获取排行榜描述
                desc_element = await list_element.query_selector('.toplist_nav__desc')
                desc = await desc_element.text_content() if desc_element else ""
                
                # 获取排行榜链接
                link = await list_element.get_attribute('href')
                list_id = link.split('/')[-1] if link else None
                
                top_lists.append({
                    "name": name.strip(),
                    "desc": desc.strip(),
                    "id": list_id
                })
                
            except Exception as e:
                print(f"处理排行榜元素时出错: {str(e)}")
                continue
        
        # 格式化返回结果
        if top_lists:
            result = "QQ音乐排行榜列表：\n\n"
            for i, top_list in enumerate(top_lists, 1):
                result += f"{i}. {top_list['name']}\n"
                if top_list['desc']:
                    result += f"   简介: {top_list['desc']}\n"
                result += f"   ID: {top_list['id']}\n\n"
            
            return result
        else:
            return "未能获取到排行榜信息"
    
    except Exception as e:
        print(f"获取排行榜时出错: {str(e)}")
        return f"获取排行榜时出错: {str(e)}"

if __name__ == "__main__":
    # 初始化并运行服务器
    print("启动QQ音乐MCP服务器...")
    print("请在MCP客户端（如Claude for Desktop）中配置此服务器")
    mcp.run(transport='stdio') 