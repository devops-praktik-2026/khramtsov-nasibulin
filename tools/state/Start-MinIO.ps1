# Run in the same PowerShell session as OpenTofu; secrets stay in its environment.
$ErrorActionPreference = 'Stop'
if (-not $env:AWS_ACCESS_KEY_ID) { $env:AWS_ACCESS_KEY_ID = 'praktikum' }
if (-not $env:AWS_SECRET_ACCESS_KEY) {
    $secret = Read-Host 'MinIO password (at least 8 characters)' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    try {
        $env:AWS_SECRET_ACCESS_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}
if ($env:AWS_SECRET_ACCESS_KEY.Length -lt 8) { throw 'MinIO password is too short.' }
$compose = Join-Path $PSScriptRoot 'compose.yaml'
& docker compose -f $compose up -d --build --wait minio
if ($LASTEXITCODE -ne 0) { throw 'MinIO failed to start.' }
& docker compose -f $compose run --rm init
if ($LASTEXITCODE -ne 0) { throw 'MinIO bucket initialization failed.' }
Write-Host 'MinIO ready: http://127.0.0.1:9001; bucket: praktikum-state (versioning enabled).'
