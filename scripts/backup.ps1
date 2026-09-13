# Back up committed SQLite data, including WAL. Keep backups until explicitly removed.
param([string]$DatabasePath = "", [string]$BackupDirectory = "")
$projectRoot = Split-Path -Parent $PSScriptRoot
if (!$DatabasePath) { $DatabasePath = Join-Path $projectRoot "backend/shijian.db" }
if (!$BackupDirectory) { $BackupDirectory = Join-Path $projectRoot "backups" }
python (Join-Path $PSScriptRoot "backup_sqlite.py") $DatabasePath --output-dir $BackupDirectory
if ($LASTEXITCODE -ne 0) { throw "SQLite backup failed" }
