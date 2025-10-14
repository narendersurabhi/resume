Param(
    [string]$StackName = "ResumePipelineStack",
    [string]$Profile = "resume-deploy",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = 'Stop'

try {
    $stack = aws cloudformation describe-stacks --stack-name $StackName --profile $Profile --region $Region | ConvertFrom-Json
    if (-not $stack.Stacks) { throw "Stack '$StackName' not found." }
    $output = $stack.Stacks[0].Outputs | Where-Object { $_.OutputKey -eq 'ConnectionArnOutput' }
    if (-not $output) { throw "Output 'ConnectionArnOutput' not found on stack '$StackName'." }
    $arn = $output.OutputValue

    $consoleUrl = "https://console.aws.amazon.com/codesuite/settings/connections?region=$Region#connections/$arn"
    Write-Host "Opening AWS Console for CodeConnections authorization:" -ForegroundColor Cyan
    Write-Host "  $consoleUrl"
    Start-Process $consoleUrl | Out-Null
    Write-Host "In the browser, choose 'Update pending connection' to authorize GitHub." -ForegroundColor Yellow
}
catch {
    Write-Error $_
    exit 1
}

