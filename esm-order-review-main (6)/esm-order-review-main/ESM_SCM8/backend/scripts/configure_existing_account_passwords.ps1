param(
    [switch]$SkipConfirmation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$accountIds = @(
    "eu_manager",
    "bm1",
    "bm2",
    "bm3",
    "adminmaster",
    "my_team",
    "vn_team",
    "hnb_team",
    "ia",
    "sales_team"
)

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$environmentPath = Join-Path $projectRoot "backend\.env"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

function Invoke-ProjectPython {
    param([string]$Code)

    if (Test-Path -LiteralPath $venvPython) {
        return & $venvPython -c $Code
    }
    return & py -3.14 -c $Code
}

function ConvertFrom-SecureValue {
    param([Security.SecureString]$SecureValue)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Get-PasswordHash {
    param([string]$Password)

    $environmentName = "ESM_SCM_ACCOUNT_PASSWORD_INPUT"
    $previousValue = [Environment]::GetEnvironmentVariable($environmentName, "Process")
    [Environment]::SetEnvironmentVariable($environmentName, $Password, "Process")
    try {
        Push-Location $projectRoot
        $hash = Invoke-ProjectPython -Code (
            "import os; from backend.auth.passwords import hash_password; " +
            "print(hash_password(os.environ['ESM_SCM_ACCOUNT_PASSWORD_INPUT']))"
        )
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($hash)) {
            throw "비밀번호 해시를 생성하지 못했습니다."
        }
        return $hash.Trim()
    }
    finally {
        Pop-Location
        [Environment]::SetEnvironmentVariable($environmentName, $previousValue, "Process")
    }
}

function Set-EnvironmentHash {
    param(
        [string]$AccountId,
        [string]$Hash
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $environmentPath) {
        foreach ($line in Get-Content -LiteralPath $environmentPath -Encoding UTF8) {
            [void]$lines.Add([string]$line)
        }
    }

    $key = "AUTH_{0}_PASSWORD_HASH" -f $AccountId.ToUpperInvariant()
    $pattern = "^{0}=" -f [Regex]::Escape($key)
    $replacement = "$key=$Hash"
    $matched = $false

    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match $pattern) {
            $lines[$index] = $replacement
            $matched = $true
            break
        }
    }
    if (-not $matched) {
        [void]$lines.Add($replacement)
    }

    [IO.File]::WriteAllLines(
        $environmentPath,
        $lines,
        [Text.UTF8Encoding]::new($false)
    )
}

Write-Host "계정 비밀번호를 보안 입력으로 받습니다. 입력 문자는 화면에 표시되지 않습니다."
foreach ($accountId in $accountIds) {
    $securePassword = Read-Host "$accountId 비밀번호" -AsSecureString
    $password = ConvertFrom-SecureValue -SecureValue $securePassword
    try {
        if ([string]::IsNullOrEmpty($password)) {
            throw "$accountId 비밀번호가 비어 있습니다."
        }

        if (-not $SkipConfirmation) {
            $secureConfirmation = Read-Host "$accountId 비밀번호 확인" -AsSecureString
            $confirmation = ConvertFrom-SecureValue -SecureValue $secureConfirmation
            try {
                if ($password -cne $confirmation) {
                    throw "$accountId 비밀번호가 일치하지 않습니다."
                }
            }
            finally {
                $confirmation = $null
            }
        }

        Set-EnvironmentHash -AccountId $accountId -Hash (Get-PasswordHash -Password $password)
        Write-Host "$accountId 설정 완료"
    }
    finally {
        $password = $null
    }
}

Write-Host "10개 계정 설정이 완료됐습니다. 백엔드를 재시작해야 적용됩니다."
