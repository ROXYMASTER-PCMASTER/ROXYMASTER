$scripts = "$env:USERPROFILE\desktop\roxymaster\pcbot\scripts"
Get-ChildItem "$scripts\*.py" | ForEach-Object {
    $c = Get-Content $_.FullName -Raw -Encoding UTF8
    $c = $c -replace 'from pcbot\.scripts\.\S+ import', 'from'
    $c = $c -replace 'from pcbot\.scripts import', 'import'
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($_.FullName, $c, $utf8)
}
Write-Host 'imports corregidos'