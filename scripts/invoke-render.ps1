Param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,
    [Parameter(Mandatory = $true)]
    [string]$UserId,
    [string]$TemplateId = 'default',
    [ValidateSet('docx','pdf')]
    [string]$Format = 'docx',
    [string]$JsonBucket,
    [string]$JsonKey,
    [string]$Profile = 'resume-deploy',
    [string]$Region = 'us-east-1'
)

$ErrorActionPreference = 'Stop'

function Get-RenderFunctionName {
    param([string]$Profile,[string]$Region)
    $res = aws cloudformation describe-stack-resources `
        --stack-name ResumeBackendStack `
        --query "StackResources[?contains(LogicalResourceId,'Render') && ResourceType=='AWS::Lambda::Function'].PhysicalResourceId | [0]" `
        --output text `
        --profile $Profile `
        --region $Region 2>$null
    if (-not $res -or $res -eq 'None') { throw "Could not resolve render Lambda function name from CloudFormation." }
    return $res.Trim()
}

try {
    $fn = Get-RenderFunctionName -Profile $Profile -Region $Region
    Write-Host "Render function: $fn" -ForegroundColor Cyan

    $payload = @{ jobId=$JobId; userId=$UserId; templateId=$TemplateId; format=$Format }
    if ($JsonBucket -and $JsonKey) { $payload.jsonS3 = @{ bucket=$JsonBucket; key=$JsonKey } }
    $evt = @{ httpMethod='POST'; path='/render'; body=($payload | ConvertTo-Json -Compress) } | ConvertTo-Json -Compress
    $tmp = New-TemporaryFile
    Set-Content -LiteralPath $tmp -Value $evt -Encoding Ascii

    aws lambda invoke --function-name $fn --payload fileb://$tmp render_resp.json --profile $Profile --region $Region | Out-Null
    Write-Host "Invocation complete. Response body (render_resp.json):" -ForegroundColor Cyan
    Get-Content render_resp.json
}
catch {
    Write-Error $_
    exit 1
}

