# Signs dist\DCSGraphicsOptimizer.exe with Azure Artifact Signing (formerly Trusted Signing).
# Run it as:  build\sign.ps1 -Sha256 <hash printed by build\build.ps1>
# It signs only dist\DCSGraphicsOptimizer.exe and only if the file still has that hash, so a file
# swapped in after the build is not signed.
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
#   3. The client secret: paste it when asked. It is removed from this console again when the
#      script ends, however it ends. Never put it in a file, and do not type it into the console
#      as $env:AZURE_CLIENT_SECRET = '...' (that would be kept in the console history).
param([Parameter(Mandatory = $true)][string]$Sha256)
$File = "dist\DCSGraphicsOptimizer.exe"
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$cfgPath = "build\signing.json"
if (-not (Test-Path $cfgPath)) { throw "build\signing.json not found - see the header of build\sign.ps1" }
$cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
if ($cfg.Endpoint -notmatch '^https://[a-z0-9-]+\.codesigning\.azure\.net/?$') { throw "signing.json: Endpoint is not an Azure Artifact Signing address" }
if (-not (Test-Path $File)) { throw "not found: $File" }
if ((Get-FileHash $File -Algorithm SHA256).Hash -ne $Sha256.Trim().ToUpper()) { throw "$File does not have the hash you gave; it is not the file that was built. Not signing." }
# Tenant and client ID are not secret and may come from signing.json. If the secret is not in
# the environment, ask for it (hidden); it stays in this process's memory only.
if (-not $env:AZURE_TENANT_ID -and $cfg.TenantId) { $env:AZURE_TENANT_ID = $cfg.TenantId }
if (-not $env:AZURE_CLIENT_ID -and $cfg.ClientId) { $env:AZURE_CLIENT_ID = $cfg.ClientId }
try {
if (-not $env:AZURE_CLIENT_SECRET) {
    $sec = Read-Host -AsSecureString "Paste the signing client secret (it will not be shown) and press Enter"
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { $env:AZURE_CLIENT_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
foreach ($v in 'AZURE_TENANT_ID','AZURE_CLIENT_ID','AZURE_CLIENT_SECRET') {
    if (-not [Environment]::GetEnvironmentVariable($v)) { throw "$v is not set (environment or build\signing.json)" }
}
foreach ($p in $cfg.SignTool, $cfg.Dlib, $File) { if (-not (Test-Path $p)) { throw "not found: $p" } }

# SignTool wants only the three service fields in the metadata file.
$meta = Join-Path $env:TEMP ("dcsgo-signing-" + [guid]::NewGuid().ToString("N") + ".json")
@{ Endpoint = $cfg.Endpoint; CodeSigningAccountName = $cfg.CodeSigningAccountName;
   CertificateProfileName = $cfg.CertificateProfileName } | ConvertTo-Json | Set-Content $meta -Encoding ascii
    # The timestamp is required: these certificates are valid for only a few days, and the
    # timestamp is what keeps the signature valid after they expire.
    & $cfg.SignTool sign /v /fd SHA256 /tr "http://timestamp.acs.microsoft.com" /td SHA256 `
        /dlib $cfg.Dlib /dmdf $meta $File
    if ($LASTEXITCODE -ne 0) { throw "signtool sign failed ($LASTEXITCODE)" }
    & $cfg.SignTool verify /pa /v $File
    if ($LASTEXITCODE -ne 0) { throw "signature did not verify ($LASTEXITCODE)" }
} finally {
    if ($meta) { Remove-Item $meta -ErrorAction SilentlyContinue }
    Remove-Item Env:AZURE_CLIENT_SECRET -ErrorAction SilentlyContinue
}
"Signed: $File"
(Get-AuthenticodeSignature $File).SignerCertificate.Subject
