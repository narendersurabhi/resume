Param(
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [string]$Profile = "resume-deploy",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = 'Stop'

if (-not $Tag -or $Tag.Trim().Length -eq 0) {
    Write-Error "-Tag is required (e.g., -Tag abc1234)"
    exit 1
}

try {
    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
    Set-Location $repoRoot

    $npx = "C:\\Program Files\\nodejs\\npx.cmd"
    if (-not (Test-Path $npx)) { $npx = 'npx' }

    $app = ".\\.venv\\Scripts\\python.exe -m cdk.app"

    & $npx cdk deploy `
        ResumeAuthStack `
        ResumeBackendStack `
        ResumeFrontendStack `
        -a $app `
        -c account=026654547457 `
        -c region=$Region `
        --profile $Profile `
        --require-approval never `
        --parameters "ResumeBackendStack:DownloadImageTag=$Tag" `
        --parameters "ResumeBackendStack:GenerateImageTag=$Tag" `
        --parameters "ResumeBackendStack:UploadImageTag=$Tag"
}
catch {
    Write-Error $_
    exit 1
}

