# 构建 1.3.9（官方基底 1.0.5）

在 Windows x64 上准备 Python 3.12、Node.js 22+、Inno Setup 7，并安装：

```powershell
python -m pip install -r requirements-build.txt
```

另外准备以下未提交到仓库的输入：

1. 官方 1.0.5 安装包内的主程序 `WuwaTappo.exe`，SHA-256 为 `06a7222645e5da3a86baeaea3bb61a1f63c0408df1e21d5b985a9eb01054b7ae`。通过文件属性核对产品名称为 Wuwa Tappo，产品版本为 1.0.5。构建器按哈希拒绝未知基底。
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

`build/`、`dist/` 和 `inputs/` 均不进入 Git。本地安装器输出 `dist/WuwaTappo全图鉴版-1.3.9-Setup.exe`。线上文件使用英文附件名，安装程序使用中文名称。

原地升级 ZIP 为 `dist/WuwaTappo-FullAtlas-1.3.9-x64-update.zip`，包含程序、服务、脚本及公共配置。发布时同时上传 `SHA256SUMS.txt`。客户端核对正式 Release 的版本清单、文件列表与每个文件的 SHA-256。

修改版更新保留账号目录和本地状态。辅助进程在原程序正常退出后备份及替换文件，重新启动；新前端确认启动成功后清理旧程序备份。启动超时回退。官方后续版本发生结构变化时必须重新适配并发布修改版，不直接运行官方安装器覆盖修改版。

单文件绿色版：完成基础 payload 构建后运行 python tools/build_portable.py。只纳入公开程序、运行库和缓存；不纳入 host 副本、旧缓存、账号或本机配置。首次启动解压到 EXE 旁的 WuwaTappoPortableData。
完成四种包后运行 python tools/make_checksums.py 生成校验清单。
