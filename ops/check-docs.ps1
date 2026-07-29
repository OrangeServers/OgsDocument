[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$errors = [System.Collections.Generic.List[string]]::new()

Push-Location $repoRoot
try {
    $markdownPaths = & rg --files `
        -g '*.md' `
        -g '!.agents/**' `
        -g '!.pnpm-store/**' `
        -g '!node_modules/**' `
        -g '!frontend/dist/**' `
        -g '!.deploy_notes_*.md' `
        -g '!docs/research/**'
    if ($LASTEXITCODE -ne 0) {
        throw 'rg failed while listing Markdown files'
    }
} finally {
    Pop-Location
}
$publicMarkdown = $markdownPaths | ForEach-Object {
    Get-Item -LiteralPath (Join-Path $repoRoot $_)
}

foreach ($file in $publicMarkdown) {
    $relativeFile = [System.IO.Path]::GetRelativePath($repoRoot, $file.FullName).
        Replace('\', '/')
    $content = Get-Content -LiteralPath $file.FullName -Raw

    if ($content -match '(?im)[ \t]+$') {
        $errors.Add("$relativeFile`: trailing whitespace")
    }

    if ($content -match '(?i)GPL-3\.0') {
        $errors.Add("$relativeFile`: stale GPL-3.0 reference; project license is Apache-2.0")
    }

    if ($content -match '(?i)(?:/data/install|10\.0\.1\.\d{1,3}|root@10\.)') {
        $errors.Add("$relativeFile`: possible private deployment address or path")
    }

    if ($content -match '(?i)(?:\d{3,5}\+?\s+(?:passed|tests?|用例)|passed\s*/\s*\d+\s+skipped)') {
        $errors.Add("$relativeFile`: volatile test count")
    }

    $markdownMatches = [regex]::Matches(
        $content,
        '\[[^\]]+\]\((?<target>[^)\s]+)(?:\s+"[^"]*")?\)'
    )
    $htmlMatches = [regex]::Matches(
        $content,
        '(?:href|src)="(?<target>[^"]+)"'
    )
    $targets = @($markdownMatches) + @($htmlMatches) |
        ForEach-Object { $_.Groups['target'].Value.Trim('<', '>') }
    foreach ($target in $targets) {
        if (
            $target.StartsWith('#') -or
            $target -match '^(?i:https?|mailto):' -or
            $target.StartsWith('/')
        ) {
            continue
        }

        $pathPart = [Uri]::UnescapeDataString(($target -split '#', 2)[0])
        if ([string]::IsNullOrWhiteSpace($pathPart)) {
            continue
        }
        $resolved = [System.IO.Path]::GetFullPath(
            (Join-Path $file.DirectoryName $pathPart)
        )
        if (-not $resolved.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $errors.Add("$relativeFile`: link escapes repository: $target")
            continue
        }
        if (-not (Test-Path -LiteralPath $resolved)) {
            $errors.Add("$relativeFile`: broken link: $target")
        }
    }
}

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object {
        Write-Host $_ -ForegroundColor Red
    }
    exit 1
}

Write-Host "Documentation checks passed ($($publicMarkdown.Count) Markdown files)."
