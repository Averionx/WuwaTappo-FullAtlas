# 第三方内容说明

本项目名称和功能描述仅用于识别兼容的原程序，不表示官方认可或授权。

| 内容 | 说明 |
| --- | --- |
| WuwaTappo 原程序、原界面及其美术素材 | 权利归原权利人。仓库不包含原版二进制及完整提取前端。1.2 使用经过修改的官方 1.0.2 程序和从其公开素材接口准备的离线缓存；不声称拥有这些内容，也不以 MIT 重新授权。 |
| Microsoft Edge WebView2 Fixed Version Runtime x64 | Microsoft 的第三方运行时，适用其独立许可条款。下载及分发文档：https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution 。原始随包许可和第三方说明保留在 `runtime/` 内。 |
| Python | 冻结本地服务内包含 Python 运行时，适用 Python Software Foundation License；许可文件随发行包保留。 |
| psutil 7.2.2 | 原地更新辅助进程使用的进程查询依赖，BSD 3-Clause License；许可随包保留在 `licenses/PSUTIL_LICENSE.txt`。 |
| PyInstaller | 构建工具，GPL with exception，允许生成的应用按自己的许可证分发。https://pyinstaller.org/en/stable/license.html 。相关依赖和许可保留在冻结服务中。 |
| Acorn 8.15.0 | 构建时的 JavaScript 解析器，MIT License，许可见 `tools/ACORN_LICENSE`。 |
| Brotli、pefile、jsbeautifier | 仅为构建依赖，不改变它们各自的授权；安装依赖时获取其原有许可证。 |
| Inno Setup | 用于生成安装包的构建工具，保留其安装器自身标识；https://jrsoftware.org/ 。 |

MIT 许可证只覆盖本项目新编写的修改逻辑、工具和文档，不构成对第三方内容的额外授权。
