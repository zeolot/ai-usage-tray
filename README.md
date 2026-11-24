# AI Usage Tray — Codex & Antigravity 任务栏用量统计

轻量级跨平台（**Windows 10/11** & **Linux 统信 UOS / Deepin / GNOME / KDE**）系统托盘应用，实时统计本机 **Codex** 和 **Antigravity** 的模型用量、Token 数、估算费用、缓存命中率、生成速度与首字延迟。

## 功能特性

- **简洁浅色卡片样式**：每个模型以彩色胶囊圆点 + 占比进度条展示，包含总 Token、请求数、估算费用（`$`）、生成速度（`token/秒`）、计时次数、首字延迟（Codex 原生支持）、缓存命中率与占比百分比。
- **双来源自动增量扫描**（按文件修改时间缓存，刷新仅约 1ms）：
  - **Codex**：自动读取 `~/.codex/sessions`（支持环境变量 `CODEX_HOME`），按 `response_id` 去重，精确统计 `input_tokens`、`cached_input_tokens`、`output_tokens`、`reasoning_output_tokens`，并使用流式 `AgentMessage` 毫秒级起止时间与 `time_to_first_token_ms` 计算速度与首字延迟。
  - **Antigravity**：自动读取 `~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl`（支持环境变量 `ANTIGRAVITY_HOME`），精确统计未缓存输入、`cache_read_tokens`、输出 Token 与缓存命中率；速度通过相邻步骤时间差及后台实时落盘观测估算（以 `~` 标注）。
- **快捷筛选与明细**：顶部一键切换来源（`全部` / `Codex` / `Antigravity`）与时间范围（`今日` / `7天` / `30天` / `全部`）；鼠标悬停任意模型行可查看详细 Token 拆解。
- **自定义模型单价**：点击面板右上角 `$` 或托盘右键“模型单价设置”，配置持久化保存（Linux：`~/.config/ai-usage-tray/pricing.json`；Windows：`%APPDATA%\ai-usage-tray\pricing.json`）。
- **跨平台任务栏与开机自启**：
  - **Windows 10/11**：支持原生任务栏通知区域图标（多分辨率渲染）、上下左右四边任务栏与多显示器自动贴边弹出、Windows Named Mutex 单实例锁、注册表 `HKCU\...\Run` 开机自启、`pythonw.exe` 无黑框静默运行，以及一键打包单文件 `.exe`。
  - **Linux（统信 UOS 20 / Deepin `dde-dock` 等）**：支持 XWayland/Wayland 自动适配与 `~/.config/autostart/` 开机自启。

---

## 快速开始

### Windows 10 / 11

1. 安装依赖（Python 3.7+）：

   ```powershell
   pip install -r requirements.txt
   ```

2. 启动到任务栏（无终端黑框）：
   - 双击 `launch.bat`（或直接双击 `run.pyw`）
   - 或命令行启动并立即弹出面板：

     ```powershell
     .\launch.bat --show
     ```

3. 配置开机自启：
   - 直接右键任务栏蓝色图标勾选 **“开机自启”**，或运行：

     ```powershell
     .\install_windows_autostart.bat
     ```

   - 取消自启：`.\install_windows_autostart.bat --uninstall`

4. （可选）打包为独立单文件 `AIUsageTray.exe`：

   ```powershell
   .\build_windows_exe.bat
   ```

---

### Linux（统信 UOS 20 / Deepin / Ubuntu / Debian）

#### 方式 1：直接安装 `.deb` 安装包（推荐，同时兼容 ARM64 与 x86_64）

从 GitHub [Releases](https://github.com/zeolot/ai-usage-tray/releases) 下载 `ai-usage-tray_1.0.0_all.deb`，双击或执行：

```bash
sudo apt install ./ai-usage-tray_1.0.0_all.deb
```

安装后可直接从系统应用菜单启动 **AI 用量统计**，或在终端运行 `ai-usage-tray --show`。

自行重新构建 `.deb`：

```bash
./build_deb.sh 1.0.0
```

#### 方式 2：从源码直接运行

1. 系统自带 Python 3 与 PyQt5 时无需额外安装依赖（其他发行版可执行 `pip3 install -r requirements.txt`）。
2. 启动到任务栏托盘并首次弹出面板：

   ```bash
   nohup ./launch.sh --show >/dev/null 2>&1 &
   ```

3. 安装开机自启与应用菜单快捷方式：

   ```bash
   ./install_autostart.sh
   ```

   卸载：`./install_autostart.sh --uninstall`

---

## 交互说明

- **左键点击任务栏图标**：展开 / 收起统计面板（支持拖动，点击桌面其他区域自动隐藏）。
- **右键点击任务栏图标**：显示/隐藏面板、立即刷新、修改模型单价、开关开机自启、退出。
- **鼠标悬停任务栏图标**：快速查看今日与累计 Token、请求数和估算费用摘要。
