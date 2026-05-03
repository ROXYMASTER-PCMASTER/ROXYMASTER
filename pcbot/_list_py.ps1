$base = "$env:USERPROFILE\desktop\roxymaster\pcbot\scripts"
$files = Get-ChildItem -Recurse -Path $base -Filter "*.py"
foreach ($f in $files) {
    $name = $f.FullName
    if ($name -notmatch "_backup") {
        Write-Output $name
    }
}