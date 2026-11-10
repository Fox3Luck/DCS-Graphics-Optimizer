# Signs dist\DCSGraphicsOptimizer.exe with Azure Artifact Signing (formerly Trusted Signing).
#
# Needs on the build PC:
#   1. SignTool >= 10.0.2261.755 (NuGet package Microsoft.Windows.SDK.BuildTools), the
#      Azure.CodeSigning.Dlib.dll plugin (NuGet package Microsoft.ArtifactSigning.Client) and
#      the .NET 8 runtime. Unzipping both packages under build\tools is enough. See
#      https://learn.microsoft.com/azure/artifact-signing/how-to-signing-integrations
#   2. build\signing.json (not committed; nothing secret in it):
#        { "Endpoint": "https://<region>.codesigning.azure.net/",
#          "CodeSigningAccountName": "<account>",
#          "CertificateProfileName": "<profile>",
#          "SignTool": "C:\\path\\to\\signtool.exe",
#          "Dlib": "C:\\path\\to\\Azure.CodeSigning.Dlib.dll" }
#      Optional there: "TenantId" and "ClientId" (not secret).
#   3. The client secret: environment variable AZURE_CLIENT_SECRET, or paste it when asked.
#      Never put it in a file in this repo.
param([string]$File = "dist\DCSGraphicsOptimizer.exe")
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$cfgPath = "build\signing.json"
if (-not (Test-Path $cfgPath)) { throw "build\signing.json not found - see the header of build\sign.ps1" }
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
# Tenant and client ID are not secret and may come from signing.json. If the secret is not in
# the environment, ask for it (hidden); it stays in this process's memory only.
if (-not $env:AZURE_TENANT_ID -and $cfg.TenantId) { $env:AZURE_TENANT_ID = $cfg.TenantId }
if (-not $env:AZURE_CLIENT_ID -and $cfg.ClientId) { $env:AZURE_CLIENT_ID = $cfg.ClientId }
$asked = $false
if (-not $env:AZURE_CLIENT_SECRET) {
    $sec = Read-Host -AsSecureString "Paste the signing client secret (it will not be shown) and press Enter"
    $env:AZURE_CLIENT_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)).Trim()
    $asked = $true
}
foreach ($v in 'AZURE_TENANT_ID','AZURE_CLIENT_ID','AZURE_CLIENT_SECRET') {
    if (-not [Environment]::GetEnvironmentVariable($v)) { throw "$v is not set (environment or build\signing.json)" }
}
foreach ($p in $cfg.SignTool, $cfg.Dlib, $File) { if (-not (Test-Path $p)) { throw "not found: $p" } }

# SignTool wants only the three service fields in the metadata file.
$meta = Join-Path $env:TEMP "dcsgo-signing-metadata.json"
@{ Endpoint = $cfg.Endpoint; CodeSigningAccountName = $cfg.CodeSigningAccountName;
   CertificateProfileName = $cfg.CertificateProfileName } | ConvertTo-Json | Set-Content $meta -Encoding ascii
try {
    # The timestamp is required: these certificates are valid for only a few days, and the
    # timestamp is what keeps the signature valid after they expire.
    & $cfg.SignTool sign /v /fd SHA256 /tr "http://timestamp.acs.microsoft.com" /td SHA256 `
        /dlib $cfg.Dlib /dmdf $meta $File
    if ($LASTEXITCODE -ne 0) { throw "signtool sign failed ($LASTEXITCODE)" }
    & $cfg.SignTool verify /pa /v $File
    if ($LASTEXITCODE -ne 0) { throw "signature did not verify ($LASTEXITCODE)" }
} finally {
    Remove-Item $meta -ErrorAction SilentlyContinue
    if ($asked) { Remove-Item Env:AZURE_CLIENT_SECRET -ErrorAction SilentlyContinue }
}
"Signed: $File"
(Get-AuthenticodeSignature $File).SignerCertificate.Subject
