#!/bin/sh
set -eu
# 只停止本轮独立观察器；保留记录，不触碰原厂或引闪服务。
systemctl stop hbl-event-observer.service
test ! -L /run/systemd/system/hbl-event-observer.service
rm -f /run/systemd/system/hbl-event-observer.service
systemctl daemon-reload
