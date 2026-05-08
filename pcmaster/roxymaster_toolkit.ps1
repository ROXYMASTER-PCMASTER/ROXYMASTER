$base="C:\Users\PCMASTER\Desktop\roxymaster\pcmaster"
$out="$env:USERPROFILE\Desktop\roxymaster_report"

New-Item -ItemType Directory -Force -Path $out | Out-Null

# 1. archivos grandes
Get-ChildItem -Recurse -Filter *.py |
ForEach-Object {
    $l=(Get-Content $_.FullName).Count
    if($l -gt 400){
        "$($_.FullName) | $l"
    }
} > "$out\big_files.txt"

# 2. async riesgos
Select-String -Path "$base\**\*.py" -Pattern "while True|create_task|global " `
> "$out\async_risks.txt"

# 3. websocket/db
Select-String -Path "$base\**\*.py" -Pattern "websocket|sqlite|commit|cursor" `
> "$out\runtime_risks.txt"

# 4. resumen
"ROXYMASTER TOOLKIT DONE" > "$out\status.txt"

Write-Host "toolkit ejecutado -> $out"