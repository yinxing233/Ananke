# Ananke

基于存续检验（persistence-based）的三层记忆 MVP。实现严格遵循
[`Memory_Architecture_设计文档_MVP.md`](docs/Memory_Architecture_设计文档_MVP.md)：工作记忆只能经由存续得分迁入巩固层，巩固层只能经由局部重组迁入核心层。

## 运行

```bash
uv run python run.py
```

默认使用 mock LLM，因此无需 API 密钥；首次运行会下载 sentence-transformers 的本地嵌入模型。数据保存在 `data/*.jsonl`，审计事件保存在 `logs/events.jsonl`。

## 当前实现

- 三层 JSONL 存储、慢层优先检索与工作层容量淘汰
- 内部激活、非系统引导的外部验证、persistence score 与逐级迁移
- 仅在快→中迁移后触发的合并/矛盾局部重组检查
- 全链路 JSONL 操作日志
- 用 fake embedding/LLM 编写的确定性场景测试，覆盖迁移、重组、淘汰和重启恢复

## 测试与实验组

```bash
uv run pytest -q
```

默认实验组为 `Config.WORKING_PROMOTION_STRATEGY = "persistence"`：外部验证权重高于内部激活。设置为 `"frequency"` 可运行对照组；对照组只按内部激活次数（默认 3 次）将工作记忆迁入巩固层。两组共用提取、检索、容量淘汰与中→慢局部重组逻辑，以隔离快→中迁移准则的影响。
