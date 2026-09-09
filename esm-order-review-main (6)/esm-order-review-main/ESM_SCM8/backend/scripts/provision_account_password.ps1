param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("adminmaster", "eu_manager", "bm1", "bm2", "bm3", "hnb_team", "ia", "my_team", "sales_team", "vn_team")]
    [string]$AccountId,

    [ValidateRange(12, 64)]
    [int]$PasswordLength = 14,

    [switch]$ReplaceExisting
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not ("EsmScmCredentialProvisionNative" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class EsmScmCredentialProvisionNative
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct Credential
    {
        public UInt32 Flags;
        public UInt32 Type;
        public IntPtr TargetName;
        public IntPtr Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public IntPtr TargetAlias;
        public IntPtr UserName;
    }

    [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredWrite(ref Credential credential, UInt32 flags);

    [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredRead(string target, UInt32 type, Int32 reservedFlag, out IntPtr credentialPtr);

    [DllImport("advapi32.dll", SetLastError = true)]
    public static extern void CredFree(IntPtr buffer);
}
"@
}

function New-SecurePassword {
    param([int]$Length)

    $groups = @(
        "ABCDEFGHJKLMNPQRSTUVWXYZ",
        "abcdefghijkmnopqrstuvwxyz",
        "23456789",
        "!@#$%*-_"
    )
    $characters = ($groups -join "").ToCharArray()
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $result = [System.Collections.Generic.List[char]]::new()
        foreach ($group in $groups) {
            $bytes = [byte[]]::new(4)
            $rng.GetBytes($bytes)
            $result.Add($group[[BitConverter]::ToUInt32($bytes, 0) % $group.Length])
        }
        while ($result.Count -lt $Length) {
            $bytes = [byte[]]::new(4)
            $rng.GetBytes($bytes)
            $result.Add($characters[[BitConverter]::ToUInt32($bytes, 0) % $characters.Length])
        }
        for ($index = $result.Count - 1; $index -gt 0; $index--) {
            $bytes = [byte[]]::new(4)
            $rng.GetBytes($bytes)
            $swapIndex = [BitConverter]::ToUInt32($bytes, 0) % ($index + 1)
            $temporary = $result[$index]
            $result[$index] = $result[$swapIndex]
            $result[$swapIndex] = $temporary
        }
        return -join $result
    }
    finally {
        $rng.Dispose()
    }
}

function Get-PasswordHash {
    param([string]$Password, [string]$ProjectRoot)

    $python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Could not find the project Python runtime at '$python'."
    }
    $environmentName = "ESM_SCM_PROVISION_PASSWORD"
    $previousPassword = [Environment]::GetEnvironmentVariable($environmentName, "Process")
    [Environment]::SetEnvironmentVariable($environmentName, $Password, "Process")
    try {
        Push-Location $ProjectRoot
        $hash = & $python -c "import os; from backend.auth.passwords import hash_password; print(hash_password(os.environ['ESM_SCM_PROVISION_PASSWORD']))"
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($hash)) {
            throw "Could not generate the password hash."
        }
        return $hash.Trim()
    }
    finally {
        Pop-Location
        [Environment]::SetEnvironmentVariable($environmentName, $previousPassword, "Process")
    }
}

function Set-WindowsCredential {
    param([string]$Target, [string]$UserName, [string]$Password)

    $targetPointer = [Runtime.InteropServices.Marshal]::StringToCoTaskMemUni($Target)
    $userNamePointer = [Runtime.InteropServices.Marshal]::StringToCoTaskMemUni($UserName)
    $passwordPointer = [Runtime.InteropServices.Marshal]::StringToCoTaskMemUni($Password)
    try {
        $credential = [EsmScmCredentialProvisionNative+Credential]::new()
        $credential.Type = 1
        $credential.TargetName = $targetPointer
        $credential.UserName = $userNamePointer
        $credential.CredentialBlob = $passwordPointer
        $credential.CredentialBlobSize = [Text.Encoding]::Unicode.GetByteCount($Password)
        $credential.Persist = 2
        if (-not [EsmScmCredentialProvisionNative]::CredWrite([ref]$credential, 0)) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "Could not write Windows Credential Manager entry. Win32 error: $errorCode"
        }
    }
    finally {
        [Runtime.InteropServices.Marshal]::FreeCoTaskMem($targetPointer)
        [Runtime.InteropServices.Marshal]::FreeCoTaskMem($userNamePointer)
        [Runtime.InteropServices.Marshal]::FreeCoTaskMem($passwordPointer)
    }
}

function Test-WindowsCredential {
    param([string]$Target)

    $credentialPointer = [IntPtr]::Zero
    $exists = [EsmScmCredentialProvisionNative]::CredRead($Target, 1, 0, [ref]$credentialPointer)
    if ($credentialPointer -ne [IntPtr]::Zero) {
        [EsmScmCredentialProvisionNative]::CredFree($credentialPointer)
    }
    return $exists
}

function Set-EnvironmentHash {
    param([string]$Path, [string]$Key, [string]$Hash)

    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $Path) {
        foreach ($existingLine in Get-Content -LiteralPath $Path) {
            [void]$lines.Add([string]$existingLine)
        }
    }
    $pattern = "^{0}=" -f [Regex]::Escape($Key)
    $replacementIndex = -1
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match $pattern) {
            $replacementIndex = $index
            break
        }
    }
    $entry = "$Key=$Hash"
    if ($replacementIndex -ge 0) {
        $lines[$replacementIndex] = $entry
    } else {
        $lines.Add($entry)
    }
    [IO.File]::WriteAllLines($Path, $lines, [Text.UTF8Encoding]::new($false))
}

$backendRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $backendRoot ".env"
$environmentKey = "AUTH_{0}_PASSWORD_HASH" -f $AccountId.ToUpperInvariant()
$credentialTarget = "ESM_SCM8/$AccountId"
if ((Test-WindowsCredential -Target $credentialTarget) -and -not $ReplaceExisting) {
    throw "A password already exists for '$AccountId'. Use -ReplaceExisting only when intentionally rotating it."
}
$password = New-SecurePassword -Length $PasswordLength
$passwordHash = Get-PasswordHash -Password $password -ProjectRoot (Split-Path -Parent $backendRoot)

Set-WindowsCredential -Target $credentialTarget -UserName $AccountId -Password $password
Set-EnvironmentHash -Path $environmentPath -Key $environmentKey -Hash $passwordHash
Set-Clipboard -Value "[cleared]"
Write-Host "Provisioned '$AccountId': password stored in Windows Credential Manager and hash saved to backend/.env. Use copy_account_password.ps1 to copy it when needed."
