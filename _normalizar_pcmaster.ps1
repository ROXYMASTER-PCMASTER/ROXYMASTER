$scriptsDir = "$env:USERPROFILE\Desktop\roxymaster\pcmaster\scripts"
$archivos = Get-ChildItem -Path $scriptsDir -Filter *.py
foreach ($f in $archivos) {
    $contenido = Get-Content $f.FullName -Raw
    $nuevo = $contenido -replace 'ROXYMASTER', 'roxymaster' -replace 'PCMASTER', 'pcmaster' -replace 'PCBOT', 'pcbot'
    if ($nuevo -ne $contenido) {
        $nuevo | Set-Content -Path $f.FullName -Encoding UTF8
        Write-Host "Corregido: $($f.Name)"
    }
}
$bats = Get-ChildItem -Path "$env:USERPROFILE\Desktop\roxymaster\pcmaster" -Filter *.bat
foreach ($b in $bats) {
    $contenido = Get-Content $b.FullName -Raw
    $nuevo = $contenido -replace 'ROXYMASTER', 'roxymaster' -replace 'PCMASTER', 'pcmaster' -replace 'PCBOT', 'pcbot'
    if ($nuevo -ne $contenido) {
        $nuevo | Set-Content -Path $b.FullName -Encoding ASCII
        Write-Host "Corregido: $($b.Name)"
    }
}
Write-Host "Normalizacion pcmaster completada."