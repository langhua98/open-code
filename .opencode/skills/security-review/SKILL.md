---
name: security-review
description: 检查仓库的安全问题：泄露的密钥和 token、危险的代码写法、不安全的配置。用户说"安全检查""有没有泄露密钥""安全审查"，或者准备把代码公开、部署之前使用。
---

# 安全检查

1. **泄露的密钥**：当前文件和 git 历史都要查。
   - `git grep -nIE 'KGAT_|ghp_|gho_|github_pat_|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|[0-9]{8,10}:[A-Za-z0-9_-]{35}|-----BEGIN [A-Z ]*PRIVATE KEY'`
   - `git log -p --all | grep -nIE '<同一个表达式>' | head`
   - 找到后不要在回复里写出完整的值，只说文件和行号（或提交号）。告诉用户：马上去对应网站重新生成这个密钥，新的放进 Codespaces Secrets，用环境变量读取。只从代码里删掉是不够的，git 历史里还有。
2. **危险写法**：
   - 用户输入拼进命令：`os.system`、`subprocess(..., shell=True)`。
   - `eval`、`exec`、`pickle.load` 处理不可信的数据。
   - SQL 用字符串拼接，没用参数。
   - 关掉证书验证：`verify=False`。
   - 机器人或接口没检查是谁发来的请求，任何人都能触发管理操作。
3. **配置**：`.gitignore` 是否忽略 `.env` 和密钥文件；密钥是否都从环境变量读取；端口是否被设成了公开。
4. **依赖**：需要的话运行 `pip install pip-audit && pip-audit`，查已知漏洞。
5. 回复：先用一句话给结论，再按严重程度列问题（位置、风险、怎么修）。
