# 备份 SQLite 数据库
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = "D:\_TTS-Studio_Claude-Trae_\shijian-v2\backups"
$dbPath = "D:\_TTS-Studio_Claude-Trae_\shijian-v2\backend\shijian.db"

if (!(Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

$backupFile = Join-Path $backupDir "shijian-$timestamp.db"
Copy-Item $dbPath $backupFile
Write-Host "Backup created: $backupFile"

# 清理 7 天前的备份
$cutoff = (Get-Date).AddDays(-7)
Get-ChildItem $backupDir -Filter "shijian-*.db" | Where-Object { $_.LastWriteTime -lt $cutoff } | Remove-Item -Force
Write-Host "Old backups cleaned."
