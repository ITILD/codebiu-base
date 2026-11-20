#!/usr/bin/env bash
# ==============================================================================
# 服务器清单自检：读取 servers.yaml，逐台测试 SSH 连通性与远端环境
#   ./check.sh                 # 检查 servers.yaml
#   ./check.sh path/to/x.yaml  # 检查指定清单
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

FILE="${1:-servers.yaml}"
[ -f "$FILE" ] || { echo "缺少 $FILE：先执行 cp servers.example.yaml servers.yaml"; exit 1; }
[ "$(stat -c %a "$FILE")" = "600" ] || echo "提示: 建议 chmod 600 $FILE（含敏感信息）"

# 找一个能 import yaml 的 python
HERE="$(pwd)"
VENV_PY="$HERE/../../../code/backend/server_py/.venv/bin/python"
[ -x "$VENV_PY" ] && VENV_PY="$(realpath "$VENV_PY")"
PY=""
for p in "$VENV_PY" python3 python; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c "import yaml" >/dev/null 2>&1; then PY="$p"; break; fi
done
[ -n "$PY" ] || { echo "需要带 PyYAML 的 python：python3 -m pip install pyyaml"; exit 1; }

# 输出: 角色 <TAB> 名称 <TAB> host <TAB> port <TAB> user <TAB> key
PARSE="$("$PY" - "$FILE" <<'PYCODE'
import os, sys, yaml
base = os.path.dirname(os.path.abspath(sys.argv[1]))
data = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
for role, s in data.items():
    if not isinstance(s, dict):
        continue
    ssh = s.get("ssh") or {}
    host = str(ssh.get("host") or s.get("ip") or "")
    port = str(ssh.get("port") or 22)
    user = str(ssh.get("user") or "root")
    key = str(ssh.get("key") or "")
    if key and not os.path.isabs(key):
        key = os.path.normpath(os.path.join(base, key))
    print("\t".join([role, str(s.get("name") or role), host, port, user, key]))
PYCODE
)"

fail=0
while IFS=$'\t' read -r role name host port user key; do
    [ -n "$host" ] || { echo "跳过 $role：未配置 host/ip"; continue; }
    opts=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 -p "$port")
    if [ -n "$key" ]; then
        [ -f "$key" ] || { echo "FAIL $role($name)：密钥不存在 $key"; fail=1; continue; }
        opts+=(-i "$key")
    fi
    if out="$(ssh "${opts[@]}" "$user@$host" 'echo ok; command -v docker >/dev/null 2>&1 && echo docker=yes || echo docker=no' 2>&1)"; then
        echo "OK   $role($name) $user@$host:$port ${out//$'\n'/ }"
    else
        echo "FAIL $role($name) $user@$host:$port -> ${out##*$'\n'}"
        fail=1
    fi
done <<< "$PARSE"

[ "$fail" = "0" ] && echo "全部通过" || echo "存在失败项"
exit "$fail"
