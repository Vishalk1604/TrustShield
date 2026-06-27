# TrustShield — stop the local services (frees ports 8001 / 8002 / 5173).
foreach ($port in 8001, 8002, 5173) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        $conns.OwningProcess | Select-Object -Unique | ForEach-Object {
            try { Stop-Process -Id $_ -Force -ErrorAction Stop; Write-Host ("stopped PID {0} on :{1}" -f $_, $port) -ForegroundColor Green }
            catch { }
        }
    } else {
        Write-Host ("nothing listening on :{0}" -f $port) -ForegroundColor DarkGray
    }
}
