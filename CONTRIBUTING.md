# Contributing

感谢你改进 Awesome Agent Engineering。这个仓库优先接受能够让课程更准确、更容易运行、更容易验证的改动。

## 适合贡献的内容

- 课程勘误、失效链接和跨平台运行修复
- 不改变课程主线的模型适配与降级实现
- 能复现的评估、消融实验和失败案例
- 作品项目的测试、安全性与可观测性改进

新增整门课程或引入新的核心框架前，请先创建 Issue 说明学习目标、与现有路线的关系及维护成本。

## 本地验证

```bash
python quickstart.py
python -m pytest portfolio-projects/knowledge-base-qa/tests -q
python -m pytest portfolio-projects/research-assistant/tests -q
```

只修改单节课程时，至少运行该课程的 `code.py`，并在 Pull Request 中说明是否调用了真实 API。不要提交 `.env`、API Key、本地数据库、浏览器配置或未经脱敏的运行数据。

## Pull Request

1. 保持改动聚焦，一个 Pull Request 解决一个问题。
2. 说明当前行为、改动原因、验证命令和结果。
3. 用户可见行为变化需要同步更新中英文入口文档。
4. 新功能应提供测试；依赖外部 API 的测试必须有 mock 或明确的跳过条件。
5. 不要把环境相关的评估数字描述为通用生产结论。

提交 Pull Request 即表示你同意贡献内容按仓库的 [MIT License](LICENSE) 发布。
