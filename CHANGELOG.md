# 更新记录

## Unreleased

- `0001_init` 改为显式 `op.create_table` / `op.create_index`，运行期走 `alembic upgrade`
- `app/` 只依赖 `ports`，新增内存假实现用例
- 开 ruff `E2`/`E3`；CI 增加 `docker build` 与 `/health` 探活

## 1.0.0

- 账龄台账：1-30 / 31-60 / 61-90 / 90+ 四档分桶
- 客户付款画像：历史平均拖延天数决定催收档位
- 三档语气：温和 / 明确 / 最后通牒
- 数字守卫：消息里出现台账外金额或天数即丢弃
- 任务队列：失败退避重试，同一天同一档不重复发送
- webhook 推送：飞书 / 钉钉 / 企微
- CLI（`seed` / `scan` / `serve` / `doctor`）与 Web 双入口
- 40 条测试
