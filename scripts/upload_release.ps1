# Upload files to a GitHub release with a progress bar (creates the release if missing). Needs `gh auth login` once.
# Skips files already uploaded with the same size; deletes half-uploaded leftovers first, so it can be re-run after an interruption.
#
#   powershell -ExecutionPolicy Bypass -File scripts\upload_release.ps1 -Tag models-v1 -Files dist\github_release\SHA256SUMS.txt,dist\github_release\models-docling.zip.*
#   powershell -ExecutionPolicy Bypass -File scripts\upload_release.ps1 -Tag compare-results-v1 -Title "Compare results v1" -Files dist\github_release_results\*
param(
  [Parameter(Mandatory = $true)][string]$Tag,
  [Parameter(Mandatory = $true)][string[]]$Files,
  [string]$Title = "",
  [string]$Notes = "",
  [switch]$Latest,   # 新 release 是否標成 Latest（預設否，models-v1 保持 Latest）
  [string]$Repo = "FrankHsu327/DatasheetExtract-",
  [string]$Gh = "C:\Program Files\GitHub CLI\gh.exe"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
New-Item -ItemType Directory -Force logs | Out-Null
$log = "$root\logs\upload_release.log"
function Log($m) { $m | Out-File $log -Append; Write-Host $m }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
if (-not (Test-Path $Gh)) { $Gh = "gh" }

# powershell -File 會把 "a,b" 當成一個字串傳進來，自行拆開
$items = $Files | ForEach-Object { $_ -split "," } | Where-Object { $_ } | ForEach-Object { Get-ChildItem $_.Trim() -File } | Sort-Object Name
if (-not $items) { throw "no files match: $Files" }

$rel = & $Gh api "repos/$Repo/releases" --jq ".[] | select(.tag_name==\`"$Tag\`") | .id" | Select-Object -First 1
if (-not $rel) {
  if (-not $Title) { $Title = $Tag }
  & $Gh release create $Tag -R $Repo --target main --title $Title --notes $Notes "--latest=$($Latest.IsPresent.ToString().ToLower())" | Out-Null
  $rel = & $Gh api "repos/$Repo/releases" --jq ".[] | select(.tag_name==\`"$Tag\`") | .id" | Select-Object -First 1
  Log "created release $Tag"
}
$assets = & $Gh api "repos/$Repo/releases/$rel/assets?per_page=100" | ConvertFrom-Json
$token = (& $Gh auth token).Trim()   # 只在記憶體中使用，不印出

function Remove-Partial($name) {
  $a = & $Gh api "repos/$Repo/releases/$rel/assets?per_page=100" | ConvertFrom-Json
  $a | Where-Object { $_.name -eq $name } | ForEach-Object {
    & $Gh api -X DELETE "repos/$Repo/releases/assets/$($_.id)" | Out-Null; Log "removed partial $name"
  }
}

function Send-File($f, $i) {
  $req = [Net.HttpWebRequest]::Create("https://uploads.github.com/repos/$Repo/releases/$rel/assets?name=$([Uri]::EscapeDataString($f.Name))")
  $req.Method = "POST"
  $req.Headers.Add("Authorization", "Bearer $token")
  $req.Accept = "application/vnd.github+json"
  $req.UserAgent = "datasheet-extractor-upload"
  $req.ContentType = "application/octet-stream"
  $req.ContentLength = $f.Length
  $req.AllowWriteStreamBuffering = $false
  $req.Timeout = [Threading.Timeout]::Infinite
  $req.ReadWriteTimeout = 600000
  $in = [IO.File]::OpenRead($f.FullName)
  $buf = New-Object byte[] (4MB)
  $sent = 0L; $t0 = Get-Date; $lastPct = -1; $lastLog = -10
  try {
    $out = $req.GetRequestStream()
    while (($n = $in.Read($buf, 0, $buf.Length)) -gt 0) {
      $out.Write($buf, 0, $n); $sent += $n
      $pct = [int](100 * $sent / [Math]::Max(1, $f.Length))
      if ($pct -ne $lastPct) {
        $sec = ((Get-Date) - $t0).TotalSeconds
        $mbs = if ($sec -gt 0) { $sent / 1MB / $sec } else { 0 }
        $eta = if ($mbs -gt 0) { [TimeSpan]::FromSeconds(($f.Length - $sent) / 1MB / $mbs).ToString("hh\:mm\:ss") } else { "?" }
        $bar = ("#" * [int]($pct / 2.5)).PadRight(40, ".")
        Write-Progress -Activity "File $i of $($items.Count): $($f.Name)" -Status ("{0}%  {1:N0} / {2:N0} MB  {3:N1} MB/s  ETA {4}" -f $pct, ($sent / 1MB), ($f.Length / 1MB), $mbs, $eta) -PercentComplete $pct
        Write-Host ("`r[{0}] {1,3}%  {2,6:N0}/{3:N0} MB  {4:N1} MB/s  ETA {5}  " -f $bar, $pct, ($sent / 1MB), ($f.Length / 1MB), $mbs, $eta) -NoNewline
        if ($pct -ge $lastLog + 10) { ("  {0} {1}%" -f $f.Name, $pct) | Out-File $log -Append; $lastLog = $pct - ($pct % 10) }
        $lastPct = $pct
      }
    }
    $out.Close(); $in.Close()
    $resp = $req.GetResponse(); $resp.Close()
  } catch {
    $in.Close(); Write-Host ""
    $msg = $_.Exception.Message
    # 伺服器提前回應錯誤時，讀出它的訊息（比 .NET 的 "concurrent IO" 訊息有用）
    try { $r = $req.GetResponse() } catch [Net.WebException] { if ($_.Exception.Response) { $msg += " | server: " + (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() } } catch {}
    Log "  attempt failed $($f.Name): $msg"
    return $false
  }
  Write-Host ""
  Write-Progress -Activity "File $i" -Completed
  return $true
}

$i = 0
foreach ($f in $items) {
  $i++
  $old = $assets | Where-Object { $_.name -eq $f.Name }
  if ($old -and $old.state -eq "uploaded" -and $old.size -eq $f.Length) { Log "skip $($f.Name) (already uploaded)"; continue }
  $ok = $false
  foreach ($try in 1..3) {
    Remove-Partial $f.Name
    Log "upload $($f.Name)  try $try  $(Get-Date -Format s)"
    if (Send-File $f $i) { $ok = $true; break }
    Start-Sleep -Seconds (30 * $try)
  }
  if (-not $ok) { Log "UPLOAD FAILED $($f.Name) after 3 tries (run the same command again to resume)"; exit 1 }
  Log "  done $(Get-Date -Format s)"
}
& $Gh release edit $Tag -R $Repo --draft=false | Out-Null
$v = & $Gh release view $Tag -R $Repo --json url,assets --jq '.url, (.assets[] | .name + \"  \" + (.size|tostring) + \"  \" + .state)'
$v | ForEach-Object { Log $_ }
Log "UPLOAD DONE"
