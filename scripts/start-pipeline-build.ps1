Param(
    [string]$StackName = 'ResumePipelineStack',
    [string]$Profile = 'resume-deploy',
    [string]$Region = 'us-east-1',
    [switch]$DeployApp = $true
)

$ErrorActionPreference = 'Stop'

try {
    $stack = aws cloudformation describe-stacks --stack-name $StackName --profile $Profile --region $Region | ConvertFrom-Json
    if (-not $stack.Stacks) { throw "Pipeline stack '$StackName' not found." }
    $projOut = $stack.Stacks[0].Outputs | Where-Object { $_.OutputKey -eq 'CodeBuildProjectName' }
    if (-not $projOut) { throw "Output 'CodeBuildProjectName' not found on stack '$StackName'." }
    $project = $projOut.OutputValue

    if ($DeployApp) {
        aws codebuild start-build `
            --project-name $project `
            --environment-variables-override name=DEPLOY_APP,value=true,type=PLAINTEXT `
            --profile $Profile `
            --region $Region | Out-Null
    } else {
        aws codebuild start-build `
            --project-name $project `
            --profile $Profile `
            --region $Region | Out-Null
    }
    Write-Host "Started CodeBuild project '$project' (DEPLOY_APP=$([bool]$DeployApp))." -ForegroundColor Green
}
catch {
    Write-Error $_
    exit 1
}
