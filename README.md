# wwmi-mod-repair

[![CI](https://github.com/shennian0909/wwmi-mod-repair/actions/workflows/ci.yml/badge.svg)](https://github.com/shennian0909/wwmi-mod-repair/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

为了自行适配UHD画质下使用MOD而创建的Skills。

面向具备本地文件读写能力的 AI 助手的鸣潮 WWMI Mod 修复与改造技能。根据MOD作者资源、实际绘制与计算证据定位问题，按需要配置 FrameAnalysis，保存备份并记录游戏验证。

技能保持一个入口 `$wwmi-mod-repair`，提供两种工作模式：

| 模式 | 目标与范围 |
| --- | --- |
| 常规兼容性修复（默认） | 恢复作者原有外观、动画和功能；处理 hash、绑定、检测、计算及原有变体切换失效。作者贴图和模型默认保持原样，必要资源适配须有证据。 |
| 原 Mod 改造 | 按用户明确要求改善固有穿模、补面、改变材质效果，或新增/重新设计变体及切换功能。 |

两种模式共用备份、抓取、安装和验证流程。分类依据是修复目标，技术难度或文件扩展名不决定模式。

## 使用前：选择合适的 AI

**建议使用能连接游戏所在 Windows 电脑、具备文件操作和工具调用能力的 AI 助手（Coding Agent）。** 是否适用取决于客户端实际开放的工具与权限，不能只看模型名称；把技能文本发给一个纯聊天 AI，并不会自动给它操作电脑的能力。

| 能力 | 要求与用途 |
| --- | --- |
| 读取完整技能及关联文件 | 能读取 `SKILL.md`，并按需访问 `references/` 与 `scripts/`；只加载名称、简介或单段提示词不足以执行完整流程。 |
| 本机文件读取与写入 | 自动检查、备份和安装补丁需要访问用户指定的 WWMI/Mod 目录，处理文本与二进制文件，并保留编码、原始字节和备份。权限应覆盖实际目标目录。 |
| 终端或代码执行 | 强烈建议能在访问这些文件的环境中运行命令及 Python 3.11+，并读取执行结果和错误，以使用随附的检查、哈希和补丁暂存脚本。只有隔离的云端代码沙箱不等于能修改本机文件。 |
| 联网检索并读取原始资料 | 用于核对当前版本、作者说明和疑难问题。同一问题第二次实际修订仍失败或只部分改善时，第三版前须执行技能要求的联网研究；没有此能力时应说明限制，不能声称已完成研究。 |
| 看图与多轮反馈 | 建议能查看截图、贴图预览，并结合日志和用户反馈判断。截图不能代替绘制证据；缺少视觉能力时需要用户准确描述，不能声称已目视验证。 |

仅能聊天、无法调用工具的 AI 可以讲解技能；只有上传文件或只读访问时，可以分析已提供的材料。若还具备生成文件的能力，可以交付补丁供用户安装，但不能声称已直接修复本机。运行环境缺少能力时，AI 应先说明能完成到哪一步及下一步需要什么。

游戏操作仍可由用户完成：AI 不必具备自动操控游戏的功能，但应能指导用户抓取、重载和验证，并读取反馈或抓取文件。DDS 像素统计按需安装 Pillow；模型/动画改造另需能处理相应模型、缓冲与导出格式的工具（例如适配的 Blender/WWMI 工具链），常规兼容性修复不默认要求它们。

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

安装工具只复制技能正文、参考资料、检查脚本和许可/版本信息，不安装开发依赖，不写入游戏或 Mod 目录。同内容文件不重复写入，其他本地文件保留。覆盖已有技能文件前，将其原字节保存在与目标技能目录并列的 `.<目标目录名>-backups/内容SHA-256/原相对路径` 中；保留原文件名并核对备份内容，具体路径随安装结果返回。相同内容可复用已有副本，不覆盖不同内容的备份。此安装备份与 Mod 原文件的时间后缀规则分开。

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

检查工具保持只读。别名工具生成暂存补丁，不安装补丁，也不自动证明映射正确；修复 Mod 并安装补丁前仍须完成证据与差异检查，并在待修改的 Mod 原文件旁创建时间戳备份。这条命名与存放要求仅用于 Mod 修复，不适用于 `d3dx.ini`、启动器配置、报告、脚本或其他任务；诊断配置的恢复副本保存到工作目录。

## 更新与维护

本仓库是技能源码的维护入口。更新本地仓库后再次运行安装工具，将更新同步到客户端：

```powershell
git pull --ff-only
py -3 -X utf8 tools\install_skill.py
```

有本地源码修改时先提交或保留差异，再拉取更新。安装更新不会合并安装目录中的自定义正文；被替换内容保留在独立备份目录，原有历史 `.BAK` 和其他本地文件保持原样。

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
