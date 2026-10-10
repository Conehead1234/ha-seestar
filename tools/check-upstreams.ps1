[CmdletBinding()]
param(
    [switch]$NoFetch,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$driverUrl = "https://github.com/smart-underworld/seestar_alp.git"
$reviewedDriverTag = "v3.2.2"
$addOnUpstreamPattern = "github\.com[/:]jaxzin/ha-seestar(?:\.git)?$"

function Invoke-RepoGit {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $output = @(& git -C $repoRoot @Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
    return $output
}

function Get-RemoteUrl {
    param([Parameter(Mandatory)][string]$Name)

    return (Invoke-RepoGit @("remote", "get-url", $Name) | Select-Object -First 1)
}

$remoteNames = @(Invoke-RepoGit @("remote"))
$remoteDetails = @(
    foreach ($name in $remoteNames) {
        [pscustomobject]@{
            name = $name
            url = Get-RemoteUrl $name
        }
    }
)

$upstreamRemote = $remoteDetails |
    Where-Object { $_.url -match $addOnUpstreamPattern } |
    Select-Object -First 1
if ($null -eq $upstreamRemote) {
    throw "No remote points to jaxzin/ha-seestar; add it as 'upstream' first."
}

$personalRemote = $remoteDetails |
    Where-Object { $_.url -notmatch $addOnUpstreamPattern } |
    Select-Object -First 1

if (-not $NoFetch) {
    Invoke-RepoGit @("fetch", "--prune", $upstreamRemote.name, "main") | Out-Null
}

$upstreamRef = "$($upstreamRemote.name)/main"
$branch = (Invoke-RepoGit @("branch", "--show-current") | Select-Object -First 1)
$statusLines = @(Invoke-RepoGit @("status", "--porcelain"))
$countsLine = (Invoke-RepoGit @("rev-list", "--left-right", "--count", "$upstreamRef...HEAD") |
    Select-Object -First 1)
$counts = @($countsLine -split "\s+" | Where-Object { $_ })
if ($counts.Count -ne 2) {
    throw "Unexpected rev-list output: $countsLine"
}

$dockerfile = Join-Path $repoRoot "seestar/Dockerfile"
$pinMatch = Select-String -LiteralPath $dockerfile -Pattern "^ARG SEESTAR_ALP_REF=([0-9a-f]{40})$"
if ($null -eq $pinMatch) {
    throw "Could not find the immutable SEESTAR_ALP_REF in seestar/Dockerfile."
}
$driverPin = $pinMatch.Matches[0].Groups[1].Value

$driverHeadLine = @(& git ls-remote $driverUrl HEAD) | Select-Object -First 1
if ($LASTEXITCODE -ne 0 -or -not $driverHeadLine) {
    throw "Could not read seestar_alp HEAD."
}
$driverHead = ($driverHeadLine -split "\s+")[0]

$tagLines = @(& git ls-remote --tags --refs $driverUrl "refs/tags/v*")
if ($LASTEXITCODE -ne 0) {
    throw "Could not read seestar_alp tags."
}
$tagRows = @(
    foreach ($line in $tagLines) {
        if ($line -match "^([0-9a-f]{40})\s+refs/tags/(v\d+\.\d+\.\d+)$") {
            [pscustomobject]@{
                sha = $Matches[1]
                tag = $Matches[2]
                version = [version]$Matches[2].Substring(1)
            }
        }
    }
)
$latestTag = $tagRows | Sort-Object version -Descending | Select-Object -First 1

$compareStatus = "same"
$driverCommitsAhead = 0
if ($driverHead -ne $driverPin) {
    $compareStatus = "unavailable"
    $driverCommitsAhead = $null
    try {
        $compareUri = "https://api.github.com/repos/smart-underworld/seestar_alp/compare/$driverPin...$driverHead"
        $compare = Invoke-RestMethod -Uri $compareUri -Headers @{ "User-Agent" = "ha-seestar-upstream-check" }
        $compareStatus = [string]$compare.status
        $driverCommitsAhead = [int]$compare.ahead_by
    }
    catch {
        # HEAD/tag comparison is still useful when the GitHub compare API is
        # temporarily unavailable or rate-limited.
    }
}

$actions = [System.Collections.Generic.List[string]]::new()
if ($statusLines.Count -gt 0) {
    $actions.Add("Commit or stash unrelated working-tree changes before merging upstream.")
}
if ([int]$counts[0] -gt 0) {
    $actions.Add("Review and merge $($counts[0]) new ha-seestar upstream commit(s).")
}
if ($null -eq $personalRemote) {
    $actions.Add("Create a personal GitHub fork and configure origin/upstream remotes; the local branch currently has no push-safe fork.")
}
if ($driverHead -ne $driverPin) {
    if ($null -ne $latestTag -and $latestTag.tag -eq $reviewedDriverTag) {
        $actions.Add("seestar_alp main moved beyond the pin, but the latest release remains $reviewedDriverTag; review only and keep the immutable pin unless a tested commit is required.")
    }
    else {
        $actions.Add("Review the newer seestar_alp release/commit before changing SEESTAR_ALP_REF; never follow main automatically.")
    }
}
if ($actions.Count -eq 0) {
    $actions.Add("No upstream action is currently required.")
}

$report = [ordered]@{
    checked_at_utc = [DateTime]::UtcNow.ToString("o")
    branch = $branch
    working_tree_clean = ($statusLines.Count -eq 0)
    addon = [ordered]@{
        upstream_remote = $upstreamRemote.name
        upstream_url = $upstreamRemote.url
        upstream_ref = $upstreamRef
        commits_behind = [int]$counts[0]
        local_commits_ahead = [int]$counts[1]
        personal_remote = if ($null -eq $personalRemote) { $null } else { $personalRemote.name }
        personal_remote_url = if ($null -eq $personalRemote) { $null } else { $personalRemote.url }
    }
    driver = [ordered]@{
        pinned_sha = $driverPin
        upstream_head_sha = $driverHead
        compare_status = $compareStatus
        commits_ahead_of_pin = $driverCommitsAhead
        reviewed_release_tag = $reviewedDriverTag
        latest_release_tag = if ($null -eq $latestTag) { $null } else { $latestTag.tag }
        latest_release_sha = if ($null -eq $latestTag) { $null } else { $latestTag.sha }
    }
    actions = @($actions)
}

if ($Json) {
    $report | ConvertTo-Json -Depth 6
    exit 0
}

Write-Output "ha-seestar upstream check"
Write-Output "  Branch:              $branch"
Write-Output "  Working tree clean:  $($report.working_tree_clean)"
Write-Output "  Add-on upstream:     $upstreamRef"
Write-Output "  Behind / ahead:      $($report.addon.commits_behind) / $($report.addon.local_commits_ahead)"
Write-Output "  Personal fork:       $(if ($null -eq $personalRemote) { 'not configured' } else { $personalRemote.url })"
Write-Output "  Driver pin:          $($driverPin.Substring(0, 12))"
Write-Output "  Driver HEAD:         $($driverHead.Substring(0, 12))"
Write-Output "  Driver compare:      $compareStatus$(if ($null -eq $driverCommitsAhead) { '' } else { " ($driverCommitsAhead commit(s) ahead)" })"
Write-Output "  Latest driver tag:   $(if ($null -eq $latestTag) { 'none found' } else { $latestTag.tag })"
Write-Output "Actions:"
foreach ($action in $actions) {
    Write-Output "  - $action"
}
