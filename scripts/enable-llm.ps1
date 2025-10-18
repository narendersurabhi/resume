Param(
    [string]$Profile = "resume-deploy",
    [string]$Region = "us-east-1",
    [string]$OpenAiKey = $env:OPENAI_API_KEY,
    [string]$UserId = "test-user",
    [switch]$Invoke = $true
)

$ErrorActionPreference = 'Stop'

function Get-TailorFunctionName {
    param(
        [string]$Profile,
        [string]$Region
    )
    $res = aws cloudformation describe-stack-resources `
        --stack-name ResumeBackendStack `
        --query "StackResources[?contains(LogicalResourceId,'TailorHandler')].PhysicalResourceId | [0]" `
        --output text `
        --profile $Profile `
        --region $Region 2>$null
    if (-not $res -or $res -eq "None") { throw "Could not resolve TailorHandler function name from CloudFormation." }
    return $res.Trim()
}

try {
    $TailorFn = Get-TailorFunctionName -Profile $Profile -Region $Region
    Write-Host "Tailor function:" $TailorFn -ForegroundColor Cyan

    if (-not $OpenAiKey -or $OpenAiKey.Trim().Length -eq 0) {
        Write-Warning "OPENAI_API_KEY not provided and not found in environment. Set -OpenAiKey or env:OPENAI_API_KEY."
    }

    $rawVars = aws lambda get-function-configuration `
        --function-name $TailorFn `
        --query 'Environment.Variables' `
        --output json `
        --profile $Profile `
        --region $Region | ConvertFrom-Json

    $vars = @{}
    if ($rawVars) {
        foreach ($prop in $rawVars.PSObject.Properties) {
            $vars[$prop.Name] = $prop.Value
        }
    }
    $vars['ENABLE_LLM'] = 'true'
    if ($OpenAiKey) { $vars['OPENAI_API_KEY'] = $OpenAiKey }

    $envDoc = @{ Variables = $vars } | ConvertTo-Json -Compress
    $envFile = New-TemporaryFile
    Set-Content -LiteralPath $envFile -Value $envDoc -Encoding Ascii
    aws lambda update-function-configuration `
        --function-name $TailorFn `
        --environment file://$envFile `
        --profile $Profile `
        --region $Region | Out-Null
    Write-Host "Updated Lambda env: ENABLE_LLM=true, OPENAI_API_KEY (set: $([bool]$OpenAiKey))" -ForegroundColor Green

    if ($Invoke) {
        $resume = @'
Experienced software engineer with 8+ years building cloud-native services in AWS. Led a team delivering a low-latency event pipeline; improved reliability and reduced costs by 25%. Golang, Python, CDK, Kubernetes.
'@
        $jd = @'
Seeking backend engineer with AWS, Lambda, API Gateway, DynamoDB, and IaC (CDK). Experience with observability, security, and CI/CD is a plus.
'@
        $body = @{ resumeText=$resume; jobDescription=$jd; userId=$UserId } | ConvertTo-Json -Compress
        $event = @{ httpMethod='POST'; path='/tailor'; body=$body } | ConvertTo-Json -Compress
        $tmp = New-TemporaryFile
        Set-Content -LiteralPath $tmp -Value $event -Encoding Ascii
        aws lambda invoke `
            --function-name $TailorFn `
            --payload fileb://$tmp `
            resp.json `
            --profile $Profile `
            --region $Region | Out-Null
        Write-Host "Invocation complete. Response body (resp.json):" -ForegroundColor Cyan
        Get-Content resp.json
    }
}
catch {
    Write-Error $_
    exit 1
}
