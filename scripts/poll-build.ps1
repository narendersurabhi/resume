Param(
    [string]$ProjectName,
    [string]$Profile = 'resume-deploy',
    [string]$Region = 'us-east-1'
)

$ErrorActionPreference = 'Stop'

if (-not $ProjectName) { Write-Error "-ProjectName is required"; exit 1 }

function Get-LatestBuildId {
    param([string]$ProjectName)
    $ids = aws codebuild list-builds-for-project --project-name $ProjectName --profile $Profile --region $Region --query 'ids[0]' --output text 2>$null
    if (-not $ids -or $ids -eq 'None') { return $null }
    return $ids.Trim()
}

try {
    $buildId = Get-LatestBuildId -ProjectName $ProjectName
    if (-not $buildId) { throw "No builds found for project '$ProjectName'" }
    Write-Host "Monitoring build: $buildId" -ForegroundColor Cyan

    while ($true) {
        $b = aws codebuild batch-get-builds --ids $buildId --profile $Profile --region $Region | ConvertFrom-Json
        $status = $b.builds[0].buildStatus
        $ph = $b.builds[0].currentPhase
        Write-Host ("Status: {0} / Phase: {1}" -f $status,$ph)
        if ($status -in @('SUCCEEDED','FAILED','FAULT','TIMED_OUT','STOPPED')) { break }
        Start-Sleep -Seconds 10
    }

    $sha = $b.builds[0].resolvedSourceVersion.Substring(0,7)
    Write-Host "Build completed with status: $status (SHORT_SHA=$sha)" -ForegroundColor Green
}
catch {
    Write-Error $_
    exit 1
}

