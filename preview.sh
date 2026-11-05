#!/usr/bin/env bash
# 一键构建并预览网站。用法：bash preview.sh，也可以在资源管理器里双击。按 Ctrl+C 停止预览。

PORT=${PORT:-8000} # 8000 被占用时可以换端口：PORT=8001 bash preview.sh
URL="http://localhost:$PORT"

export PYTHONUTF8=1 # 否则 Git Bash 里中文提示会乱码

# 双击运行时窗口会立刻关闭，出错要停一下才能看到原因
fail() {
  echo
  echo "$1"
  read -r -p "按回车键关闭..."
  exit 1
}

cd "$(dirname "$0")" || fail "找不到项目文件夹"

python build.py || fail "构建失败，请看上面的错误信息"

# 预览已经在运行时，它读的就是刚生成的 _site，不用再开一个（Windows 上重复开也不会报错）
if (exec 3<>"/dev/tcp/localhost/$PORT") 2>/dev/null; then
  echo "端口 $PORT 已有服务在运行，网站已重新构建，直接打开：$URL"
  start chrome "$URL"
  read -r -t 3 -p "3 秒后自动关闭此窗口..."
  exit 0
fi

echo "预览地址：$URL （按 Ctrl+C 停止）"
(
  sleep 1 # 等服务启动
  start chrome "$URL"
) &
python -m http.server "$PORT" -d _site || fail "预览服务启动失败，请看上面的错误信息"
