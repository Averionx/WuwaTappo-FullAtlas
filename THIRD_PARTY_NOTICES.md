# 第三方内容说明

本项目名称和功能描述仅用于识别兼容的原程序，不表示官方认可或授权。

| 内容 | 说明 |
| --- | --- |
| WuwaTappo 原程序、原界面及其美术素材 | 权利归原权利人。仓库不包含原版二进制及完整提取前端。1.3.6 使用经过修改的官方 1.0.3 程序和从其公开素材接口准备的离线缓存；不声称拥有这些内容，也不以 MIT 重新授权。 |
| Microsoft Edge WebView2 Fixed Version Runtime x64 | Microsoft 的第三方运行时，适用其独立许可条款。下载及分发文档：https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution 。原始随包许可和第三方说明保留在 `runtime/` 内。 |
| Python | 冻结本地服务内包含 Python 运行时，适用 Python Software Foundation License；许可文件随发行包保留。 |
| Tcl/Tk 8.6 | 独立安装进度窗口通过 Python tkinter 使用，适用 Tcl/Tk 原有许可；完整许可保留在 `licenses/TCL_LICENSE.txt`、`licenses/TK_LICENSE.txt`。 |
| 975Maru SC 界面字体 | 安装进度沿用原版字体形状；本机字形子集采用私有字体族名 WT Tappo UI，仅当前进程加载，按 SIL OFL 1.1 保留原版权与许可，见 `licenses/975MARU_SC_OFL.txt`。 |
| psutil 7.2.2 | 原地更新辅助进程使用的进程查询依赖，BSD 3-Clause License；许可随包保留在 `licenses/PSUTIL_LICENSE.txt`。 |
| comtypes 1.4.13 | 通过 Windows UI Automation 只读检查现代编辑控件类型，不读取文本内容。MIT License，许可随包保留在 `licenses/COMTYPES_LICENSE.txt`。 |
| PyInstaller | 构建工具，GPL with exception，允许生成的应用按自己的许可证分发。https://pyinstaller.org/en/stable/license.html 。相关依赖和许可保留在冻结服务中。 |
| Acorn 8.15.0 | 构建时的 JavaScript 解析器，MIT License，许可见 `tools/ACORN_LICENSE`。 |
| Brotli、pefile、jsbeautifier | 仅为构建依赖，不改变它们各自的授权；安装依赖时获取其原有许可证。 |
| Inno Setup | 用于生成安装包的构建工具，保留其安装器自身标识；https://jrsoftware.org/ 。 |

MIT 许可证只覆盖本项目新编写的修改逻辑、工具和文档，不构成对第三方内容的额外授权。
