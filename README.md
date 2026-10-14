# wwmi-mod-repair

[![CI](https://github.com/shennian0909/wwmi-mod-repair/actions/workflows/ci.yml/badge.svg)](https://github.com/shennian0909/wwmi-mod-repair/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

面向具备本地文件读写能力的 AI 助手的鸣潮 WWMI Mod 修复与改造技能。根据作者资源、实际绘制与计算证据定位问题，按需要配置 FrameAnalysis，保存备份并记录游戏验证。

技能保持一个入口 `$wwmi-mod-repair`，提供两种工作模式：

| 模式 | 目标与范围 |
| --- | --- |
| 常规兼容性修复（默认） | 恢复作者原有外观、动画和功能；处理 hash、绑定、检测、计算及原有变体切换失效。作者贴图和模型默认保持原样，必要资源适配须有证据。 |
| 原 Mod 改造 | 按用户明确要求改善固有穿模、补面、改变材质效果，或新增/重新设计变体及切换功能。 |

两种模式共用备份、抓取、安装和验证流程。分类依据是修复目标，技术难度或文件扩展名不决定模式。

## 安装

需要 Python 3.11+。核心检查与补丁暂存脚本仅使用标准库；选择 DDS 像素统计时需要 Pillow，支持的 DDS 格式仍需按实际文件核对。

在 Windows PowerShell 中克隆项目并安装到默认的 Codex 技能目录：

```powershell
git clone https://github.com/shennian0909/wwmi-mod-repair.git
Set-Location -LiteralPath .\wwmi-mod-repair
py -3 -X utf8 tools\install_skill.py
```

默认目标为 `CODEX_HOME/skills/wwmi-mod-repair`；没有设置 `CODEX_HOME` 时使用用户目录下的 `.codex/skills/wwmi-mod-repair`。其他支持文件技能的客户端可以指定其技能目录：

```powershell
py -3 -X utf8 tools\install_skill.py --dest "目标技能目录\wwmi-mod-repair"
```

也可以从 [Releases](https://github.com/shennian0909/wwmi-mod-repair/releases) 下载 ZIP，将其中的 `wwmi-mod-repair` 文件夹放入客户端支持的技能目录。客户端如何重新加载技能，以该客户端的实际行为为准。

安装工具只复制技能正文、参考资料、检查脚本和许可/版本信息，不安装开发依赖，不写入游戏或 Mod 目录。同内容文件不重复写入，其他本地文件保留；覆盖已有文件前在该文件旁创建 `原文件名 YYYY-MM-DD HH-mm-ss.BAK`，并核对备份哈希。

## 使用

常规修复请求示例：

```text
使用 $wwmi-mod-repair 检查我指定的鸣潮 Mod。
异常：头发有色块，大世界和角色界面都有。
Mod 路径：请填写实际目录。
根据实际需求取证并集中修复，保留抓取并提醒我自行清理。
```

改造请求示例：

```text
使用 $wwmi-mod-repair 改善指定 Mod 原模型的裙摆穿模。
允许调整必要的模型/动画数据，保留裙长、配色和原有切换功能。
Mod 路径、异常动作和允许修改范围：请填写实际信息。
```

技能的完整规则见 [SKILL.md](SKILL.md)。它指导 AI 完成诊断和修复，不会仅凭一个目录自动保证所有 Mod 可用。抓取由用户操作游戏，文件验证与游戏画面验证分别记录。

## 可独立运行的检查工具

```powershell
py -3 -X utf8 scripts\inspect_wwmi.py mod --path "实际Mod目录" --out "新报告.json"
py -3 -X utf8 scripts\inspect_wwmi.py capture --path "实际抓取目录" --mod-fragment "目标Mod目录名"
py -3 -X utf8 scripts\stage_texture_aliases.py --ini "实际mod.ini" --mapping "已取证的映射.json" --out-dir "加载目录之外的新暂存目录"
```

检查工具保持只读。别名工具生成暂存补丁，不安装补丁，也不自动证明映射正确；实际安装前仍须完成证据与差异检查，以及原文件旁的时间戳备份。

## 更新与维护

本仓库是技能源码的维护入口。更新本地仓库后再次运行安装工具，将更新同步到客户端：

```powershell
git pull --ff-only
py -3 -X utf8 tools\install_skill.py
```

有本地源码修改时先提交或保留差异，再拉取更新。安装更新不会合并安装目录中的自定义正文，旧内容会在被覆盖的文件旁保留为 `.BAK`。

开发检查：

```powershell
py -3 -m pip install -r requirements-dev.txt
py -3 -X utf8 tools\check_project.py
py -3 -X utf8 -m unittest discover -s tests -v
py -3 -X utf8 tools\package_skill.py --out-dir dist
```

GitHub Actions 在提交和 Pull Request 时执行检查与测试。维护者更新 `VERSION` 和 `CHANGELOG.md` 后推送对应 `v版本号` 标签，发布流程会重新检查并生成带 SHA-256 清单的技能 ZIP。

贡献方式和发布步骤见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 项目内容

- `SKILL.md`：两种模式和共用规则。
- `references/`：材质、抓取、表情、改造及交接方法。
- `scripts/`：只读检查与纹理别名暂存工具。
- `agents/`：客户端技能元数据。
- `tools/`、`tests/`：安装、项目校验、打包及回归检查。

仓库与发布包不包含游戏/Mod 资源、原始抓取、个人路径、凭据或历史备份。实际 FrameAnalysis 抓取由使用者保留，确认不再需要后自行清理。

## 许可

本项目技能文本和脚本使用 [MIT](LICENSE) 许可。外部参考资料、游戏和第三方 Mod 资源的权利归各自权利人。
