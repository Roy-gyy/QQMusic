---
css: styles.css
---

# QQ音乐自动搜索工具（MCP Server）

<div align="right">

[English](README_EN.md) | 中文

</div>

> 本项目基于 Playwright + FastMCP 实现，支持自动化登录QQ音乐、搜索歌曲、获取歌曲详情、热门评论、发布评论等功能，并可作为 MCP Server 接入 Claude for Desktop 等 AI 客户端，实现自然语言驱动的音乐内容自动化。

---

<style>
h1, h2, h3, h4, h5, h6 {
  font-size: 90%;
}
p, li {
  font-size: 90%;
}
</style>

## 主要特点与优势

- **自动化浏览器操作**：基于 Playwright，模拟真实用户操作，兼容新版QQ音乐网页版。
- **MCP协议集成**：可作为MCP Server，支持Claude for Desktop等AI客户端自然语言调用。
- **持久化登录**：首次扫码后自动保存登录态，后续无需重复扫码。
- **丰富的音乐数据获取能力**：支持歌曲、歌手、专辑、评论等多维度信息自动提取。
- **自动评论与AI结合**：可结合AI生成评论内容并自动发布。
- **详细日志与调试支持**：遇到页面结构变化可快速定位问题。

---

## 一、核心功能

### 1. 用户认证与登录
- **持久化登录**：支持扫码登录，首次登录后保存状态，后续使用无需重复扫码。
- **登录状态管理**：自动检测登录状态，失效时自动提示。

### 2. 歌曲与歌手搜索
- **关键词搜索歌曲**：支持多关键词搜索，返回歌名、歌手、专辑、时长、歌曲ID等。
- **歌手搜索与ID获取**：支持歌手名模糊/精确搜索，返回歌手ID。

### 3. 歌曲与歌手详情
- **获取歌曲详情**：根据歌曲ID获取详细信息，包括歌词、专辑、发行时间、简介等。
- **获取歌手信息**：根据歌手ID获取简介、统计、热门歌曲等。

### 4. 评论获取与发布
- **获取歌曲评论**：自动加载并提取热门评论和最新评论，支持表情、换行等内容解析。

### 5. 数据返回与反馈
- **结构化数据返回**：所有API均返回结构化文本，便于AI客户端处理。
- **操作结果反馈**：实时返回操作结果与错误信息。

---

## 二、安装步骤

1. **Python 环境准备**：确保系统已安装 Python 3.8 或更高版本。
2. **项目获取**：克隆或下载本项目到本地。
3. **创建虚拟环境**：
   ```bash
   python3 -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```
4. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   playwright install
   ```
5. **启动服务器**：
   ```bash
   python qqmusic.py
   ```

---

## 三、MCP Server 配置

在 MCP Client（如Claude for Desktop）的配置文件中添加以下内容，将本工具配置为 MCP Server：

### Windows 配置示例
```json
{
    "mcpServers": {
        "qqmusic MCP": {
            "command": "C:\\Users\\username\\Desktop\\MCP\\Redbook-Search-Comment-MCP2.0\\venv\\Scripts\\python.exe",
            "args": [
                "C:\\Users\\username\\Desktop\\MCP\\Redbook-Search-Comment-MCP2.0\\qqmusic.py",
                "--stdio"
            ]
        }
    }
}
```
> **重要提示**：请使用虚拟环境中Python解释器和qqmusic.py的完整绝对路径，Windows路径需双反斜杠。

---

## 四、使用方法

### （一）启动服务器

1. 激活虚拟环境，运行：
   ```bash
   python qqmusic.py
   ```
2. 配置好MCP Client后，按照客户端操作流程启动和连接。

![命令行启动服务](/images/startup.png)

---

### （二）主要功能操作

在MCP Client（如Claude for Desktop）中连接到服务器后，可以使用以下功能：

---

#### 1. 登录QQ音乐

**浏览器自动化界面：**

![自动化登录界面](/images/login.png)


**MCP客户端界面：**

![MCP客户端调用界面](/images/mcp_client.png)


---

**工具函数**：
```
login()
```
**自然语言示例**：
```
请登录QQ音乐
```

---

#### 2. 搜索歌曲

**浏览器自动化界面：**

![搜索歌曲效果](/images/search.png)


**MCP客户端界面：**

![MCP客户端调用界面](/images/mcp_client1.png)


---

**工具函数**：
```
search_songs(keywords="关键词", limit=5)
```
**自然语言示例**：
```
帮我搜索QQ音乐歌曲，关键词为：飞鸟与蝉
```

---

#### 3. 获取歌曲详情

**MCP客户端界面：**

![MCP客户端调用界面](/images/mcp_client4.png)


---

**工具函数**：
```
get_song_details(song_id="歌曲ID")
```
**自然语言示例**：
```
帮我获取歌曲 飞鸟和蝉 的详细信息
```

---

#### 4. 获取歌曲评论

**浏览器自动化界面：**

![获取歌曲评论效果](/images/comment.png)


**MCP客户端界面：**

![MCP客户端调用界面](/images/mcp_client2.png)


---

**工具函数**：
```
get_song_comments(song_id="歌曲ID", limit=10)
```
**自然语言示例**：
```
帮我获取 飞鸟和蝉 的热门评论
```

---

#### 5. 搜索歌手与获取歌手信息

**MCP客户端界面：**

![MCP客户端调用界面](/images/mcp_client3.png)


---

**工具函数**：
```
search_artist_id_by_name(name="歌手名")
get_artist_info(artist_id="歌手ID")
get_artist_songs(artist_id="歌手ID", limit=10)
```
**自然语言示例**：
```
帮我查找歌手 王源 的信息
```

---

## 五、API参数与返回说明

- `keywords`：搜索关键词，支持模糊匹配。
- `limit`：返回结果数量，默认5或10。
- `song_id`：歌曲唯一ID，可通过搜索结果获得。
- `artist_id`：歌手唯一ID，可通过搜索或ID查询获得。

所有API均返回结构化文本，便于AI客户端解析。

---

## 六、常见问题与解决方案

1. **登录失败/页面打不开**：
   - 检查网络，首次登录需扫码，后续自动保持。
   - 若浏览器未弹出，请确认Playwright已正确安装。
2. **评论区为空/结构变化**：
   - QQ音乐页面结构如有变动，请关注项目更新或自行调整选择器。
3. **依赖安装问题**：
   - 严格按照 requirements.txt 安装依赖，并执行 `playwright install`。
4. **MCP集成问题**：
   - MCP Client 配置的 python 路径和 qqmusic.py 路径需为绝对路径。
5. **浏览器实例问题**：
   - 如遇"Target page, context or browser has been closed"错误，重启MCP服务器。
6. **内容获取不全**：
   - 增加等待时间，或尝试多次。

---

## 七、代码结构

- **qqmusic.py**：QQ音乐自动化主程序，包含所有MCP工具函数。
- **requirements.txt**：依赖库清单。
- **README_QQMUSIC.md**：本说明文档。
- **browser_data/**：浏览器持久化数据目录。

---

## 八、使用注意事项

- **浏览器模式**：工具使用 Playwright 的非隐藏模式运行，运行时会打开真实浏览器窗口。
- **登录方式**：首次登录需扫码，后续自动保持。
- **平台规则**：请遵守QQ音乐平台规定，避免频繁操作。

---

## 九、免责声明

本工具仅用于学习与研究目的，严禁用于任何商业或违法用途。请遵守QQ音乐平台相关规定，因使用本工具造成的任何后果，开发者不承担任何责任。 
