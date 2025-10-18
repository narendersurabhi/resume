Param(
    [Parameter(Mandatory = $true)]
    [string]$Username,
    [Parameter(Mandatory = $true)]
    [string]$Email,
    [Parameter(Mandatory = $true)]
    [string]$Password,
    [ValidateSet('User','Manager','Admin')]
    [string]$Group = 'User',
    [string]$Profile = 'resume-deploy',
    [string]$Region = 'us-east-1'
)

$ErrorActionPreference = 'Stop'

function Get-ExportValue {
    param([string]$Name)
    $val = aws cloudformation list-exports --query "Exports[?Name=='$Name'].Value | [0]" --output text --profile $Profile --region $Region 2>$null
    if (-not $val -or $val -eq 'None') { throw "Export '$Name' not found." }
    return $val.Trim()
}

try {
    $UserPoolId = Get-ExportValue -Name 'ResumeUserPoolId'
    Write-Host "UserPoolId: $UserPoolId" -ForegroundColor Cyan

    # Ensure group exists
    $groupExists = $true
    try { aws cognito-idp get-group --user-pool-id $UserPoolId --group-name $Group --profile $Profile --region $Region | Out-Null }
    catch { $groupExists = $false }
    if (-not $groupExists) {
        aws cognito-idp create-group --user-pool-id $UserPoolId --group-name $Group --profile $Profile --region $Region | Out-Null
        Write-Host "Created group '$Group'" -ForegroundColor Green
    }

    # Create or update user
    $exists = $true
    try { aws cognito-idp admin-get-user --user-pool-id $UserPoolId --username $Username --profile $Profile --region $Region | Out-Null }
    catch { $exists = $false }

    if (-not $exists) {
        aws cognito-idp admin-create-user `
            --user-pool-id $UserPoolId `
            --username $Username `
            --user-attributes Name=email,Value=$Email Name=email_verified,Value=true `
            --message-action SUPPRESS `
            --profile $Profile `
            --region $Region | Out-Null
        Write-Host "Created user '$Username' (email=$Email)" -ForegroundColor Green
    } else {
        Write-Host "User '$Username' already exists; updating password and group." -ForegroundColor Yellow
    }

    aws cognito-idp admin-set-user-password `
        --user-pool-id $UserPoolId `
        --username $Username `
        --password $Password `
        --permanent `
        --profile $Profile `
        --region $Region | Out-Null
    Write-Host "Set permanent password for '$Username'" -ForegroundColor Green

    aws cognito-idp admin-add-user-to-group `
        --user-pool-id $UserPoolId `
        --username $Username `
        --group-name $Group `
        --profile $Profile `
        --region $Region | Out-Null
    Write-Host "Added '$Username' to group '$Group'" -ForegroundColor Green

    Write-Host "User created and ready to sign in. Configure your frontend with the exported UserPoolId and UserPoolClientId." -ForegroundColor Cyan
}
catch {
    Write-Error $_
    exit 1
}

