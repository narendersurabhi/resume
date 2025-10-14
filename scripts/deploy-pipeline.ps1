Param(
    [string]$Owner = "userprofiles",
    [string]$Repo = "resume",
    [string]$Branch = "main",
    [string]$ConnectionName = "resume-github-connection",
    [string]$Profile = "resume-deploy",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = 'Stop'

try {
    # Ensure we run from repo root
    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
    Set-Location $repoRoot

    # Prefer explicit npx path on Windows
    $npx = "C:\\Program Files\\nodejs\\npx.cmd"
    if (-not (Test-Path $npx)) { $npx = 'npx' }

    $app = ".\\.venv\\Scripts\\python.exe -m cdk.app"

    & $npx cdk deploy `
        ResumePipelineStack `
        --exclusively `
        -a $app `
        -c account=026654547457 `
        -c region=$Region `
        --profile $Profile `
        --require-approval never `
        --parameters "ResumePipelineStack:RepositoryOwner=$Owner" `
        --parameters "ResumePipelineStack:RepositoryName=$Repo" `
        --parameters "ResumePipelineStack:RepositoryBranch=$Branch" `
        --parameters "ResumePipelineStack:ConnectionName=$ConnectionName"
}
catch {
    Write-Error $_
    exit 1
}

