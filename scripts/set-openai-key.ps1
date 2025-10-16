Param(
    [Parameter(Mandatory = $false)]
    [string]$Profile = 'resume-deploy',
    [Parameter(Mandatory = $false)]
    [string]$Region = 'us-east-1',
    [Parameter(Mandatory = $false)]
    [string]$SecretName = 'openai/api-key',
    [Parameter(Mandatory = $false)]
    [switch]$UseEnv = $true,
    [Parameter(Mandatory = $false)]
    [string]$Key = ''
)

$ErrorActionPreference = 'Stop'

try {
    if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
        throw "AWS CLI not found in PATH. Please install and retry."
    }

    Write-Host "Setting OpenAI API key in Secrets Manager: $SecretName ($Region)" -ForegroundColor Cyan

    $plain = ''
    if ($Key -and $Key.Trim().Length -gt 0) {
        $plain = $Key.Trim()
    } elseif ($UseEnv -and $env:OPENAI_API_KEY) {
        $plain = "$($env:OPENAI_API_KEY)".Trim()
        Write-Host "Using OPENAI_API_KEY from environment." -ForegroundColor Yellow
    } else {
        $secure = Read-Host -AsSecureString 'Enter OpenAI API key (input hidden)'
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    }
    if (-not $plain -or $plain.Trim().Length -eq 0) { throw "OpenAI API key cannot be empty." }

    # Detect existence using exit code (aws CLI writes errors to stderr and does not throw PowerShell exceptions)
    $null = aws secretsmanager describe-secret --secret-id $SecretName --profile $Profile --region $Region --output json 2>$null
    $exists = ($LASTEXITCODE -eq 0)

    if ($exists) {
        $null = aws secretsmanager put-secret-value --secret-id $SecretName --secret-string $plain --profile $Profile --region $Region 2>$null
        if ($LASTEXITCODE -ne 0) { throw "Failed to update secret '$SecretName'" }
        Write-Host "Updated existing secret: $SecretName" -ForegroundColor Green
    } else {
        $null = aws secretsmanager create-secret --name $SecretName --secret-string $plain --profile $Profile --region $Region 2>$null
        if ($LASTEXITCODE -ne 0) { throw "Failed to create secret '$SecretName'" }
        Write-Host "Created new secret: $SecretName" -ForegroundColor Green
    }

    # Verify
    $arn = (aws secretsmanager describe-secret --secret-id $SecretName --profile $Profile --region $Region --output json 2>$null | ConvertFrom-Json).ARN
    if (-not $arn) { throw "Verification failed: could not read ARN for '$SecretName'" }
    Write-Host "Secret ARN: $arn" -ForegroundColor Yellow
}
catch {
    Write-Error $_
    exit 1
}
