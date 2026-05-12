param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [Parameter(Mandatory = $true)][string]$KeyFile,
    [string]$OutputZip = "",
    [string]$ExtractTo = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($OutputZip)) {
    $OutputZip = [System.IO.Path]::ChangeExtension($BackupFile, ".zip")
}

$keyLine = Get-Content -LiteralPath $KeyFile | Where-Object { $_ -like "key_base64=*" } | Select-Object -First 1
if (-not $keyLine) {
    throw "Missing key_base64 entry in key file."
}

$master = [Convert]::FromBase64String(($keyLine -split "=", 2)[1])
if ($master.Length -ne 64) {
    throw "Invalid key length."
}

$encKey = [byte[]]::new(32)
$macKey = [byte[]]::new(32)
[Array]::Copy($master, 0, $encKey, 0, 32)
[Array]::Copy($master, 32, $macKey, 0, 32)

$payload = [System.IO.File]::ReadAllBytes((Resolve-Path $BackupFile))
$magic = [System.Text.Encoding]::ASCII.GetBytes("CFTAESCBC1")
if ($payload.Length -le ($magic.Length + 16 + 32)) {
    throw "Backup file is too small."
}

for ($i = 0; $i -lt $magic.Length; $i++) {
    if ($payload[$i] -ne $magic[$i]) {
        throw "Unsupported backup format."
    }
}

$tagLength = 32
$dataLength = $payload.Length - $tagLength
$data = [byte[]]::new($dataLength)
$actualTag = [byte[]]::new($tagLength)
[Array]::Copy($payload, 0, $data, 0, $dataLength)
[Array]::Copy($payload, $dataLength, $actualTag, 0, $tagLength)

$hmac = [System.Security.Cryptography.HMACSHA256]::new($macKey)
try {
    $expectedTag = $hmac.ComputeHash($data)
} finally {
    $hmac.Dispose()
}

for ($i = 0; $i -lt $tagLength; $i++) {
    if ($actualTag[$i] -ne $expectedTag[$i]) {
        throw "Backup authentication failed. The file or key is wrong."
    }
}

$iv = [byte[]]::new(16)
$cipherLength = $data.Length - $magic.Length - $iv.Length
$cipher = [byte[]]::new($cipherLength)
[Array]::Copy($data, $magic.Length, $iv, 0, $iv.Length)
[Array]::Copy($data, $magic.Length + $iv.Length, $cipher, 0, $cipherLength)

$aes = [System.Security.Cryptography.Aes]::Create()
$aes.Mode = [System.Security.Cryptography.CipherMode]::CBC
$aes.Padding = [System.Security.Cryptography.PaddingMode]::PKCS7
$aes.KeySize = 256
$aes.Key = $encKey
$aes.IV = $iv
try {
    $decryptor = $aes.CreateDecryptor()
    $plain = $decryptor.TransformFinalBlock($cipher, 0, $cipher.Length)
} finally {
    if ($decryptor) {
        $decryptor.Dispose()
    }
    $aes.Dispose()
}

[System.IO.File]::WriteAllBytes($OutputZip, $plain)
Write-Host "Wrote $OutputZip"

if (-not [string]::IsNullOrWhiteSpace($ExtractTo)) {
    New-Item -ItemType Directory -Force -Path $ExtractTo | Out-Null
    Expand-Archive -LiteralPath $OutputZip -DestinationPath $ExtractTo -Force
    Write-Host "Extracted to $ExtractTo"
}
