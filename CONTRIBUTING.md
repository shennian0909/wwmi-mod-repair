# 维护与贡献

技能正文和参考资料直接在本仓库维护。`scripts/` 为运行时辅助工具；`tools/` 和 `tests/` 用于项目维护。两种工作模式、Mod 修复时的原文件备份以及保留抓取的规则应保持一致。时间后缀备份不是技能维护或其他任务的全局规范。

## 提交改动

1. 说明要恢复的原有行为或明确的改造目标，限定受影响的范围。
2. 先利用作者资源和实际执行证据。案例 hash 只用于解释判断方法，不作为所有版本通用补丁。
3. 修改技能源码时用 Git 提交或工作目录副本保留可恢复状态；不要套用仅面向 Mod 原文件的同目录时间后缀备份规则。安装工具将被替换技能文件保存在独立备份目录。
4. 运行项目校验和与改动有关的测试。脚本行为变化增加有意义的回归检查；文档修改检查规则一致性和引用即可。
5. 提交清晰的改动说明。明确区分文件、抓取和用户游戏验证，保留真实反馈范围。

```powershell
py -3 -m pip install -r requirements-dev.txt
py -3 -X utf8 tools\check_project.py
py -3 -X utf8 -m unittest discover -s tests -v
```

## 报告问题

使用 Issue 模板说明环境、异常部位、场景/形态和已完成的步骤。提交必要且已脱敏的配置或日志片段；原始抓取和第三方资源由使用者本地保留。涉及作者资源时提供原发布页链接，避免把其他 Mod 的贴图作为修复依据。

## 发布新版本

先更新 `VERSION` 与 `CHANGELOG.md`，校验并提交，再推送与版本文件一致的标签：

```powershell
git add VERSION CHANGELOG.md
git commit -m "Prepare release"
git push origin main
$wwmiVersion = (Get-Content -LiteralPath VERSION -Raw).Trim()
git tag "v$wwmiVersion"
git push origin "v$wwmiVersion"
```

`release.yml` 会检查版本与标签、执行测试并创建 Release，附上最小技能 ZIP 和 SHA-256 清单。发布包只包含技能运行文件、许可、版本及文件哈希清单，省略本机备份、开发文件和抓取。

修改默认行为或任务边界时在更新记录中说明影响；保留仍有效的用户授权、验证边界和恢复方式。
