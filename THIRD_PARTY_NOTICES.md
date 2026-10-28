# 第三方组件声明

本项目复用了以下组件源文件，并按业务交互作了适配。此声明保留上游许可信息，不为整个项目另行指定开源许可证。

| 来源 | 目录 | 上游许可 |
| --- | --- | --- |
| [Vercel AI Elements](https://github.com/vercel/ai-elements) | `apps/web/src/components/ai-elements/` | Apache-2.0，见 [上游声明](licenses/ai-elements-LICENSE) 和 [许可全文](licenses/Apache-2.0.txt) |
| [shadcn/ui](https://github.com/shadcn-ui/ui) | `apps/web/src/components/ui/` | MIT，见 [许可全文](licenses/shadcn-ui-LICENSE.md) |

AI Elements 组件的适配包括本项目提示词输入、语音输入、工具/任务展示和文件树等交互。shadcn 组件按项目主题及布局组合使用。模型、数据库、框架和其他依赖的具体版本以 Python / pnpm 锁文件为准，其许可仍由各上游项目规定。

小马图标来自作者的个人简历项目；演示制度与业务数据为本作业准备的虚构资料。默认不把模型密钥、私有文档、登录凭据或运行快照作为分发内容。
