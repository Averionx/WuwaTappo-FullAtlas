# 构建 1.2（官方基底 1.0.2）

在 Windows x64 上准备 Python 3.12、Node.js 22+、Inno Setup 7，并安装：

```powershell
python -m pip install -r requirements-build.txt
```

另外准备以下未提交到仓库的输入：

1. 官方 1.0.2 的实际 `WuwaTappo.exe`，SHA-256：`099b62be14efe2cc99bb0ad3d37860488c42fb0f4e6282b5687e6335ab178573`。这不是下载页的外层安装器。构建器拒绝未验证的基底；1.2 的助手适配器要求 1.0.2。
2. 完整缓存目录，包含 `atlas.json`、`activity-config.json`、`offline_catalog.json`、`asset_manifest.json`、`assets/`。可运行 `python tools/prepare_cache.py inputs` 准备 `inputs/cache`；该步骤需要联网，只读取公开素材接口，不使用账号令牌。图片文件哈希在构建时逐个校验。
3. 从 [Microsoft 官方下载页](https://developer.microsoft.com/microsoft-edge/webview2/) 获取并解压的 WebView2 Fixed Version x64 运行时目录。本项目使用 `155.0.4283.62`。保留运行时全部文件及许可。

```powershell
python build.py --official "inputs\WuwaTappo.exe" --cache "inputs\cache" --runtime "inputs\runtime" --node node --iscc "C:\Program Files\Inno Setup 7\ISCC.exe"
```

构建先静态提取资源并解析 JavaScript 结构，再注入本地视图和房间及本地数据提交保护，重算脚本 CSP 哈希和 PE 校验和。程序入口由自身位置定位专用 WebView2 与用户数据目录；不含开发机固定路径。

安装时生成随机的本机控制令牌，不将构建者的控制令牌、登录目录或用户配置放入发行包。服务冻结为 `LocalGalleryHost.exe`，不要求目标机器安装 Python。

```powershell
node tests/test_controller.cjs
node tests/test_desktop_assistant.cjs
python tests/test_sync_cache.py
python -m unittest discover -s tests -p "test_desktop_*.py"
python tools/make_update.py
```

控制器测试需要先完成构建以读取 `build/payload/cache`。仅测试逻辑或缓存单元不等于通过真实网络与联机行为测试。发布前必须安装到包含空格或中文的新目录，验证本地模式、普通网络可用、房间禁止、更新入口和旧规则清理。

`build/`、`dist/` 和 `inputs/` 均不进入 Git。本地安装器输出 `dist/WuwaTappo全图鉴版-1.2-Setup.exe`。GitHub 会改写附件名中的中文，因此线上文件使用英文附件名，安装程序内部仍使用中文名称。

原地升级 ZIP 为 `dist/WuwaTappo-FullAtlas-1.2-x64-update.zip`，只含程序、服务、脚本及公共配置；排除账号目录、控制令牌、本地设置、素材缓存和运行时。发布时同时上传 `SHA256SUMS.txt`。客户端只接受本仓库的正式 Release、匹配版本清单、精确文件列表和逐文件 SHA256；不接受未知路径或覆盖用户数据的升级包。

修改版更新保留账号目录和本地状态。辅助进程在原程序正常退出后备份及替换文件，重新启动；新前端确认启动成功后清理旧程序备份。启动超时回退。官方后续版本发生结构变化时必须重新适配并发布修改版，不直接运行官方安装器覆盖修改版。
