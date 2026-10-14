# Remove rehearsal leftovers from dist\datasheet-extractor and sync the latest code/docs into it.
$root = Split-Path $PSScriptRoot -Parent
$dist = "$root\dist\datasheet-extractor"
foreach ($d in ".venv-docling", "tools", "logs", "out") {
  if (Test-Path "$dist\$d") { Remove-Item -Recurse -Force "$dist\$d" }
}
foreach ($d in "docs", "scripts", "datasheet_extractor", "config", "golden", "tests") {
  robocopy "$root\$d" "$dist\$d" /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ | Out-Null
}
Copy-Item "$root\README.md", "$root\.gitignore" $dist -Force
$size = (Get-ChildItem $dist -Recurse -File -Force | Measure-Object Length -Sum).Sum
"dist: {0:N2} GB" -f ($size / 1GB)
Get-ChildItem $dist -Name
