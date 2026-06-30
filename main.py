"""
Bili-Music-UU 哔哩哔哩音频下载助手 —— 主入口模块

一个基于 tkinter 的 Windows 桌面应用程序，用于下载 B站视频的音频。
界面分为三块：顶部菜单栏、左侧输入/控制面板、右侧分P数据表格。

使用方法:
    python main.py
    启动后在输入框中粘贴 B站视频链接或 BV 号，点击「拉取」获取分P列表，
    选中需要下载的分P后点击「下载选中」即可保存为 MP3 文件。
"""

import io
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Any

from PIL import Image, ImageDraw, ImageTk

from tools.config import (
    APP_TITLE,
    APP_GEOMETRY,
    TABLE_COLUMNS,
    MENU_ITEMS,
    DEFAULT_DOWNLOAD_DIR,
)
from module.bili_api import (
    parse_bvid,
    get_video_info,
    get_audio_url,
    get_cover_bytes,
    format_duration,
)
from module.download_manager import (
    DownloadManager,
    STATUS_PENDING,
    STATUS_DOWNLOADING,
    STATUS_DOWNLOADED,
    STATUS_FAILED,
)


class BiliMusicApp:
    """
    哔哩哔哩音频下载助手主窗口类。

    负责构建整个 GUI 界面，包括菜单栏、左侧控制面板和右侧分P数据表格，
    并处理用户交互与下载调度。

    Attributes:
        root: tkinter 根窗口实例
        download_manager: 下载管理器实例
        _bvid: 当前拉取的 BV 号
        _video_info: 当前视频信息字典（含标题、作者、封面、分P列表）
        _page_status: 每行分P的下载状态字典，键为行 ID，值为状态字符串
        tree: ttk.Treeview 表格控件
    """

    def __init__(self) -> None:
        """初始化应用程序：创建主窗口、菜单、布局并安装下载管理器。"""
        # ---- 根窗口 ----
        self.root: tk.Tk = tk.Tk()
        """tkinter 根窗口对象"""
        self.root.title(APP_TITLE)
        self.root.geometry(APP_GEOMETRY)
        self.root.minsize(1400, 750)

        # ---- 下载管理器 ----
        self.download_manager: DownloadManager = DownloadManager()
        """下载管理器实例，负责后台下载与转码"""

        # ---- 内部状态 ----
        self._bvid: str | None = None
        """当前已拉取的视频 BV 号"""
        self._video_info: dict[str, Any] | None = None
        """当前视频信息字典，包含 title/author/cover_url/pages"""
        self._page_status: dict[str, str] = {}
        """每行分P的下载状态，键为 Treeview iid，值为状态字符串"""
        self._dir_var: tk.StringVar = tk.StringVar(
            value=os.path.abspath(DEFAULT_DOWNLOAD_DIR)
        )
        """下载目录路径绑定的 StringVar"""

        self._face_image: ImageTk.PhotoImage | None = None
        """UP 主头像的 PhotoImage 对象，需保持引用防止被 tkinter 垃圾回收"""

        # ---- 构建界面 ----
        self._build_menu()
        """构建顶部菜单栏"""
        self._build_body()
        """构建主体区域（左侧控制面板 + 右侧表格）"""

        # ---- 居中显示 ----
        self._center_window()

    # ==================== 菜单构建 ====================

    def _build_menu(self) -> None:
        """
        构建顶部菜单栏。

        根据 MENU_ITEMS 配置动态创建菜单项，并绑定对应的回调方法。
        """
        menubar: tk.Menu = tk.Menu(self.root)
        """菜单栏控件"""

        command_map: dict[str, Any] = {
            "set_dir": self._on_set_download_dir,
            "exit": self._on_exit,
            "about": self._on_about,
        }
        """命令标识 → 回调方法映射表"""

        for menu_name, items in MENU_ITEMS.items():
            sub_menu: tk.Menu = tk.Menu(menubar, tearoff=0)
            """当前顶级菜单下的下拉菜单"""

            for item_name, cmd, _desc in items:
                if cmd == "separator":
                    sub_menu.add_separator()
                elif cmd and cmd in command_map:
                    sub_menu.add_command(label=item_name, command=command_map[cmd])
                else:
                    sub_menu.add_command(label=item_name, state=tk.DISABLED)

            menubar.add_cascade(label=menu_name, menu=sub_menu)

        self.root.config(menu=menubar)

    # ==================== 主体布局 ====================

    def _build_body(self) -> None:
        """
        构建主体区域。

        使用垂直 PanedWindow 分为上下两部分：
        - 上部：水平 PanedWindow，左侧控制面板 + 右侧分P表格
        - 下部：日志信息框（跨整个窗口宽度）
        """
        # 外层垂直分隔面板（上：内容区 / 下：日志区）
        main_paned: ttk.PanedWindow = ttk.PanedWindow(
            self.root, orient=tk.VERTICAL
        )
        """垂直分隔面板，上下拖动可调整日志区高度"""
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ---- 上部：水平分隔面板（左右布局） ----
        top_frame: ttk.Frame = ttk.Frame(main_paned)
        """上部内容区容器"""
        h_paned: ttk.PanedWindow = ttk.PanedWindow(top_frame, orient=tk.HORIZONTAL)
        """水平分隔面板，左右拖动可调整面板宽度"""
        h_paned.pack(fill=tk.BOTH, expand=True)

        # 左侧控制面板
        left_frame: ttk.Frame = ttk.Frame(h_paned, width=450)
        """左侧控制面板容器"""
        self._build_left_panel(left_frame)
        h_paned.add(left_frame, weight=0)

        # 右侧表格面板
        right_frame: ttk.Frame = ttk.Frame(h_paned)
        """右侧表格面板容器"""
        self._build_right_panel(right_frame)
        h_paned.add(right_frame, weight=1)

        main_paned.add(top_frame, weight=1)

        # ---- 下部：日志信息框（跨整个窗口宽度） ----
        log_frame: ttk.Frame = ttk.Frame(main_paned, height=140)
        """日志信息区容器"""
        self._build_log_panel(log_frame)
        main_paned.add(log_frame, weight=0)

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        """
        构建左侧控制面板。

        包含以下组件：
        1. BV 号输入框 + 拉取按钮
        2. 视频信息展示区（标题、作者）
        3. 下载目录设置区
        4. 下载选中按钮

        Args:
            parent: 左侧面板的父容器 Frame
        """
        # ---- 面板标题 ----
        title_label: ttk.Label = ttk.Label(
            parent, text="🎵 B站音频下载", font=("Microsoft YaHei", 13, "bold")
        )
        """面板标题"""
        title_label.pack(pady=(10, 15))

        # ---- BV 号输入区 ----
        input_section: ttk.LabelFrame = ttk.LabelFrame(parent, text="视频地址")
        """BV 号输入区域的外框"""
        input_section.pack(fill=tk.X, padx=15, pady=(0, 10))

        # 输入提示
        hint_label: ttk.Label = ttk.Label(
            input_section,
            text="请输入 B站视频链接或 BV 号：",
            font=("Microsoft YaHei", 9),
        )
        """输入提示标签"""
        hint_label.pack(anchor="w", padx=10, pady=(8, 2))

        # 输入框容器
        entry_row: ttk.Frame = ttk.Frame(input_section)
        """输入框与按钮的行容器"""
        entry_row.pack(fill=tk.X, padx=10, pady=(0, 8))

        self._bvid_var: tk.StringVar = tk.StringVar()
        """BV 号输入框绑定的 StringVar"""
        bvid_entry: ttk.Entry = ttk.Entry(entry_row, textvariable=self._bvid_var)
        """BV 号输入框"""
        bvid_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        bvid_entry.bind("<Return>", self._on_fetch)
        bvid_entry.focus_set()

        fetch_btn: ttk.Button = ttk.Button(
            entry_row,
            text="🔍 拉取",
            command=self._on_fetch,
        )
        """拉取视频信息按钮"""
        fetch_btn.pack(side=tk.RIGHT)

        # ---- 视频信息展示区 ----
        info_section: ttk.LabelFrame = ttk.LabelFrame(parent, text="视频信息")
        """视频信息展示区域的外框"""
        info_section.pack(fill=tk.X, padx=15, pady=(0, 10))

        self._info_title_var: tk.StringVar = tk.StringVar(value="")
        """视频标题展示文本"""
        self._info_author_var: tk.StringVar = tk.StringVar(value="")
        """视频作者展示文本"""
        self._info_pages_var: tk.StringVar = tk.StringVar(value="")
        """分P数量展示文本"""
        self._info_view_var: tk.StringVar = tk.StringVar(value="")
        """观看数展示文本"""
        self._info_favorite_var: tk.StringVar = tk.StringVar(value="")
        """收藏数展示文本"""
        self._info_coin_var: tk.StringVar = tk.StringVar(value="")
        """投币数展示文本"""
        self._info_share_var: tk.StringVar = tk.StringVar(value="")
        """分享数展示文本"""
        self._info_like_var: tk.StringVar = tk.StringVar(value="")
        """点赞数展示文本"""

        # 第一层：圆形头像（居中）
        self._face_label: ttk.Label = ttk.Label(info_section)
        """UP 主头像标签，显示圆形头像图片，居中放置"""
        self._face_label.pack(pady=(10, 8))

        # 标题
        ttk.Label(
            info_section, text="标题：", font=("Microsoft YaHei", 9, "bold")
        ).pack(anchor="w", padx=10, pady=(0, 0))
        ttk.Label(
            info_section, textvariable=self._info_title_var,
            font=("Microsoft YaHei", 9), wraplength=300,
        ).pack(anchor="w", padx=10, pady=(0, 2))

        # 作者
        ttk.Label(
            info_section, text="作者：", font=("Microsoft YaHei", 9, "bold")
        ).pack(anchor="w", padx=10)
        ttk.Label(
            info_section, textvariable=self._info_author_var,
            font=("Microsoft YaHei", 9),
        ).pack(anchor="w", padx=10, pady=(0, 2))

        # 分P数量
        ttk.Label(
            info_section, textvariable=self._info_pages_var,
            font=("Microsoft YaHei", 9),
        ).pack(anchor="w", padx=10, pady=(0, 6))

        # 分隔线
        ttk.Separator(info_section, orient=tk.HORIZONTAL).pack(
            fill=tk.X, padx=10, pady=(0, 6)
        )

        # 互动数据 —— 每项单独一行
        stats_labels: list[tuple[str, tk.StringVar]] = [
            ("👁  观看", self._info_view_var),
            ("⭐  收藏", self._info_favorite_var),
            ("🪙  投币", self._info_coin_var),
            ("↗  分享", self._info_share_var),
            ("👍  点赞", self._info_like_var),
        ]
        """互动数据标签配置：(图标+名称, StringVar)"""

        for icon_text, var in stats_labels:
            row_frame: ttk.Frame = ttk.Frame(info_section)
            """单行互动数据容器"""
            row_frame.pack(fill=tk.X, padx=10, pady=(0, 2))

            ttk.Label(
                row_frame, text=icon_text,
                font=("Microsoft YaHei", 9), width=8, anchor="w",
            ).pack(side=tk.LEFT)
            ttk.Label(
                row_frame, textvariable=var,
                font=("Microsoft YaHei", 9, "bold"), foreground="#333333",
            ).pack(side=tk.LEFT)

        # 底部留白
        ttk.Label(info_section, text="").pack()

        # ---- 操作按钮区 ----
        action_row: ttk.Frame = ttk.Frame(parent)
        """操作按钮行容器"""
        action_row.pack(fill=tk.X, padx=15, pady=(0, 5))

        self._download_btn: ttk.Button = ttk.Button(
            action_row,
            text="⬇ 下载选中",
            command=self._on_download_selected,
            state=tk.DISABLED,
        )
        """下载选中分P的按钮（初始禁用，拉取后启用）"""
        self._download_btn.pack(fill=tk.X)

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        """
        构建底部日志信息面板。

        包含一个带滚动条的只读文本框，用于展示操作日志，
        每条日志自动附加时间戳。

        Args:
            parent: 日志面板的父容器 Frame
        """
        log_section: ttk.LabelFrame = ttk.LabelFrame(parent, text="📜 日志信息")
        """日志信息区域的外框"""
        log_section.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # 日志文本框 + 滚动条容器
        inner_frame: ttk.Frame = ttk.Frame(log_section)
        """包裹日志文本框与滚动条的容器"""
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._log_text: tk.Text = tk.Text(
            inner_frame,
            height=6,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state=tk.DISABLED,
            bg="#f8f8f8",
        )
        """日志文本框，只读模式，用于展示操作日志"""
        log_scrollbar: ttk.Scrollbar = ttk.Scrollbar(
            inner_frame, orient=tk.VERTICAL, command=self._log_text.yview
        )
        """日志文本框的垂直滚动条"""
        self._log_text.configure(yscrollcommand=log_scrollbar.set)

        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 写入初始日志
        self._log("就绪，请输入视频地址")

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        """
        构建右侧分P数据表格面板。

        使用 Treeview 展示视频所有分P的信息，包括序号、标题、时长、CID 和下载状态。
        附带垂直与水平滚动条。

        Args:
            parent: 右侧面板的父容器 Frame
        """
        # ---- 面板标题 ----
        title_label: ttk.Label = ttk.Label(
            parent, text="📋 分P列表", font=("Microsoft YaHei", 12, "bold")
        )
        """表格区域标题"""
        title_label.pack(pady=(10, 5))

        # ---- 下载目录设置区 ----
        dir_section: ttk.LabelFrame = ttk.LabelFrame(parent, text="📁 下载设置")
        """下载目录设置区域的外框"""
        dir_section.pack(fill=tk.X, padx=5, pady=(0, 5))

        dir_row: ttk.Frame = ttk.Frame(dir_section)
        """目录选择行容器"""
        dir_row.pack(fill=tk.X, padx=10, pady=8)

        dir_entry: ttk.Entry = ttk.Entry(
            dir_row, textvariable=self._dir_var, state="readonly"
        )
        """下载目录只读展示框"""
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        dir_btn: ttk.Button = ttk.Button(
            dir_row,
            text="浏览",
            command=self._on_set_download_dir,
        )
        """选择下载目录按钮"""
        dir_btn.pack(side=tk.RIGHT)

        # ---- 表格容器（含滚动条） ----
        table_frame: ttk.Frame = ttk.Frame(parent)
        """包裹 Treeview 和滚动条的容器"""
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        col_names: list[str] = [col["name"] for col in TABLE_COLUMNS]
        """Treeview 内部列标识符列表"""

        self.tree: ttk.Treeview = ttk.Treeview(
            table_frame,
            columns=col_names,
            show="headings",
            selectmode="browse",
        )
        """分P数据展示表格"""

        # 按配置设置每一列
        for col in TABLE_COLUMNS:
            self.tree.heading(col["name"], text=col["text"])
            self.tree.column(col["name"], width=col["width"], anchor=col["anchor"])

        # 垂直滚动条
        v_scrollbar: ttk.Scrollbar = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        """垂直滚动条"""
        self.tree.configure(yscrollcommand=v_scrollbar.set)

        # 水平滚动条
        h_scrollbar: ttk.Scrollbar = ttk.Scrollbar(
            table_frame, orient=tk.HORIZONTAL, command=self.tree.xview
        )
        """水平滚动条"""
        self.tree.configure(xscrollcommand=h_scrollbar.set)

        # grid 布局
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # 绑定选中事件
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        """表格行选中变化事件"""

        # 绑定双击事件 → 下载选中分P
        self.tree.bind("<Double-1>", self._on_row_double_click)
        """双击表格行触发下载"""

    # ==================== 事件回调 ====================

    def _on_fetch(self, event: tk.Event | None = None) -> None:
        """
        「拉取」按钮的回调。

        解析输入的 BV 号，调用 B站 API 获取视频信息，
        并将所有分P渲染到右侧表格中。

        Args:
            event: tkinter 事件对象（绑定回车键时传入）
        """
        raw_input: str = self._bvid_var.get().strip()
        """用户输入的原始文本"""
        if not raw_input:
            messagebox.showwarning("输入为空", "请输入 B站视频链接或 BV 号！")
            return

        # 解析 BV 号
        bvid = parse_bvid(raw_input)
        """解析出的 BV 号"""
        if not bvid:
            messagebox.showerror(
                "解析失败",
                "无法从输入中解析出 BV 号，请检查链接或 BV 号是否正确。\n\n"
                "支持格式：\n"
                "  • https://www.bilibili.com/video/BV1xx2xx3xx4xx\n"
                "  • BV1xx2xx3xx4xx",
            )
            return

        # 调用 API 获取视频信息
        self._log("正在拉取视频信息...")
        self.root.config(cursor="watch")
        self.root.update()

        try:
            info = get_video_info(bvid)
            """从 B站 API 获取的视频信息"""
        finally:
            self.root.config(cursor="")

        if info is None:
            self._log("拉取失败，请检查 BV 号是否正确")
            messagebox.showerror(
                "拉取失败",
                f"无法获取视频信息，请确认 BV 号有效：{bvid}",
            )
            return

        # 保存状态
        self._bvid = bvid
        self._video_info = info
        self._page_status.clear()

        # 更新视频信息展示
        self._info_title_var.set(info["title"])
        self._info_author_var.set(info["author"])
        pages_count = len(info["pages"])
        """分P总数"""
        self._info_pages_var.set(f"共 {pages_count} 个分P")

        # 更新互动数据（观看/收藏/投币/分享/点赞）—— 每项单独一行
        fmt = self._format_count
        """计数格式化函数的本地别名"""
        self._info_view_var.set(fmt(info.get("view")))
        self._info_favorite_var.set(fmt(info.get("favorite")))
        self._info_coin_var.set(fmt(info.get("coin")))
        self._info_share_var.set(fmt(info.get("share")))
        self._info_like_var.set(fmt(info.get("like")))

        # 下载并显示 UP 主圆形头像
        self._load_face_avatar(info.get("face", ""))

        # 刷新表格
        self._refresh_table(info)

        # 启用下载按钮
        self._download_btn.config(state=tk.NORMAL)

        self._log(f"拉取成功！共 {pages_count} 个分P，选中一条后点击「下载选中」")

    def _on_set_download_dir(self) -> None:
        """
        「浏览」按钮 / 菜单「设置下载目录」的回调。

        弹出文件夹选择对话框，将选中的路径更新到下载目录。
        """
        directory: str = filedialog.askdirectory(
            title="选择音频保存目录",
            initialdir=self._dir_var.get(),
        )
        """用户选择的文件夹路径"""
        if directory:
            self._dir_var.set(os.path.abspath(directory))
            self.download_manager.set_download_dir(directory)
            self._log(f"下载目录已设置为: {os.path.abspath(directory)}")

    def _on_download_selected(self) -> None:
        """
        「下载选中」按钮的回调。

        获取表格中当前选中行的分P信息，启动后台下载任务。
        """
        if not self._video_info:
            messagebox.showinfo("提示", "请先拉取视频信息。")
            return

        selected: tuple[str, ...] | None = self.tree.selection()
        """当前选中行 ID 元组"""
        if not selected:
            messagebox.showinfo("提示", "请先在表格中选择一个分P。")
            return

        self._start_download_for_row(selected[0])

    def _on_row_double_click(self, event: tk.Event) -> None:
        """
        表格行双击事件回调 —— 下载双击的分P。

        Args:
            event: tkinter 事件对象
        """
        selected: tuple[str, ...] | None = self.tree.selection()
        """当前选中行 ID 元组"""
        if not selected:
            return
        self._start_download_for_row(selected[0])

    def _on_tree_select(self, event: tk.Event) -> None:
        """
        表格行选中变化事件回调。

        当有行被选中且该行状态为「未下载」或「下载失败」时启用下载按钮。

        Args:
            event: tkinter 事件对象
        """
        selected: tuple[str, ...] | None = self.tree.selection()
        """当前选中行 ID 元组"""
        if not selected:
            self._download_btn.config(state=tk.DISABLED)
            return

        item_iid = selected[0]
        """选中行的 Treeview 行 ID"""
        status = self._page_status.get(item_iid, STATUS_PENDING)
        """该行的下载状态"""

        # 仅未下载和失败状态允许再次下载
        if status in (STATUS_PENDING, STATUS_FAILED):
            self._download_btn.config(state=tk.NORMAL)
        else:
            self._download_btn.config(state=tk.DISABLED)

    def _on_exit(self) -> None:
        """「退出」菜单的回调 —— 关闭应用程序。"""
        self.root.destroy()

    def _on_about(self) -> None:
        """「关于」菜单的回调 —— 显示关于对话框。"""
        ffmpeg_status = (
            "✅ FFmpeg 可用（支持 MP3 转码）"
            if self.download_manager._ffmpeg_available
            else "⚠ FFmpeg 不可用（仅支持 m4a 下载）"
        )
        """FFmpeg 可用性状态文本"""

        about_text: str = (
            f"{APP_TITLE}\n\n"
            "版本：2.0.0\n"
            "一款哔哩哔哩视频音频下载工具。\n"
            "支持多分P视频的独立音频下载。\n\n"
            f"{ffmpeg_status}\n\n"
            "基于 Python tkinter 构建。"
        )
        """关于对话框内容"""
        messagebox.showinfo("关于", about_text)

    # ==================== 下载调度 ====================

    def _start_download_for_row(self, item_iid: str) -> None:
        """
        启动指定表格行对应的分P音频下载。

        获取该行对应的分P数据，调用下载管理器在后台执行下载，
        并通过回调更新 UI 状态。

        Args:
            item_iid: Treeview 中目标行的 iid
        """
        # 检查当前状态，避免重复下载
        current_status = self._page_status.get(item_iid, STATUS_PENDING)
        """该行当前的下载状态"""
        if current_status == STATUS_DOWNLOADING:
            messagebox.showinfo("提示", "该分P正在下载中，请等待完成。")
            return

        # 获取行数据
        item: dict[str, Any] = self.tree.item(item_iid)
        """Treeview 行属性字典"""
        values: list[Any] = item["values"]
        """行中各列的数值列表：[page, part, duration, cid, status]"""
        page_num: int = int(values[0])
        """分P序号"""
        cid: int = int(values[3])
        """内容 ID"""

        # 确保下载目录已设置
        self.download_manager.set_download_dir(self._dir_var.get())

        # 获取音频下载链接
        self._log(f"正在获取分P {page_num} 的音频链接...")
        audio_url = get_audio_url(self._bvid, cid)
        """该分P的 DASH 音频流直链"""
        if not audio_url:
            messagebox.showerror(
                "获取失败",
                f"无法获取分P {page_num} 的音频下载链接。\nCID: {cid}",
            )
            return

        # 更新状态为「下载中」
        self._update_row_status(item_iid, STATUS_DOWNLOADING)
        self._download_btn.config(state=tk.DISABLED)

        # 提取分P标题和视频信息
        part_title = str(values[1])
        """分P的标题文本"""
        author = (
            self._video_info.get("author", "")
            if self._video_info else ""
        )
        cover_url = (
            self._video_info.get("cover_url", "")
            if self._video_info else ""
        )

        # 启动后台下载
        self.download_manager.download_audio(
            bvid=self._bvid,
            cid=cid,
            title=part_title,
            author=author,
            cover_url=cover_url,
            audio_url=audio_url,
            status_callback=lambda msg: self._on_download_status(item_iid, msg),
            complete_callback=lambda ok, msg: self._on_download_complete(item_iid, ok, msg),
        )

    def _on_download_status(self, item_iid: str, status_text: str) -> None:
        """
        下载过程中的状态更新回调（在后台线程中调用）。

        使用 tkinter 的线程安全方法更新行状态和底部状态栏。

        Args:
            item_iid: 目标行 iid
            status_text: 状态描述文本
        """
        def _update() -> None:
            """在主线程中执行的 UI 更新函数"""
            self._update_row_status(item_iid, status_text)
            self._log(status_text)
        self.root.after(0, _update)

    def _on_download_complete(
        self, item_iid: str, success: bool, message: str
    ) -> None:
        """
        下载完成后的回调（在后台线程中调用）。

        更新行状态为「已下载」或「下载失败」，恢复下载按钮。

        Args:
            item_iid: 目标行 iid
            success: 是否下载成功
            message: 结果描述
        """
        def _update() -> None:
            """在主线程中执行的 UI 更新函数"""
            new_status = STATUS_DOWNLOADED if success else STATUS_FAILED
            """根据成功/失败确定的新状态"""
            self._update_row_status(item_iid, new_status)
            self._log(message)

            # 若当前仍选中该行则启用下载按钮（允许重试失败的下载）
            selected: tuple[str, ...] | None = self.tree.selection()
            if selected and selected[0] == item_iid and not success:
                self._download_btn.config(state=tk.NORMAL)
            elif selected and selected[0] == item_iid and success:
                self._download_btn.config(state=tk.DISABLED)

        self.root.after(0, _update)

    # ==================== 辅助方法 ====================

    def _refresh_table(self, info: dict[str, Any]) -> None:
        """
        用视频信息刷新右侧表格显示。

        清空 Treeview 中所有行后，根据视频的 pages 列表逐条插入。

        Args:
            info: 视频信息字典，需包含 pages 列表
        """
        # 清空现有行
        for child in self.tree.get_children():
            self.tree.delete(child)
        self._page_status.clear()

        # 逐条插入分P
        for p in info.get("pages", []):
            page_num = p["page"]
            """分P序号"""
            part = p["part"]
            """分P标题"""
            duration_fmt = format_duration(p["duration"])
            """格式化后的时长"""
            cid = p["cid"]
            """内容 ID"""

            iid = self.tree.insert(
                "", tk.END,
                values=(page_num, part, duration_fmt, cid, STATUS_PENDING),
            )
            """新插入的 Treeview 行 ID"""
            self._page_status[iid] = STATUS_PENDING

    def _update_row_status(self, item_iid: str, status: str) -> None:
        """
        更新表格中指定行的状态列显示。

        Args:
            item_iid: Treeview 行 iid
            status: 新的状态文本
        """
        self._page_status[item_iid] = status
        # 更新 Treeview 行的 values（状态在第5列，索引4）
        item: dict[str, Any] = self.tree.item(item_iid)
        """目标行的属性字典"""
        values: list[Any] = list(item["values"])
        """行数据列表的副本"""
        values[4] = status
        self.tree.item(item_iid, values=tuple(values))

    def _log(self, text: str) -> None:
        """
        向日志信息框追加一行带时间戳的日志。

        自动在文本末尾追加换行符，并滚动到最新位置。

        Args:
            text: 日志文本内容
        """
        from datetime import datetime

        timestamp: str = datetime.now().strftime("[%H:%M:%S] ")
        """当前时间戳，格式为 [HH:MM:SS]"""
        line: str = f"{timestamp}{text}\n"
        """完整的一行日志（含时间戳和换行）"""

        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, line)
        self._log_text.see(tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _center_window(self) -> None:
        """
        将主窗口居中显示在屏幕上。

        通过计算屏幕尺寸与窗口尺寸的差值来设置窗口的起始坐标。
        """
        self.root.update_idletasks()
        screen_w: int = self.root.winfo_screenwidth()
        """屏幕宽度（像素）"""
        screen_h: int = self.root.winfo_screenheight()
        """屏幕高度（像素）"""
        window_w: int = self.root.winfo_width()
        """窗口宽度（像素）"""
        window_h: int = self.root.winfo_height()
        """窗口高度（像素）"""

        x: int = (screen_w - window_w) // 2
        """窗口左上角 X 坐标"""
        y: int = (screen_h - window_h) // 2
        """窗口左上角 Y 坐标"""
        self.root.geometry(f"+{x}+{y}")

    # ==================== 视频信息辅助方法 ====================

    @staticmethod
    def _format_count(count: Any) -> str:
        """
        将计数数值格式化为易读的中文缩写字符串。

        大于等于 10000 时显示为「x.x万」格式，否则直接显示原数值。
        空值或无效值返回 ``--``。

        Args:
            count: 原始计数值（整数或整数字符串）

        Returns:
            格式化后的计数字符串
        """
        if count is None or count == "":
            return "--"
        try:
            num: int = int(count)
            """转换为整数的计数值"""
        except (ValueError, TypeError):
            return str(count)
        if num >= 10000:
            wan: float = num / 10000.0
            """以万为单位的浮点数值"""
            return f"{wan:.1f}万"
        return str(num)

    @staticmethod
    def _make_circular_image(image_data: bytes, size: int = 64) -> ImageTk.PhotoImage:
        """
        将图片二进制数据裁剪为圆形并返回 tkinter 可用的 PhotoImage 对象。

        使用 PIL 将图片缩放至指定尺寸后，通过椭圆遮罩实现圆形裁剪，
        圆形以外的区域设为透明。

        Args:
            image_data: 原始图片的二进制字节数据
            size: 输出头像的像素尺寸（宽高相等）

        Returns:
            圆形裁剪后的 PhotoImage 对象，可直接设置到 Label 的 image 属性
        """
        img: Image.Image = Image.open(io.BytesIO(image_data))
        """从二进制数据打开的 PIL Image 对象"""
        img = img.resize((size, size), Image.LANCZOS)

        # 创建圆形遮罩
        mask: Image.Image = Image.new("L", (size, size), 0)
        """圆形遮罩图像，黑色为透明区域，白色为保留区域"""
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(mask)
        """遮罩绘制对象"""
        draw.ellipse((0, 0, size - 1, size - 1), fill=255)

        # 将遮罩应用到原图，圆形以外的区域设为透明
        result: Image.Image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        """带透明通道的输出图像"""
        result.paste(img, (0, 0), mask)

        return ImageTk.PhotoImage(result)

    def _load_face_avatar(self, face_url: str) -> None:
        """
        下载 UP 主头像并显示为圆形头像。

        若头像 URL 为空或下载失败，则显示空白。
        下载到的 PhotoImage 对象保存在 ``self._face_image`` 中以防止被垃圾回收。

        Args:
            face_url: UP 主头像的图片 URL
        """
        # 清除旧头像
        self._face_label.configure(image="")
        self._face_image = None

        if not face_url:
            return

        try:
            image_data: bytes | None = get_cover_bytes(face_url)
            """下载到的头像图片二进制数据"""
            if image_data:
                self._face_image = self._make_circular_image(image_data, size=64)
                self._face_label.configure(image=self._face_image)
        except Exception as e:
            # 头像加载失败不影响主流程
            self._log(f"头像加载失败: {e}")

    def run(self) -> None:
        """
        启动应用程序主循环。

        调用此方法将阻塞当前线程，进入 tkinter 事件循环，
        直到用户关闭窗口。
        """
        self.root.mainloop()


# ==================== 程序入口 ====================

if __name__ == "__main__":
    """应用程序入口：创建 BiliMusicApp 实例并启动主循环。"""
    app: BiliMusicApp = BiliMusicApp()
    app.run()
