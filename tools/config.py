"""
配置常量模块

定义 Bili-Music-UU 应用程序中使用的所有常量，包括窗口标题、尺寸、
表格列定义和菜单结构等。
"""

# ==================== 窗口配置 ====================

APP_TITLE: str = "Bili-Music-UU — 哔哩哔哩音频下载助手"
"""主窗口标题"""

APP_GEOMETRY: str = "1050x650"
"""主窗口默认尺寸（宽 x 高）"""

# ==================== 下载相关配置 ====================

DEFAULT_DOWNLOAD_DIR: str = "."
"""默认下载目录，使用当前工作目录"""

HTTP_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/58.0.3029.110 Safari/537.3"
    ),
    "Origin": "https://www.bilibili.com",
}
"""B站 API 请求使用的 HTTP 请求头"""

BILI_VIDEO_INFO_API: str = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
"""B站视频信息 API 地址模板"""

BILI_PLAYURL_API: str = (
    "https://api.bilibili.com/x/player/playurl"
    "?fnval=16&bvid={bvid}&cid={cid}"
)
"""B站音频播放地址 API 模板（fnval=16 启用 DASH 格式）"""

BILI_VIDEO_BASE_URL: str = "https://www.bilibili.com/video/"
"""B站视频页面基础 URL"""

# ==================== 表格列定义 ====================

TABLE_COLUMNS: list[dict] = [
    {"name": "page", "text": "分P序号", "width": 60, "anchor": "center"},
    {"name": "part", "text": "分P标题", "width": 280, "anchor": "w"},
    {"name": "duration", "text": "时长", "width": 80, "anchor": "center"},
    {"name": "cid", "text": "CID", "width": 100, "anchor": "center"},
    {"name": "status", "text": "状态", "width": 100, "anchor": "center"},
]
"""表格列配置列表，每列包含 name（内部标识）、text（显示标题）、width（列宽）、anchor（对齐方式）"""

# ==================== 菜单结构定义 ====================

MENU_ITEMS: dict[str, list[tuple[str, str | None, str | None]]] = {
    "文件": [
        ("设置下载目录", "set_dir", "设置音频文件的保存目录"),
        ("separator", None, None),
        ("退出", "exit", "退出应用程序"),
    ],
    "帮助": [
        ("关于", "about", "关于本应用程序"),
    ],
}
"""
菜单项定义，结构为 {菜单名: [(子项名称, 命令标识, 描述), ...]}。
命令标识为 "separator" 时表示分隔线。
"""
