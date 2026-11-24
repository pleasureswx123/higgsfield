#!/bin/sh
# 正式库备份写入数据盘，并在受限 NAS 目录放置一份。
set -eu
umask 077
mountpoint -q /mnt/data
mountpoint -q /mnt/higgsfield
local_dir=/mnt/data/higgsfield/backups
nas_dir=/mnt/higgsfield/NightmareTheatre/prod/.platform/database-backups
mkdir -p "$local_dir" "$nas_dir"
name="higgsfield-$(date -u +%Y%m%dT%H%M%SZ).dump"
tmp=$(mktemp "$local_dir/.backup.XXXXXXXX")
trap 'rm -f "$tmp"' EXIT
docker exec higgsfield-prod-postgres-1 pg_dump -U higgsfield -Fc higgsfield_prod > "$tmp"
docker exec -i higgsfield-prod-postgres-1 pg_restore -l < "$tmp" > /dev/null
mv "$tmp" "$local_dir/$name"
cp "$local_dir/$name" "$nas_dir/.$name.tmp"
cmp "$local_dir/$name" "$nas_dir/.$name.tmp"
mv "$nas_dir/.$name.tmp" "$nas_dir/$name"
