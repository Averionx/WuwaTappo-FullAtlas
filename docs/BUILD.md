# 构建 1.0

在 Windows x64 上准备 Python 3.12、Node.js 22+、Inno Setup 7，并安装：

```powershell
python -m pip install -r requirements-build.txt
```

另外准备以下未提交到仓库的输入：

1. 官方 1.0.1 的 `WuwaTappo.exe`，SHA-256：`dd340c92a7320d1ecf3697ba65b4ad23d8f196acb547d2baf3f75ba09d696d97`。构建器拒绝其他版本。
2. 完整缓存目录，包含 `atlas.json`、`activity-config.json`、`offline_catalog.json`、`asset_manifest.json`、`assets/`。可运行 `python tools/prepare_cache.py inputs` 准备 `inputs/cache`；该步骤需要联网，只读取公开素材接口，不使用账号令牌。图片文件哈希在构建时逐个校验。
3. 从 [Microsoft 官方下载页](https://developer.microsoft.com/microsoft-edge/webview2/) 获取并解压的 WebView2 Fixed Version x64 运行时目录。1.0 使用 `155.0.4283.62`。保留运行时全部文件及许可。

```powershell
python build.py --official "inputs\WuwaTappo.exe" --cache "inputs\cache" --runtime "inputs\runtime" --node node --iscc "C:\Program Files\Inno Setup 7\ISCC.exe"
```

构建先静态提取资源并解析 JavaScript 结构，再注入本地视图和离线网络限制，重算脚本 CSP 哈希和 PE 校验和。程序入口由自身位置定位专用 WebView2 与用户数据目录；不含开发机固定路径。

安装时生成随机的本机控制令牌，不将构建者的控制令牌、登录目录或用户配置放入发行包。服务冻结为 `LocalGalleryHost.exe`，不要求目标机器安装 Python。

```powershell
node tests/test_controller.cjs
python tests/test_sync_cache.py
```

控制器测试需要先完成构建以读取 `build/payload/cache`。仅测试逻辑或缓存单元不等于通过系统防火墙实测。发布前必须安装到包含空格或中文的新目录，验证本地模式、普通模式、更新入口和卸载清理。

`build/`、`dist/` 和 `inputs/` 均不进入 Git。将 `dist/WuwaTappo全图鉴版-1.0-Setup.exe` 及其 SHA-256 清单作为 `v1.0` Release 附件上传。
