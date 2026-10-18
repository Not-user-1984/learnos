#!/bin/sh
# Служба xray: socks5:1080 из vless-ключа. Конфиг пишет сервер LearnOS в
# /etc/xray/config.json (volume ./data/xray). Здесь — цикл: старт xray,
# каждые 15с проверяем хеш конфига; изменился — перезапуск с новым.
CONF=/etc/xray/config.json
hash_file=/tmp/conf.md5

gen_default() {
  # пока ключ не задан: socks-вход → прямые соединения (чтобы healthcheck жил)
  cat > "$CONF" <<'EOF'
{
  "log": {"loglevel": "warning"},
  "inbounds": [{"port": 1080, "listen": "0.0.0.0", "protocol": "socks", "settings": {"udp": true}}],
  "outbounds": [{"protocol": "freedom"}]
}
EOF
}

[ -s "$CONF" ] || gen_default
md5sum "$CONF" > "$hash_file"

while :; do
  xray run -c "$CONF" &
  XPID=$!
  while kill -0 "$XPID" 2>/dev/null; do
    sleep 15
    md5sum "$CONF" 2>/dev/null > "$CONF.new"
    if cmp -s "$CONF.new" "$hash_file"; then
      rm -f "$CONF.new"
    else
      mv "$CONF.new" "$hash_file"
      echo "config changed, restarting xray"
      kill "$XPID" 2>/dev/null
      sleep 1
      break
    fi
  done
  wait "$XPID" 2>/dev/null
done
