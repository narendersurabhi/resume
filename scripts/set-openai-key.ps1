Param(
    [Parameter(Mandatory = $false)]
    [string]$Profile = 'resume-deploy',
    [Parameter(Mandatory = $false)]
    [string]$Region = 'us-east-1',
    [Parameter(Mandatory = $false)]
    [string]$SecretName = 'openai/api-key'
)

$ErrorActionPreference = 'Stop'

try {
    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        throw "AWS CLI not found in PATH. Please install and retry."
    }

    Write-Host "Setting OpenAI API key in Secrets Manager: $SecretName ($Region)" -ForegroundColor Cyan
    $secure = Read-Host -AsSecureString 'Enter OpenAI API key (input hidden)'
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    if (-not $plain -or $plain.Trim().Length -eq 0) { throw "OpenAI API key cannot be empty." }

    $exists = $false
    try {
        aws secretsmanager describe-secret --secret-id $SecretName --profile $Profile --region $Region | Out-Null
        $exists = $true
    } catch {
        $exists = $false
    }

    if ($exists) {
        aws secretsmanager put-secret-value `
            --secret-id $SecretName `
            --secret-string $plain `
            --profile $Profile `
            --region $Region | Out-Null
        Write-Host "Updated existing secret: $SecretName" -ForegroundColor Green
    } else {
        aws secretsmanager create-secret `
            --name $SecretName `
            --secret-string $plain `
            --profile $Profile `
            --region $Region | Out-Null
        Write-Host "Created new secret: $SecretName" -ForegroundColor Green
    }

    # Verify
    $arn = (aws secretsmanager describe-secret --secret-id $SecretName --profile $Profile --region $Region | ConvertFrom-Json).ARN
    Write-Host "Secret ARN: $arn" -ForegroundColor Yellow
}
catch {
    Write-Error $_
    exit 1
}

