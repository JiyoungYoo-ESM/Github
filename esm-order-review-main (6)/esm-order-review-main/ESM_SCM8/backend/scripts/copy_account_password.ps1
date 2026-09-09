param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("adminmaster", "eu_manager", "bm1", "bm2", "bm3", "hnb_team", "ia", "my_team", "sales_team", "vn_team")]
    [string]$AccountId
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not ("EsmScmCredentialNative" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class EsmScmCredentialNative
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

    [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredRead(string target, UInt32 type, Int32 reservedFlag, out IntPtr credentialPtr);

    [DllImport("advapi32.dll", SetLastError = true)]
    public static extern void CredFree(IntPtr buffer);
}
"@
}

$target = "ESM_SCM8/$AccountId"
$credentialPointer = [IntPtr]::Zero
if (-not [EsmScmCredentialNative]::CredRead($target, 1, 0, [ref]$credentialPointer)) {
    $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    throw "Could not read the '$AccountId' account from Windows Credential Manager. Win32 error: $errorCode"
}

try {
    $credential = [Runtime.InteropServices.Marshal]::PtrToStructure(
        $credentialPointer,
        [type][EsmScmCredentialNative+Credential]
    )
    $password = [Runtime.InteropServices.Marshal]::PtrToStringUni(
        $credential.CredentialBlob,
        [int]($credential.CredentialBlobSize / 2)
    )
    if ([string]::IsNullOrEmpty($password)) {
        throw "The stored password is empty."
    }
    Set-Clipboard -Value $password
    Write-Host "Copied the '$AccountId' password to the clipboard. Clear the clipboard after pasting it."
}
finally {
    if ($credentialPointer -ne [IntPtr]::Zero) {
        [EsmScmCredentialNative]::CredFree($credentialPointer)
    }
}
