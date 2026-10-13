# 部署：veriplan.yikuaibanz.cn

服务器：`ssh banzi`（49.233.252.47，Ubuntu 24.04，ubuntu 用户 + sudo）。80/443 由 **Caddy** 托管，同机还有 api / pi / pandeflow / jev 等站点——只动 VeriPlan 自己的东西。

- 代码：`/opt/veriplan`（rsync，排除 .git/.venv/node_modules/docs/artifacts/*.db）
- 后端：`veriplan.service`（系统用户 veriplan，127.0.0.1:9195），环境变量 `/opt/veriplan/.env`（600，仅 DEEPSEEK/TAVILY key + 现场配置）
- 数据：`/opt/veriplan/data/veriplan.db`
- Caddy：`/etc/caddy/Caddyfile` 末尾追加 `deploy/veriplan.caddy`（basic_auth 全站；改前备份为 `Caddyfile.pre-veriplan-<时间>`；`caddy validate` 通过后 `systemctl reload caddy`）

## 重新部署

```sh
cd frontend && npm run build && cd ..
rsync -az --delete --exclude=.env --exclude=data --exclude=.git --exclude=.venv --exclude=node_modules --exclude='*.db' --exclude=docs --exclude=artifacts ./ banzi:/opt/veriplan/
ssh banzi 'cd /opt/veriplan/backend && .venv/bin/pip install -q -e . && sudo systemctl restart veriplan'
```

注意 rsync `--delete` 不会删掉服务器上的 `.env`（被排除规则之外但本地不存在时会被删！）——重部署时加 `--exclude=.env`。
