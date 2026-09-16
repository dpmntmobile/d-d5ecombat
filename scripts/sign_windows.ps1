param(
    [Parameter(Mandatory = $true)]
    [string]$File,
    [string]$CertificateThumbprint = $env:WINDOWS_CERT_THUMBPRINT,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$ResolvedFile = (Resolve-Path -LiteralPath $File).Path
$SignTool = Get-Command signtool.exe -ErrorAction Stop

if (-not $CertificateThumbprint) {
    throw "Provide -CertificateThumbprint or set WINDOWS_CERT_THUMBPRINT."
}

& $SignTool.Source sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $ResolvedFile
if ($LASTEXITCODE -ne 0) {
    throw "Signing failed with exit code $LASTEXITCODE"
}

Write-Output "Signed $ResolvedFile"
